"""
Trust Layer — SHA256-Hashing und Integritätsprüfung für Claims.

Jeder Claim erhält beim Erstellen einen Hash über seinen kanonischen Inhalt.
Dadurch ist jede nachträgliche Änderung nachweisbar (tamper-evident).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


def _canonical(claim: dict) -> str:
    """Erstellt eine deterministische JSON-Repräsentation (sortierte Keys, ohne embedding)."""
    fields = {
        "id": claim.get("id", ""),
        "text": claim.get("text", ""),
        "domain_id": claim.get("domain_id", ""),
        "language": claim.get("language", "de"),
        "source_urls": sorted(claim.get("source_urls", [])),
    }
    return json.dumps(fields, ensure_ascii=False, sort_keys=True)


def sign_claim(claim: dict) -> str:
    """Berechnet SHA256-Hash über den kanonischen Claim-Inhalt."""
    canonical = _canonical(claim)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_claim(claim: dict, stored_hash: str) -> bool:
    """Prüft ob der gespeicherte Hash mit dem aktuellen Inhalt übereinstimmt."""
    return sign_claim(claim) == stored_hash


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def expiry_iso(days: int = 365) -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def decay_confidence(
    base: float,
    last_reviewed_iso: str | None,
    decay_per_month: float = 0.01,
    min_confidence: float = 0.50,
) -> float:
    """
    Berechnet die aktuelle Konfidenz unter Berücksichtigung des Alters.

    Sinkt um decay_per_month (Standard 1%) pro Monat seit letztem Review.
    Minimum: min_confidence (Standard 0.50) — ein Claim wird nie wertlos,
    er muss aber erneuert werden.

    Beispiel: base=0.97, 18 Monate alt → 0.97 − 0.18 = 0.79
    """
    if not last_reviewed_iso:
        return base
    try:
        from datetime import timedelta
        reviewed = datetime.fromisoformat(last_reviewed_iso.replace("Z", "+00:00"))
        months_elapsed = (datetime.now(timezone.utc) - reviewed).days / 30.44
        decayed = base - (decay_per_month * months_elapsed)
        return round(max(min_confidence, decayed), 4)
    except Exception:
        return base
