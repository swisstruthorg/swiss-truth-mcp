"""
Tests für MCP Tool-Logik — Neo4j wird gemockt.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# search_knowledge
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_knowledge_returns_results():
    mock_claims = [
        {
            "id": "abc-123",
            "text": "RAG reduziert Halluzinationen.",
            "domain_id": "ai-ml",
            "confidence_score": 0.96,
            "status": "certified",
            "language": "de",
            "hash_sha256": "sha256:aabbcc",
            "created_at": "2026-01-01T00:00:00Z",
            "last_reviewed": "2026-01-01T00:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "validated_by": [],
            "source_references": ["https://arxiv.org/abs/2005.11401"],
            "vector_score": 0.95,
        }
    ]

    with (
        patch("swiss_truth_mcp.mcp_server.tools.embed_text", new_callable=AsyncMock) as mock_embed,
        patch("swiss_truth_mcp.mcp_server.tools.get_session") as mock_ctx,
        patch("swiss_truth_mcp.mcp_server.tools.queries.search_claims", new_callable=AsyncMock) as mock_search,
    ):
        mock_embed.return_value = [0.1] * 384
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_search.return_value = mock_claims

        from swiss_truth_mcp.mcp_server.tools import search_knowledge
        result = await search_knowledge("RAG Halluzinationen")

    assert result["total"] == 1
    assert result["results"][0]["confidence"] == 0.96
    assert result["results"][0]["hash"] == "sha256:aabbcc"


# ---------------------------------------------------------------------------
# get_claim
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_not_found():
    with (
        patch("swiss_truth_mcp.mcp_server.tools.get_session") as mock_ctx,
        patch("swiss_truth_mcp.mcp_server.tools.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get.return_value = None

        from swiss_truth_mcp.mcp_server.tools import get_claim
        result = await get_claim("nonexistent-id")

    assert "error" in result


# ---------------------------------------------------------------------------
# list_domains
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_domains_returns_list():
    mock_domains = [
        {"id": "ai-ml", "name": "AI/ML", "description": "...", "language": "de", "certified_claims": 50}
    ]

    with (
        patch("swiss_truth_mcp.mcp_server.tools.get_session") as mock_ctx,
        patch("swiss_truth_mcp.mcp_server.tools.queries.list_domains", new_callable=AsyncMock) as mock_list,
    ):
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_list.return_value = mock_domains

        from swiss_truth_mcp.mcp_server.tools import list_domains
        result = await list_domains()

    assert result["total"] == 1
    assert result["domains"][0]["id"] == "ai-ml"


# ---------------------------------------------------------------------------
# get_claim_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_claim_status_certified():
    mock_claim = {
        "id": "abc-123",
        "status": "certified",
        "confidence_score": 0.95,
        "validated_by": [{"name": "Dr. X", "institution": "ETH"}],
        "created_at": "2026-01-01T00:00:00Z",
        "last_reviewed": "2026-01-01T00:00:00Z",
    }

    with (
        patch("swiss_truth_mcp.mcp_server.tools.get_session") as mock_ctx,
        patch("swiss_truth_mcp.mcp_server.tools.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
    ):
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_get.return_value = mock_claim

        from swiss_truth_mcp.mcp_server.tools import get_claim_status
        result = await get_claim_status("abc-123")

    assert result["status"] == "certified"
    assert result["validators"] == 1
