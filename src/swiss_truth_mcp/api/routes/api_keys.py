"""
API Key Management — Phase 4 (Plan 04-01)

Admin-only endpoints for managing API keys with usage tiers.
Keys are stored in Neo4j with SHA256 hashing. No public self-service.

Endpoints:
- POST   /admin/api-keys              — Generate a new API key
- GET    /admin/api-keys              — List all API keys (prefix + metadata only)
- DELETE /admin/api-keys/{key_id}     — Revoke an API key
- GET    /admin/api-keys/{key_id}/usage — Usage statistics for a key
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

router = APIRouter(prefix="/admin/api-keys", tags=["api-keys"])


# ── Auth ──────────────────────────────────────────────────────────────────────

async def _require_admin(request):
    """Reuse admin auth from quality.py pattern."""
    from fastapi import Request as _Req
    from swiss_truth_mcp.config import settings
    from swiss_truth_mcp.auth.dependencies import get_current_user

    api_key = (
        request.headers.get("x-swiss-truth-key", "").strip()
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    if api_key and api_key == settings.swiss_truth_api_key:
        return {"username": "automation", "role": "admin"}

    user = await get_current_user(request)
    if user and user.get("role") == "admin" and user.get("active"):
        return user

    raise HTTPException(status_code=401, detail="Admin authentication required")


# ── Models ────────────────────────────────────────────────────────────────────

class CreateApiKeyRequest(BaseModel):
    owner_name: str = Field(..., min_length=1, max_length=200, description="Name of the key owner")
    owner_email: str = Field(default="", max_length=200, description="Contact email")
    tier: str = Field(default="pro", description="Usage tier: free, pro, enterprise")
    tenant_id: str | None = Field(default=None, description="Optional tenant ID")
    expires_in_days: int | None = Field(default=365, description="Days until expiry (null = never)")


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    tier: str
    owner_name: str
    owner_email: str
    tenant_id: str | None
    active: bool
    created_at: str
    expires_at: str | None
    request_count: int
    last_used_at: str | None


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned only on creation — includes the full key (shown once)."""
    api_key: str = Field(..., description="Full API key — store securely, shown only once")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_key(tier: str) -> str:
    """Generate a prefixed API key: sk-{tier[:3]}-{random}."""
    prefix = tier[:3]
    random_part = secrets.token_urlsafe(32)
    return f"sk-{prefix}-{random_part}"


def _hash_key(key: str) -> str:
    """SHA256 hash of the API key for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


def _key_prefix(key: str) -> str:
    """First 12 characters of the key for display."""
    return key[:12] + "..."


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=ApiKeyCreatedResponse)
async def create_api_key(
    body: CreateApiKeyRequest,
    auth=Depends(_require_admin),
):
    """
    Generate a new API key. The full key is returned ONCE — store it securely.

    Tiers:
    - free: 1,000 requests/day
    - pro: 100,000 requests/day
    - enterprise: unlimited
    """
    if body.tier not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=422, detail="Tier must be: free, pro, enterprise")

    now = datetime.now(timezone.utc).isoformat()
    raw_key = _generate_key(body.tier)

    from swiss_truth_mcp.validation.trust import expiry_iso
    expires_at = expiry_iso(days=body.expires_in_days) if body.expires_in_days else None

    key_data = {
        "id": f"key-{secrets.token_hex(8)}",
        "key_hash": _hash_key(raw_key),
        "key_prefix": _key_prefix(raw_key),
        "tier": body.tier,
        "owner_name": body.owner_name,
        "owner_email": body.owner_email,
        "tenant_id": body.tenant_id,
        "active": True,
        "created_at": now,
        "expires_at": expires_at,
        "request_count": 0,
        "last_used_at": None,
    }

    async with get_session() as session:
        await queries.create_api_key(session, key_data)

    # Invalidate rate limiter cache
    from swiss_truth_mcp.middleware.rate_limiter import invalidate_key_cache
    invalidate_key_cache()

    return ApiKeyCreatedResponse(
        **{k: v for k, v in key_data.items() if k != "key_hash"},
        api_key=raw_key,
    )


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(auth=Depends(_require_admin)):
    """List all API keys (prefix + metadata only, no full keys)."""
    async with get_session() as session:
        keys = await queries.list_api_keys(session)
    return keys


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, auth=Depends(_require_admin)):
    """Revoke an API key. The key will immediately stop working."""
    async with get_session() as session:
        success = await queries.revoke_api_key(session, key_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"API key '{key_id}' not found")

    from swiss_truth_mcp.middleware.rate_limiter import invalidate_key_cache
    invalidate_key_cache()

    return {"ok": True, "revoked": key_id}


@router.get("/{key_id}/usage")
async def get_api_key_usage(key_id: str, auth=Depends(_require_admin)):
    """Usage statistics for a specific API key."""
    async with get_session() as session:
        key = await queries.get_api_key_by_id(session, key_id)

    if not key:
        raise HTTPException(status_code=404, detail=f"API key '{key_id}' not found")

    return {
        "key_id": key["id"],
        "key_prefix": key["key_prefix"],
        "tier": key["tier"],
        "owner_name": key["owner_name"],
        "active": key["active"],
        "request_count": key.get("request_count", 0),
        "last_used_at": key.get("last_used_at"),
        "created_at": key["created_at"],
        "expires_at": key.get("expires_at"),
    }
