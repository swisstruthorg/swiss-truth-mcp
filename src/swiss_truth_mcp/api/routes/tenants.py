"""
Multi-Tenant Management — Phase 4 (Plan 04-05)

Admin-only endpoints for managing tenants with usage plans.

Endpoints:
- POST  /admin/tenants              — Create a new tenant
- GET   /admin/tenants              — List all tenants
- GET   /admin/tenants/{tenant_id}  — Tenant details with usage stats
- PATCH /admin/tenants/{tenant_id}  — Update tenant (plan, active, settings)
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

router = APIRouter(prefix="/admin/tenants", tags=["tenants"])


# ── Auth ──────────────────────────────────────────────────────────────────────

async def _require_admin(request: Request) -> dict:
    """Admin auth via cookie or API key."""
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

class CreateTenantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Tenant display name")
    slug: str = Field(
        ..., min_length=2, max_length=50,
        description="URL-safe slug (lowercase, hyphens only)",
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
    )
    plan: str = Field(default="pro", description="Tenant plan: free, pro, enterprise")
    settings_json: dict = Field(default_factory=dict, description="Custom tenant settings (JSON)")


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    plan: str | None = Field(default=None, description="free, pro, enterprise")
    active: bool | None = Field(default=None)
    settings_json: dict | None = Field(default=None)


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    active: bool
    created_at: str
    settings_json: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=TenantResponse)
async def create_tenant(
    body: CreateTenantRequest,
    auth=Depends(_require_admin),
):
    """
    Create a new tenant.

    Plans:
    - free: Basic access, shared rate limits
    - pro: Higher limits, priority support
    - enterprise: Custom limits, dedicated support, SLA
    """
    if body.plan not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=422, detail="Plan must be: free, pro, enterprise")

    now = datetime.now(timezone.utc).isoformat()

    tenant_data = {
        "id": f"tenant-{secrets.token_hex(8)}",
        "name": body.name,
        "slug": body.slug,
        "plan": body.plan,
        "active": True,
        "created_at": now,
        "settings_json": body.settings_json,
    }

    async with get_session() as session:
        # Check slug uniqueness
        existing = await queries.get_tenant_by_slug(session, body.slug)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Tenant with slug '{body.slug}' already exists",
            )
        await queries.create_tenant(session, tenant_data)

    return TenantResponse(**tenant_data)


@router.get("", response_model=list[TenantResponse])
async def list_tenants(auth=Depends(_require_admin)):
    """List all tenants."""
    async with get_session() as session:
        tenants = await queries.list_tenants(session)
    return tenants


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: str, auth=Depends(_require_admin)):
    """
    Tenant details with usage statistics.

    Returns tenant info plus:
    - Number of API keys
    - Total request count across all keys
    - Number of claims owned by tenant
    """
    async with get_session() as session:
        tenant = await queries.get_tenant_by_id(session, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

        stats = await queries.get_tenant_usage_stats(session, tenant_id)

    return {
        **tenant,
        "usage": stats,
    }


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    body: UpdateTenantRequest,
    auth=Depends(_require_admin),
):
    """Update tenant properties (name, plan, active status, settings)."""
    if body.plan and body.plan not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=422, detail="Plan must be: free, pro, enterprise")

    async with get_session() as session:
        tenant = await queries.get_tenant_by_id(session, tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found")

        updates = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.plan is not None:
            updates["plan"] = body.plan
        if body.active is not None:
            updates["active"] = body.active
        if body.settings_json is not None:
            updates["settings_json"] = body.settings_json

        if updates:
            await queries.update_tenant(session, tenant_id, updates)

        updated = await queries.get_tenant_by_id(session, tenant_id)

    return TenantResponse(**updated)
