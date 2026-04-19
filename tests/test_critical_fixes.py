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

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_cls.return_value = MagicMock()
        ps._get_sdk_client()
        mock_cls.assert_called_once()
        call_kwargs = mock_cls.call_args[1] if mock_cls.call_args[1] else {}
        call_args = mock_cls.call_args[0] if mock_cls.call_args[0] else ()
        # timeout kann als positional oder keyword arg übergeben werden
        all_kwargs = dict(zip(["api_key", "timeout"], call_args))
        all_kwargs.update(call_kwargs)
        assert "timeout" in all_kwargs, (
            f"AsyncAnthropic wurde ohne timeout-Parameter aufgerufen. Calls: {mock_cls.call_args}"
        )
        assert all_kwargs["timeout"] == 30


def test_get_http_client_uses_timeout():
    """_get_http_client() muss httpx.AsyncClient mit timeout=float(settings.anthropic_timeout_seconds) erstellen."""
    import swiss_truth_mcp.validation.pre_screen as ps
    import httpx as _httpx
    from unittest.mock import patch, MagicMock

    # Reset cached singleton so the factory runs fresh
    ps._http_client = None

    fake_client = MagicMock()
    with patch("swiss_truth_mcp.validation.pre_screen.httpx.AsyncClient", return_value=fake_client) as mock_cls:
        ps._get_http_client()
        assert mock_cls.called, "_get_http_client() did not call httpx.AsyncClient"
        call_kwargs = mock_cls.call_args[1] if mock_cls.call_args[1] else {}
        timeout_arg = call_kwargs.get("timeout")
        assert timeout_arg is not None, "httpx.AsyncClient was called without a timeout keyword argument"
        # httpx.Timeout stores the connect/read/write/pool values; default is the first arg
        assert timeout_arg.read == float(ps.settings.anthropic_timeout_seconds), (
            f"Expected read timeout {float(ps.settings.anthropic_timeout_seconds)}, got {timeout_arg.read}"
        )
    # Restore global
    ps._http_client = None


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


# ---------------------------------------------------------------------------
# SEC-03: SSRF Validation (Plan 01-02 Task 1)
# ---------------------------------------------------------------------------

def test_ssrf_blocks_loopback_v4():
    """validate_webhook_url muss 127.0.0.1 ablehnen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://127.0.0.1/hook")


def test_ssrf_blocks_loopback_hostname(monkeypatch):
    """validate_webhook_url muss localhost ablehnen (DNS gemockt)."""
    from swiss_truth_mcp.validation import ssrf
    monkeypatch.setattr("swiss_truth_mcp.validation.ssrf.socket.gethostbyname",
                        lambda h: "127.0.0.1")
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://localhost/hook")


def test_ssrf_blocks_rfc1918_10():
    """validate_webhook_url muss 10.x.x.x ablehnen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://10.0.0.1/hook")


def test_ssrf_blocks_rfc1918_192():
    """validate_webhook_url muss 192.168.x.x ablehnen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://192.168.1.100/hook")


def test_ssrf_blocks_rfc1918_172():
    """validate_webhook_url muss 172.16.x.x ablehnen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://172.16.0.1/hook")


def test_ssrf_blocks_link_local():
    """validate_webhook_url muss 169.254.169.254 (AWS-Metadata) ablehnen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://169.254.169.254/meta")


def test_ssrf_blocks_ipv6_loopback():
    """validate_webhook_url muss IPv6 ::1 ablehnen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    with pytest.raises(ValueError):
        validate_webhook_url("http://[::1]/hook")


def test_ssrf_allows_public(monkeypatch):
    """validate_webhook_url muss öffentliche URLs durchlassen."""
    monkeypatch.setattr("swiss_truth_mcp.validation.ssrf.socket.gethostbyname",
                        lambda h: "93.184.216.34")  # example.com
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    validate_webhook_url("https://example.com/hook")  # darf nicht raisen


def test_ssrf_allows_public_ip():
    """validate_webhook_url muss öffentliche IPs durchlassen."""
    from swiss_truth_mcp.validation.ssrf import validate_webhook_url
    validate_webhook_url("https://8.8.8.8/hook")  # darf nicht raisen


