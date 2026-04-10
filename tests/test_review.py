"""
Tests für den Expert-Review-Workflow (routes/review.py + queries).

Neo4j und externe Abhängigkeiten werden gemockt — keine Live-DB nötig.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claim(
    claim_id: str = "test-id-123",
    status: str = "peer_review",
    confidence: float = 0.75,
    validated_by: list | None = None,
    source_references: list | None = None,
) -> dict:
    return {
        "id": claim_id,
        "text": "RAG reduziert Halluzinationen.",
        "domain_id": "ai-ml",
        "language": "de",
        "status": status,
        "confidence_score": confidence,
        "hash_sha256": "sha256:aabbcc112233",
        "created_at": "2026-04-09T10:00:00+00:00",
        "last_reviewed": None,
        "expires_at": "2027-04-09T10:00:00+00:00",
        "domain_name": "AI/ML",
        "source_references": source_references or ["https://arxiv.org/abs/2005.11401"],
        "validated_by": validated_by or [],
    }


def _get_test_client():
    from swiss_truth_mcp.api.main import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /review — Review Queue
# ---------------------------------------------------------------------------

class TestReviewQueue:
    def test_empty_queue(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.list_claims_by_status", new_callable=AsyncMock) as mock_list,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_list.return_value = []

            client = _get_test_client()
            resp = client.get("/review")

        assert resp.status_code == 200
        assert "Keine Claims" in resp.text
        assert "Review Queue" in resp.text

    def test_queue_with_one_claim(self):
        claim = _make_claim()
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.list_claims_by_status", new_callable=AsyncMock) as mock_list,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_list.return_value = [claim]

            client = _get_test_client()
            resp = client.get("/review")

        assert resp.status_code == 200
        assert "RAG reduziert Halluzinationen" in resp.text
        assert "peer_review" in resp.text

    def test_flash_message_displayed(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.list_claims_by_status", new_callable=AsyncMock) as mock_list,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_list.return_value = []

            client = _get_test_client()
            resp = client.get("/review?msg=Claim+zertifiziert+von+Dr.+Meier")

        assert resp.status_code == 200
        assert "Claim zertifiziert von Dr. Meier" in resp.text

    def test_error_flash_displayed(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.list_claims_by_status", new_callable=AsyncMock) as mock_list,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_list.return_value = []

            client = _get_test_client()
            resp = client.get("/review?err=Name+ist+Pflichtfeld")

        assert resp.status_code == 200
        assert "Name ist Pflichtfeld" in resp.text


# ---------------------------------------------------------------------------
# GET /review/certified
# ---------------------------------------------------------------------------

class TestCertifiedList:
    def test_certified_empty(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.list_claims_by_status", new_callable=AsyncMock) as mock_list,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_list.return_value = []

            client = _get_test_client()
            resp = client.get("/review/certified")

        assert resp.status_code == 200
        assert "Zertifizierte Claims" in resp.text

    def test_certified_shows_claim_and_hash(self):
        claim = _make_claim(status="certified", confidence=0.95)
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.list_claims_by_status", new_callable=AsyncMock) as mock_list,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_list.return_value = [claim]

            client = _get_test_client()
            resp = client.get("/review/certified")

        assert resp.status_code == 200
        assert "sha256:aabbcc112233" in resp.text
        assert "RAG reduziert Halluzinationen" in resp.text


# ---------------------------------------------------------------------------
# GET /review/{claim_id} — Detail
# ---------------------------------------------------------------------------

class TestReviewDetail:
    def test_detail_shows_claim(self):
        claim = _make_claim()
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.embed_text", new_callable=AsyncMock) as mock_embed,
            patch("swiss_truth_mcp.api.routes.review.queries.find_conflicting_claims", new_callable=AsyncMock) as mock_conflicts,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim
            mock_embed.return_value = [0.0] * 384
            mock_conflicts.return_value = []

            client = _get_test_client()
            resp = client.get(f"/review/{claim['id']}")

        assert resp.status_code == 200
        assert "RAG reduziert Halluzinationen" in resp.text
        assert "sha256:aabbcc112233" in resp.text
        assert "Expertenvalidierung" in resp.text

    def test_detail_404_on_missing_claim(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = None

            client = TestClient(_get_test_client().app, raise_server_exceptions=False)
            resp = client.get("/review/nonexistent-id")

        assert resp.status_code == 404

    def test_detail_shows_conflict_warning(self):
        claim = _make_claim()
        conflict = {
            "id": "other-claim-99",
            "text": "RAG mindert Halluzinationen signifikant.",
            "confidence_score": 0.90,
            "similarity": 0.95,
        }
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.embed_text", new_callable=AsyncMock) as mock_embed,
            patch("swiss_truth_mcp.api.routes.review.queries.find_conflicting_claims", new_callable=AsyncMock) as mock_conflicts,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim
            mock_embed.return_value = [0.0] * 384
            mock_conflicts.return_value = [conflict]

            client = _get_test_client()
            resp = client.get(f"/review/{claim['id']}")

        assert resp.status_code == 200
        assert "Mögliche Konflikte" in resp.text
        assert "95%" in resp.text


# ---------------------------------------------------------------------------
# POST /review/{claim_id}/approve
# ---------------------------------------------------------------------------

class TestApproveClaim:
    def test_approve_redirects_to_queue(self):
        claim = _make_claim()
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.queries.validate_claim", new_callable=AsyncMock) as mock_validate,
        ):
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim
            mock_validate.return_value = None
            mock_session.run = AsyncMock()

            client = TestClient(_get_test_client().app, raise_server_exceptions=True)
            resp = client.post(
                f"/review/{claim['id']}/approve",
                data={"expert_name": "Dr. Anna Meier", "expert_institution": "ETH Zürich", "confidence": "0.92"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert "/review" in resp.headers["location"]
        assert "zertifiziert" in resp.headers["location"]

    def test_approve_missing_name_redirects_with_error(self):
        client = _get_test_client()
        resp = client.post(
            "/review/test-id-123/approve",
            data={"expert_name": "   ", "confidence": "0.85"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert "err=" in resp.headers["location"]

    def test_approve_clamps_confidence_above_1(self):
        """Confidence > 1.0 must be clamped to 1.0."""
        claim = _make_claim()
        captured_confidence = {}

        async def capture_validate(session, *, claim_id, expert_name, expert_institution, verdict, confidence_score, reviewed_at):
            captured_confidence["value"] = confidence_score

        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.queries.validate_claim", side_effect=capture_validate),
        ):
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim
            mock_session.run = AsyncMock()

            client = _get_test_client()
            client.post(
                f"/review/{claim['id']}/approve",
                data={"expert_name": "Dr. X", "confidence": "1.5"},
                follow_redirects=False,
            )

        assert captured_confidence.get("value", 999) <= 1.0

    def test_approve_clamps_confidence_below_0(self):
        """Confidence < 0.0 must be clamped to 0.0."""
        claim = _make_claim()
        captured_confidence = {}

        async def capture_validate(session, *, claim_id, expert_name, expert_institution, verdict, confidence_score, reviewed_at):
            captured_confidence["value"] = confidence_score

        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.queries.validate_claim", side_effect=capture_validate),
        ):
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim
            mock_session.run = AsyncMock()

            client = _get_test_client()
            client.post(
                f"/review/{claim['id']}/approve",
                data={"expert_name": "Dr. X", "confidence": "-0.5"},
                follow_redirects=False,
            )

        assert captured_confidence.get("value", -999) >= 0.0

    def test_approve_404_on_missing_claim(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = None

            client = TestClient(_get_test_client().app, raise_server_exceptions=False)
            resp = client.post(
                "/review/nonexistent/approve",
                data={"expert_name": "Dr. X", "confidence": "0.9"},
                follow_redirects=False,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /review/{claim_id}/reject
# ---------------------------------------------------------------------------

class TestRejectClaim:
    def test_reject_redirects_to_queue(self):
        claim = _make_claim()
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.queries.validate_claim", new_callable=AsyncMock) as mock_validate,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim
            mock_validate.return_value = None

            client = _get_test_client()
            resp = client.post(
                f"/review/{claim['id']}/reject",
                data={"expert_name": "Dr. Müller", "expert_institution": "EPFL"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert "/review" in resp.headers["location"]
        assert "abgelehnt" in resp.headers["location"]

    def test_reject_without_name_uses_anonym(self):
        """Empty expert_name falls back to 'Anonym'."""
        claim = _make_claim()
        captured_name = {}

        async def capture_validate(session, *, claim_id, expert_name, expert_institution, verdict, confidence_score, reviewed_at):
            captured_name["value"] = expert_name

        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.queries.validate_claim", side_effect=capture_validate),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim

            client = _get_test_client()
            client.post(
                f"/review/{claim['id']}/reject",
                data={"expert_name": "", "expert_institution": ""},
                follow_redirects=False,
            )

        assert captured_name.get("value") == "Anonym"

    def test_reject_sets_confidence_zero(self):
        """Reject always sets confidence_score = 0.0."""
        claim = _make_claim(confidence=0.85)
        captured = {}

        async def capture_validate(session, *, claim_id, expert_name, expert_institution, verdict, confidence_score, reviewed_at):
            captured["confidence"] = confidence_score
            captured["verdict"] = verdict

        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
            patch("swiss_truth_mcp.api.routes.review.queries.validate_claim", side_effect=capture_validate),
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = claim

            client = _get_test_client()
            client.post(
                f"/review/{claim['id']}/reject",
                data={"expert_name": "Dr. X"},
                follow_redirects=False,
            )

        assert captured.get("confidence") == 0.0
        assert captured.get("verdict") == "rejected"

    def test_reject_404_on_missing_claim(self):
        with (
            patch("swiss_truth_mcp.api.routes.review.get_session") as mock_ctx,
            patch("swiss_truth_mcp.api.routes.review.queries.get_claim_by_id", new_callable=AsyncMock) as mock_get,
        ):
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_get.return_value = None

            client = TestClient(_get_test_client().app, raise_server_exceptions=False)
            resp = client.post(
                "/review/nonexistent/reject",
                data={"expert_name": "Dr. X"},
                follow_redirects=False,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# validate_claim query (unit)
# ---------------------------------------------------------------------------

class TestValidateClaimQuery:
    @pytest.mark.asyncio
    async def test_approved_sets_status_certified(self):
        mock_session = AsyncMock()
        mock_session.run = AsyncMock()

        from swiss_truth_mcp.db.queries import validate_claim
        from swiss_truth_mcp.validation.trust import now_iso

        await validate_claim(
            session=mock_session,
            claim_id="abc-123",
            expert_name="Dr. Anna Meier",
            expert_institution="ETH Zürich",
            verdict="approved",
            confidence_score=0.92,
            reviewed_at=now_iso(),
        )

        assert mock_session.run.called
        call_args = mock_session.run.call_args
        # The Cypher string should set status = 'certified' for approved
        cypher = call_args[0][0]
        params = call_args[0][1]
        assert params["status"] == "certified"
        assert params["verdict"] == "approved"
        assert params["confidence"] == 0.92

    @pytest.mark.asyncio
    async def test_rejected_sets_status_draft(self):
        mock_session = AsyncMock()
        mock_session.run = AsyncMock()

        from swiss_truth_mcp.db.queries import validate_claim
        from swiss_truth_mcp.validation.trust import now_iso

        await validate_claim(
            session=mock_session,
            claim_id="abc-123",
            expert_name="Dr. Müller",
            expert_institution="EPFL",
            verdict="rejected",
            confidence_score=0.0,
            reviewed_at=now_iso(),
        )

        call_args = mock_session.run.call_args
        params = call_args[0][1]
        assert params["status"] == "draft"
        assert params["verdict"] == "rejected"
        assert params["confidence"] == 0.0
