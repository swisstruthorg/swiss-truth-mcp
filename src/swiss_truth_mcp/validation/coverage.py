"""
Coverage Analysis per Domain (Plan 03-04)

Analyzes which topics within a domain are covered by certified claims
and identifies knowledge gaps.

Usage:
    from swiss_truth_mcp.validation.coverage import analyze_coverage
    report = await analyze_coverage("swiss-health")
"""
from __future__ import annotations

import logging
from typing import Any

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

logger = logging.getLogger(__name__)


def _get_domain_topics() -> dict[str, dict[str, Any]]:
    """Load domain definitions from the generator config."""
    try:
        from swiss_truth_mcp.seed.generator import DOMAINS
        return DOMAINS
    except ImportError:
        return {}


def _topic_covered(topic: str, claim_texts: list[str]) -> bool:
    """Check if a topic is covered by any claim text (keyword matching)."""
    topic_lower = topic.lower()
    # Extract key terms from topic (split on common separators)
    key_terms = []
    for part in topic_lower.replace("—", " ").replace("–", " ").replace("/", " ").split():
        cleaned = part.strip("().,;:\"'")
        if len(cleaned) >= 3 and cleaned not in {
            "und", "der", "die", "das", "von", "für", "mit", "the", "and",
            "for", "with", "from", "into", "over", "via", "etc", "e.g.",
        }:
            key_terms.append(cleaned)

    if not key_terms:
        return False

    # A topic is "covered" if at least 40% of its key terms appear in any claim
    threshold = max(1, int(len(key_terms) * 0.4))

    for text in claim_texts:
        matches = sum(1 for term in key_terms if term in text)
        if matches >= threshold:
            return True

    return False


async def analyze_coverage(domain_id: str) -> dict[str, Any]:
    """
    Analyze topic coverage for a domain.

    Returns:
        Dict with coverage_rate, covered_topics, gaps, and per-topic details
    """
    domains = _get_domain_topics()
    domain_config = domains.get(domain_id)

    if not domain_config:
        return {
            "domain_id": domain_id,
            "error": f"Domain '{domain_id}' not found in generator config",
            "coverage_rate": 0.0,
            "topics": [],
            "gaps": [],
        }

    topics = domain_config.get("topics", [])
    if not topics:
        return {
            "domain_id": domain_id,
            "domain_name": domain_config.get("name", ""),
            "coverage_rate": 1.0,
            "message": "No topics defined for this domain",
            "topics": [],
            "gaps": [],
        }

    # Fetch all claim texts for this domain
    async with get_session() as session:
        claim_texts = await queries.get_claim_texts_by_domain(session, domain_id)

    if not claim_texts:
        return {
            "domain_id": domain_id,
            "domain_name": domain_config.get("name", ""),
            "total_topics": len(topics),
            "covered": 0,
            "gaps_count": len(topics),
            "coverage_rate": 0.0,
            "certified_claims": 0,
            "topics": [{"topic": t, "covered": False} for t in topics],
            "gaps": topics,
        }

    # Check each topic
    topic_results = []
    covered_topics = []
    gaps = []

    for topic in topics:
        is_covered = _topic_covered(topic, claim_texts)
        topic_results.append({"topic": topic, "covered": is_covered})
        if is_covered:
            covered_topics.append(topic)
        else:
            gaps.append(topic)

    coverage_rate = round(len(covered_topics) / len(topics), 4) if topics else 0.0

    return {
        "domain_id": domain_id,
        "domain_name": domain_config.get("name", ""),
        "total_topics": len(topics),
        "covered": len(covered_topics),
        "gaps_count": len(gaps),
        "coverage_rate": coverage_rate,
        "certified_claims": len(claim_texts),
        "quality": (
            "excellent" if coverage_rate >= 0.9
            else "good" if coverage_rate >= 0.7
            else "moderate" if coverage_rate >= 0.5
            else "low"
        ),
        "topics": topic_results,
        "gaps": gaps,
        "covered_topics": covered_topics,
    }


async def analyze_all_domains() -> dict[str, Any]:
    """Analyze coverage across all domains."""
    domains = _get_domain_topics()
    results = []

    for domain_id in sorted(domains.keys()):
        report = await analyze_coverage(domain_id)
        results.append({
            "domain_id": domain_id,
            "domain_name": report.get("domain_name", ""),
            "coverage_rate": report.get("coverage_rate", 0.0),
            "total_topics": report.get("total_topics", 0),
            "covered": report.get("covered", 0),
            "gaps_count": report.get("gaps_count", 0),
            "certified_claims": report.get("certified_claims", 0),
            "quality": report.get("quality", "unknown"),
        })

    total_topics = sum(r["total_topics"] for r in results)
    total_covered = sum(r["covered"] for r in results)
    avg_coverage = round(total_covered / total_topics, 4) if total_topics else 0.0

    return {
        "total_domains": len(results),
        "average_coverage": avg_coverage,
        "total_topics": total_topics,
        "total_covered": total_covered,
        "total_gaps": total_topics - total_covered,
        "domains": results,
    }
