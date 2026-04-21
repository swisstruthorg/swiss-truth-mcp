"""
Agent API Routes — Phase 6 (Plan 06-A)

Public endpoints for AI agents to interact with the Swiss Truth platform:
- POST /api/agent/feedback  — report what's missing / needed
- GET  /api/agent/feedback  — list feedback (admin)
- GET  /api/agent/feedback/stats — aggregated demand signals (admin)
- PATCH /api/agent/feedback/{id} — update status (admin)
- GET  /api/agent/capabilities — what Swiss Truth offers agents
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.agent.feedback import (
    FEEDBACK_TYPES,
    AGENT_FRAMEWORKS,
    build_feedback_record,
    create_feedback,
    list_feedback,
    get_feedback_stats,
    update_feedback_status,
)

router = APIRouter(tags=["agent"])


# ── Pydantic models ──────────────────────────────────────────────────────────

class FeedbackCreate(BaseModel):
    agent_framework: str = Field(
        default="unknown",
        description=f"Agent framework. One of: {', '.join(AGENT_FRAMEWORKS)}",
    )
    agent_name: str = Field(
        default="",
        description="Optional agent identifier (e.g. 'research-assistant-v2')",
    )
    request_type: str = Field(
        description=f"Type of feedback. One of: {', '.join(FEEDBACK_TYPES.keys())}",
    )
    details: str = Field(
        description="Detailed description of what the agent needs or what went wrong",
        max_length=2000,
    )
    context: str = Field(
        default="",
        description="Optional: what was the agent trying to do when this issue occurred?",
        max_length=1000,
    )
    domain_hint: str = Field(
        default="",
        description="Optional: which domain/topic area is this about? (e.g. 'swiss-mietrecht', 'quantum-error-correction')",
        max_length=100,
    )
    query_that_failed: str = Field(
        default="",
        description="Optional: the exact query/claim that returned no results",
        max_length=500,
    )


class FeedbackStatusUpdate(BaseModel):
    status: str = Field(description="New status: open | in_progress | resolved")
    resolution_note: str = Field(default="", description="How was this resolved?")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/api/agent/feedback", status_code=201)
async def submit_agent_feedback(body: FeedbackCreate) -> dict[str, Any]:
    """
    Submit feedback from an AI agent about what it needs from Swiss Truth.

    Use this when:
    - You searched for a fact but found nothing (missing_claim)
    - You need a domain that doesn't exist (missing_domain)
    - You found a claim that seems wrong (quality_issue)
    - You need a feature the platform doesn't offer (feature_request)
    - You had integration problems (integration_issue)
    - A topic area has too few claims (coverage_gap)

    This feedback directly shapes what Swiss Truth builds next.
    """
    record = build_feedback_record(
        agent_framework=body.agent_framework,
        request_type=body.request_type,
        details=body.details,
        agent_name=body.agent_name,
        context=body.context,
        domain_hint=body.domain_hint,
        query_that_failed=body.query_that_failed,
    )
    async with get_session() as session:
        saved = await create_feedback(session, record)

    return {
        "feedback_id": saved.get("id", record["id"]),
        "status": "received",
        "message": (
            "Thank you! Your feedback has been recorded and will directly influence "
            "what Swiss Truth builds next. We review all agent feedback weekly."
        ),
        "request_type": record["request_type"],
    }


@router.get("/api/agent/feedback")
async def get_agent_feedback(
    request_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> dict[str, Any]:
    """List agent feedback entries (admin use)."""
    async with get_session() as session:
        items = await list_feedback(session, request_type=request_type, status=status, limit=limit)
    return {"feedback": items, "total": len(items)}


@router.get("/api/agent/feedback/stats")
async def get_feedback_statistics() -> dict[str, Any]:
    """
    Aggregated demand signals from AI agents.
    Shows what agents need most — use this to prioritize platform development.
    """
    async with get_session() as session:
        stats = await get_feedback_stats(session)
    return stats


@router.patch("/api/agent/feedback/{feedback_id}")
async def update_feedback(
    feedback_id: str,
    body: FeedbackStatusUpdate,
) -> dict[str, Any]:
    """Update feedback status (admin use)."""
    valid_statuses = {"open", "in_progress", "resolved"}
    if body.status not in valid_statuses:
        raise HTTPException(422, f"Invalid status. Must be one of: {valid_statuses}")

    async with get_session() as session:
        updated = await update_feedback_status(
            session, feedback_id, body.status, body.resolution_note
        )
    if updated is None:
        raise HTTPException(404, f"Feedback '{feedback_id}' not found")
    return updated


@router.get("/api/agent/capabilities")
async def get_agent_capabilities() -> dict[str, Any]:
    """
    Discover what Swiss Truth offers AI agents.

    Returns a structured capability manifest that agents can use to understand
    when and how to use Swiss Truth in their workflows.
    """
    return {
        "platform": "Swiss Truth MCP",
        "version": "1.2.0",
        "tagline": "Verified knowledge infrastructure for AI agents",
        "homepage": "https://swisstruth.org",
        "mcp_endpoint": "https://swisstruth.org/mcp",
        "openai_tools": "https://swisstruth.org/openai-tools.json",
        "discovery": "https://swisstruth.org/.well-known/mcp.json",

        "when_to_use": [
            "Before answering factual questions where being wrong would matter",
            "When generating content about Swiss law, health, finance, or politics",
            "When you need citable, source-backed information",
            "When checking if your response contains hallucinations",
            "When you need to know if a fact is still current",
            "Before publishing facts in regulated domains (finance, health, law)",
        ],

        "core_tools": [
            {
                "name": "search_knowledge",
                "use_case": "Find verified facts on any topic",
                "returns": "Certified claims with confidence scores and source URLs",
                "best_for": "RAG pipelines, fact-grounding, knowledge retrieval",
            },
            {
                "name": "verify_claim",
                "use_case": "Check if a specific statement is true",
                "returns": "Verdict: supported | contradicted | unknown + evidence",
                "best_for": "Fact-checking before publishing, validating user claims",
            },
            {
                "name": "verify_response",
                "use_case": "Check a full AI response for hallucinations",
                "returns": "Hallucination risk: low | medium | high + per-statement breakdown",
                "best_for": "Post-generation quality check, safety guardrails",
            },
            {
                "name": "get_knowledge_brief",
                "use_case": "Get a structured, citable knowledge summary on a topic",
                "returns": "Formatted brief with key facts, sources, and confidence",
                "best_for": "Enriching agent responses with verified content",
            },
            {
                "name": "get_citations",
                "use_case": "Get properly formatted citations for a claim",
                "returns": "APA/inline citations with verified source URLs",
                "best_for": "Academic agents, research assistants, content generators",
            },
            {
                "name": "check_freshness",
                "use_case": "Check if a fact is still current",
                "returns": "Current | Outdated | Changed + latest verified version",
                "best_for": "Agents with old training data, time-sensitive topics",
            },
            {
                "name": "check_regulatory_compliance",
                "use_case": "Check if agent output complies with Swiss/EU regulations",
                "returns": "Compliance status + required corrections",
                "best_for": "Finance, health, legal agents operating in Switzerland/EU",
            },
            {
                "name": "report_agent_need",
                "use_case": "Tell Swiss Truth what you need that's missing",
                "returns": "Confirmation that feedback was recorded",
                "best_for": "When you can't find what you need — help us build it",
            },
        ],

        "domains": [
            "swiss-law", "swiss-health", "swiss-finance", "swiss-education",
            "swiss-energy", "swiss-transport", "swiss-politics", "swiss-agriculture",
            "swiss-digital", "ai-ml", "ai-safety", "climate", "world-science",
            "world-history", "eu-law", "eu-health", "global-science",
            "quantum-computing", "cybersecurity", "space-science", "biotech",
            "economics", "international-law", "renewable-energy", "us-law",
        ],

        "integrations": {
            "mcp": "Native MCP server (StreamableHTTP) — works with Claude, Cursor, etc.",
            "langchain": "pip install swiss-truth-langchain",
            "crewai": "pip install swiss-truth-crewai",
            "autogen": "pip install swiss-truth-autogen",
            "npm": "npm install swiss-truth-mcp",
            "openai_functions": "GET /openai-tools.json",
        },

        "feedback_endpoint": "POST /api/agent/feedback",
        "feedback_note": (
            "If you can't find what you need, use report_agent_need or POST /api/agent/feedback. "
            "We review all agent feedback weekly and prioritize based on demand signals."
        ),
    }
