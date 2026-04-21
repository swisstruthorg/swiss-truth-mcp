"""
Agent Knowledge Tools — Phase 6 (Plans 06-01 to 06-04)

New MCP tools designed specifically for AI agent workflows:
- get_knowledge_brief: structured, citable knowledge summary
- get_citations: formatted citations for verified claims
- check_freshness: is this fact still current?
- check_regulatory_compliance: Swiss/EU compliance check for agent output
- report_agent_need: feedback loop tool
"""
from __future__ import annotations

from typing import Any, Optional


async def get_knowledge_brief(
    topic: str,
    domain: Optional[str] = None,
    language: Optional[str] = None,
    max_facts: int = 5,
) -> dict[str, Any]:
    """
    Get a structured, citable knowledge brief on a topic.

    Returns a ready-to-use knowledge summary with key facts, source references,
    and confidence scores. Optimized for enriching agent responses.

    Args:
        topic: The topic or question to get a brief on
        domain: Optional domain filter (e.g. 'swiss-health', 'ai-ml')
        language: Optional language filter ('de', 'en', 'fr', 'it')
        max_facts: Maximum number of key facts to include (default 5, max 10)

    Returns:
        Dict with 'brief' (formatted text), 'key_facts', 'sources', 'confidence'
    """
    from swiss_truth_mcp.db.neo4j_client import get_session
    from swiss_truth_mcp.db import queries
    from swiss_truth_mcp.embeddings import embed_text
    from swiss_truth_mcp.mcp_server.tools import _detect_language

    max_facts = min(max_facts, 10)
    detected_lang = language or _detect_language(topic)

    embedding = await embed_text(topic)
    async with get_session() as session:
        results = await queries.search_claims(
            session, embedding, topic, domain,
            min_confidence=0.75, limit=max_facts * 2,
            language=detected_lang,
        )
        if len(results) < 2 and not language:
            results = await queries.search_claims(
                session, embedding, topic, domain,
                min_confidence=0.75, limit=max_facts * 2,
                language=None,
            )

    if not results:
        return {
            "topic": topic,
            "brief": None,
            "key_facts": [],
            "sources": [],
            "confidence": 0.0,
            "total_facts": 0,
            "message": "No verified knowledge found on this topic. Consider submitting claims via submit_claim.",
        }

    top = results[:max_facts]
    all_sources: list[str] = []
    for r in top:
        for s in r.get("source_references", []):
            if s and s not in all_sources:
                all_sources.append(s)

    avg_confidence = round(
        sum(r.get("effective_confidence", r.get("confidence_score", 0)) for r in top) / len(top), 3
    )

    key_facts = [
        {
            "fact": r["text"],
            "claim_id": r["id"],
            "confidence": r.get("effective_confidence", r.get("confidence_score", 0)),
            "domain": r.get("domain_id"),
            "language": r.get("language"),
            "sources": r.get("source_references", []),
            "last_reviewed": r.get("last_reviewed"),
            "hash": r.get("hash_sha256"),
        }
        for r in top
    ]

    brief_lines = [f"**Knowledge Brief: {topic}**", ""]
    for i, f in enumerate(key_facts, 1):
        brief_lines.append(f"{i}. {f['fact']} (confidence: {f['confidence']:.0%})")
    brief_lines.append("")
    if all_sources:
        brief_lines.append(f"Sources: {', '.join(all_sources[:5])}")

    return {
        "topic": topic,
        "brief": "\n".join(brief_lines),
        "key_facts": key_facts,
        "sources": all_sources[:10],
        "confidence": avg_confidence,
        "total_facts": len(key_facts),
        "domain_filter": domain,
        "language": detected_lang,
    }


