"""
Swiss Truth — Rate Limiter Middleware

Sliding-window rate limiter (in-memory, per process).
Applied to both MCP (/mcp) and REST API endpoints.

Tiers (daily limits):
  free       — 1 000 req/day  (IP-based, no key)
  pro        — 100 000 req/day (Bearer token)
  enterprise — unlimited       (Bearer token)

API keys are stored in env var SWISS_TRUTH_API_KEYS as JSON:
  {"sk-pro-abc123": "pro", "sk-ent-xyz999": "enterprise"}

Free-tier IPs are identified via X-Forwarded-For (Caddy sets this).
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier limits  (requests per 24 h)
# ---------------------------------------------------------------------------

TIER_LIMITS: dict[str, Optional[int]] = {
    "free":       1_000,
    "pro":        100_000,
    "enterprise": None,   # unlimited
}

WINDOW_SECONDS = 86_400  # 24 hours


# ---------------------------------------------------------------------------
# Sliding-window bucket (per key)
# ---------------------------------------------------------------------------

@dataclass
class _Bucket:
    count: int = 0
    window_start: float = field(default_factory=time.time)


class _RateLimiterStore:
    """In-memory sliding-window store. Process-local, resets on restart."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = defaultdict(
            lambda: _Bucket(window_start=time.time())
        )

    def check(self, key: str, limit: int) -> tuple[bool, int, int]:
        """
        Returns (allowed, remaining, retry_after_seconds).
        Thread-safe for asyncio (single-thread event loop).
        """
        now = time.time()
        b = self._buckets[key]

        # Reset window if expired
        if now - b.window_start >= WINDOW_SECONDS:
            b.count = 0
            b.window_start = now

        remaining = max(0, limit - b.count)
        reset_in = max(0, int(WINDOW_SECONDS - (now - b.window_start)))

        if b.count >= limit:
            return False, 0, reset_in

        b.count += 1
        return True, remaining - 1, reset_in


_store = _RateLimiterStore()


# ---------------------------------------------------------------------------
# API key → tier lookup
# ---------------------------------------------------------------------------

def _load_api_keys() -> dict[str, str]:
    """Load {api_key: tier} from SWISS_TRUTH_API_KEYS env var (JSON dict)."""
    raw = os.environ.get("SWISS_TRUTH_API_KEYS", "{}")
    try:
        keys = json.loads(raw)
        if isinstance(keys, dict):
            return {str(k): str(v) for k, v in keys.items()}
    except Exception:
        pass
    return {}


_API_KEYS: dict[str, str] = _load_api_keys()

# Admin key (from existing config) also gets enterprise tier
_ADMIN_KEY = os.environ.get("SWISS_TRUTH_API_KEY", "")


# ---------------------------------------------------------------------------
# DB-backed API key cache (Phase 4 — Plan 04-01)
# ---------------------------------------------------------------------------

_db_key_cache: dict[str, tuple[str, float]] = {}  # hash → (tier, timestamp)
_DB_CACHE_TTL = 60.0  # seconds


def invalidate_key_cache() -> None:
    """Clear the in-memory API key cache. Called when keys are created/revoked."""
    _db_key_cache.clear()
    logger.info("API key cache invalidated")


