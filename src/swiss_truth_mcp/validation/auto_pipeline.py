"""
Automated Fact-Check Pipeline — Phase 5 (Plan 05-05)

Full pipeline: submit → pre-screen → AI verify → human review queue.
Human-in-the-loop only when AI confidence < 0.7.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.validation.source_scoring import score_url, compute_weighted_confidence

logger = logging.getLogger(__name__)

# Confidence threshold: above this → auto-certify, below → human review
AUTO_CERTIFY_THRESHOLD = 0.70


async def auto_verify_claim(
    claim_text: str,
    domain_id: str,
    source_urls: list[str],
    question: str = "",
    submitter: str = "auto-pipeline",
) -> dict[str, Any]:
    """
    Full automated fact-check pipeline:
    1. Pre-screen claim quality
    2. Score sources
    3. AI verification against existing knowledge
    4. Auto-certify if confidence >= threshold, else queue for human review

    Returns pipeline result with status and claim data.
    """
    now = datetime.now(timezone.utc)
    claim_id = str(uuid.uuid4())

    # Step 1: Pre-screen
    pre_screen_result = await _pre_screen(claim_text, domain_id)
    if pre_screen_result.get("rejected"):
        return {
            "pipeline_status": "rejected",
            "reason": pre_screen_result.get("reason", "Failed pre-screening"),
            "claim_id": None,
            "step": "pre_screen",
        }

    # Step 2: Score sources
    source_scores = [score_url(url) for url in source_urls]
    avg_source_quality = (
        sum(s["score"] for s in source_scores) / len(source_scores)
        if source_scores else 0.5
    )

    # Step 3: AI verification
    ai_result = await _ai_verify(claim_text, domain_id)
    ai_confidence = ai_result.get("confidence", 0.5)

    # Step 4: Compute final confidence with source weighting
    final_confidence = compute_weighted_confidence(
        ai_confidence,
        [s["score"] for s in source_scores],
        weight=0.15,
    )

    # Step 5: Create claim in DB
    claim_hash = hashlib.sha256(claim_text.encode()).hexdigest()
    from swiss_truth_mcp.embeddings import embed_text
    embedding = await embed_text(claim_text)

    expiry = datetime(now.year + 1, now.month, now.day, tzinfo=timezone.utc)

    # Decide status based on confidence
    if final_confidence >= AUTO_CERTIFY_THRESHOLD:
        status = "certified"
        pipeline_status = "auto_certified"
    else:
        status = "peer_review"
        pipeline_status = "queued_for_review"

    claim_data = {
        "id": claim_id,
        "text": claim_text,
        "question": question,
        "domain_id": domain_id,
        "confidence_score": final_confidence,
        "status": status,
        "language": pre_screen_result.get("language", "en"),
        "hash_sha256": claim_hash,
        "created_at": now.isoformat(),
        "last_reviewed": now.isoformat(),
        "expires_at": expiry.isoformat(),
        "embedding": embedding,
        "source_urls": source_urls,
    }

    async with get_session() as session:
        await queries.create_claim(session, claim_data)

        # If auto-certified, create validation record
        if status == "certified":
            await queries.validate_claim(
                session,
                claim_id=claim_id,
                expert_name="Auto-Pipeline",
                expert_institution="Swiss Truth AI",
                verdict="approved",
                confidence_score=final_confidence,
                reviewed_at=now.isoformat(),
            )

    logger.info(
        "Pipeline %s: claim=%s confidence=%.3f status=%s",
        pipeline_status, claim_id[:8], final_confidence, status,
    )

    return {
        "pipeline_status": pipeline_status,
        "claim_id": claim_id,
        "confidence": final_confidence,
        "ai_confidence": ai_confidence,
        "source_quality": round(avg_source_quality, 3),
        "status": status,
        "threshold": AUTO_CERTIFY_THRESHOLD,
        "source_analysis": source_scores,
        "pre_screen": pre_screen_result,
    }


async def _pre_screen(claim_text: str, domain_id: str) -> dict:
    """Quick quality check on claim text."""
    # Basic checks
    if len(claim_text) < 20:
        return {"rejected": True, "reason": "Claim too short (min 20 chars)"}
    if len(claim_text) > 2000:
        return {"rejected": True, "reason": "Claim too long (max 2000 chars)"}

    # Try AI pre-screen if available
    try:
        from swiss_truth_mcp.validation.pre_screen import pre_screen_claim
        result = await pre_screen_claim(claim_text, domain_id)
        return {
            "rejected": not result.get("pass", True),
            "reason": result.get("reason", ""),
            "language": result.get("language", "en"),
            "quality_score": result.get("quality_score", 0.5),
        }
    except Exception as e:
        logger.warning("Pre-screen AI failed, using basic checks: %s", e)
        return {"rejected": False, "language": "en", "quality_score": 0.5}


async def _ai_verify(claim_text: str, domain_id: str) -> dict:
    """AI verification against existing knowledge base."""
    try:
        from swiss_truth_mcp.embeddings import embed_text
        embedding = await embed_text(claim_text)

        async with get_session() as session:
            # Search for similar certified claims
            similar = await queries.search_claims(
                session,
                query_embedding=embedding,
                query_text=claim_text,
                domain_id=domain_id,
                min_confidence=0.7,
                limit=5,
            )

        if not similar:
            return {"confidence": 0.5, "verdict": "unknown", "evidence": []}

        # Check if any similar claim supports or contradicts
        max_similarity = max(c.get("vector_score", 0) for c in similar)
        avg_confidence = sum(c.get("confidence_score", 0) for c in similar) / len(similar)

        if max_similarity > 0.95:
            return {
                "confidence": min(0.95, avg_confidence),
                "verdict": "supported",
                "evidence": [c["id"] for c in similar[:3]],
            }
        elif max_similarity > 0.85:
            return {
                "confidence": min(0.80, avg_confidence * 0.9),
                "verdict": "partially_supported",
                "evidence": [c["id"] for c in similar[:3]],
            }
        else:
            return {
                "confidence": 0.5,
                "verdict": "insufficient_evidence",
                "evidence": [],
            }
    except Exception as e:
        logger.warning("AI verify failed: %s", e)
        return {"confidence": 0.5, "verdict": "error", "evidence": []}
