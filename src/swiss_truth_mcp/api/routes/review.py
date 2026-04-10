from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from swiss_truth_mcp.auth.dependencies import require_user
from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.embeddings import embed_text
from swiss_truth_mcp.integrations.webhook import fire_event, fire_subscribers
from swiss_truth_mcp.validation.trust import now_iso, sign_claim

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/review", tags=["review"])


def _flash(request: Request, msg: str, type: str = "ok") -> dict:
    return {"request": request, "flash": {"msg": msg, "type": type}}


async def _renewal_count() -> int:
    """Zählt needs_renewal Claims für den Nav-Badge — schnell, gecacht pro Request."""
    try:
        async with get_session() as session:
            r = await session.run(
                "MATCH (c:Claim {status: 'needs_renewal'}) RETURN count(c) AS n"
            )
            row = await r.single()
            return row["n"] if row else 0
    except Exception:
        return 0


def _ctx(request: Request, active: str, extra: dict | None = None,
         flash: dict | None = None, renewal_count: int = 0) -> dict:
    base = {"request": request, "active": active, "flash": flash,
            "renewal_count": renewal_count}
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# GET /review  — Review Queue
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def review_queue(request: Request, msg: Optional[str] = None, err: Optional[str] = None, user=Depends(require_user)):
    flash = None
    if msg:
        flash = {"msg": msg, "type": "ok"}
    elif err:
        flash = {"msg": err, "type": "err"}

    async with get_session() as session:
        claims = await queries.list_claims_by_status(session, "peer_review")
    rc = await _renewal_count()

    return templates.TemplateResponse(
        request, "review_list.html",
        _ctx(request, "review", {"claims": claims}, flash, renewal_count=rc),
    )


# ---------------------------------------------------------------------------
# GET /review/certified  — Zertifizierte Claims
# ---------------------------------------------------------------------------

