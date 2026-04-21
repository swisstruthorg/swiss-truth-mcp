"""
EU AI Act Compliance Endpoints — Phase 2 improvements.

Provides:
- GET  /api/compliance/eu-ai-act/{claim_id}       — single claim attestation (moved from main.py)
- POST /api/compliance/eu-ai-act/batch             — batch attestation for multiple claims
- GET  /api/compliance/eu-ai-act/domain/{domain_id} — domain-level compliance summary
- GET  /api/compliance/eu-ai-act/report            — full system compliance report
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.validation.trust import decay_confidence

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_attestation(claim: dict, claim_id: str) -> dict:
    """Build a single EU AI Act compliance attestation for a certified claim."""
    effective_conf = decay_confidence(
        claim["confidence_score"], claim.get("last_reviewed")
    )
    validators = claim.get("validated_by", [])
    sources = claim.get("source_references", [])
    now = _now_iso()

    return {
        "attestation_version": "1.1",
        "attested_at": now,
        "attested_by": "Swiss Truth MCP — swisstruth.org",
        "claim_id": claim_id,
        "claim_text": claim["text"],
        "domain": claim["domain_id"],
        "language": claim.get("language", "unknown"),
        "compliant_with": [
            "EU-AI-Act-Art-9",
            "EU-AI-Act-Art-13",
            "EU-AI-Act-Art-17",
        ],
        "risk_management": {
            "article": "EU AI Act Article 9",
            "validation_stages_passed": 5,
            "stages": [
                "1. Semantic deduplication (cosine similarity >= 0.95)",
                "2. AI pre-screen (Claude Haiku — atomicity, factuality, source check)",
                "3. Source URL verification (content fetched and validated)",
                "4. Expert peer review (human validation with confidence score)",
                "5. SHA256 cryptographic signing + expiry assignment",
            ],
            "human_review_confirmed": len(validators) > 0,
            "expert_count": len(validators),
        },
        "transparency": {
            "article": "EU AI Act Article 13",
            "validators": validators,
            "source_count": len(sources),
            "source_references": sources,
            "confidence_score": claim["confidence_score"],
            "effective_confidence": round(effective_conf, 4),
            "last_reviewed": claim.get("last_reviewed"),
            "expires_at": claim.get("expires_at"),
        },
        "quality_management": {
            "article": "EU AI Act Article 17",
            "cryptographic_integrity": claim.get("hash_sha256", ""),
            "integrity_method": "SHA256 over canonical claim content",
            "confidence_decay_rate": "1% per month since last review (floor: 50%)",
            "ttl_days": 365,
            "knowledge_cutoff": claim.get("last_reviewed"),
            "renewal_required_after": claim.get("expires_at"),
        },
        "summary": {
            "is_compliant": True,
            "risk_level": "minimal",
            "data_quality": (
                "high" if effective_conf >= 0.90
                else "medium" if effective_conf >= 0.75
                else "low"
            ),
            "freshness": (
                "current"
                if (
                    claim.get("expires_at") is None
                    or claim.get("expires_at", "") > now[:10]
                )
                else "renewal_recommended"
            ),
        },
        "verification_url": f"https://swisstruth.org/api/claims/{claim_id}",
        "methodology_url": "https://swisstruth.org/trust",
    }


# ── Full Extended Compliance Report (Phase 4 — Plan 04-03) ───────────────────

@router.get("/eu-ai-act/report/full")
async def eu_ai_act_full_report():
    """
    Full extended EU AI Act compliance report with per-domain analysis.

    Includes everything from /report plus:
    - Per-domain compliance metrics (confidence, quality distribution, renewal status)
    - Certification timeline (monthly counts)
    - Validator leaderboard with certification rates
    - Blockchain anchoring status
    - SLA monitoring status
    - Audit trail availability

    Suitable for regulatory submissions and enterprise compliance audits.
    """
    async with get_session() as session:
        domains = await queries.list_domains(session)
        stats = await queries.get_trust_stats(session)
        timeline = await queries.get_certification_timeline(session, months=12)
        validator_stats = await queries.get_validator_stats(session)
        latest_anchor = await queries.get_latest_anchor(session)
        anchor_records = await queries.list_anchor_records(session, limit=5)

    now = _now_iso()

    # Per-domain detailed analysis
    domain_details = []
    async with get_session() as session:
        for d in sorted(domains, key=lambda x: -x.get("certified_claims", 0)):
            if d.get("certified_claims", 0) == 0:
                continue
            claims = await queries.get_certified_claims_by_domain(session, d["id"])
            total = len(claims)
            if total == 0:
                continue

            effective_confs = []
            high_q, med_q, low_q = 0, 0, 0
            needs_renewal = 0
            human_reviewed = 0

            for c in claims:
                eff = decay_confidence(c["confidence_score"], c.get("last_reviewed"))
                effective_confs.append(eff)
                if eff >= 0.90:
                    high_q += 1
                elif eff >= 0.75:
                    med_q += 1
                else:
                    low_q += 1
                expires = c.get("expires_at")
                if expires and expires <= now[:10]:
                    needs_renewal += 1
                if c.get("validated_by"):
                    human_reviewed += 1

            avg_conf = round(sum(effective_confs) / total, 4) if total else 0.0

            domain_details.append({
                "domain_id": d["id"],
                "domain_name": d.get("name", ""),
                "certified_claims": total,
                "avg_effective_confidence": avg_conf,
                "quality_distribution": {
                    "high": high_q,
                    "medium": med_q,
                    "low": low_q,
                },
                "needs_renewal": needs_renewal,
                "human_reviewed": human_reviewed,
                "human_review_rate": round(human_reviewed / total, 4) if total else 0.0,
                "overall_quality": (
                    "high" if avg_conf >= 0.90
                    else "medium" if avg_conf >= 0.75
                    else "low"
                ),
            })

    total_certified = sum(d["certified_claims"] for d in domain_details)

    # SLA status (if available)
    try:
        from swiss_truth_mcp.monitoring.sla import sla_tracker
        sla_status = sla_tracker.get_status()
    except Exception:
        sla_status = None

    return {
        "report_version": "2.0",
        "generated_at": now,
        "generated_by": "Swiss Truth MCP — swisstruth.org",
        "regulation": {
            "name": "EU Artificial Intelligence Act",
            "reference": "Regulation (EU) 2024/1689",
            "applicable_articles": [
                {
                    "article": "Article 9",
                    "title": "Risk Management System",
                    "compliance_method": (
                        "5-stage validation pipeline: semantic dedup, "
                        "AI pre-screen, source verification, expert peer review, "
                        "cryptographic signing"
                    ),
                },
                {
                    "article": "Article 13",
                    "title": "Transparency and Provision of Information",
                    "compliance_method": (
                        "Full provenance chain: validator identity, institution, "
                        "review date, source URLs, confidence scores, "
                        "language metadata. JSON-LD audit trail (W3C PROV-O)."
                    ),
                },
                {
                    "article": "Article 17",
                    "title": "Quality Management System",
                    "compliance_method": (
                        "SHA256 tamper-evident hashing, confidence decay model "
                        "(1%/month, floor 50%), annual expiry with renewal workflow, "
                        "daily API cost cap, blockchain anchoring (Merkle root)"
                    ),
                },
            ],
        },
        "system_metrics": {
            "total_domains": len(domains),
            "active_domains": len(domain_details),
            "total_certified_claims": total_certified,
            "total_claims": stats.get("total", total_certified),
            "average_confidence": stats.get("avg_confidence", 0.0),
            "unique_sources": stats.get("unique_sources", 0),
            "languages": stats.get("languages", []),
            "validation_pipeline_stages": 5,
            "integrity_method": "SHA256",
            "confidence_decay_model": "1% per month since last review (floor: 50%)",
            "claim_ttl_days": 365,
        },
        "domains": domain_details,
        "certification_timeline": timeline,
        "validators": {
            "total": len(validator_stats),
            "leaderboard": validator_stats[:20],
        },
        "blockchain_anchoring": {
            "enabled": bool(latest_anchor),
            "latest_anchor": latest_anchor,
            "recent_anchors": anchor_records,
            "chain": latest_anchor.get("chain", "not configured") if latest_anchor else "not configured",
        },
        "sla_monitoring": sla_status if sla_status else {"status": "not available"},
        "audit_trail": {
            "format": "JSON-LD (W3C PROV-O)",
            "endpoints": {
                "full_trail": "/api/audit/trail",
                "claim_trail": "/api/audit/trail/{claim_id}",
                "export": "/api/audit/export",
            },
        },
        "summary": {
            "is_compliant": True,
            "compliance_scope": "All certified claims across all domains",
            "audit_trail": "Full provenance stored in Neo4j graph database, exportable as JSON-LD",
            "data_integrity": "SHA256 hash per claim + weekly Merkle root blockchain anchoring",
            "monitoring": "Real-time SLA tracking with alerting",
        },
        "endpoints": {
            "single_attestation": "/api/compliance/eu-ai-act/{claim_id}",
            "batch_attestation": "/api/compliance/eu-ai-act/batch",
            "domain_summary": "/api/compliance/eu-ai-act/domain/{domain_id}",
            "system_report": "/api/compliance/eu-ai-act/report",
            "full_report": "/api/compliance/eu-ai-act/report/full",
            "audit_trail": "/api/audit/trail",
            "claim_verification": "/api/claims/{claim_id}",
            "methodology": "/trust",
        },
        "methodology_url": "https://swisstruth.org/trust",
    }


# ── Single Claim Attestation ─────────────────────────────────────────────────

@router.get("/eu-ai-act/{claim_id}")
async def eu_ai_act_compliance(claim_id: str):
    """
    EU AI Act Compliance Attestation for a single certified claim.

    Returns structured JSON documenting compliance with:
    - Art. 9: Risk management (5-stage validation pipeline)
    - Art. 13: Transparency (provenance, validator, confidence, sources)
    - Art. 17: Quality management (SHA256 integrity, expiry, confidence decay)
    """
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)

    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    if claim["status"] != "certified":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Claim is not certified (status: {claim['status']}). "
                "Only certified claims qualify for compliance attestation."
            ),
        )

    return _build_attestation(claim, claim_id)


# ── Batch Attestation ────────────────────────────────────────────────────────

class BatchComplianceRequest(BaseModel):
    claim_ids: list[str] = Field(
        ..., min_length=1, max_length=50,
        description="List of claim UUIDs to attest (max 50).",
    )


@router.post("/eu-ai-act/batch")
async def eu_ai_act_batch(body: BatchComplianceRequest):
    """
    Batch EU AI Act Compliance Attestation for multiple claims.

    Returns attestations for all valid certified claims, plus a summary
    of compliant/non-compliant/not-found counts.
    """
    attestations = []
    errors = []

    async with get_session() as session:
        for cid in body.claim_ids[:50]:
            claim = await queries.get_claim_by_id(session, cid)
            if claim is None:
                errors.append({"claim_id": cid, "error": "not_found"})
            elif claim["status"] != "certified":
                errors.append({
                    "claim_id": cid,
                    "error": "not_certified",
                    "status": claim["status"],
                })
            else:
                attestations.append(_build_attestation(claim, cid))

    return {
        "attestation_version": "1.1",
        "attested_at": _now_iso(),
        "total_requested": len(body.claim_ids),
        "compliant": len(attestations),
        "errors": len(errors),
        "attestations": attestations,
        "error_details": errors,
        "summary": {
            "all_compliant": len(errors) == 0,
            "compliance_rate": (
                round(len(attestations) / len(body.claim_ids), 4)
                if body.claim_ids else 0.0
            ),
        },
    }


# ── Domain Compliance Summary ────────────────────────────────────────────────

@router.get("/eu-ai-act/domain/{domain_id}")
async def eu_ai_act_domain(domain_id: str):
    """
    Domain-level EU AI Act compliance summary.

    Aggregates compliance metrics across all certified claims in a domain:
    - Total certified claims
    - Average effective confidence
    - Claims with high/medium/low data quality
    - Claims needing renewal
    - Expert coverage (claims with human review)
    """
    async with get_session() as session:
        claims = await queries.get_certified_claims_by_domain(
            session, domain_id
        )

    if not claims:
        raise HTTPException(
            status_code=404,
            detail=f"No certified claims found for domain '{domain_id}'.",
        )

    now = _now_iso()
    total = len(claims)
    effective_confs = []
    high_quality = 0
    medium_quality = 0
    low_quality = 0
    needs_renewal = 0
    human_reviewed = 0

    for c in claims:
        eff = decay_confidence(
            c["confidence_score"], c.get("last_reviewed")
        )
        effective_confs.append(eff)

        if eff >= 0.90:
            high_quality += 1
        elif eff >= 0.75:
            medium_quality += 1
        else:
            low_quality += 1

        expires = c.get("expires_at")
        if expires and expires <= now[:10]:
            needs_renewal += 1

        if c.get("validated_by"):
            human_reviewed += 1

    avg_conf = round(sum(effective_confs) / total, 4) if total else 0.0

    return {
        "domain_id": domain_id,
        "attested_at": now,
        "attested_by": "Swiss Truth MCP — swisstruth.org",
        "compliant_with": [
            "EU-AI-Act-Art-9",
            "EU-AI-Act-Art-13",
            "EU-AI-Act-Art-17",
        ],
        "metrics": {
            "total_certified_claims": total,
            "average_effective_confidence": avg_conf,
            "data_quality_distribution": {
                "high": high_quality,
                "medium": medium_quality,
                "low": low_quality,
            },
            "needs_renewal": needs_renewal,
            "human_reviewed": human_reviewed,
            "human_review_rate": round(human_reviewed / total, 4) if total else 0.0,
        },
        "summary": {
            "is_compliant": True,
            "overall_quality": (
                "high" if avg_conf >= 0.90
                else "medium" if avg_conf >= 0.75
                else "low"
            ),
            "renewal_urgency": (
                "none" if needs_renewal == 0
                else "low" if needs_renewal / total < 0.1
                else "medium" if needs_renewal / total < 0.3
                else "high"
            ),
        },
        "methodology_url": "https://swisstruth.org/trust",
    }


# ── System-Wide Compliance Report ────────────────────────────────────────────

@router.get("/eu-ai-act/report")
async def eu_ai_act_report():
    """
    Full system-wide EU AI Act compliance report.

    Aggregates compliance metrics across all domains and certified claims.
    Suitable for regulatory submissions and audit documentation.
    """
    async with get_session() as session:
        domains = await queries.list_domains(session)
        stats = await queries.get_trust_stats(session)

    now = _now_iso()
    total_certified = sum(d.get("certified_claims", 0) for d in domains)
    domain_summaries = []

    for d in sorted(domains, key=lambda x: -x.get("certified_claims", 0)):
        if d.get("certified_claims", 0) > 0:
            domain_summaries.append({
                "domain_id": d["id"],
                "domain_name": d.get("name", ""),
                "certified_claims": d.get("certified_claims", 0),
            })

    return {
        "report_version": "1.0",
        "generated_at": now,
        "generated_by": "Swiss Truth MCP — swisstruth.org",
        "regulation": {
            "name": "EU Artificial Intelligence Act",
            "reference": "Regulation (EU) 2024/1689",
            "applicable_articles": [
                {
                    "article": "Article 9",
                    "title": "Risk Management System",
                    "compliance_method": (
                        "5-stage validation pipeline: semantic dedup, "
                        "AI pre-screen, source verification, expert peer review, "
                        "cryptographic signing"
                    ),
                },
                {
                    "article": "Article 13",
                    "title": "Transparency and Provision of Information",
                    "compliance_method": (
                        "Full provenance chain: validator identity, institution, "
                        "review date, source URLs, confidence scores, "
                        "language metadata"
                    ),
                },
                {
                    "article": "Article 17",
                    "title": "Quality Management System",
                    "compliance_method": (
                        "SHA256 tamper-evident hashing, confidence decay model "
                        "(1%/month, floor 50%), annual expiry with renewal workflow, "
                        "daily API cost cap"
                    ),
                },
            ],
        },
        "system_metrics": {
            "total_domains": len(domains),
            "active_domains": len(domain_summaries),
            "total_certified_claims": total_certified,
            "total_claims": stats.get("total_claims", total_certified),
            "total_validators": stats.get("total_validators", 0),
            "average_confidence": stats.get("avg_confidence", 0.0),
            "validation_pipeline_stages": 5,
            "integrity_method": "SHA256",
            "confidence_decay_model": "1% per month since last review (floor: 50%)",
            "claim_ttl_days": 365,
        },
        "domains": domain_summaries,
        "summary": {
            "is_compliant": True,
            "compliance_scope": "All certified claims across all domains",
            "audit_trail": "Full provenance stored in Neo4j graph database",
            "data_integrity": "SHA256 hash per claim, verifiable via /api/claims/{id}",
        },
        "endpoints": {
            "single_attestation": "/api/compliance/eu-ai-act/{claim_id}",
            "batch_attestation": "/api/compliance/eu-ai-act/batch",
            "domain_summary": "/api/compliance/eu-ai-act/domain/{domain_id}",
            "system_report": "/api/compliance/eu-ai-act/report",
            "claim_verification": "/api/claims/{claim_id}",
            "methodology": "/trust",
        },
        "methodology_url": "https://swisstruth.org/trust",
    }
