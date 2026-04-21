"""
Developer Portal Registration — Phase 5 (Plan 05-03)

Self-service registration: email + password → tenant + free-tier API key.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

import bcrypt

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _generate_api_key(tier: str = "free") -> tuple[str, str, str]:
    """Generate API key. Returns (raw_key, key_hash, key_prefix)."""
    raw = f"sk-{tier[:3]}-{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:16]
    return raw, key_hash, prefix


def _generate_verification_token() -> str:
    return secrets.token_urlsafe(48)


async def register_developer(
    email: str,
    password: str,
    name: str,
    company: str = "",
) -> dict:
    """
    Register a new developer:
    1. Create User node
    2. Create Tenant node
    3. Create free-tier API key
    4. Return credentials

    Raises ValueError if email already exists.
    """
    now = datetime.now(timezone.utc).isoformat()
    slug = email.split("@")[0].lower().replace(".", "-").replace("+", "-")[:32]

    async with get_session() as session:
        # Check if user exists
        existing = await queries.get_user_by_username(session, email)
        if existing:
            raise ValueError(f"User with email {email} already exists")

        # Check if slug exists, append random suffix if needed
        existing_tenant = await queries.get_tenant_by_slug(session, slug)
        if existing_tenant:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # 1. Create User
        user_id = str(uuid.uuid4())
        password_hash = _hash_password(password)
        await queries.create_user(session, {
            "id": user_id,
            "username": email,
            "email": email,
            "password_hash": password_hash,
            "role": "developer",
            "active": True,
            "created_at": now,
        })

        # 2. Create Tenant
        tenant_id = str(uuid.uuid4())
        await queries.create_tenant(session, {
            "id": tenant_id,
            "name": company or name,
            "slug": slug,
            "plan": "free",
            "active": True,
            "created_at": now,
            "settings_json": {
                "owner_user_id": user_id,
                "owner_email": email,
                "owner_name": name,
            },
        })

        # 3. Create free-tier API key
        raw_key, key_hash, key_prefix = _generate_api_key("free")
        key_id = str(uuid.uuid4())
        await queries.create_api_key(session, {
            "id": key_id,
            "key_hash": key_hash,
            "key_prefix": key_prefix,
            "tier": "free",
            "owner_name": name,
            "owner_email": email,
            "tenant_id": tenant_id,
            "active": True,
            "created_at": now,
            "expires_at": "",  # free keys don't expire
            "request_count": 0,
            "last_used_at": "",
        })

    return {
        "user_id": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "tenant_slug": slug,
        "api_key": raw_key,
        "api_key_prefix": key_prefix,
        "tier": "free",
        "message": "Registration successful. Save your API key — it won't be shown again.",
    }


async def login_developer(email: str, password: str) -> dict:
    """
    Authenticate a developer and return their profile + API keys.
    Raises ValueError on invalid credentials.
    """
    async with get_session() as session:
        user = await queries.get_user_by_username_with_hash(session, email)
        if not user:
            raise ValueError("Invalid email or password")

        if not _verify_password(password, user["password_hash"]):
            raise ValueError("Invalid email or password")

        if not user.get("active", True):
            raise ValueError("Account is deactivated")

        # Get tenant and API keys
        # Find tenant by owner email in settings
        tenants = await queries.list_tenants(session)
        user_tenant = None
        for t in tenants:
            settings = t.get("settings_json", {})
            if isinstance(settings, dict) and settings.get("owner_email") == email:
                user_tenant = t
                break

        # Get API keys for tenant
        api_keys = []
        if user_tenant:
            all_keys = await queries.list_api_keys(session)
            api_keys = [
                k for k in all_keys
                if k.get("tenant_id") == user_tenant["id"]
            ]

    return {
        "user_id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "tenant": user_tenant,
        "api_keys": api_keys,
    }
