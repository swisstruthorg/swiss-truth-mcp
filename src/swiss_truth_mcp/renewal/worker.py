"""
Automated Renewal Worker (Plan 03-01)

Daily job that re-verifies expiring claims via Claude Haiku.
Respects the daily API cost cap (SEC-05).

Usage:
    # Called automatically by APScheduler at 03:00 UTC
    from swiss_truth_mcp.renewal.worker import run_renewal_batch
    result = await run_renewal_batch()
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.renewal.cost_cap import daily_cap, CapExceededError
from swiss_truth_mcp.validation.trust import (
    sign_claim, now_iso, expiry_iso, decay_confidence,
)

logger = logging.getLogger(__name__)

# Cost estimate per Claude Haiku call (conservative)
_HAIKU_COST_PER_CALL = 0.0015  # ~$0.0015 per call

_REVERIFY_SYSTEM = """You are a fact verification expert. Given a previously certified claim
and its source URLs, determine if the claim is still accurate and current.

Return ONLY valid JSON:
{
  "still_valid": true/false,
  "confidence": 0.90-0.99,
  "reason": "Brief explanation (1-2 sentences)"
}

Rules:
- If the claim states a fact that is timeless or still current, mark still_valid=true
- If the claim references outdated data, mark still_valid=false
- Confidence should reflect how certain you are about the claim's current accuracy
- Be conservative: when in doubt, mark still_valid=true with lower confidence"""


async def _reverify_claim(claim: dict) -> dict[str, Any]:
    """Re-verify a single claim using Claude Haiku."""
    from swiss_truth_mcp.validation.pre_screen import _get_sdk_client
    import json

    client = _get_sdk_client()
    sources = claim.get("source_references", [])
    source_text = "\n".join(f"- {s}" for s in sources[:3]) if sources else "No sources"

    user_msg = (
        f"Claim: {claim['text']}\n"
        f"Domain: {claim.get('domain_id', 'unknown')}\n"
        f"Sources:\n{source_text}\n"
        f"Last reviewed: {claim.get('last_reviewed', 'unknown')}"
    )

    msg = await client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        system=_REVERIFY_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = msg.content[0].text.strip()
    # Parse JSON (handle code fences)
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) >= 3 else parts[-1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        result = {"still_valid": True, "confidence": 0.85, "reason": "Parse error — defaulting to valid"}

    return result


async def run_renewal_batch(
    max_claims: int = 20,
    lookahead_days: int = 30,
) -> dict[str, Any]:
    """
    Process expiring claims: re-verify via AI and renew if still valid.

    Args:
        max_claims: Maximum claims to process per batch (default 20)
        lookahead_days: Renew claims expiring within this many days

    Returns:
        Summary dict with renewed/skipped/failed counts
    """
    from datetime import datetime, timezone

    now = now_iso()
    cutoff = expiry_iso(days=lookahead_days)

    renewed = 0
    skipped = 0
    failed = 0
    cap_hit = False

    async with get_session() as session:
        # First: expire any already-past claims
        expired = await queries.expire_outdated_claims(session, now)
        if expired:
            logger.info("Expired %d outdated claims", len(expired))

        # Then: find claims expiring soon
        expiring = await queries.list_expiring_soon(session, now, cutoff, limit=max_claims)

    if not expiring:
        logger.info("No claims expiring within %d days", lookahead_days)
        return {"renewed": 0, "skipped": 0, "failed": 0, "expired": len(expired) if expired else 0}

    logger.info("Found %d claims expiring within %d days", len(expiring), lookahead_days)

    for claim in expiring:
        # Check cost cap before each API call
        try:
            daily_cap.check_cap_or_raise()
        except CapExceededError:
            logger.warning("Daily cost cap reached — stopping renewal batch")
            cap_hit = True
            skipped += len(expiring) - (renewed + failed + skipped)
            break

        try:
            # Re-verify via Claude
            result = await _reverify_claim(claim)
            daily_cap.record_spend(_HAIKU_COST_PER_CALL)

            if result.get("still_valid", False):
                confidence = min(result.get("confidence", 0.90), 0.99)
                new_hash = sign_claim(claim)
                reviewed_at = now_iso()
                new_expiry = expiry_iso(days=365)

                async with get_session() as session:
                    await queries.renew_claim(
                        session=session,
                        claim_id=claim["id"],
                        expert_name="AI Renewal Agent",
                        expert_institution="Swiss Truth Automated Renewal",
                        confidence_score=confidence,
                        new_hash=new_hash,
                        reviewed_at=reviewed_at,
                        new_expiry=new_expiry,
                    )
                renewed += 1
                logger.debug("Renewed claim %s (confidence: %.2f)", claim["id"], confidence)
            else:
                skipped += 1
                logger.info(
                    "Claim %s not renewed: %s",
                    claim["id"], result.get("reason", "no longer valid"),
                )
        except Exception as e:
            failed += 1
            logger.error("Failed to renew claim %s: %s", claim["id"], e)

    return {
        "renewed": renewed,
        "skipped": skipped,
        "failed": failed,
        "expired": len(expired) if expired else 0,
        "cap_hit": cap_hit,
        "spend_today": round(daily_cap.current_spend, 4),
    }
