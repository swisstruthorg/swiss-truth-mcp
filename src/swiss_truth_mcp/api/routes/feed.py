"""
RSS Feed + Webhook-Subscription API — öffentlich, kein Login erforderlich.

GET  /feed.rss                  — RSS 2.0 Feed (neueste certified Claims)
POST /webhooks                  — Webhook-URL registrieren
DELETE /webhooks/{id}?token=... — Abmelden
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any, Optional
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, HttpUrl

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.validation.trust import now_iso
from swiss_truth_mcp.validation.ssrf import validate_webhook_url

router = APIRouter(tags=["feed"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_to_rfc2822(iso_str: str | None) -> str:
    if not iso_str:
        return format_datetime(datetime.now(timezone.utc))
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return format_datetime(dt.astimezone(timezone.utc))
    except Exception:
        return format_datetime(datetime.now(timezone.utc))


def _build_rss(claims: list[dict[str, Any]]) -> str:
    build_date = _iso_to_rfc2822(now_iso())

    items: list[str] = []
    for c in claims:
        text = c.get("text") or ""
        title = escape(text[:120] + ("…" if len(text) > 120 else ""))
        domain_name = escape(c.get("domain_name") or c.get("domain_id") or "")
        conf = c.get("confidence_score", 0)
        sources = c.get("source_references") or []
        source_line = escape(", ".join(str(s) for s in sources[:3]))

        desc_parts = [f"Domain: {domain_name}", f"Confidence: {conf:.0%}"]
        if source_line:
            desc_parts.append(f"Sources: {source_line}")
        description = escape(" | ".join(desc_parts))

        pub_date = _iso_to_rfc2822(c.get("last_reviewed"))
        guid = escape(c.get("hash_sha256") or c.get("id") or "")
        claim_id = escape(c.get("id") or "")
        domain_id = escape(c.get("domain_id") or "")

        items.append(f"""  <item>
    <title>{title}</title>
    <description>{description}</description>
    <link>https://swisstruth.org/trust#{claim_id}</link>
    <guid isPermaLink="false">{guid}</guid>
    <pubDate>{pub_date}</pubDate>
    <category>{domain_id}</category>
  </item>""")

    items_xml = "\n".join(items)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Swiss Truth — Certified Claims</title>
    <link>https://swisstruth.org/trust</link>
    <description>Latest certified, source-backed facts from the Swiss Truth knowledge base for AI agents.</description>
    <language>de</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="https://swisstruth.org/feed.rss" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>"""


# ---------------------------------------------------------------------------
# RSS Feed
# ---------------------------------------------------------------------------

@router.get("/feed.rss", include_in_schema=False)
async def rss_feed(
    domain: Optional[str] = Query(default=None, description="Filter by domain ID"),
    limit:  int           = Query(default=50, le=100),
):
    """RSS 2.0 Feed — neueste zertifizierte Claims. Optional nach Domain filtern."""
    async with get_session() as session:
        claims = await queries.get_feed_claims(session, limit=limit)

    if domain:
        claims = [c for c in claims if c.get("domain_id") == domain]

    xml = _build_rss(claims)
    return Response(
        content=xml.encode("utf-8"),
        media_type="application/rss+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


# ---------------------------------------------------------------------------
# Webhook Subscribe / Unsubscribe
# ---------------------------------------------------------------------------

class WebhookSubscribeRequest(BaseModel):
    url:    HttpUrl
    label:  str = ""
    domain: Optional[str] = None  # Domain-Filter, z.B. "swiss-health"


@router.post("/webhooks", status_code=201)
async def subscribe_webhook(body: WebhookSubscribeRequest):
    """
    Webhook-URL registrieren. Liefert {id, token} — token wird für Unsubscribe benötigt.
    Bei jedem neuen certified Claim wird ein POST mit dem vollen Claim-Objekt gesendet.

    Payload-Format:
    {
      "event": "claim.certified",
      "source": "swiss-truth-mcp",
      "timestamp": "...",
      "claim": { "id", "text", "domain_id", "confidence_score", "hash_sha256", ... },
      "mcp_endpoint": "https://swisstruth.org/mcp"
    }
    """
    # SSRF-Schutz: URL gegen private IP-Ranges prüfen (SEC-03)
    try:
        validate_webhook_url(str(body.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    sub_id = str(uuid.uuid4())
    token  = str(uuid.uuid4())
    sub = {
        "id":            sub_id,
        "url":           str(body.url),
        "label":         body.label.strip() or "unnamed",
        "domain_filter": body.domain or None,
        "token":         token,
        "created_at":    now_iso(),
    }
    async with get_session() as session:
        await queries.create_webhook_subscription(session, sub)

    return {
        "id":              sub_id,
        "token":           token,
        "subscribed_to":   str(body.url),
        "domain_filter":   body.domain,
        "unsubscribe_url": f"https://swisstruth.org/webhooks/{sub_id}?token={token}",
        "message":         "Subscribed. Store the token — it is required to unsubscribe.",
    }


@router.delete("/webhooks/{sub_id}")
async def unsubscribe_webhook(sub_id: str, token: str = Query(...)):
    """Webhook-Subscription anhand von ID + Token entfernen."""
    async with get_session() as session:
        deleted = await queries.delete_webhook_subscription(session, sub_id, token)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subscription not found or invalid token.")
    return {"message": "Unsubscribed successfully."}
