"""
Quality & Scale API Routes (Phase 3)

- GET  /api/coverage/{domain_id}  — Domain coverage analysis
- GET  /api/coverage              — All-domains coverage overview
- GET  /api/conflicts             — Known conflicts in knowledge base
- POST /admin/renewal             — Manual renewal trigger
- GET  /admin/renewal/status      — Renewal status
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session

router = APIRouter(tags=["quality"])


# ── Auth helper ───────────────────────────────────────────────────────────────

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


# ── Coverage Endpoints ────────────────────────────────────────────────────────

@router.get("/api/coverage/{domain_id}")
async def get_domain_coverage(domain_id: str):
    """
    Analyze topic coverage for a specific domain.

    Returns which topics are covered by certified claims and which are gaps.
    """
    from swiss_truth_mcp.validation.coverage import analyze_coverage
    return await analyze_coverage(domain_id)


@router.get("/api/coverage")
async def get_all_coverage():
    """
    Coverage overview across all domains.

    Returns average coverage rate, per-domain breakdown, and total gaps.
    """
    from swiss_truth_mcp.validation.coverage import analyze_all_domains
    return await analyze_all_domains()


# ── Conflict Endpoints ────────────────────────────────────────────────────────

@router.get("/api/conflicts")
async def list_conflicts():
    """
    List all known conflicts between certified claims.

    Returns pairs of claims with CONFLICTS_WITH relationships.
    """
    from swiss_truth_mcp.validation.conflict_detect import get_all_conflicts

    async with get_session() as session:
        conflicts = await get_all_conflicts(session)

    return {
        "total": len(conflicts),
        "conflicts": conflicts,
    }


# ── Renewal Admin Endpoints ──────────────────────────────────────────────────

class RenewalRequest(BaseModel):
    max_claims: int = 20
    lookahead_days: int = 30


@router.post("/admin/renewal")
async def trigger_renewal(
    req: RenewalRequest = RenewalRequest(),
    auth=Depends(_require_admin),
):
    """
    Manually trigger the renewal pipeline.

    Re-verifies expiring claims via Claude Haiku, respecting the daily cost cap.
    """
    from swiss_truth_mcp.renewal.worker import run_renewal_batch

    result = await run_renewal_batch(
        max_claims=req.max_claims,
        lookahead_days=req.lookahead_days,
    )
    return {"ok": True, "result": result}


@router.get("/admin/renewal/status")
async def renewal_status(auth=Depends(_require_admin)):
    """Current renewal pipeline status: cost cap, expiring claims count."""
    from swiss_truth_mcp.renewal.cost_cap import daily_cap
    from swiss_truth_mcp.validation.trust import now_iso, expiry_iso
    from swiss_truth_mcp.db import queries

    now = now_iso()
    cutoff_30 = expiry_iso(days=30)
    cutoff_7 = expiry_iso(days=7)

    async with get_session() as session:
        expiring_30 = await queries.list_expiring_soon(session, now, cutoff_30, limit=100)
        expiring_7 = await queries.list_expiring_soon(session, now, cutoff_7, limit=100)

    return {
        "cost_cap": {
            "spend_today": round(daily_cap.current_spend, 4),
            "max_daily": settings.max_renewal_spend_usd,
            "cap_reached": daily_cap.is_cap_reached(),
        },
        "expiring_claims": {
            "within_7_days": len(expiring_7),
            "within_30_days": len(expiring_30),
        },
    }
