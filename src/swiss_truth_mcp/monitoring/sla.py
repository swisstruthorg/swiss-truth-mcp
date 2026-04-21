"""
SLA Monitoring — Phase 4 (Plan 04-02)

In-memory ring-buffer tracker for uptime, latency, and error rates.
Stores 24 hours of data in 5-minute buckets (288 buckets).

Usage:
    from swiss_truth_mcp.monitoring.sla import sla_tracker

    # Record a request (called by SLA middleware):
    sla_tracker.record(path_group="api", latency_ms=42.5, status_code=200)

    # Get current SLA status:
    status = sla_tracker.get_status()

    # Get 24h history:
    history = sla_tracker.get_history()
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from swiss_truth_mcp.config import settings

logger = logging.getLogger(__name__)

BUCKET_SECONDS = 300  # 5 minutes
MAX_BUCKETS = 288     # 24 hours


@dataclass
class _Bucket:
    """A 5-minute time bucket for SLA metrics."""
    timestamp: float = 0.0
    total_requests: int = 0
    error_count: int = 0       # 5xx responses
    client_errors: int = 0     # 4xx responses
    latencies: list[float] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return self.total_requests - self.error_count

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.error_count / self.total_requests * 100

    def percentile(self, p: float) -> float:
        """Calculate p-th percentile of latencies."""
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * p / 100)
        idx = min(idx, len(sorted_lat) - 1)
        return sorted_lat[idx]


class SLATracker:
    """
    In-memory SLA tracker with 5-minute ring buffer.

    Tracks:
    - Request count per path group (mcp, api, admin)
    - Latency distribution (p50, p95, p99)
    - Error rate (5xx)
    - Uptime percentage
    """

    def __init__(self) -> None:
        self._buckets: deque[_Bucket] = deque(maxlen=MAX_BUCKETS)
        self._current_bucket: _Bucket = _Bucket(timestamp=time.time())
        self._start_time: float = time.time()
        self._total_requests: int = 0
        self._total_errors: int = 0
        self._alerts: list[dict] = []  # Recent SLA violations

    def record(self, path_group: str, latency_ms: float, status_code: int) -> None:
        """Record a single request metric."""
        now = time.time()
        self._total_requests += 1

        # Rotate bucket if needed
        if now - self._current_bucket.timestamp >= BUCKET_SECONDS:
            self._buckets.append(self._current_bucket)
            self._current_bucket = _Bucket(timestamp=now)

        self._current_bucket.total_requests += 1
        self._current_bucket.latencies.append(latency_ms)

        if 500 <= status_code < 600:
            self._current_bucket.error_count += 1
            self._total_errors += 1
        elif 400 <= status_code < 500:
            self._current_bucket.client_errors += 1

        # Check SLA violations
        self._check_sla_violations(latency_ms, status_code)

    def _check_sla_violations(self, latency_ms: float, status_code: int) -> None:
        """Check for SLA violations and fire alerts."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # P95 latency violation (check every 100 requests)
        if self._current_bucket.total_requests % 100 == 0:
            p95 = self._current_bucket.percentile(95)
            if p95 > settings.sla_p95_latency_ms:
                alert = {
                    "type": "latency_violation",
                    "message": f"P95 latency {p95:.0f}ms exceeds target {settings.sla_p95_latency_ms}ms",
                    "value": round(p95, 1),
                    "target": settings.sla_p95_latency_ms,
                    "detected_at": now_iso,
                }
                self._alerts.append(alert)
                if len(self._alerts) > 100:
                    self._alerts = self._alerts[-50:]
                logger.warning("SLA VIOLATION: %s", alert["message"])
                self._fire_webhook_alert(alert)

        # Error rate violation (>1% in current bucket)
        if self._current_bucket.total_requests >= 10:
            error_rate = self._current_bucket.error_rate
            if error_rate > 5.0:  # >5% error rate
                alert = {
                    "type": "error_rate_violation",
                    "message": f"Error rate {error_rate:.1f}% exceeds 5% threshold",
                    "value": round(error_rate, 2),
                    "target": 5.0,
                    "detected_at": now_iso,
                }
                # Only alert once per bucket
                if not any(
                    a["type"] == "error_rate_violation"
                    and a["detected_at"][:16] == now_iso[:16]
                    for a in self._alerts[-5:]
                ):
                    self._alerts.append(alert)
                    logger.warning("SLA VIOLATION: %s", alert["message"])
                    self._fire_webhook_alert(alert)

    def _fire_webhook_alert(self, alert: dict) -> None:
        """Send alert to configured webhook (fire-and-forget)."""
        url = settings.sla_alert_webhook_url
        if not url:
            return
        try:
            # Synchronous fire-and-forget (non-blocking in practice)
            import threading
            def _send():
                try:
                    httpx.post(url, json=alert, timeout=5)
                except Exception:
                    pass
            threading.Thread(target=_send, daemon=True).start()
        except Exception:
            pass

    def get_status(self) -> dict:
        """Current SLA status summary."""
        all_buckets = list(self._buckets) + [self._current_bucket]
        # Only consider last 24h
        cutoff = time.time() - 86400
        recent = [b for b in all_buckets if b.timestamp >= cutoff]

        total_req = sum(b.total_requests for b in recent)
        total_err = sum(b.error_count for b in recent)
        all_latencies = []
        for b in recent:
            all_latencies.extend(b.latencies)

        uptime_seconds = time.time() - self._start_time
        # Uptime = (total - errors) / total * 100
        uptime_pct = ((total_req - total_err) / total_req * 100) if total_req > 0 else 100.0

        p50 = self._percentile(all_latencies, 50)
        p95 = self._percentile(all_latencies, 95)
        p99 = self._percentile(all_latencies, 99)

        error_rate = (total_err / total_req * 100) if total_req > 0 else 0.0

        return {
            "uptime_percentage": round(uptime_pct, 3),
            "uptime_target": settings.sla_uptime_target,
            "uptime_met": uptime_pct >= settings.sla_uptime_target,
            "latency": {
                "p50_ms": round(p50, 1),
                "p95_ms": round(p95, 1),
                "p99_ms": round(p99, 1),
                "target_p95_ms": settings.sla_p95_latency_ms,
                "p95_met": p95 <= settings.sla_p95_latency_ms,
            },
            "error_rate_percentage": round(error_rate, 3),
            "requests_24h": total_req,
            "errors_24h": total_err,
            "uptime_since": datetime.fromtimestamp(
                self._start_time, tz=timezone.utc
            ).isoformat(),
            "active_alerts": len([a for a in self._alerts[-20:]]),
        }

    def get_history(self) -> list[dict]:
        """24h history in 5-minute buckets."""
        all_buckets = list(self._buckets) + [self._current_bucket]
        cutoff = time.time() - 86400
        recent = [b for b in all_buckets if b.timestamp >= cutoff]

        return [
            {
                "timestamp": datetime.fromtimestamp(
                    b.timestamp, tz=timezone.utc
                ).isoformat(),
                "requests": b.total_requests,
                "errors": b.error_count,
                "client_errors": b.client_errors,
                "error_rate": round(b.error_rate, 2),
                "p50_ms": round(b.percentile(50), 1),
                "p95_ms": round(b.percentile(95), 1),
                "p99_ms": round(b.percentile(99), 1),
            }
            for b in recent
        ]

    def get_alerts(self) -> list[dict]:
        """Recent SLA violation alerts."""
        return list(reversed(self._alerts[-50:]))

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        sorted_v = sorted(values)
        idx = int(len(sorted_v) * p / 100)
        idx = min(idx, len(sorted_v) - 1)
        return sorted_v[idx]


# Module singleton
sla_tracker = SLATracker()
