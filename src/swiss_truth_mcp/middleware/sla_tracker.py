"""
SLA Tracking ASGI Middleware — Phase 4 (Plan 04-02)

Captures request latency and status codes for every HTTP request,
feeding them into the SLA ring-buffer tracker.

Inserted between RateLimitMiddleware and the inner app.
"""
from __future__ import annotations

import time

from starlette.types import ASGIApp, Receive, Scope, Send

from swiss_truth_mcp.monitoring.sla import sla_tracker

# Path prefixes → group names for SLA bucketing
_GROUP_MAP = [
    ("/mcp", "mcp"),
    ("/admin/", "admin"),
    ("/api/", "api"),
    ("/static/", "static"),
]

_SKIP_PREFIXES = ("/static/", "/favicon.ico")


def _path_group(path: str) -> str:
    """Classify a request path into a monitoring group."""
    for prefix, group in _GROUP_MAP:
        if path.startswith(prefix):
            return group
    return "other"


class SLATrackerMiddleware:
    """
    ASGI middleware that measures request latency and records it
    in the SLA tracker singleton.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Skip static assets
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        group = _path_group(path)
        start = time.perf_counter()
        status_code = 200  # default

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            status_code = 500
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            sla_tracker.record(
                path_group=group,
                latency_ms=latency_ms,
                status_code=status_code,
            )