def test_webhook_secret_default():
    """Settings().webhook_secret leer → effective_webhook_secret gibt secret_key zurück."""
    from swiss_truth_mcp.config import Settings
    s = Settings()
    assert s.effective_webhook_secret == s.secret_key


# ---------------------------------------------------------------------------
# SEC-03 / SEC-04: SSRF in feed.py + HMAC in webhook.py (Plan 01-02 Task 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_subscribe_webhook_rejects_private_ip():
    """subscribe_webhook muss bei privater IP eine HTTPException(422) raisen."""
    # Direkte Unit-Test ohne FastAPI TestClient (fastapi nicht im Test-env installiert)
    from swiss_truth_mcp.api.routes.feed import subscribe_webhook, WebhookSubscribeRequest
    from pydantic import HttpUrl

    body = WebhookSubscribeRequest(url=HttpUrl("http://10.0.0.1/hook"))

    with patch("swiss_truth_mcp.api.routes.feed.validate_webhook_url",
               side_effect=ValueError("private IP")):
        try:
            await subscribe_webhook(body)
            assert False, "HTTPException wurde nicht geraist"
        except Exception as exc:
            # Prüfe status_code + detail (funktioniert mit echter HTTPException und dem Stub)
            assert hasattr(exc, "status_code"), f"Exception hat kein status_code-Attribut: {type(exc)}"
            assert exc.status_code == 422, f"Falscher status_code: {exc.status_code}"
            assert "private" in str(exc.detail).lower(), f"detail enthält nicht 'private': {exc.detail}"


@pytest.mark.asyncio
async def test_subscribe_webhook_accepts_public():
    """subscribe_webhook muss öffentliche URLs akzeptieren (kein Fehler)."""
    from swiss_truth_mcp.api.routes.feed import subscribe_webhook, WebhookSubscribeRequest
    from pydantic import HttpUrl

    body = WebhookSubscribeRequest(url=HttpUrl("https://example.com/hook"))

    with patch("swiss_truth_mcp.api.routes.feed.validate_webhook_url", return_value=None):
        session_mock = AsyncMock()
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=None)
        with patch("swiss_truth_mcp.api.routes.feed.get_session", return_value=session_mock):
            with patch("swiss_truth_mcp.api.routes.feed.queries.create_webhook_subscription",
                       new=AsyncMock(return_value=None)):
                result = await subscribe_webhook(body)
    assert "id" in result
    assert result["subscribed_to"] == "https://example.com/hook"


@pytest.mark.asyncio
async def test_fire_event_sends_hmac(monkeypatch):
    """fire_event() muss X-Signature Header mit sha256= Prefix senden."""
    import swiss_truth_mcp.integrations.webhook as wh
    monkeypatch.setattr("swiss_truth_mcp.integrations.webhook.settings",
                        type("S", (), {
                            "n8n_webhook_url": "https://n8n.example.com/hook",
                            "effective_webhook_secret": "test-secret",
                        })())

    captured_headers = {}

    async def fake_post(url, *, content=None, headers=None, **kwargs):
        captured_headers.update(headers or {})
        resp = MagicMock()
        resp.status_code = 200
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    with patch("swiss_truth_mcp.integrations.webhook.httpx.AsyncClient",
               return_value=mock_client):
        await wh.fire_event("claim.certified", {"claim_id": "abc"})

    assert "X-Signature" in captured_headers, "X-Signature Header fehlt in fire_event"
    assert captured_headers["X-Signature"].startswith("sha256="), \
        f"X-Signature hat falsches Format: {captured_headers['X-Signature']}"


