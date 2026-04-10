from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query

from swiss_truth_mcp.api.models import SearchResponse, ClaimSearchResult
from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.embeddings import embed_text

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=2, description="Suchanfrage in natürlicher Sprache"),
    domain: Optional[str] = Query(None, description="Domänen-ID Filter, z.B. 'ai-ml'"),
    min_confidence: float = Query(default=settings.default_min_confidence, ge=0.0, le=1.0),
    limit: int = Query(default=10, ge=1, le=50),
):
    embedding = await embed_text(q)
    async with get_session() as session:
        raw = await queries.search_claims(session, embedding, q, domain, min_confidence, limit)

    results = [ClaimSearchResult(**r) for r in raw]
    return SearchResponse(query=q, results=results, total=len(results))
