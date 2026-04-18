"""
Täglicher API-Kosten-Cap für den Renewal Loop (SEC-05).

Akkumuliert Ausgaben pro Tag und pausiert neue Renewal-Jobs
wenn MAX_RENEWAL_SPEND_USD überschritten wird.

Verwendung:
    from swiss_truth_mcp.renewal.cost_cap import daily_cap, CapExceededError

    # Vor jedem Anthropic-API-Call im Renewal-Worker:
    daily_cap.check_cap_or_raise()

    # Nach dem API-Call, geschätzten Kosten addieren:
    daily_cap.record_spend(0.001)  # ~$0.001 pro Haiku-Call
"""
from __future__ import annotations

import asyncio
import logging

from swiss_truth_mcp.config import settings

logger = logging.getLogger(__name__)


class CapExceededError(Exception):
    """Wird geworfen wenn der tägliche API-Kosten-Cap überschritten ist."""


class DailySpendCap:
    """
    Thread-sicherer Tageskosten-Akkumulator für Claude API-Calls.

    - record_spend(usd): addiert Betrag zum Tagesverbrauch
    - is_cap_reached(): True wenn Verbrauch >= MAX_RENEWAL_SPEND_USD
    - check_cap_or_raise(): wirft CapExceededError wenn Cap erreicht
    - reset(): setzt Verbrauch auf 0.0 zurück (täglich durch APScheduler)
    """

    def __init__(self) -> None:
        self._spend: float = 0.0
        self._lock = asyncio.Lock()
        self._alert_fired: bool = False  # verhindert mehrfache Alerts pro Tag

    @property
    def current_spend(self) -> float:
        return self._spend

    def record_spend(self, usd_amount: float) -> None:
        """Addiert usd_amount zum Tagesverbrauch. Kann synchron aufgerufen werden."""
        self._spend += usd_amount
        if self.is_cap_reached() and not self._alert_fired:
            self._fire_alert()

    def is_cap_reached(self) -> bool:
        """True wenn Tagesverbrauch >= MAX_RENEWAL_SPEND_USD."""
        return self._spend >= settings.max_renewal_spend_usd

    def check_cap_or_raise(self) -> None:
        """
        Wirft CapExceededError wenn Cap erreicht ist.
        Muss vor jedem Anthropic-API-Call im Renewal-Worker aufgerufen werden.
        """
        if self.is_cap_reached():
            raise CapExceededError(
                f"Täglicher Renewal-API-Cap erreicht: "
                f"${self._spend:.4f} >= ${settings.max_renewal_spend_usd:.2f}. "
                "Renewal-Jobs pausiert bis Mitternacht UTC."
            )

    def reset(self) -> None:
        """Setzt Tagesverbrauch auf 0.0 zurück. Wird täglich durch APScheduler aufgerufen."""
        previous = self._spend
        self._spend = 0.0
        self._alert_fired = False
        if previous > 0:
            logger.info(
                "Tageskosten-Cap zurückgesetzt. Gestrige Ausgaben: $%.4f",
                previous,
            )

    def _fire_alert(self) -> None:
        """Einmaliger WARNING-Log beim Cap-Erreichen. Kein n8n-Call in Phase 1 (synchron)."""
        self._alert_fired = True
        logger.warning(
            "RENEWAL CAP ERREICHT: $%.4f >= $%.2f. "
            "Neue Renewal-Jobs werden pausiert bis Mitternacht UTC. "
            "Cap via MAX_RENEWAL_SPEND_USD konfigurierbar.",
            self._spend,
            settings.max_renewal_spend_usd,
        )


# Modul-Singleton — wird importiert von Renewal-Worker (Phase 5)
daily_cap = DailySpendCap()