async def get_citations(
    claim_text: str,
    domain: Optional[str] = None,
    citation_style: str = "inline",
) -> dict[str, Any]:
    """
    Get properly formatted citations for a factual claim.

    Finds the best matching verified claim and returns formatted citations
    with source URLs. Solves the #1 agent problem: inability to cite sources.

    Args:
        claim_text: The factual statement to find citations for
        domain: Optional domain filter
        citation_style: 'inline' | 'apa' | 'all' (default: 'inline')

    Returns:
        Dict with 'citations' list, 'best_match' claim, 'formatted' citation strings
    """
    from swiss_truth_mcp.db.neo4j_client import get_session
    from swiss_truth_mcp.db import queries
    from swiss_truth_mcp.embeddings import embed_text
    from swiss_truth_mcp.mcp_server.tools import _detect_language
    from datetime import datetime

    detected_lang = _detect_language(claim_text)
    embedding = await embed_text(claim_text)

    async with get_session() as session:
        results = await queries.search_claims(
            session, embedding, claim_text, domain,
            min_confidence=0.80, limit=3,
            language=detected_lang,
        )
        if not results:
            results = await queries.search_claims(
                session, embedding, claim_text, domain,
                min_confidence=0.80, limit=3,
                language=None,
            )

    if not results:
        return {
            "claim": claim_text,
            "citations": [],
            "formatted": {},
            "message": "No verified sources found for this claim.",
        }

    best = results[0]
    sources = best.get("source_references", [])
    claim_id = best.get("id", "")
    last_reviewed = best.get("last_reviewed", "")
    year = ""
    if last_reviewed:
        try:
            year = str(datetime.fromisoformat(last_reviewed.replace("Z", "+00:00")).year)
        except Exception:
            year = ""

    citations = []
    for url in sources:
        domain_name = url.split("/")[2] if url.startswith("http") else url
        citations.append({
            "url": url,
            "domain": domain_name,
            "claim_id": claim_id,
            "confidence": best.get("effective_confidence", best.get("confidence_score", 0)),
            "verified_by": "Swiss Truth MCP",
            "last_reviewed": last_reviewed,
        })

    inline = f"[Swiss Truth, {year}]" if year else "[Swiss Truth]"
    apa_parts = []
    for url in sources[:3]:
        domain_name = url.split("/")[2] if url.startswith("http") else url
        apa_parts.append(f"Swiss Truth MCP. ({year or 'n.d.'}). *{best['text'][:80]}*. {domain_name}. {url}")

    formatted: dict[str, Any] = {}
    if citation_style in ("inline", "all"):
        formatted["inline"] = inline
    if citation_style in ("apa", "all"):
        formatted["apa"] = apa_parts
    if citation_style == "all":
        formatted["claim_id"] = claim_id
        formatted["hash"] = best.get("hash_sha256", "")

    return {
        "claim": claim_text,
        "best_match": best["text"],
        "match_confidence": best.get("effective_confidence", best.get("confidence_score", 0)),
        "citations": citations,
        "formatted": formatted,
        "total_sources": len(sources),
    }


async def check_freshness(
    claim_text: str,
    domain: Optional[str] = None,
    known_as_of: Optional[str] = None,
) -> dict[str, Any]:
    """
    Check if a factual claim is still current and up-to-date.

    Agents often have outdated training data. This tool checks whether
    a fact is still valid according to the latest verified knowledge.

    Args:
        claim_text: The factual statement to check
        domain: Optional domain filter
        known_as_of: ISO date string of when the agent last knew this fact (optional)

    Returns:
        Dict with 'freshness_status' (current|outdated|changed|unknown),
        'latest_version', 'last_reviewed', 'recommendation'
    """
    from swiss_truth_mcp.db.neo4j_client import get_session
    from swiss_truth_mcp.db import queries
    from swiss_truth_mcp.embeddings import embed_text
    from swiss_truth_mcp.validation.pre_screen import compare_claims
    from swiss_truth_mcp.mcp_server.tools import _detect_language
    from datetime import datetime, timezone

    detected_lang = _detect_language(claim_text)
    embedding = await embed_text(claim_text)

    async with get_session() as session:
        results = await queries.search_claims(
            session, embedding, claim_text, domain,
            min_confidence=0.75, limit=5,
            language=detected_lang,
        )
        if not results:
            results = await queries.search_claims(
                session, embedding, claim_text, domain,
                min_confidence=0.75, limit=5,
                language=None,
            )

    if not results:
        return {
            "claim": claim_text,
            "freshness_status": "unknown",
            "latest_version": None,
            "last_reviewed": None,
            "recommendation": "No verified version of this claim found. Cannot determine freshness.",
            "confidence": 0.0,
        }

    best = results[0]
    last_reviewed = best.get("last_reviewed")

    # Compare semantically
    comparison = await compare_claims(submitted=claim_text, certified=best["text"])
    relation = comparison.get("relation", "unrelated")

    # Determine freshness
    if relation == "supports":
        status = "current"
        recommendation = "This fact is verified and current."
    elif relation == "contradicts":
        status = "changed"
        recommendation = f"This fact has changed. Latest verified version: {best['text']}"
    elif relation == "unrelated":
        status = "unknown"
        recommendation = "Could not find a matching verified claim to compare against."
    else:
        status = "current"
        recommendation = "Fact appears consistent with verified knowledge."

    # Age check
    age_warning = None
    if last_reviewed:
        try:
            reviewed_dt = datetime.fromisoformat(last_reviewed.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - reviewed_dt).days
            if age_days > 365:
                age_warning = f"Last reviewed {age_days} days ago — consider requesting renewal."
        except Exception:
            pass

    return {
        "claim": claim_text,
        "freshness_status": status,
        "latest_version": best["text"] if status in ("changed", "current") else None,
        "latest_claim_id": best.get("id"),
        "last_reviewed": last_reviewed,
        "confidence": best.get("effective_confidence", best.get("confidence_score", 0)),
        "recommendation": recommendation,
        "age_warning": age_warning,
        "known_as_of": known_as_of,
    }


# ── Regulatory domains config ────────────────────────────────────────────────