def _hash_token(token: str) -> str:
    """SHA256 hash of a token for DB lookup."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def _check_db_key(token: str) -> str | None:
    """
    Check if token is a valid DB-managed API key.
    Uses in-memory cache with 60s TTL to avoid DB hits on every request.
    Returns tier string or None.
    """
    key_hash = _hash_token(token)
    now = time.time()

    # Check cache first
    if key_hash in _db_key_cache:
        cached_tier, cached_at = _db_key_cache[key_hash]
        if now - cached_at < _DB_CACHE_TTL:
            return cached_tier if cached_tier else None

    # DB lookup (async → run in sync context via cache miss marker)
    # We store a "pending" marker and resolve on next async opportunity
    # For now, use the env-var keys as primary, DB keys via cache warming
    return None


async def _async_check_db_key(token: str) -> str | None:
    """Async version: check DB for API key and cache result."""
    key_hash = _hash_token(token)
    now = time.time()

    # Check cache
    if key_hash in _db_key_cache:
        cached_tier, cached_at = _db_key_cache[key_hash]
        if now - cached_at < _DB_CACHE_TTL:
            return cached_tier if cached_tier else None

    # DB lookup
    try:
        from swiss_truth_mcp.db.neo4j_client import get_session
        from swiss_truth_mcp.db import queries
        async with get_session() as session:
            key_data = await queries.get_api_key_by_hash(session, key_hash)
            if key_data and key_data.get("active"):
                # Check expiry
                expires_at = key_data.get("expires_at")
                if expires_at:
                    from datetime import datetime, timezone
                    now_iso = datetime.now(timezone.utc).isoformat()
                    if expires_at < now_iso:
                        _db_key_cache[key_hash] = ("", now)
                        return None
                tier = key_data.get("tier", "free")
                _db_key_cache[key_hash] = (tier, now)
                # Fire-and-forget usage recording
                try:
                    await queries.record_api_key_usage(session, key_hash)
                except Exception:
                    pass
                return tier
            else:
                _db_key_cache[key_hash] = ("", now)
                return None
    except Exception as e:
        logger.debug("DB key lookup failed: %s", e)
        return None


def _resolve_tier(request_headers: dict[str, str]) -> tuple[str, str]:
    """
    Returns (tier, rate_limit_key).
    Checks Authorization: Bearer <token> and X-Swiss-Truth-Key header.
    Checks env-var keys first, then DB-backed keys via cache.
    """
    # 1. Bearer token
    auth = request_headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token == _ADMIN_KEY and _ADMIN_KEY:
            return "enterprise", f"key:{token}"
        tier = _API_KEYS.get(token)
        if tier:
            return tier, f"key:{token}"
        # Check DB cache (sync — cache hit only)
        db_tier = _check_db_key(token)
        if db_tier:
            return db_tier, f"key:{_hash_token(token)[:16]}"

    # 2. X-Swiss-Truth-Key header (legacy MCP header)
    x_key = request_headers.get("x-swiss-truth-key", "")
    if x_key:
        if x_key == _ADMIN_KEY and _ADMIN_KEY:
            return "enterprise", f"key:{x_key}"
        tier = _API_KEYS.get(x_key)
        if tier:
            return tier, f"key:{x_key}"
        db_tier = _check_db_key(x_key)
        if db_tier:
            return db_tier, f"key:{_hash_token(x_key)[:16]}"

    return "free", ""   # IP resolved by caller


async def _async_resolve_tier(request_headers: dict[str, str]) -> tuple[str, str]:
    """
    Async version of _resolve_tier — includes DB lookup for API keys.
    Used by the middleware for full DB-backed key resolution.
    """
    # 1. Bearer token
    auth = request_headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token == _ADMIN_KEY and _ADMIN_KEY:
            return "enterprise", f"key:{token}"
        tier = _API_KEYS.get(token)
        if tier:
            return tier, f"key:{token}"
        db_tier = await _async_check_db_key(token)
        if db_tier:
            return db_tier, f"key:{_hash_token(token)[:16]}"

    # 2. X-Swiss-Truth-Key header
    x_key = request_headers.get("x-swiss-truth-key", "")
    if x_key:
        if x_key == _ADMIN_KEY and _ADMIN_KEY:
            return "enterprise", f"key:{x_key}"
        tier = _API_KEYS.get(x_key)
        if tier:
            return tier, f"key:{x_key}"
        db_tier = await _async_check_db_key(x_key)
        if db_tier:
            return db_tier, f"key:{_hash_token(x_key)[:16]}"

    return "free", ""


def _client_ip(scope: dict) -> str:
    """Extract real client IP from X-Forwarded-For or connection info."""
    headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
    xff = headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"


# ---------------------------------------------------------------------------
# ASGI Middleware
# ---------------------------------------------------------------------------

# Paths exempt from rate limiting (health, static, admin UI)
_EXEMPT_PREFIXES = ("/static/", "/health", "/login", "/admin/", "/kanban", "/dashboard", "/review")
_EXEMPT_EXACT    = {"/health", "/favicon.ico"}


class RateLimitMiddleware:
    """
    ASGI middleware wrapping the entire Swiss Truth app.
    Applies sliding-window rate limiting per IP (free) or per API key (pro/enterprise).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Exempt internal/admin paths
        if path in _EXEMPT_EXACT or any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        tier, rate_key = _resolve_tier(headers)

        if tier == "enterprise":
            # Unlimited — pass through immediately
            await self.app(scope, receive, send)
            return

        limit = TIER_LIMITS[tier]
        assert limit is not None  # only enterprise is None

        if not rate_key:
            rate_key = f"ip:{_client_ip(scope)}"

        allowed, remaining, retry_after = _store.check(rate_key, limit)

        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "tier": tier,
                    "limit": limit,
                    "window": "24h",
                    "retry_after_seconds": retry_after,
                    "upgrade": (
                        "Increase your limit: https://swisstruth.org/trust"
                        if tier == "free" else None
                    ),
                },
                headers={
                    "X-RateLimit-Limit":     str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset":     str(int(time.time()) + retry_after),
                    "Retry-After":           str(retry_after),
                },
            )
            await response(scope, receive, send)
            logger.warning("Rate limit exceeded: %s tier=%s path=%s", rate_key, tier, path)
            return

        # Inject rate-limit headers into the downstream response
        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers_list = list(message.get("headers", []))
                headers_list += [
                    (b"x-ratelimit-limit",     str(limit).encode()),
                    (b"x-ratelimit-remaining", str(remaining).encode()),
                    (b"x-ratelimit-reset",     str(int(time.time() + retry_after)).encode()),
                    (b"x-ratelimit-tier",      tier.encode()),
                ]
                message = {**message, "headers": headers_list}
            await send(message)

        await self.app(scope, receive, send_with_headers)
