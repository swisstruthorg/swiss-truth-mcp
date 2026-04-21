"""
Agent Feedback Loop — Phase 6 (Plan 06-A)

Allows AI agents to report what they need from the Swiss Truth platform.
This creates a demand-signal loop: agents tell us what's missing,
we build it. Stored in Neo4j as AgentFeedback nodes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from neo4j import AsyncSession


# ── Valid feedback types ────────────────────────────────────────────────────

FEEDBACK_TYPES = {
    "missing_domain": "Agent needs a domain that doesn't exist yet",
    "missing_claim": "Agent searched for a fact but found nothing",
    "quality_issue": "Agent found a claim that seems wrong or outdated",
    "feature_request": "Agent needs a capability the platform doesn't offer",
    "integration_issue": "Agent had trouble integrating with the platform",
    "coverage_gap": "Agent found a topic area with insufficient coverage",
}

AGENT_FRAMEWORKS = [
    "langchain", "crewai", "autogen", "openai", "anthropic",
    "llamaindex", "haystack", "dspy", "smolagents", "custom", "unknown",
]


# ── DB operations ────────────────────────────────────────────────────────────

async def create_feedback(
    session: AsyncSession,
    feedback: dict[str, Any],
) -> dict[str, Any]:
    """Store agent feedback in Neo4j."""
    cypher = """
    CREATE (f:AgentFeedback {
        id: $id,
        agent_framework: $agent_framework,
        agent_name: $agent_name,
        request_type: $request_type,
        details: $details,
        context: $context,
        domain_hint: $domain_hint,
        query_that_failed: $query_that_failed,
        created_at: $created_at,
        status: 'open'
    })
    RETURN f
    """
    result = await session.run(cypher, feedback)
    row = await result.single()
    return dict(row["f"]) if row else feedback


async def list_feedback(
    session: AsyncSession,
    request_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List agent feedback entries."""
    filters = []
    params: dict[str, Any] = {"limit": limit}

    if request_type:
        filters.append("f.request_type = $request_type")
        params["request_type"] = request_type
    if status:
        filters.append("f.status = $status")
        params["status"] = status

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    cypher = f"""
    MATCH (f:AgentFeedback)
    {where}
    RETURN f
    ORDER BY f.created_at DESC
    LIMIT $limit
    """
    result = await session.run(cypher, params)
    rows = await result.data()
    return [dict(row["f"]) for row in rows]


async def get_feedback_stats(
    session: AsyncSession,
) -> dict[str, Any]:
    """Aggregate feedback statistics for the dashboard."""
    cypher = """
    MATCH (f:AgentFeedback)
    RETURN
        count(f) AS total,
        count(CASE WHEN f.status = 'open' THEN 1 END) AS open_count,
        count(CASE WHEN f.status = 'resolved' THEN 1 END) AS resolved_count,
        collect(DISTINCT f.request_type) AS types,
        collect(DISTINCT f.agent_framework) AS frameworks
    """
    result = await session.run(cypher)
    row = await result.single()
    if not row:
        return {"total": 0, "open_count": 0, "resolved_count": 0, "types": [], "frameworks": []}

    # Top requested types
    type_cypher = """
    MATCH (f:AgentFeedback)
    RETURN f.request_type AS type, count(f) AS count
    ORDER BY count DESC
    LIMIT 10
    """
    type_result = await session.run(type_cypher)
    type_rows = await type_result.data()

    # Top missing domains/topics
    domain_cypher = """
    MATCH (f:AgentFeedback)
    WHERE f.domain_hint IS NOT NULL AND f.domain_hint <> ''
    RETURN f.domain_hint AS domain, count(f) AS count
    ORDER BY count DESC
    LIMIT 10
    """
    domain_result = await session.run(domain_cypher)
    domain_rows = await domain_result.data()

    return {
        "total": row["total"],
        "open_count": row["open_count"],
        "resolved_count": row["resolved_count"],
        "by_type": [{"type": r["type"], "count": r["count"]} for r in type_rows],
        "top_missing_domains": [{"domain": r["domain"], "count": r["count"]} for r in domain_rows],
        "frameworks_seen": list(row["frameworks"]),
    }


async def update_feedback_status(
    session: AsyncSession,
    feedback_id: str,
    status: str,
    resolution_note: str = "",
) -> Optional[dict[str, Any]]:
    """Update feedback status (open → in_progress → resolved)."""
    cypher = """
    MATCH (f:AgentFeedback {id: $id})
    SET f.status = $status,
        f.resolution_note = $resolution_note,
        f.resolved_at = CASE WHEN $status = 'resolved' THEN $now ELSE f.resolved_at END
    RETURN f
    """
    result = await session.run(cypher, {
        "id": feedback_id,
        "status": status,
        "resolution_note": resolution_note,
        "now": datetime.now(timezone.utc).isoformat(),
    })
    row = await result.single()
    return dict(row["f"]) if row else None


# ── Business logic ───────────────────────────────────────────────────────────

def build_feedback_record(
    agent_framework: str,
    request_type: str,
    details: str,
    agent_name: str = "",
    context: str = "",
    domain_hint: str = "",
    query_that_failed: str = "",
) -> dict[str, Any]:
    """Build a validated feedback record ready for DB insertion."""
    return {
        "id": str(uuid.uuid4()),
        "agent_framework": agent_framework if agent_framework in AGENT_FRAMEWORKS else "unknown",
        "agent_name": agent_name[:200] if agent_name else "",
        "request_type": request_type if request_type in FEEDBACK_TYPES else "feature_request",
        "details": details[:2000],
        "context": context[:1000] if context else "",
        "domain_hint": domain_hint[:100] if domain_hint else "",
        "query_that_failed": query_that_failed[:500] if query_that_failed else "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
