"""
Redis Cache Client — Phase 5 (Plan 05-02)

Provides a unified cache interface with Redis backend.
Falls back to in-memory dict if REDIS_URL is not configured.

Usage:
    from swiss_truth_mcp.cache.redis_client import cache

    await cache.set("key", "value", ttl=60)
    value = await cache.get("key")
    await cache.delete("key")
    await cache.incr("counter")
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

_redis_client = None
_redis_available = False


async def _get_redis():
    """Lazy-init Redis connection."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client

    from swiss_truth_mcp.config import settings
    url = settings.redis_url
    if not url:
        logger.info("REDIS_URL not set — using in-memory cache fallback")
        _redis_available = False
        return None

    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        # Test connection
        await _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected: %s", url.split("@")[-1] if "@" in url else url)
        return _redis_client
    except Exception as e:
        logger.warning("Redis connection failed (%s) — using in-memory fallback", e)
        _redis_available = False
        _redis_client = None
        return None


# ---------------------------------------------------------------------------
# In-memory fallback store
# ---------------------------------------------------------------------------

@dataclass
class _MemEntry:
    value: str
    expires_at: float = 0.0  # 0 = no expiry


class _InMemoryStore:
    """Simple in-memory cache with TTL support."""

    def __init__(self) -> None:
        self._data: dict[str, _MemEntry] = {}
        self._counters: dict[str, int] = defaultdict(int)

    def _is_expired(self, key: str) -> bool:
        entry = self._data.get(key)
        if entry and entry.expires_at > 0 and time.time() > entry.expires_at:
            del self._data[key]
            return True
        return entry is None

    async def get(self, key: str) -> Optional[str]:
        if self._is_expired(key):
            return None
        entry = self._data.get(key)
        return entry.value if entry else None

    async def set(self, key: str, value: str, ttl: int = 0) -> None:
        expires_at = time.time() + ttl if ttl > 0 else 0.0
        self._data[key] = _MemEntry(value=value, expires_at=expires_at)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        self._counters[key] += 1
        return self._counters[key]

    async def expire(self, key: str, ttl: int) -> None:
        entry = self._data.get(key)
        if entry:
            entry.expires_at = time.time() + ttl

    async def exists(self, key: str) -> bool:
        if self._is_expired(key):
            return False
        return key in self._data

    async def keys(self, pattern: str = "*") -> list[str]:
        """Simple pattern matching (only supports prefix*)."""
        if pattern == "*":
            return list(self._data.keys())
        prefix = pattern.rstrip("*")
        return [k for k in self._data if k.startswith(prefix)]

    async def flushdb(self) -> None:
        self._data.clear()
        self._counters.clear()

    async def ping(self) -> bool:
        return True


_mem_store = _InMemoryStore()


# ---------------------------------------------------------------------------
# Unified Cache Interface
# ---------------------------------------------------------------------------

class Cache:
    """
    Unified cache interface.
    Uses Redis if available, falls back to in-memory.
    """

    async def get(self, key: str) -> Optional[str]:
        r = await _get_redis()
        if r:
            try:
                return await r.get(key)
            except Exception:
                pass
        return await _mem_store.get(key)

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def set(self, key: str, value: str, ttl: int = 0) -> None:
        r = await _get_redis()
        if r:
            try:
                if ttl > 0:
                    await r.setex(key, ttl, value)
                else:
                    await r.set(key, value)
                return
            except Exception:
                pass
        await _mem_store.set(key, value, ttl)

    async def set_json(self, key: str, value: Any, ttl: int = 0) -> None:
        await self.set(key, json.dumps(value, default=str), ttl)

    async def delete(self, key: str) -> None:
        r = await _get_redis()
        if r:
            try:
                await r.delete(key)
                return
            except Exception:
                pass
        await _mem_store.delete(key)

    async def incr(self, key: str) -> int:
        r = await _get_redis()
        if r:
            try:
                return await r.incr(key)
            except Exception:
                pass
        return await _mem_store.incr(key)

    async def exists(self, key: str) -> bool:
        r = await _get_redis()
        if r:
            try:
                return bool(await r.exists(key))
            except Exception:
                pass
        return await _mem_store.exists(key)

    async def flush_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern. Returns count deleted."""
        r = await _get_redis()
        if r:
            try:
                keys = []
                async for key in r.scan_iter(match=pattern):
                    keys.append(key)
                if keys:
                    await r.delete(*keys)
                return len(keys)
            except Exception:
                pass
        mem_keys = await _mem_store.keys(pattern)
        for k in mem_keys:
            await _mem_store.delete(k)
        return len(mem_keys)

    async def health_check(self) -> dict:
        """Check cache health status."""
        r = await _get_redis()
        if r:
            try:
                await r.ping()
                info = await r.info("memory")
                return {
                    "backend": "redis",
                    "status": "healthy",
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                }
            except Exception as e:
                return {"backend": "redis", "status": "unhealthy", "error": str(e)}
        return {"backend": "in-memory", "status": "healthy"}

    @property
    def is_redis(self) -> bool:
        return _redis_available


# Module singleton
cache = Cache()
