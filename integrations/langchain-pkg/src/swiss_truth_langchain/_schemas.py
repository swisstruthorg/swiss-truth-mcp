"""Input schemas for Swiss Truth LangChain tools."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SearchInput(BaseModel):
    query: str = Field(description="Natural-language question or keyword to search the certified knowledge base.")
    domain: Optional[str] = Field(default=None, description="Optional domain filter (e.g. 'quantum-computing', 'ai-ml').")
    limit: int = Field(default=5, description="Max results to return (1-20).")
    min_confidence: float = Field(default=0.8, description="Minimum confidence threshold 0.0-1.0.")


class VerifyInput(BaseModel):
    claim_text: str = Field(description="The factual claim to verify.")
    domain: Optional[str] = Field(default=None, description="Optional domain hint (e.g. 'eu-health', 'swiss-law').")


class SubmitInput(BaseModel):
    text: str = Field(description="The factual claim text (one atomic fact per claim).")
    question: str = Field(default="", description="The question this claim answers.")
    source_url: str = Field(default="", description="Primary source URL backing this claim.")
    domain_id: str = Field(description="Domain to file it under, e.g. 'eu-law'.")
    confidence: float = Field(default=0.90, description="Your confidence score (0.0-1.0).")


class ClaimIdInput(BaseModel):
    claim_id: str = Field(description="UUID of the claim.")


class BatchVerifyInput(BaseModel):
    claims: list[str] = Field(description="List of factual statements to verify. Max 20 items.")
    domain: Optional[str] = Field(default=None, description="Optional domain filter applied to all claims.")


class VerifyResponseInput(BaseModel):
    text: str = Field(description="The full response text to check for hallucination risk.")
    domain: Optional[str] = Field(default=None, description="Optional domain filter.")


class FindContradictionsInput(BaseModel):
    claim_text: str = Field(description="The factual statement to check for contradictions.")
    domain: Optional[str] = Field(default=None, description="Optional domain filter.")


class EmptyInput(BaseModel):
    pass
