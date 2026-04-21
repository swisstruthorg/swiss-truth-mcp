"""
Audit Trail Export Endpoints — Phase 4 (Plan 04-04)

Provides JSON-LD (W3C PROV-O) export of the Swiss Truth audit trail.

Endpoints:
- GET /api/audit/trail              — Full system audit trail (JSON-LD)
- GET /api/audit/trail/{claim_id}   — Single claim audit trail (JSON-LD)
- GET /api/audit/export             — Bulk export with optional time filter
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.audit.jsonld import (
    build_claim_audit_trail,
    build_full_audit_trail,
)

router = APIRouter(prefix="/api/audit", tags=["audit"])


# ── Single Claim Audit Trail ─────────────────────────────────────────────────

@router.get("/trail/{claim_id}")
async def claim_audit_trail(claim_id: str):
    """
    JSON-LD audit trail for a single claim (W3C PROV-O compatible).

    Returns the claim as prov:Entity with all validation events (prov:Activity),
    expert attributions (prov:Agent), source references (prov:wasDerivedFrom),
    and related blockchain anchors.
    """
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

        # Get validation history for this claim
        validations = await queries.get_claim_validations(session, claim_id)

        # Get blockchain anchors
        anchors = await queries.list_anchor_records(session, limit=10)

    return build_claim_audit_trail(
        claim=claim,
        validations=validations,
        anchors=anchors,
    )


# ── Full System Audit Trail ──────────────────────────────────────────────────

@router.get("/trail")
async def full_audit_trail(
    limit: int = Query(default=500, le=2000, description="Max claims to include"),
):
    """
    Full system audit trail as JSON-LD (W3C PROV-O compatible).

    Returns all certified claims as prov:Entity nodes, all blockchain anchors
    as prov:Activity nodes, with full provenance chain.

    Suitable for regulatory audit submissions and compliance documentation.
    """
    async with get_session() as session:
        claims = await queries.get_all_certified_claims(session, limit=limit)
        anchors = await queries.list_anchor_records(session, limit=52)

    return build_full_audit_trail(
        claims=claims,
        anchors=anchors,
    )


# ── Bulk Export with Time Filter ──────────────────────────────────────────────

@router.get("/export")
async def audit_export(
    since: Optional[str] = Query(
        default=None,
        description="ISO datetime filter — only claims reviewed after this date (e.g. 2026-01-01T00:00:00Z)",
    ),
    domain: Optional[str] = Query(
        default=None,
        description="Optional domain filter (e.g. swiss-health, ai-ml)",
    ),
    limit: int = Query(default=1000, le=5000, description="Max claims to export"),
):
    """
    Bulk audit trail export with optional time and domain filters.

    Returns JSON-LD (W3C PROV-O) with:
    - Filtered certified claims
    - Blockchain anchor records
    - Export metadata (filter params, counts, generation timestamp)
    """
    async with get_session() as session:
        claims = await queries.get_certified_claims_filtered(
            session,
            since=since,
            domain_id=domain,
            limit=limit,
        )
        anchors = await queries.list_anchor_records(session, limit=52)

    trail = build_full_audit_trail(
        claims=claims,
        anchors=anchors,
    )

    # Add export metadata
    trail["st:exportMetadata"] = {
        "filters": {
            "since": since,
            "domain": domain,
            "limit": limit,
        },
        "claimsExported": len(claims),
        "anchorsIncluded": len(anchors),
    }

    return trail
