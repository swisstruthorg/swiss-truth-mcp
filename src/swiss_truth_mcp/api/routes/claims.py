from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Header

from swiss_truth_mcp.api.models import ClaimResponse, ClaimSubmission, SubmissionResponse
from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.validation.trust import sign_claim, now_iso, expiry_iso
from swiss_truth_mcp.validation.pre_screen import pre_screen_claim
from swiss_truth_mcp.validation.conflict_detect import detect_conflicts
from swiss_truth_mcp.embeddings import embed_text

router = APIRouter(prefix="/claims", tags=["claims"])


def require_api_key(x_swiss_truth_key: Annotated[Optional[str], Header()] = None) -> str:
    if x_swiss_truth_key != settings.swiss_truth_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_swiss_truth_key


@router.get("/{claim_id}", response_model=ClaimResponse)
async def get_claim(claim_id: str):
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    return ClaimResponse(**claim)


@router.post("", response_model=SubmissionResponse, status_code=201)
async def submit_claim(
    body: ClaimSubmission,
    _: str = Depends(require_api_key),
):
    claim_id = str(uuid.uuid4())

    # Tier-1: AI-gestützte Vorprüfung
    pre_screen = await pre_screen_claim(body.text, body.domain_id, body.source_urls)

    # Embedding berechnen
    embedding = await embed_text(body.text)

    claim_dict = {
        "id": claim_id,
        "text": body.text,
        "domain_id": body.domain_id,
        "confidence_score": 0.0,
        "status": "draft" if not pre_screen["passed"] else "peer_review",
        "language": body.language,
        "source_urls": body.source_urls,
        "created_at": now_iso(),
        "last_reviewed": None,
        "expires_at": None,
        "embedding": embedding,
    }
    claim_dict["hash_sha256"] = sign_claim(claim_dict)

    # Konflikt-Check
    async with get_session() as session:
        conflicts = await detect_conflicts(session, embedding, body.text)
        await queries.create_claim(session, claim_dict)

    pre_screen["conflicts_found"] = len(conflicts)
    if conflicts:
        pre_screen["potential_conflicts"] = [c["id"] for c in conflicts]

    return SubmissionResponse(
        claim_id=claim_id,
        status=claim_dict["status"],
        pre_screen=pre_screen,
    )
