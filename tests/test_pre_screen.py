import pytest
from unittest.mock import AsyncMock, patch

from swiss_truth_mcp.validation.pre_screen import _fallback_pre_screen, pre_screen_claim


def test_fallback_passes_good_claim():
    result = _fallback_pre_screen(
        "RAG reduziert Halluzinationen in LLMs durch externe Wissensquellen.",
        ["https://arxiv.org/abs/2005.11401"],
    )
    assert result["passed"] is True
    assert result["has_sources"] is True
    assert result["issues"] == []


def test_fallback_fails_no_sources():
    result = _fallback_pre_screen("RAG ist eine Technik.", [])
    assert result["passed"] is False
    assert any("Quellen" in issue for issue in result["issues"])


def test_fallback_fails_question():
    result = _fallback_pre_screen("Was ist RAG?", ["https://example.com"])
    assert result["passed"] is False
    assert any("Frage" in issue for issue in result["issues"])


def test_fallback_fails_too_short():
    result = _fallback_pre_screen("Kurz.", ["https://example.com"])
    assert result["passed"] is False


@pytest.mark.asyncio
async def test_pre_screen_uses_fallback_without_api_key():
    with patch("swiss_truth_mcp.validation.pre_screen.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        result = await pre_screen_claim(
            "RAG reduziert Halluzinationen.", "ai-ml", ["https://arxiv.org"]
        )
    assert "passed" in result
    assert result.get("fallback_mode") is True
