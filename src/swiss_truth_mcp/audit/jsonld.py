"""
JSON-LD Audit Trail Serializer — Phase 4 (Plan 04-04)

Serializes Swiss Truth audit data into W3C PROV-O compatible JSON-LD.

Ontology mapping:
- Claim       → prov:Entity
- Validation  → prov:Activity
- Expert      → prov:Agent
- Source      → prov:Entity (prov:wasDerivedFrom)
- AnchorRecord → prov:Activity (blockchain anchoring)

References:
- W3C PROV-O: https://www.w3.org/TR/prov-o/
- JSON-LD: https://www.w3.org/TR/json-ld11/
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


# ── JSON-LD Context ───────────────────────────────────────────────────────────

PROV_CONTEXT = {
    "@context": {
        "prov": "http://www.w3.org/ns/prov#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "schema": "http://schema.org/",
        "st": "https://swisstruth.org/ontology/",
        "prov:Entity": {"@id": "prov:Entity"},
        "prov:Activity": {"@id": "prov:Activity"},
        "prov:Agent": {"@id": "prov:Agent"},
        "prov:wasGeneratedBy": {"@id": "prov:wasGeneratedBy", "@type": "@id"},
        "prov:wasAttributedTo": {"@id": "prov:wasAttributedTo", "@type": "@id"},
        "prov:wasDerivedFrom": {"@id": "prov:wasDerivedFrom", "@type": "@id"},
        "prov:used": {"@id": "prov:used", "@type": "@id"},
        "prov:startedAtTime": {"@id": "prov:startedAtTime", "@type": "xsd:dateTime"},
        "prov:endedAtTime": {"@id": "prov:endedAtTime", "@type": "xsd:dateTime"},
        "prov:generatedAtTime": {"@id": "prov:generatedAtTime", "@type": "xsd:dateTime"},
        "prov:value": {"@id": "prov:value"},
        "st:confidenceScore": {"@id": "st:confidenceScore", "@type": "xsd:float"},
        "st:effectiveConfidence": {"@id": "st:effectiveConfidence", "@type": "xsd:float"},
        "st:hashSHA256": {"@id": "st:hashSHA256"},
        "st:domain": {"@id": "st:domain"},
        "st:status": {"@id": "st:status"},
        "st:verdict": {"@id": "st:verdict"},
        "st:merkleRoot": {"@id": "st:merkleRoot"},
        "st:txHash": {"@id": "st:txHash"},
        "st:chain": {"@id": "st:chain"},
    }
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Claim → prov:Entity ──────────────────────────────────────────────────────

def claim_to_jsonld(claim: dict) -> dict:
    """Convert a claim dict to a PROV-O Entity."""
    claim_id = claim.get("id", "unknown")
    entity = {
        "@id": f"https://swisstruth.org/api/claims/{claim_id}",
        "@type": "prov:Entity",
        "prov:value": claim.get("text", ""),
        "prov:generatedAtTime": claim.get("created_at", ""),
        "st:confidenceScore": claim.get("confidence_score", 0.0),
        "st:effectiveConfidence": claim.get("effective_confidence", 0.0),
        "st:hashSHA256": claim.get("hash_sha256", ""),
        "st:domain": claim.get("domain_id", ""),
        "st:status": claim.get("status", ""),
        "schema:inLanguage": claim.get("language", ""),
    }

    # Expiry
    if claim.get("expires_at"):
        entity["st:expiresAt"] = claim["expires_at"]

    # Sources → prov:wasDerivedFrom
    sources = claim.get("source_references", [])
    if sources:
        entity["prov:wasDerivedFrom"] = [
            {"@id": url, "@type": "prov:Entity", "schema:url": url}
            for url in sources
        ]

    # Validators → prov:wasAttributedTo
    validators = claim.get("validated_by", [])
    if validators:
        entity["prov:wasAttributedTo"] = [
            _expert_to_jsonld(v) for v in validators if v.get("name")
        ]

    return entity


# ── Expert → prov:Agent ──────────────────────────────────────────────────────

def _expert_to_jsonld(expert: dict) -> dict:
    """Convert an expert dict to a PROV-O Agent."""
    name = expert.get("name", "unknown")
    return {
        "@id": f"https://swisstruth.org/validators/{name.lower().replace(' ', '-')}",
        "@type": "prov:Agent",
        "schema:name": name,
        "schema:affiliation": expert.get("institution", ""),
    }


# ── Validation → prov:Activity ───────────────────────────────────────────────

def validation_to_jsonld(validation: dict, claim_id: str) -> dict:
    """Convert a validation event to a PROV-O Activity."""
    return {
        "@id": f"https://swisstruth.org/validations/{claim_id}/{validation.get('timestamp', '')}",
        "@type": "prov:Activity",
        "prov:startedAtTime": validation.get("timestamp", ""),
        "prov:endedAtTime": validation.get("timestamp", ""),
        "st:verdict": validation.get("verdict", ""),
        "prov:used": {"@id": f"https://swisstruth.org/api/claims/{claim_id}"},
        "prov:wasAssociatedWith": _expert_to_jsonld({
            "name": validation.get("expert_name", ""),
            "institution": validation.get("expert_institution", ""),
        }),
    }


# ── AnchorRecord → prov:Activity ─────────────────────────────────────────────

def anchor_to_jsonld(anchor: dict) -> dict:
    """Convert a blockchain anchor record to a PROV-O Activity."""
    return {
        "@id": f"https://swisstruth.org/anchors/{anchor.get('id', '')}",
        "@type": "prov:Activity",
        "prov:startedAtTime": anchor.get("anchored_at", ""),
        "st:merkleRoot": anchor.get("merkle_root", ""),
        "st:txHash": anchor.get("tx_hash", ""),
        "st:chain": anchor.get("chain", ""),
        "st:chainId": anchor.get("chain_id"),
        "st:claimCount": anchor.get("claim_count", 0),
        "st:status": anchor.get("status", ""),
        "st:explorerUrl": anchor.get("explorer_url", ""),
    }


# ── Full Audit Trail ─────────────────────────────────────────────────────────

def build_claim_audit_trail(
    claim: dict,
    validations: list[dict],
    anchors: list[dict],
) -> dict:
    """
    Build a complete JSON-LD audit trail for a single claim.

    Includes:
    - The claim as prov:Entity
    - All validation events as prov:Activity
    - Related blockchain anchors as prov:Activity
    """
    claim_id = claim.get("id", "unknown")

    graph = [claim_to_jsonld(claim)]

    for v in validations:
        graph.append(validation_to_jsonld(v, claim_id))

    for a in anchors:
        graph.append(anchor_to_jsonld(a))

    return {
        **PROV_CONTEXT,
        "@graph": graph,
        "st:generatedAt": _now_iso(),
        "st:generatedBy": "Swiss Truth MCP — swisstruth.org",
    }


def build_full_audit_trail(
    claims: list[dict],
    anchors: list[dict],
    validations_by_claim: dict[str, list[dict]] | None = None,
) -> dict:
    """
    Build a complete JSON-LD audit trail for the entire system.

    Includes all certified claims, their validations, and blockchain anchors.
    """
    graph = []

    for claim in claims:
        graph.append(claim_to_jsonld(claim))
        claim_id = claim.get("id", "")
        if validations_by_claim and claim_id in validations_by_claim:
            for v in validations_by_claim[claim_id]:
                graph.append(validation_to_jsonld(v, claim_id))

    for anchor in anchors:
        graph.append(anchor_to_jsonld(anchor))

    return {
        **PROV_CONTEXT,
        "@graph": graph,
        "st:generatedAt": _now_iso(),
        "st:generatedBy": "Swiss Truth MCP — swisstruth.org",
        "st:totalEntities": len(claims),
        "st:totalAnchors": len(anchors),
    }
