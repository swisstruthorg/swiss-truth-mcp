"""
SLA Monitoring Admin Endpoints — Phase 4 (Plan 04-02)

Endpoints:
- GET /admin/sla/status   — Current SLA status (uptime, latency, error rate)
- GET /admin/sla/history  — 24h history in 5-minute buckets
- GET /admin/sla/alerts   — Active SLA violation alerts
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.monitoring.sla import sla_tracker

router = APIRouter(prefix="/admin/sla", tags=["monitoring"])


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def sla_status(auth=Depends(_require_admin)):
    """
    Current SLA status summary.

    Returns:
    - Uptime percentage (24h) vs target
    - Latency percentiles (p50, p95, p99) vs target
    - Error rate
    - Request count (24h)
    - Active alert count
    """
    status = sla_tracker.get_status()
    return {
        "sla": status,
        "targets": {
            "uptime_percentage": settings.sla_uptime_target,
            "p95_latency_ms": settings.sla_p95_latency_ms,
            "max_error_rate_percentage": 5.0,
        },
        "overall_healthy": (
            status["uptime_met"]
            and status["latency"]["p95_met"]
            and status["error_rate_percentage"] < 5.0
        ),
    }


@router.get("/history")
async def sla_history(auth=Depends(_require_admin)):
    """
    24-hour SLA history in 5-minute buckets.

    Each bucket contains: timestamp, request count, error count,
    error rate, and latency percentiles (p50, p95, p99).
    """
    history = sla_tracker.get_history()
    return {
        "bucket_size_seconds": 300,
        "total_buckets": len(history),
        "buckets": history,
    }


@router.get("/alerts")
async def sla_alerts(auth=Depends(_require_admin)):
    """
    Recent SLA violation alerts (last 50).

    Alert types:
    - latency_violation: P95 latency exceeds target
    - error_rate_violation: Error rate exceeds 5%
    """
    alerts = sla_tracker.get_alerts()
    return {
        "total": len(alerts),
        "alerts": alerts,
        "webhook_configured": bool(settings.sla_alert_webhook_url),
    }
