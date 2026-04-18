"""
Tests für kritische Fixes — SEC-01 (Anthropic API Timeout) und SEC-02 (Expired Claims Filter).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# SEC-01: Anthropic API Timeout (Task 1)
# ---------------------------------------------------------------------------

def test_anthropic_timeout_config():
    """Settings().anthropic_timeout_seconds muss den Standardwert 30 zurückgeben."""
    from swiss_truth_mcp.config import Settings
    assert Settings().anthropic_timeout_seconds == 30


def test_anthropic_timeout_env_override():
    """anthropic_timeout_seconds kann per env-var überschrieben werden."""
    from swiss_truth_mcp.config import Settings
    assert Settings(anthropic_timeout_seconds=10).anthropic_timeout_seconds == 10


def test_get_sdk_client_uses_timeout():
    """_get_sdk_client() muss AsyncAnthropic mit timeout=settings.anthropic_timeout_seconds erstellen."""
    import swiss_truth_mcp.validation.pre_screen as ps
    import anthropic

    # Reset singleton so factory runs fresh
    ps._sdk_client = None

    with patch.object(anthropic, "AsyncAnthropic") as mock_cls:
        mock_cls.return_value = MagicMock()
        ps._get_sdk_client()
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert "timeout" in kwargs, "AsyncAnthropic wurde ohne timeout-Parameter aufgerufen"
        # Wert muss dem settings-Default entsprechen (30)
        assert kwargs["timeout"] == 30


# ---------------------------------------------------------------------------
# SEC-02: Expired Claims Filter (Task 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_excludes_expired():
    """search_claims Cypher muss 'expires_at > datetime()' enthalten."""
    from swiss_truth_mcp.db import queries

    captured_cypher = {}

    async def fake_run(cypher, params=None):
        captured_cypher["cypher"] = cypher
        result_mock = AsyncMock()
        result_mock.data = AsyncMock(return_value=[])
        return result_mock

    session = MagicMock()
    session.run = AsyncMock(side_effect=fake_run)

    await queries.search_claims(session, [], "", None, 0.8, 5)

    cypher = captured_cypher.get("cypher", "")
    assert "expires_at > datetime()" in cypher, (
        f"expires_at-Filter fehlt im search_claims-Cypher. Aktueller Cypher:\n{cypher}"
    )


@pytest.mark.asyncio
async def test_get_claim_excludes_expired():
    """get_claim_by_id mit only_live=True muss None zurückgeben wenn der Claim abgelaufen ist."""
    from swiss_truth_mcp.db import queries

    past_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    row_mock = MagicMock()
    row_mock.__getitem__ = lambda self, key: {
        "claim": {
            "id": "abc",
            "text": "Testclaim",
            "question": "",
            "domain_id": "ai-ml",
            "confidence_score": 0.9,
            "status": "certified",
            "language": "de",
            "hash_sha256": "sha256:abc",
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_reviewed": None,
            "expires_at": past_iso,
        },
        "validators": [],
        "sources": [],
    }[key]

    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=row_mock)

    session = MagicMock()
    session.run = AsyncMock(return_value=result_mock)

    result = await queries.get_claim_by_id(session, "abc", only_live=True)
    assert result is None, "Abgelaufener Claim wurde trotz only_live=True zurückgegeben"


@pytest.mark.asyncio
async def test_get_claim_returns_live():
    """get_claim_by_id mit only_live=True muss einen noch gültigen Claim zurückgeben."""
    from swiss_truth_mcp.db import queries

    future_iso = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

    row_mock = MagicMock()
    row_mock.__getitem__ = lambda self, key: {
        "claim": {
            "id": "abc",
            "text": "Testclaim",
            "question": "",
            "domain_id": "ai-ml",
            "confidence_score": 0.9,
            "status": "certified",
            "language": "de",
            "hash_sha256": "sha256:abc",
            "created_at": "2025-01-01T00:00:00+00:00",
            "last_reviewed": None,
            "expires_at": future_iso,
        },
        "validators": [],
        "sources": [],
    }[key]

    result_mock = AsyncMock()
    result_mock.single = AsyncMock(return_value=row_mock)

    session = MagicMock()
    session.run = AsyncMock(return_value=result_mock)

    result = await queries.get_claim_by_id(session, "abc", only_live=True)
    assert result is not None, "Gültiger Claim wurde trotz only_live=True nicht zurückgegeben"
    assert result["id"] == "abc"


@pytest.mark.asyncio
async def test_get_claim_status_expired_returns_not_found():
    """get_claim_status-Tool muss not-found zurückgeben wenn Claim abgelaufen ist."""
    from swiss_truth_mcp.mcp_server import tools
    from swiss_truth_mcp.db.neo4j_client import get_session

    # Mock queries.get_claim_by_id um None zurückzugeben (abgelaufen)
    with patch.object(tools.queries, "get_claim_by_id", new=AsyncMock(return_value=None)):
        # get_session muss auch gemockt werden
        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=None)

        with patch("swiss_truth_mcp.mcp_server.tools.get_session", return_value=session_mock):
            result = await tools.get_claim_status("expired-claim-id")

    assert "error" in result, (
        f"get_claim_status gab Claim-Daten zurück obwohl only_live=True None lieferte: {result}"
    )