@pytest.mark.asyncio
async def test_fire_subscribers_sends_hmac(monkeypatch):
    """fire_subscribers() muss X-Signature Header auf Subscriber-POSTs senden."""
    import swiss_truth_mcp.integrations.webhook as wh
    monkeypatch.setattr("swiss_truth_mcp.integrations.webhook.settings",
                        type("S", (), {
                            "n8n_webhook_url": "",
                            "effective_webhook_secret": "test-secret",
                        })())

    captured_headers = {}

    async def fake_post(url, *, content=None, headers=None, **kwargs):
        captured_headers.update(headers or {})
        resp = MagicMock()
        resp.status_code = 200
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    mock_subs = [{"url": "https://receiver.example.com/hook", "label": "test",
                  "domain_filter": None}]

    session_mock = AsyncMock()
    session_mock.__aenter__ = AsyncMock(return_value=session_mock)
    session_mock.__aexit__ = AsyncMock(return_value=None)

    with patch("swiss_truth_mcp.integrations.webhook.httpx.AsyncClient",
               return_value=mock_client):
        # queries ist ein lazy import in fire_subscribers — patch am Quellmodul
        with patch("swiss_truth_mcp.db.queries.list_webhook_subscriptions",
                   new=AsyncMock(return_value=mock_subs)):
            with patch("swiss_truth_mcp.db.neo4j_client.get_session",
                       return_value=session_mock):
                await wh.fire_subscribers("claim.certified", {"domain_id": "ai-ml"})

    assert "X-Signature" in captured_headers, "X-Signature Header fehlt in fire_subscribers"
    assert captured_headers["X-Signature"].startswith("sha256="), \
        f"X-Signature hat falsches Format: {captured_headers['X-Signature']}"


# ---------------------------------------------------------------------------
# SEC-05: Renewal Cost Cap (Plan 01-03)
# ---------------------------------------------------------------------------

def test_cost_cap_starts_at_zero():
    """DailySpendCap.current_spend muss beim Start 0.0 sein."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    cap = DailySpendCap()
    assert cap.current_spend == 0.0


def test_cost_cap_record_spend():
    """record_spend() muss den Betrag kumulativ addieren."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    cap = DailySpendCap()
    cap.record_spend(3.0)
    cap.record_spend(2.5)
    assert cap.current_spend == 5.5


def test_cost_cap_not_reached():
    """is_cap_reached() muss False zurückgeben wenn Verbrauch unter dem Cap liegt."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    from swiss_truth_mcp.config import Settings
    cap = DailySpendCap()
    cap.record_spend(5.0)
    # Default cap = 10.0
    assert not cap.is_cap_reached()


def test_cost_cap_reached():
    """is_cap_reached() muss True zurückgeben wenn Verbrauch >= MAX_RENEWAL_SPEND_USD."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    cap = DailySpendCap()
    cap.record_spend(10.01)
    assert cap.is_cap_reached()


def test_cost_cap_check_raises():
    """check_cap_or_raise() muss CapExceededError werfen wenn Cap überschritten."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap, CapExceededError
    cap = DailySpendCap()
    cap.record_spend(10.01)
    with pytest.raises(CapExceededError):
        cap.check_cap_or_raise()


def test_cost_cap_check_passes():
    """check_cap_or_raise() darf keine Exception werfen wenn Cap nicht erreicht."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    cap = DailySpendCap()
    cap.record_spend(5.0)
    cap.check_cap_or_raise()  # darf nicht raisen


