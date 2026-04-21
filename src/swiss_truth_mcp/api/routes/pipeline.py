"""
Pipeline & Source Scoring API Routes — Phase 5 (Plan 05-05)

Automated fact-check pipeline and source quality scoring endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from swiss_truth_mcp.db.neo4j_client import get_session

router = APIRouter(tags=["pipeline"])


# ─── Request Models ────────────────────────────────────────────────────────────

class AutoVerifyRequest(BaseModel):
    claim_text: str
    domain_id: str
    source_urls: list[str] = []
    question: str = ""


# ─── Auto-Verify Pipeline ─────────────────────────────────────────────────────

@router.post("/api/pipeline/auto-verify")
async def auto_verify(body: AutoVerifyRequest):
    """
    Trigger automated fact-check pipeline for a claim.
    Pipeline: pre-screen → source scoring → AI verify → auto-certify or queue.
    """
    if not body.claim_text.strip():
        raise HTTPException(400, "claim_text is required")
    if not body.domain_id.strip():
        raise HTTPException(400, "domain_id is required")

    from swiss_truth_mcp.validation.auto_pipeline import auto_verify_claim

    result = await auto_verify_claim(
        claim_text=body.claim_text,
        domain_id=body.domain_id,
        source_urls=body.source_urls,
        question=body.question,
    )
    return result


# ─── Source Scoring ────────────────────────────────────────────────────────────

@router.get("/api/sources/score/{claim_id}")
async def score_claim_sources(claim_id: str):
    """Score all sources for a specific claim."""
    from swiss_truth_mcp.validation.source_scoring import score_claim_sources as _score

    async with get_session() as session:
        result = await _score(session, claim_id)
    return result


@router.get("/api/sources/domain/{domain_id}")
async def score_domain_sources(domain_id: str):
    """Score all sources across a domain."""
    from swiss_truth_mcp.validation.source_scoring import batch_score_domain_sources

    async with get_session() as session:
        result = await batch_score_domain_sources(session, domain_id)
    return result


@router.post("/api/sources/score-url")
async def score_single_url(url: str):
    """Score a single URL for source quality."""
    from swiss_truth_mcp.validation.source_scoring import score_url

    return score_url(url)
