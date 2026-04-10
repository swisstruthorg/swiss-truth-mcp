"""FastAPI-Dependencies für Authentifizierung."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from swiss_truth_mcp.auth.security import decode_token
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

COOKIE_NAME = "st_session"


async def get_current_user(request: Request) -> dict | None:
    """Gibt den eingeloggten User zurück — oder None wenn nicht eingeloggt."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    try:
        async with get_session() as session:
            return await queries.get_user_by_username(session, username)
    except Exception:
        return None


async def require_user(request: Request) -> dict:
    """Schützt eine Route — leitet zu /login weiter wenn nicht eingeloggt."""
    user = await get_current_user(request)
    if not user or not user.get("active", False):
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


async def require_admin(request: Request) -> dict:
    """Schützt eine Route — nur Admins erlaubt."""
    user = await require_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin-Rechte erforderlich")
    return user