_REGULATORY_DOMAINS = {
    "swiss-finance": {
        "regulator": "FINMA",
        "rules": [
            "Investment advice must include risk disclosure",
            "Past performance must not be presented as guarantee of future results",
            "Unlicensed financial advice is prohibited under FINMAG Art. 3",
        ],
        "keywords": ["rendite", "return", "investment", "anlage", "garantiert", "guaranteed", "profit"],
    },
    "swiss-health": {
        "regulator": "BAG / Swissmedic",
        "rules": [
            "Medical claims must reference approved treatments",
            "Dosage information must align with Swissmedic approvals",
            "Diagnostic statements require professional qualification disclaimer",
        ],
        "keywords": ["heilt", "cures", "behandlung", "treatment", "diagnose", "diagnosis", "medikament"],
    },
    "swiss-law": {
        "regulator": "Bundesgericht / Kantonale Gerichte",
        "rules": [
            "Legal advice must note that individual cases may differ",
            "References to specific articles must be current (check revision dates)",
            "Statements about legal outcomes must note uncertainty",
        ],
        "keywords": ["gesetz", "law", "recht", "legal", "artikel", "article", "paragraph", "§"],
    },
    "eu-law": {
        "regulator": "European Commission / ECJ",
        "rules": [
            "GDPR compliance statements must be accurate",
            "EU AI Act risk classifications must follow official taxonomy",
            "References to directives must include implementation status",
        ],
        "keywords": ["gdpr", "dsgvo", "ai act", "regulation", "directive", "verordnung"],
    },
}


async def check_regulatory_compliance(
    text: str,
    domain: str,
) -> dict[str, Any]:
    """
    Check if agent-generated text complies with Swiss/EU regulations.

    Designed for agents operating in regulated domains (finance, health, law).
    Identifies potentially non-compliant statements and suggests corrections.

    Args:
        text: The agent-generated text to check
        domain: Regulatory domain ('swiss-finance', 'swiss-health', 'swiss-law', 'eu-law')

    Returns:
        Dict with 'compliant' bool, 'issues' list, 'recommendations', 'regulator'
    """
    from swiss_truth_mcp.mcp_server.tools import verify_claims_batch
    import re

    domain_config = _REGULATORY_DOMAINS.get(domain)
    if not domain_config:
        supported = list(_REGULATORY_DOMAINS.keys())
        return {
            "text": text[:200],
            "domain": domain,
            "compliant": None,
            "issues": [],
            "recommendations": [],
            "message": f"Domain '{domain}' not supported for compliance check. Supported: {supported}",
        }

    issues = []
    recommendations = []

    # Keyword-based red flag detection
    text_lower = text.lower()
    for kw in domain_config["keywords"]:
        if kw in text_lower:
            issues.append({
                "type": "keyword_flag",
                "keyword": kw,
                "message": f"Text contains regulated keyword '{kw}' — verify compliance",
            })

    # Fact-check against knowledge base
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 20][:10]
    if sentences:
        batch_result = await verify_claims_batch(sentences, domain=domain)
        contradicted = [r for r in batch_result["results"] if r["verdict"] == "contradicted"]
        for c in contradicted:
            issues.append({
                "type": "factual_conflict",
                "statement": c["claim"],
                "message": f"Statement contradicts verified knowledge: {c.get('explanation', '')}",
                "evidence": c.get("evidence", [])[:1],
            })

    # Apply domain rules as recommendations
    for rule in domain_config["rules"]:
        recommendations.append(rule)

    compliant = len([i for i in issues if i["type"] == "factual_conflict"]) == 0

    return {
        "text_preview": text[:300],
        "domain": domain,
        "regulator": domain_config["regulator"],
        "compliant": compliant,
        "compliance_note": (
            "No factual conflicts detected." if compliant
            else f"{len([i for i in issues if i['type'] == 'factual_conflict'])} factual conflict(s) found."
        ),
        "issues": issues,
        "recommendations": recommendations,
        "total_issues": len(issues),
    }


async def report_agent_need(
    request_type: str,
    details: str,
    agent_framework: str = "unknown",
    domain_hint: str = "",
    query_that_failed: str = "",
) -> dict[str, Any]:
    """
    Report what you need from Swiss Truth that's currently missing.

    Use this when you can't find what you need. Your feedback directly
    shapes what Swiss Truth builds next — we review all agent feedback weekly.

    Args:
        request_type: 'missing_domain' | 'missing_claim' | 'quality_issue' |
                      'feature_request' | 'integration_issue' | 'coverage_gap'
        details: What do you need? Be specific — what topic, what use case?
        agent_framework: Your framework (langchain/crewai/autogen/openai/etc.)
        domain_hint: Which domain/topic area? (e.g. 'swiss-mietrecht')
        query_that_failed: The exact query that returned no results

    Returns:
        Confirmation with feedback_id
    """
    from swiss_truth_mcp.db.neo4j_client import get_session
    from swiss_truth_mcp.agent.feedback import build_feedback_record, create_feedback

    record = build_feedback_record(
        agent_framework=agent_framework,
        request_type=request_type,
        details=details,
        domain_hint=domain_hint,
        query_that_failed=query_that_failed,
    )
    async with get_session() as session:
        saved = await create_feedback(session, record)

    return {
        "feedback_id": saved.get("id", record["id"]),
        "status": "received",
        "message": (
            "Thank you! Your feedback has been recorded. "
            "We review all agent feedback weekly and prioritize based on demand signals. "
            "Check https://swisstruth.org for updates."
        ),
        "request_type": record["request_type"],
    }
