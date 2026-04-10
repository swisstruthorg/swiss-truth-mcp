from swiss_truth_mcp.validation.trust import sign_claim, verify_claim


def _base_claim() -> dict:
    return {
        "id": "test-123",
        "text": "RAG reduziert Halluzinationen.",
        "domain_id": "ai-ml",
        "language": "de",
        "source_urls": ["https://arxiv.org/abs/2005.11401"],
    }


def test_sign_claim_returns_sha256_prefix():
    claim = _base_claim()
    h = sign_claim(claim)
    assert h.startswith("sha256:")
    assert len(h) == 7 + 64  # "sha256:" + 64 hex chars


def test_verify_claim_ok():
    claim = _base_claim()
    h = sign_claim(claim)
    assert verify_claim(claim, h) is True


def test_verify_claim_tampered():
    claim = _base_claim()
    h = sign_claim(claim)
    claim["text"] = "RAG ist toll."  # tampering
    assert verify_claim(claim, h) is False


def test_sign_deterministic():
    claim = _base_claim()
    assert sign_claim(claim) == sign_claim(claim)


def test_sign_ignores_embedding():
    claim = _base_claim()
    h1 = sign_claim(claim)
    claim["embedding"] = [0.1, 0.2, 0.3]
    h2 = sign_claim(claim)
    assert h1 == h2


def test_sign_source_order_independent():
    claim = _base_claim()
    claim["source_urls"] = ["https://b.com", "https://a.com"]
    h1 = sign_claim(claim)
    claim["source_urls"] = ["https://a.com", "https://b.com"]
    h2 = sign_claim(claim)
    assert h1 == h2
