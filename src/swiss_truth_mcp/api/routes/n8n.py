"""
n8n-Integration — optimierte Endpunkte für Workflow-Automatisierung.

Alle Routen unter /n8n sind für den Einsatz in n8n HTTP-Request-Nodes
optimiert: schlanke Payloads, klare Fehlermeldungen, keine HTML.

Endpunkte:
  POST /n8n/fact-check          — Text gegen zertifizierte Claims prüfen
  POST /n8n/submit              — Claim einreichen (vereinfacht)
  GET  /n8n/status/{claim_id}   — Claim-Status abfragen
  GET  /n8n/digest              — Neu zertifizierte Claims seit Zeitstempel
  GET  /n8n/info                — Verfügbare Domains & Statistiken
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.embeddings import embed_text
from swiss_truth_mcp.validation.trust import sign_claim, now_iso, expiry_iso
from swiss_truth_mcp.integrations.webhook import fire_event

import uuid

router = APIRouter(prefix="/n8n", tags=["n8n"])

_api_key_header = APIKeyHeader(name="X-Swiss-Truth-Key", auto_error=False)


def _require_key(key: Optional[str] = Depends(_api_key_header)) -> str:
    if key != settings.swiss_truth_api_key:
        raise HTTPException(status_code=401, detail="Ungültiger API-Key")
    return key


# ---------------------------------------------------------------------------
# Request / Response Modelle
# ---------------------------------------------------------------------------

class FactCheckRequest(BaseModel):
    text: str = Field(..., min_length=10, description="Zu prüfender Text")
    domain_id: Optional[str] = Field(None, description="Domain-Filter (z.B. 'ai-ml')")
    min_confidence: float = Field(0.85, ge=0.0, le=1.0)
    top_k: int = Field(3, ge=1, le=10)


class FactCheckResult(BaseModel):
    verified: bool
    trust_score: float
    verdict: str
    supporting_claims: list[dict[str, Any]]
    query_text: str


class SubmitClaimRequest(BaseModel):
    text: str = Field(..., min_length=20)
    domain_id: str = Field("ai-ml")
    language: str = Field("de")
    source_urls: list[str] = Field(default_factory=list)
    confidence_score: float = Field(0.85, ge=0.0, le=1.0)


class SubmitClaimResponse(BaseModel):
    claim_id: str
    status: str
    confidence_score: float
    hash_sha256: str
    check_url: str
    message: str


class ClaimStatusResponse(BaseModel):
    claim_id: str
    status: str
    certified: bool
    confidence_score: float
    domain_id: str
    validated_by: list[dict[str, Any]]
    created_at: Optional[str]
    last_reviewed: Optional[str]
    expires_at: Optional[str]


class DigestItem(BaseModel):
    id: str
    text: str
    domain_id: str
    confidence_score: float
    hash_sha256: str
    certified_at: Optional[str]
    validated_by: list[dict[str, Any]]


class DigestResponse(BaseModel):
    count: int
    since: str
    domain_id: Optional[str]
    claims: list[DigestItem]


# ---------------------------------------------------------------------------
# GET /n8n/info  — Übersicht für n8n-Konfiguration
# ---------------------------------------------------------------------------

@router.get("/info")
async def n8n_info() -> dict[str, Any]:
    """
    Gibt verfügbare Domains und Basis-Statistiken zurück.
    Nützlich zum Einrichten eines n8n-Workflows.
    """
    async with get_session() as session:
        domains = await queries.list_domains(session)

    return {
        "service": "Swiss Truth MCP",
        "version": "0.1.0",
        "api_base": settings.public_base_url,
        "n8n_endpoints": {
            "fact_check":   "POST /n8n/fact-check",
            "submit_claim": "POST /n8n/submit",
            "check_status": "GET  /n8n/status/{claim_id}",
            "digest":       "GET  /n8n/digest?since=YYYY-MM-DD&domain=ai-ml",
            "info":         "GET  /n8n/info",
        },
        "domains": [
            {"id": d["id"], "name": d["name"], "certified_claims": d["certified_claims"]}
            for d in domains
        ],
        "total_certified": sum(d["certified_claims"] for d in domains),
    }


# ---------------------------------------------------------------------------
# POST /n8n/fact-check  — Kernfunktion: Text gegen Wissensbasis prüfen
# ---------------------------------------------------------------------------

@router.post("/fact-check", response_model=FactCheckResult)
async def fact_check(body: FactCheckRequest) -> FactCheckResult:
    """
    Prüft einen Text gegen zertifizierte Claims in der Wissensbasis.

    Gibt einen Trust-Score und unterstützende Claims zurück.
    Ideal als erster Schritt in n8n-Fact-Checking-Pipelines.

    trust_score:
      >= 0.90  → verified=True,  verdict='bestätigt'
      >= 0.70  → verified=False, verdict='teilweise_belegt'
      <  0.70  → verified=False, verdict='nicht_belegt'
    """
    embedding = await embed_text(body.text)

    async with get_session() as session:
        results = await queries.search_claims(
            session,
            query_embedding=embedding,
            query_text=body.text,
            domain_id=body.domain_id,
            min_confidence=body.min_confidence,
            limit=body.top_k,
        )

    if not results:
        return FactCheckResult(
            verified=False,
            trust_score=0.0,
            verdict="nicht_belegt",
            supporting_claims=[],
            query_text=body.text,
        )

    # Trust-Score = gewichteter Durchschnitt aus vector_score × confidence
    scores = [
        r.get("vector_score", 0.5) * r.get("confidence_score", 0.8)
        for r in results
    ]
    trust_score = round(sum(scores) / len(scores), 4)

    if trust_score >= 0.90:
        verdict = "bestätigt"
        verified = True
    elif trust_score >= 0.70:
        verdict = "teilweise_belegt"
        verified = False
    else:
        verdict = "nicht_belegt"
        verified = False

    supporting = [
        {
            "id":               r["id"],
            "text":             r["text"],
            "domain_id":        r["domain_id"],
            "confidence_score": r["confidence_score"],
            "similarity":       round(r.get("vector_score", 0.0), 4),
            "hash_sha256":      r["hash_sha256"],
            "validated_by":     r.get("validated_by", []),
            "source_references": r.get("source_references", []),
        }
        for r in results
    ]

    return FactCheckResult(
        verified=verified,
        trust_score=trust_score,
        verdict=verdict,
        supporting_claims=supporting,
        query_text=body.text,
    )


# ---------------------------------------------------------------------------
# POST /n8n/submit  — Claim einreichen (vereinfacht, API-Key required)
# ---------------------------------------------------------------------------

@router.post("/submit", response_model=SubmitClaimResponse)
async def submit_claim(
    body: SubmitClaimRequest,
    _key: str = Depends(_require_key),
) -> SubmitClaimResponse:
    """
    Vereinfachte Claim-Einreichung für n8n-Workflows.
    Kein Pre-Screening, direkter Eintrag als peer_review.
    Sendet ein Webhook-Event an N8N_WEBHOOK_URL (falls konfiguriert).
    """
    embedding = await embed_text(body.text)
    claim_id = str(uuid.uuid4())
    created_at = now_iso()

    claim: dict[str, Any] = {
        "id":               claim_id,
        "text":             body.text,
        "domain_id":        body.domain_id,
        "confidence_score": body.confidence_score,
        "status":           "peer_review",
        "language":         body.language,
        "hash_sha256":      "",
        "created_at":       created_at,
        "last_reviewed":    None,
        "expires_at":       expiry_iso(days=settings.default_ttl_days),
        "embedding":        embedding,
        "source_urls":      body.source_urls,
    }
    claim["hash_sha256"] = sign_claim(claim)

    async with get_session() as session:
        await queries.create_claim(session, claim)

    # Webhook-Event (fire-and-forget)
    asyncio.create_task(fire_event("claim.submitted", {
        "claim_id":   claim_id,
        "domain_id":  body.domain_id,
        "text":       body.text[:200],
        "status":     "peer_review",
        "created_at": created_at,
        "review_url": f"{settings.public_base_url}/review/{claim_id}",
    }))

    return SubmitClaimResponse(
        claim_id=claim_id,
        status="peer_review",
        confidence_score=body.confidence_score,
        hash_sha256=claim["hash_sha256"],
        check_url=f"{settings.public_base_url}/n8n/status/{claim_id}",
        message="Claim eingereicht. Status via check_url abrufbar.",
    )


# ---------------------------------------------------------------------------
# GET /n8n/status/{claim_id}  — Claim-Status abfragen
# ---------------------------------------------------------------------------

@router.get("/status/{claim_id}", response_model=ClaimStatusResponse)
async def claim_status(claim_id: str) -> ClaimStatusResponse:
    """
    Gibt den aktuellen Status eines Claims zurück.
    Ideal zum Polling in n8n nach claim.submitted.
    """
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)

    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id!r} nicht gefunden")

    return ClaimStatusResponse(
        claim_id=claim["id"],
        status=claim["status"],
        certified=claim["status"] == "certified",
        confidence_score=claim.get("confidence_score", 0.0),
        domain_id=claim.get("domain_id", ""),
        validated_by=claim.get("validated_by", []),
        created_at=claim.get("created_at"),
        last_reviewed=claim.get("last_reviewed"),
        expires_at=claim.get("expires_at"),
    )


# ---------------------------------------------------------------------------
# GET /n8n/digest  — Neu zertifizierte Claims seit Datum
# ---------------------------------------------------------------------------

@router.get("/digest", response_model=DigestResponse)
async def digest(
    since: str = Query(
        default="",
        description="ISO-Datum ab dem gesucht wird (z.B. 2026-04-01). Leer = heute.",
    ),
    domain: Optional[str] = Query(None, description="Domain-Filter"),
    limit: int = Query(50, ge=1, le=200),
) -> DigestResponse:
    """
    Gibt alle seit 'since' zertifizierten Claims zurück.
    Ideal für tägliche n8n-Digest-Workflows (Cron-Trigger).
    """
    # Default: ISO-Datum von heute
    if not since:
        since = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Datum normalisieren zu ISO-Datetime
    try:
        if len(since) == 10:  # YYYY-MM-DD
            since_dt = since + "T00:00:00+00:00"
        else:
            since_dt = since
        # Validierung
        datetime.fromisoformat(since_dt.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Ungültiges Datumsformat: {since!r}. Erwartet YYYY-MM-DD oder ISO-8601."
        )

    async with get_session() as session:
        result = await session.run(
            """
            MATCH (c:Claim {status: 'certified'})
            WHERE c.last_reviewed >= $since
              AND ($domain IS NULL OR c.domain_id = $domain)
            OPTIONAL MATCH (e:Expert)-[:VALIDATES]->(c)
            WITH c, collect(DISTINCT {name: e.name, institution: e.institution}) AS validators
            RETURN c {
                .id, .text, .domain_id, .confidence_score,
                .hash_sha256, .last_reviewed, .expires_at
            } AS claim, validators
            ORDER BY c.last_reviewed DESC
            LIMIT $limit
            """,
            {"since": since_dt, "domain": domain, "limit": limit},
        )
        rows = await result.data()

    claims = [
        DigestItem(
            id=row["claim"]["id"],
            text=row["claim"]["text"],
            domain_id=row["claim"]["domain_id"],
            confidence_score=row["claim"]["confidence_score"],
            hash_sha256=row["claim"]["hash_sha256"],
            certified_at=row["claim"].get("last_reviewed"),
            validated_by=[v for v in row["validators"] if v.get("name")],
        )
        for row in rows
    ]

    return DigestResponse(
        count=len(claims),
        since=since_dt,
        domain_id=domain,
        claims=claims,
    )
