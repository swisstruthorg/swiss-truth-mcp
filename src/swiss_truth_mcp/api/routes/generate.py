"""
Admin-Endpunkt: Automatische Claim-Generierung via Claude API.

POST /admin/generate  — JSON API (Automation / Cron)
GET  /admin/generate  — Admin-UI mit Formular

Authentifizierung: Admin-Cookie ODER X-Swiss-Truth-Key Header.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from swiss_truth_mcp.auth.dependencies import get_current_user, require_admin
from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.seed.generator import generate_claims, DOMAINS
from swiss_truth_mcp.seed.loader import _import_claim
from swiss_truth_mcp.validation.trust import now_iso

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["admin"])


# ─── Auth: Cookie ODER API-Key ────────────────────────────────────────────────

async def _require_admin_or_apikey(request: Request) -> dict:
    """Erlaubt Admin-Cookie (UI) ODER X-Swiss-Truth-Key Header (Automation)."""
    api_key = (
        request.headers.get("x-swiss-truth-key", "").strip()
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    if api_key and api_key == settings.swiss_truth_api_key:
        return {"username": "automation", "role": "admin", "active": True}

    user = await get_current_user(request)
    if user and user.get("role") == "admin" and user.get("active"):
        return user

    raise HTTPException(status_code=401, detail="Admin-Authentifizierung erforderlich")


# ─── Admin-UI ─────────────────────────────────────────────────────────────────

@router.get("/admin/generate", response_class=HTMLResponse)
async def generate_page(
    request: Request,
    domain: str = "",
    current_user=Depends(require_admin),
):
    return templates.TemplateResponse(
        request, "generate.html",
        {
            "request": request,
            "current_user": current_user,
            "active": "generate",
            "domains": DOMAINS,
            "selected_domain": domain,
        },
    )


# ─── JSON API ─────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    domain_id: str | None = None  # None = alle Domains in DOMAINS
    count: int = 25


@router.post("/admin/generate")
async def auto_generate(req: GenerateRequest, auth=Depends(_require_admin_or_apikey)):
    """
    Generiert Claims via Claude API und importiert sie direkt.
    confidence >= 0.95 → certified, sonst → peer_review.

    Für Automation / Cron:
      curl -X POST https://swisstruth.org/admin/generate \\
        -H "X-Swiss-Truth-Key: KEY" \\
        -H "Content-Type: application/json" \\
        -d '{"domain_id": "swiss-law", "count": 25}'
    """
    if req.count < 1 or req.count > 100:
        raise HTTPException(status_code=400, detail="count muss zwischen 1 und 100 liegen")

    domain_ids = [req.domain_id] if req.domain_id else list(DOMAINS.keys())

    results = []
    grand_total = {"generated": 0, "certified": 0, "peer_review": 0, "skipped": 0}

    for did in domain_ids:
        if did not in DOMAINS:
            results.append({"domain_id": did, "error": f"Unbekannte Domain: {did}"})
            continue

        # Claims via Claude API generieren
        try:
            claims = await generate_claims(did, req.count)
        except Exception as e:
            results.append({"domain_id": did, "error": str(e)})
            continue

        certified = peer_review = skipped = 0

        async with get_session() as session:
            for i, claim in enumerate(claims, 1):
                try:
                    result = await _import_claim(session, claim, i, len(claims))
                    if result == "certified":
                        certified += 1
                    elif result == "peer_review":
                        peer_review += 1
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1

        domain_result = {
            "domain_id": did,
            "generated": len(claims),
            "certified": certified,
            "peer_review": peer_review,
            "skipped": skipped,
        }
        results.append(domain_result)

        for k in grand_total:
            grand_total[k] += domain_result.get(k, 0)

    return {
        "ok": True,
        "domains_processed": len([r for r in results if "error" not in r]),
        "results": results,
        "total": grand_total,
    }


# ─── Renewal-Check ────────────────────────────────────────────────────────────

@router.post("/admin/run-renewal-check")
async def run_renewal_check(auth=Depends(_require_admin_or_apikey)):
    """
    Markiert alle certified Claims mit abgelaufenem expires_at als 'needs_renewal'.
    Täglicher Cron-Job:
      curl -X POST https://swisstruth.org/admin/run-renewal-check \\
        -H "X-Swiss-Truth-Key: KEY"
    """
    now = now_iso()
    async with get_session() as session:
        expired = await queries.expire_outdated_claims(session, now)

    return {
        "ok": True,
        "checked_at": now,
        "expired_count": len(expired),
        "expired_ids": [c["id"] for c in expired],
    }
