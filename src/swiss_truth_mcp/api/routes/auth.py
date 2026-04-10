"""Login / Logout Routes."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from swiss_truth_mcp.auth.dependencies import COOKIE_NAME, get_current_user
from swiss_truth_mcp.auth.security import create_access_token, verify_password
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_current_user)):
    # Bereits eingeloggt → direkt zum Dashboard
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    error = request.query_params.get("error")
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": error})


@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    async with get_session() as session:
        user = await queries.get_user_by_username_with_hash(session, username)

    if not user or not user.get("active"):
        return RedirectResponse(url="/login?error=invalid", status_code=302)

    if not verify_password(password, user["password_hash"]):
        return RedirectResponse(url="/login?error=invalid", status_code=302)

    token = create_access_token(username=user["username"], role=user["role"])
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=86400,      # 24 Stunden
        samesite="lax",
        secure=True,        # Nur HTTPS
    )
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(key=COOKIE_NAME)
    return response
