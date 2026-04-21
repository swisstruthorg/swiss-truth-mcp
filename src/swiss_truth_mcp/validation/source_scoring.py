"""
Source Quality Scoring — Phase 5 (Plan 05-05)

Scores sources based on domain reputation, citation count, and known-reliable lists.
Feeds into claim confidence calculation.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlparse

from neo4j import AsyncSession

logger = logging.getLogger(__name__)

# Known reliable source domains (curated list)
RELIABLE_DOMAINS = {
    # Government
    "admin.ch": 0.95,
    "fedlex.admin.ch": 0.98,
    "bag.admin.ch": 0.95,
    "bfs.admin.ch": 0.95,
    "parlament.ch": 0.93,
    "europa.eu": 0.92,
    "gov.uk": 0.90,
    "whitehouse.gov": 0.88,
    # Academic / Research
    "arxiv.org": 0.90,
    "pubmed.ncbi.nlm.nih.gov": 0.93,
    "nature.com": 0.95,
    "science.org": 0.95,
    "thelancet.com": 0.94,
    "nejm.org": 0.95,
    "ieee.org": 0.90,
    "acm.org": 0.90,
    # Standards / International
    "who.int": 0.92,
    "un.org": 0.90,
    "worldbank.org": 0.88,
    "imf.org": 0.88,
    "oecd.org": 0.88,
    "iea.org": 0.88,
    # News (high quality)
    "reuters.com": 0.82,
    "apnews.com": 0.82,
    "bbc.com": 0.80,
    "nzz.ch": 0.82,
    "swissinfo.ch": 0.80,
}

# Domain category patterns
CATEGORY_PATTERNS = {
    "government": [".admin.ch", ".gov", "parlament.ch", "fedlex", "europa.eu"],
    "academic": ["arxiv.org", ".edu", "nih.gov", "nature.com", "science.org",
                 "pubmed", "research", "uni-", "ieee.org", "acm.org"],
    "international": ["who.int", "un.org", "worldbank.org", "imf.org", "oecd.org"],
    "news": ["reuters.com", "apnews.com", "bbc.com", "nzz.ch", "swissinfo.ch"],
}


def score_url(url: str) -> dict[str, Any]:
    """
    Score a single URL based on domain reputation.
    Returns score (0.0-1.0), category, and domain.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().lstrip("www.")
    except Exception:
        return {"url": url, "score": 0.3, "category": "unknown", "domain": ""}

    # Check exact domain match
    for known_domain, score in RELIABLE_DOMAINS.items():
        if domain == known_domain or domain.endswith("." + known_domain):
            category = _categorize_domain(domain)
            return {
                "url": url,
                "score": score,
                "category": category,
                "domain": domain,
                "known_reliable": True,
            }

    # Check category patterns
    category = _categorize_domain(domain)
    base_scores = {
        "government": 0.85,
        "academic": 0.82,
        "international": 0.80,
        "news": 0.70,
        "other": 0.50,
    }

    return {
        "url": url,
        "score": base_scores.get(category, 0.50),
        "category": category,
        "domain": domain,
        "known_reliable": False,
    }


def _categorize_domain(domain: str) -> str:
    """Categorize a domain into government/academic/international/news/other."""
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern in domain:
                return category
    return "other"


def compute_weighted_confidence(
    base_confidence: float,
    source_scores: list[float],
    weight: float = 0.15,
) -> float:
    """
    Adjust claim confidence based on source quality.
    weight: how much source quality affects final confidence (0.0-1.0).
    """
    if not source_scores:
        return base_confidence

    avg_source_score = sum(source_scores) / len(source_scores)
    # Weighted blend: (1-w) * base + w * source_quality
    adjusted = (1 - weight) * base_confidence + weight * avg_source_score
    return round(min(1.0, max(0.0, adjusted)), 4)


async def score_claim_sources(
    session: AsyncSession, claim_id: str
) -> dict[str, Any]:
    """Score all sources for a claim and return analysis."""
    result = await session.run(
        """
        MATCH (c:Claim {id: $id})-[:REFERENCES]->(s:Source)
        RETURN s.url AS url, s.id AS source_id
        """,
        {"id": claim_id},
    )
    rows = await result.data()

    source_analyses = []
    for row in rows:
        analysis = score_url(row["url"])
        analysis["source_id"] = row["source_id"]
        source_analyses.append(analysis)

    scores = [a["score"] for a in source_analyses]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "claim_id": claim_id,
        "source_count": len(source_analyses),
        "average_score": round(avg_score, 3),
        "sources": source_analyses,
        "categories": {
            cat: len([s for s in source_analyses if s["category"] == cat])
            for cat in ["government", "academic", "international", "news", "other"]
            if any(s["category"] == cat for s in source_analyses)
        },
    }


async def batch_score_domain_sources(
    session: AsyncSession, domain_id: str
) -> dict[str, Any]:
    """Score all sources across a domain."""
    result = await session.run(
        """
        MATCH (c:Claim {status: 'certified', domain_id: $domain_id})-[:REFERENCES]->(s:Source)
        RETURN DISTINCT s.url AS url, count(c) AS citation_count
        ORDER BY citation_count DESC
        """,
        {"domain_id": domain_id},
    )
    rows = await result.data()

    scored = []
    for row in rows:
        analysis = score_url(row["url"])
        analysis["citation_count"] = row["citation_count"]
        scored.append(analysis)

    return {
        "domain_id": domain_id,
        "total_sources": len(scored),
        "average_quality": round(
            sum(s["score"] for s in scored) / len(scored), 3
        ) if scored else 0.0,
        "sources": scored[:50],  # Top 50
    }
