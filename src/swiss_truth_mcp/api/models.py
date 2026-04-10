from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ExpertRef(BaseModel):
    name: str
    institution: Optional[str] = None


class ClaimResponse(BaseModel):
    id: str
    text: str
    domain_id: str
    confidence_score: float
    status: Literal["draft", "peer_review", "certified"]
    language: str
    hash_sha256: str
    created_at: str
    last_reviewed: Optional[str] = None
    expires_at: Optional[str] = None
    validated_by: list[ExpertRef] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)


class ClaimSearchResult(ClaimResponse):
    vector_score: float | None = None


class ClaimSubmission(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="Eine klar formulierte, atomare Aussage")
    domain_id: str = Field(..., description="ID der Domäne, z.B. 'ai-ml'")
    language: str = Field(default="de", description="ISO 639-1 Sprachcode")
    source_urls: list[str] = Field(default_factory=list, description="URLs zu Quellenbelegen")


class SubmissionResponse(BaseModel):
    claim_id: str
    status: str
    pre_screen: dict


class DomainResponse(BaseModel):
    id: str
    name: str
    description: str
    language: str
    certified_claims: int


class SearchResponse(BaseModel):
    query: str
    results: list[ClaimSearchResult]
    total: int