def test_cost_cap_reset():
    """reset() muss den Tagesverbrauch auf 0.0 zurücksetzen."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    cap = DailySpendCap()
    cap.record_spend(15.0)
    cap.reset()
    assert cap.current_spend == 0.0
    assert not cap.is_cap_reached()


def test_max_renewal_spend_config():
    """Settings().max_renewal_spend_usd muss den Standardwert 10.0 haben."""
    from swiss_truth_mcp.config import Settings
    assert Settings().max_renewal_spend_usd == 10.0


# ---------------------------------------------------------------------------
# SEC-05: APScheduler in lifespan (Plan 01-03 Task 2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daily_cap_reset_fn():
    """reset() nach record_spend() muss current_spend auf 0.0 setzen."""
    from swiss_truth_mcp.renewal.cost_cap import DailySpendCap
    cap = DailySpendCap()
    cap.record_spend(5.0)
    cap.reset()
    assert cap.current_spend == 0.0


@pytest.mark.asyncio
async def test_scheduler_starts_and_stops():
    """lifespan muss AsyncIOScheduler starten und bei Exit herunterfahren."""
    from unittest.mock import patch, MagicMock, AsyncMock
    from fastapi import FastAPI

    mock_scheduler = MagicMock()
    mock_schema = AsyncMock()
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_mcp_cm = MagicMock()
    mock_mcp_cm.__aenter__ = AsyncMock(return_value=None)
    mock_mcp_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("swiss_truth_mcp.api.main.AsyncIOScheduler", return_value=mock_scheduler):
        with patch("swiss_truth_mcp.api.main.get_session", return_value=mock_session_cm):
            with patch("swiss_truth_mcp.api.main.schema.setup_schema", new=AsyncMock()):
                with patch("swiss_truth_mcp.api.main.mcp_session_manager.run", return_value=mock_mcp_cm):
                    with patch("swiss_truth_mcp.api.main.close_driver", new=AsyncMock()):
                        from swiss_truth_mcp.api.main import lifespan
                        dummy_app = FastAPI()
                        async with lifespan(dummy_app):
                            pass

    mock_scheduler.start.assert_called_once()
    mock_scheduler.shutdown.assert_called_once_with(wait=False)


@pytest.mark.asyncio
async def test_scheduler_reset_job_registered():
    """lifespan muss einen Job mit id='daily_cap_reset' registrieren."""
    from unittest.mock import patch, MagicMock, AsyncMock, call
    from fastapi import FastAPI

    mock_scheduler = MagicMock()
    mock_session_cm = MagicMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=None)

    mock_mcp_cm = MagicMock()
    mock_mcp_cm.__aenter__ = AsyncMock(return_value=None)
    mock_mcp_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("swiss_truth_mcp.api.main.AsyncIOScheduler", return_value=mock_scheduler):
        with patch("swiss_truth_mcp.api.main.get_session", return_value=mock_session_cm):
            with patch("swiss_truth_mcp.api.main.schema.setup_schema", new=AsyncMock()):
                with patch("swiss_truth_mcp.api.main.mcp_session_manager.run", return_value=mock_mcp_cm):
                    with patch("swiss_truth_mcp.api.main.close_driver", new=AsyncMock()):
                        from swiss_truth_mcp.api.main import lifespan
                        dummy_app = FastAPI()
                        async with lifespan(dummy_app):
                            pass

    # Verify add_job was called with id="daily_cap_reset"
    mock_scheduler.add_job.assert_called_once()
    _, kwargs = mock_scheduler.add_job.call_args
    assert kwargs.get("id") == "daily_cap_reset", (
        f"add_job wurde ohne id='daily_cap_reset' aufgerufen: {kwargs}"
    )


@pytest.mark.asyncio
async def test_hmac_signature_verifiable(monkeypatch):
    """HMAC-Signatur muss mit dem webhook_secret verifizierbar sein."""
    import hashlib
    import hmac as hmac_lib
    import json as json_lib
    import swiss_truth_mcp.integrations.webhook as wh

    test_secret = "my-test-webhook-secret"
    monkeypatch.setattr("swiss_truth_mcp.integrations.webhook.settings",
                        type("S", (), {
                            "n8n_webhook_url": "https://n8n.example.com/hook",
                            "effective_webhook_secret": test_secret,
                        })())

    captured = {}

    async def fake_post(url, *, content=None, headers=None, **kwargs):
        captured["body"] = content
        captured["headers"] = headers or {}
        resp = MagicMock()
        resp.status_code = 200
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = fake_post

    with patch("swiss_truth_mcp.integrations.webhook.httpx.AsyncClient",
               return_value=mock_client):
        await wh.fire_event("claim.certified", {"claim_id": "test-123"})

    body_bytes = captured["body"]
    sig_header = captured["headers"].get("X-Signature", "")
    assert sig_header.startswith("sha256=")
    received_hex = sig_header[7:]

    expected_hex = hmac_lib.new(
        test_secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    assert hmac_lib.compare_digest(expected_hex, received_hex), \
        f"Signatur nicht verifizierbar. Erwartet: {expected_hex}, Erhalten: {received_hex}"
