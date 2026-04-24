"""Dashboard — Live-Statistiken der Knowledge Base."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from swiss_truth_mcp.auth.dependencies import require_user
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user=Depends(require_user)):
    async with get_session() as session:
        stats = await queries.get_dashboard_stats(session)
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"request": request, "s": stats, "active": "dashboard", "current_user": user, "renewal_count": 0},
    )


@router.get("/coverage", response_class=HTMLResponse)
async def coverage(request: Request, user=Depends(require_user)):
    from swiss_truth_mcp.seed.generator import DOMAINS

    coverage_data = []
    async with get_session() as session:
        for domain_id, domain_info in DOMAINS.items():
            texts = await queries.get_claim_texts_by_domain(session, domain_id)
            topics = domain_info.get("topics", [])

            topic_coverage = []
            for topic in topics:
                # Erste 2 bedeutsamen Wörter (>3 Zeichen) als Keywords
                keywords = [w.lower() for w in topic.split() if len(w) > 3][:2]
                covered = bool(keywords) and any(
                    all(kw in text for kw in keywords)
                    for text in texts
                )
                topic_coverage.append({"topic": topic, "covered": covered})

            covered_count = sum(1 for t in topic_coverage if t["covered"])
            total_topics = len(topics)
            pct = round(covered_count / total_topics * 100) if total_topics else 0

            coverage_data.append({
                "id": domain_id,
                "name": domain_info["name"],
                "certified": len(texts),
                "topics": topic_coverage,
                "covered_topics": covered_count,
                "total_topics": total_topics,
                "coverage_pct": pct,
            })

    # Schlechteste Coverage zuerst
    coverage_data.sort(key=lambda x: x["coverage_pct"])

    return templates.TemplateResponse(
        request, "coverage.html",
        {"request": request, "active": "coverage", "current_user": user,
         "renewal_count": 0, "domains": coverage_data},
    )


@router.get("/analytics", response_class=HTMLResponse)
async def analytics(request: Request, user=Depends(require_user)):
    from swiss_truth_mcp.agent.feedback import get_feedback_stats
    from swiss_truth_mcp.monitoring.sla import sla_tracker

    async with get_session() as session:
        data = await queries.get_query_analytics(session)
        feedback = await get_feedback_stats(session)

    sla = sla_tracker.get_status()

    return templates.TemplateResponse(
        request, "analytics.html",
        {"request": request, "active": "analytics", "current_user": user,
         "renewal_count": 0, "a": data, "fb": feedback, "sla": sla},
    )
