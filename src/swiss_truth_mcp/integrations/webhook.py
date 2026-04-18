"""
Webhook-Delivery für n8n und registrierte Subscriber.

fire_event()       — sendet an N8N_WEBHOOK_URL (interne Integration)
fire_subscribers() — sendet an alle in Neo4j gespeicherten Subscriptions

Events:
  claim.certified   — Claim wurde von Experte zertifiziert
  claim.rejected    — Claim wurde abgelehnt
  claim.submitted   — Neuer Claim eingereicht (peer_review)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

from swiss_truth_mcp.config import settings

logger = logging.getLogger(__name__)


EVENTS = {
    "claim.certified": "Ein Claim wurde zertifiziert",
    "claim.rejected":  "Ein Claim wurde abgelehnt",
    "claim.submitted": "Ein neuer Claim wurde eingereicht",
}


def _sign_body(body_bytes: bytes) -> str:
    """Berechnet HMAC-SHA256 Signatur für einen Webhook-Body.

    Returns: 'sha256=<hex>' — passt zum X-Signature Header-Format (GitHub-Konvention).
    """
    secret = settings.effective_webhook_secret.encode("utf-8")
    sig = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


async def fire_event(event: str, payload: dict[str, Any]) -> None:
    """
    Sendet ein Webhook-Event an die konfigurierte N8N_WEBHOOK_URL.
    Fehler werden geloggt, aber nie nach oben weitergegeben
    (fire-and-forget, non-blocking für den Caller).
    Jeder Request wird mit HMAC-SHA256 signiert (SEC-04).
    """
    url = settings.n8n_webhook_url.strip()
    if not url:
        return

    body = {
        "event": event,
        "description": EVENTS.get(event, event),
        "source": "swiss-truth-mcp",
        **payload,
    }

    # Deterministische Serialisierung für HMAC-Signatur (SEC-04)
    body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = _sign_body(body_bytes)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                content=body_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                },
            )
            if resp.status_code >= 400:
                logger.warning("Webhook %s → HTTP %d: %s", url, resp.status_code, resp.text[:200])
            else:
                logger.info("Webhook fired: %s → %d", event, resp.status_code)
    except httpx.RequestError as exc:
        logger.warning("Webhook delivery failed (%s): %s", event, exc)


async def fire_subscribers(event: str, claim: dict[str, Any]) -> None:
    """
    Sendet ein claim.certified-Event an alle registrierten Webhook-Subscriber.
    Filtert nach domain_filter wenn gesetzt. Fire-and-forget, nie blockierend.
    """
    # Lazy import um Zirkularimporte zu vermeiden
    from swiss_truth_mcp.db.neo4j_client import get_session
    from swiss_truth_mcp.db import queries
    from swiss_truth_mcp.validation.trust import now_iso

    try:
        async with get_session() as session:
            subs = await queries.list_webhook_subscriptions(
                session, domain_filter=claim.get("domain_id")
            )
    except Exception as exc:
        logger.warning("Could not fetch webhook subscriptions: %s", exc)
        return

    if not subs:
        return

    body = {
        "event":  event,
        "source": "swiss-truth-mcp",
        "timestamp": now_iso(),
        "claim": {
            "id":               claim.get("id"),
            "text":             claim.get("text"),
            "domain_id":        claim.get("domain_id"),
            "confidence_score": claim.get("confidence_score"),
            "hash_sha256":      claim.get("hash_sha256"),
            "last_reviewed":    claim.get("last_reviewed"),
            "source_references": claim.get("source_references", []),
            "language":         claim.get("language"),
        },
        "mcp_endpoint": "https://swisstruth.org/mcp",
        "feed_url":     "https://swisstruth.org/feed.rss",
    }

    # Deterministische Serialisierung für HMAC-Signatur (SEC-04)
    body_bytes = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = _sign_body(body_bytes)

    async with httpx.AsyncClient(timeout=8.0) as client:
        for sub in subs:
            try:
                resp = await client.post(
                    sub["url"],
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Signature": signature,
                    },
                )
                logger.info("Subscriber [%s] %s → %d", sub.get("label", "?"), sub["url"][:60], resp.status_code)
            except httpx.RequestError as exc:
                logger.warning("Subscriber delivery failed [%s]: %s", sub.get("label", "?"), exc)
