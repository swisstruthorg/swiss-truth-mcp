"""Nutzerverwaltung — nur für Admins."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from swiss_truth_mcp.auth.dependencies import require_admin
from swiss_truth_mcp.auth.security import hash_password
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.validation.trust import now_iso

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_class=HTMLResponse)
async def users_list(request: Request, admin=Depends(require_admin)):
    async with get_session() as session:
        users = await queries.list_users(session)
    return templates.TemplateResponse(
        request, "users.html",
        {"request": request, "users": users, "active": "users", "current_user": admin, "renewal_count": 0},
    )


@router.post("/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("reviewer"),
    admin=Depends(require_admin),
):
    async with get_session() as session:
        existing = await queries.get_user_by_username(session, username)
        if existing:
            users = await queries.list_users(session)
            return templates.TemplateResponse(
                request, "users.html",
                {"request": request, "users": users, "active": "users",
                 "current_user": admin, "renewal_count": 0,
                 "flash": {"msg": f"Benutzername '{username}' bereits vergeben.", "type": "err"}},
            )
        await queries.create_user(session, {
            "id":            str(uuid.uuid4()),
            "username":      username,
            "email":         email,
            "password_hash": hash_password(password),
            "role":          role,
            "active":        True,
            "created_at":    now_iso(),
        })
    return RedirectResponse(url="/users?created=1", status_code=302)


@router.post("/{user_id}/toggle")
async def toggle_active(user_id: str, request: Request, admin=Depends(require_admin)):
    async with get_session() as session:
        users = await queries.list_users(session)
        target = next((u for u in users if u["id"] == user_id), None)
        if target and target["id"] != admin["id"]:   # Sich selbst nicht deaktivieren
            await queries.update_user_active(session, user_id, not target["active"])
    return RedirectResponse(url="/users", status_code=302)


@router.post("/{user_id}/role")
async def change_role(user_id: str, role: str = Form(...), admin=Depends(require_admin)):
    if role in ("admin", "reviewer"):
        async with get_session() as session:
            await queries.update_user_role(session, user_id, role)
    return RedirectResponse(url="/users", status_code=302)


@router.post("/{user_id}/delete")
async def delete_user(user_id: str, admin=Depends(require_admin)):
    async with get_session() as session:
        if user_id != admin["id"]:   # Sich selbst nicht löschen
            await queries.delete_user(session, user_id)
    return RedirectResponse(url="/users", status_code=302)
