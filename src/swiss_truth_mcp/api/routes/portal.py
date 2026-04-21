"""
Developer Portal API Routes — Phase 5 (Plan 05-03)

Self-service registration, login, API key management, and usage dashboard.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.middleware.rate_limiter import invalidate_key_cache

router = APIRouter(prefix="/portal", tags=["developer-portal"])


# ─── Request Models ────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    company: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateKeyRequest(BaseModel):
    name: str = "Default Key"


# ─── Registration ──────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(body: RegisterRequest):
    """Register a new developer account with free-tier API key."""
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if "@" not in body.email:
        raise HTTPException(400, "Invalid email address")

    try:
        from swiss_truth_mcp.auth.registration import register_developer
        result = await register_developer(
            email=body.email,
            password=body.password,
            name=body.name,
            company=body.company,
        )
        invalidate_key_cache()
        return result
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/login")
async def login(body: LoginRequest):
    """Authenticate and return profile with API keys."""
    try:
        from swiss_truth_mcp.auth.registration import login_developer
        return await login_developer(body.email, body.password)
    except ValueError as e:
        raise HTTPException(401, str(e))


# ─── API Key Management ───────────────────────────────────────────────────────

@router.get("/keys")
async def list_my_keys(tenant_id: str):
    """List all API keys for a tenant."""
    async with get_session() as session:
        all_keys = await queries.list_api_keys(session)
        return [k for k in all_keys if k.get("tenant_id") == tenant_id]


@router.post("/keys", status_code=201)
async def create_key(tenant_id: str, body: CreateKeyRequest):
    """Create a new free-tier API key for a tenant."""
    async with get_session() as session:
        tenant = await queries.get_tenant_by_id(session, tenant_id)
        if not tenant:
            raise HTTPException(404, "Tenant not found")

        # Limit: max 5 keys per free tenant
        all_keys = await queries.list_api_keys(session)
        tenant_keys = [k for k in all_keys if k.get("tenant_id") == tenant_id and k.get("active")]
        if tenant.get("plan") == "free" and len(tenant_keys) >= 5:
            raise HTTPException(
                403,
                "Free plan limited to 5 API keys. Upgrade to pro for unlimited keys.",
            )

        raw_key = f"sk-{tenant.get('plan', 'fre')[:3]}-{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        await queries.create_api_key(session, {
            "id": key_id,
            "key_hash": key_hash,
            "key_prefix": raw_key[:16],
            "tier": tenant.get("plan", "free"),
            "owner_name": body.name,
            "owner_email": "",
            "tenant_id": tenant_id,
            "active": True,
            "created_at": now,
            "expires_at": "",
            "request_count": 0,
            "last_used_at": "",
        })

    invalidate_key_cache()
    return {
        "id": key_id,
        "api_key": raw_key,
        "prefix": raw_key[:16],
        "tier": tenant.get("plan", "free"),
        "message": "Save your API key — it won't be shown again.",
    }


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: str, tenant_id: str):
    """Revoke an API key."""
    async with get_session() as session:
        key = await queries.get_api_key_by_id(session, key_id)
        if not key or key.get("tenant_id") != tenant_id:
            raise HTTPException(404, "Key not found")
        await queries.revoke_api_key(session, key_id)

    invalidate_key_cache()
    return {"status": "revoked", "key_id": key_id}


# ─── Usage Dashboard ──────────────────────────────────────────────────────────

@router.get("/usage")
async def get_usage(tenant_id: str):
    """Get usage statistics for a tenant."""
    async with get_session() as session:
        tenant = await queries.get_tenant_by_id(session, tenant_id)
        if not tenant:
            raise HTTPException(404, "Tenant not found")

        usage = await queries.get_tenant_usage_stats(session, tenant_id)
        all_keys = await queries.list_api_keys(session)
        tenant_keys = [k for k in all_keys if k.get("tenant_id") == tenant_id]

    return {
        "tenant": tenant,
        "usage": usage,
        "api_keys": tenant_keys,
        "limits": {
            "free": {"requests_per_day": 1000, "max_keys": 5},
            "pro": {"requests_per_day": 100000, "max_keys": 50},
            "enterprise": {"requests_per_day": "unlimited", "max_keys": "unlimited"},
        },
    }
