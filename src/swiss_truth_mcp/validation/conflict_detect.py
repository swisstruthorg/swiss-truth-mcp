"""
Advanced Conflict Detection (Plan 03-05)

Finds existing certified claims that semantically conflict with a given claim.
Uses vector similarity + Claude Haiku semantic comparison for explanation.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from neo4j import AsyncSession

from swiss_truth_mcp.db.queries import find_conflicting_claims

logger = logging.getLogger(__name__)

# Threshold for potential conflict/duplicate
CONFLICT_THRESHOLD = 0.93


async def detect_conflicts(
    session: AsyncSession,
    embedding: list[float],
    claim_text: str,
) -> list[dict]:
    """
    Returns a list of potentially conflicting claims.
    Similarity >= CONFLICT_THRESHOLD means: very similar statement already exists.
    """
    candidates = await find_conflicting_claims(session, embedding, CONFLICT_THRESHOLD)
    return candidates


async def detect_conflicts_with_explanation(
    session: AsyncSession,
    embedding: list[float],
    claim_text: str,
    threshold: float = 0.85,
) -> dict[str, Any]:
    """
    Advanced conflict detection with AI-generated explanations.

    Finds semantically similar certified claims, then uses Claude to determine
    if they support, contradict, or are unrelated — with explanations.

    Returns:
        Dict with conflicts list, each containing explanation and confidence.
    """
    from swiss_truth_mcp.validation.pre_screen import compare_claims

    candidates = await find_conflicting_claims(session, embedding, threshold)

    if not candidates:
        return {
            "conflicts": [],
            "total": 0,
            "checked_claim": claim_text,
            "message": "No similar claims found in the knowledge base.",
        }

    # Compare each candidate semantically (parallel, max 5)
    async def _check(c: dict) -> Optional[dict]:
        try:
            comparison = await compare_claims(submitted=claim_text, certified=c["text"])
            relation = comparison.get("relation", "unrelated")
            return {
                "certified_claim_id": c["id"],
                "certified_claim_text": c["text"],
                "confidence_score": c.get("confidence_score", 0.0),
                "similarity": round(c.get("similarity", 0.0), 3),
                "relation": relation,
                "comparison_confidence": comparison.get("confidence", 0.0),
                "explanation": comparison.get("explanation", ""),
            }
        except Exception as e:
            logger.warning("Conflict check failed for %s: %s", c.get("id"), e)
            return None

    results = await asyncio.gather(*[_check(c) for c in candidates[:5]])
    all_results = [r for r in results if r is not None]

    # Separate by relation type
    contradictions = [r for r in all_results if r["relation"] == "contradicts"]
    supports = [r for r in all_results if r["relation"] == "supports"]
    unrelated = [r for r in all_results if r["relation"] == "unrelated"]

    # Sort contradictions by confidence
    contradictions.sort(key=lambda x: x["comparison_confidence"], reverse=True)

    return {
        "conflicts": contradictions,
        "supports": supports,
        "unrelated_count": len(unrelated),
        "total_checked": len(all_results),
        "checked_claim": claim_text,
        "has_contradictions": len(contradictions) > 0,
        "has_duplicates": any(r["similarity"] >= 0.95 for r in supports),
        "message": (
            f"Found {len(contradictions)} contradiction(s) and {len(supports)} supporting claim(s)."
            if contradictions or supports
            else "No conflicts or duplicates found."
        ),
    }


async def get_all_conflicts(session: AsyncSession) -> list[dict[str, Any]]:
    """
    Scan all certified claims for internal conflicts.
    Returns pairs of claims that may contradict each other.

    Note: This is expensive — should be run as a batch job, not on every request.
    """
    result = await session.run(
        """
        MATCH (c1:Claim {status: 'certified'})-[r:CONFLICTS_WITH]->(c2:Claim {status: 'certified'})
        RETURN c1.id AS claim1_id, c1.text AS claim1_text, c1.domain_id AS claim1_domain,
               c2.id AS claim2_id, c2.text AS claim2_text, c2.domain_id AS claim2_domain,
               r.confidence AS confidence, r.explanation AS explanation,
               r.detected_at AS detected_at
        ORDER BY r.confidence DESC
        LIMIT 100
        """
    )
    rows = await result.data()
    return rows


async def record_conflict(
    session: AsyncSession,
    claim1_id: str,
    claim2_id: str,
    confidence: float,
    explanation: str,
) -> None:
    """Record a detected conflict between two claims in Neo4j."""
    from swiss_truth_mcp.validation.trust import now_iso
    await session.run(
        """
        MATCH (c1:Claim {id: $id1}), (c2:Claim {id: $id2})
        MERGE (c1)-[r:CONFLICTS_WITH]->(c2)
        SET r.confidence = $confidence,
            r.explanation = $explanation,
            r.detected_at = $detected_at,
            r.status = 'open'
        """,
        {
            "id1": claim1_id,
            "id2": claim2_id,
            "confidence": confidence,
            "explanation": explanation,
            "detected_at": now_iso(),
        },
    )