@router.get("/certified", response_class=HTMLResponse)
async def certified_list(request: Request, page: int = 1, user=Depends(require_user)):
    per_page = 50
    page = max(1, page)
    offset = (page - 1) * per_page

    async with get_session() as session:
        total = await queries.count_claims_by_status(session, "certified")
        claims = await queries.list_claims_by_status(session, "certified", limit=per_page, offset=offset)

    total_pages = max(1, (total + per_page - 1) // per_page)
    rc = await _renewal_count()

    return templates.TemplateResponse(
        request, "review_certified.html",
        _ctx(request, "certified", {
            "claims": claims,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "per_page": per_page,
        }, renewal_count=rc),
    )


# ---------------------------------------------------------------------------
# GET /review/renewal  — Renewal Queue  (muss VOR /{claim_id} stehen!)
# ---------------------------------------------------------------------------

@router.get("/renewal", response_class=HTMLResponse)
async def renewal_queue(request: Request, msg: Optional[str] = None, err: Optional[str] = None, user=Depends(require_user)):
    flash = None
    if msg:
        flash = {"msg": msg, "type": "ok"}
    elif err:
        flash = {"msg": err, "type": "err"}

    from swiss_truth_mcp.validation.trust import expiry_iso
    async with get_session() as session:
        claims   = await queries.list_claims_by_status(session, "needs_renewal")
        expiring = await queries.list_expiring_soon(
            session,
            now=now_iso(),
            cutoff=expiry_iso(days=30),
            limit=10,
        )
    rc = await _renewal_count()

    return templates.TemplateResponse(
        request, "review_renewal.html",
        _ctx(request, "renewal", {"claims": claims, "expiring": expiring}, flash, renewal_count=rc),
    )


# ---------------------------------------------------------------------------
# GET /review/{claim_id}  — Claim Detail
# ---------------------------------------------------------------------------

@router.get("/{claim_id}", response_class=HTMLResponse)
async def review_detail(claim_id: str, request: Request, user=Depends(require_user)):
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Claim nicht gefunden")

        # Konflikt-Check via Embedding
        conflicts = []
        if claim.get("status") == "peer_review":
            embedding = await embed_text(claim["text"])
            raw_conflicts = await queries.find_conflicting_claims(session, embedding, similarity_threshold=0.93)
            conflicts = [c for c in raw_conflicts if c["id"] != claim_id]

    rc = await _renewal_count()
    return templates.TemplateResponse(
        request, "review_detail.html",
        _ctx(request, "review", {
            "claim": claim,
            "conflicts": conflicts,
            "prefill_name": "",
            "prefill_institution": "",
        }, renewal_count=rc),
    )


# ---------------------------------------------------------------------------
# POST /review/{claim_id}/approve
# ---------------------------------------------------------------------------

@router.post("/{claim_id}/approve")
async def approve_claim(
    claim_id: str,
    expert_name: Annotated[str, Form()],
    expert_institution: Annotated[str, Form()] = "",
    confidence: Annotated[float, Form()] = 0.85,
    note: Annotated[str, Form()] = "",
):
    if not expert_name.strip():
        return RedirectResponse(f"/review/{claim_id}?err=Name+ist+Pflichtfeld", status_code=303)

    confidence = max(0.0, min(1.0, confidence))
    reviewed_at = now_iso()

    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)
        if claim is None:
            raise HTTPException(status_code=404)

        await queries.validate_claim(
            session,
            claim_id=claim_id,
            expert_name=expert_name.strip(),
            expert_institution=expert_institution.strip(),
            verdict="approved",
            confidence_score=confidence,
            reviewed_at=reviewed_at,
        )

        # Hash nach Statusänderung aktualisieren
        updated = {**claim, "status": "certified", "confidence_score": confidence}
        new_hash = sign_claim(updated)
        await session.run(
            "MATCH (c:Claim {id: $id}) SET c.hash_sha256 = $hash",
            {"id": claim_id, "hash": new_hash},
        )

    # n8n-Webhook + alle registrierten Subscriber (fire-and-forget)
    asyncio.create_task(fire_event("claim.certified", {
        "claim_id":        claim_id,
        "expert_name":     expert_name.strip(),
        "confidence_score": confidence,
        "hash_sha256":     new_hash,
        "review_url":      f"{settings.public_base_url}/n8n/status/{claim_id}",
    }))
    asyncio.create_task(fire_subscribers("claim.certified", {
        **claim,
        "status":           "certified",
        "confidence_score": confidence,
        "hash_sha256":      new_hash,
        "last_reviewed":    reviewed_at,
    }))

    return RedirectResponse(
        f"/review?msg=Claim+zertifiziert+von+{expert_name.replace(' ', '+')}",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# POST /review/{claim_id}/reject
# ---------------------------------------------------------------------------

@router.post("/{claim_id}/reject")
async def reject_claim(
    claim_id: str,
    expert_name: Annotated[str, Form()] = "",
    expert_institution: Annotated[str, Form()] = "",
):
    reviewed_at = now_iso()

    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)
        if claim is None:
            raise HTTPException(status_code=404)

        await queries.validate_claim(
            session,
            claim_id=claim_id,
            expert_name=expert_name.strip() or "Anonym",
            expert_institution=expert_institution.strip(),
            verdict="rejected",
            confidence_score=0.0,
            reviewed_at=reviewed_at,
        )

    # Webhook-Event (fire-and-forget)
    asyncio.create_task(fire_event("claim.rejected", {
        "claim_id":    claim_id,
        "expert_name": expert_name.strip() or "Anonym",
        "review_url":  f"{settings.public_base_url}/n8n/status/{claim_id}",
    }))

    return RedirectResponse(
        "/review?msg=Claim+abgelehnt+und+zur%C3%BCck+zu+draft+gesetzt",
        status_code=303,
    )


# ---------------------------------------------------------------------------
# POST /review/{claim_id}/renew
# ---------------------------------------------------------------------------

@router.post("/{claim_id}/renew")
async def renew_claim(
    claim_id: str,
    expert_name: Annotated[str, Form()],
    expert_institution: Annotated[str, Form()] = "",
    confidence: Annotated[float, Form()] = 0.90,
    ttl_days: Annotated[int, Form()] = 365,
):
    if not expert_name.strip():
        return RedirectResponse(
            f"/review/{claim_id}?err=Name+ist+Pflichtfeld", status_code=303
        )

    confidence = max(0.0, min(1.0, confidence))
    ttl_days   = max(30, min(730, ttl_days))
    reviewed_at = now_iso()

    from swiss_truth_mcp.validation.trust import expiry_iso
    new_expiry = expiry_iso(days=ttl_days)

    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)
        if claim is None:
            raise HTTPException(status_code=404)

        updated = {**claim, "status": "certified", "confidence_score": confidence}
        new_hash = sign_claim(updated)

        await queries.renew_claim(
            session,
            claim_id=claim_id,
            expert_name=expert_name.strip(),
            expert_institution=expert_institution.strip(),
            confidence_score=confidence,
            new_hash=new_hash,
            reviewed_at=reviewed_at,
            new_expiry=new_expiry,
        )

    asyncio.create_task(fire_event("claim.renewed", {
        "claim_id":        claim_id,
        "expert_name":     expert_name.strip(),
        "confidence_score": confidence,
        "new_expiry":      new_expiry,
        "review_url":      f"{settings.public_base_url}/n8n/status/{claim_id}",
    }))

    return RedirectResponse(
        f"/review/renewal?msg=Claim+erneuert+von+{expert_name.strip().replace(' ', '+')}",
        status_code=303,
    )
