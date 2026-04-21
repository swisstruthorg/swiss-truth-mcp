"""
Integration tests — run against a real Neo4j instance.

Requires:
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD env vars
  (set automatically by CI via docker-compose service)

Usage:
  pytest tests/test_integration.py -v
"""
from __future__ import annotations

import os
import uuid

import pytest

# Skip entire module if Neo4j is not available
pytestmark = pytest.mark.skipif(
    not os.environ.get("NEO4J_PASSWORD"),
    reason="NEO4J_PASSWORD not set — skipping integration tests",
)


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def neo4j_session():
    """Get a real Neo4j session for integration testing."""
    from swiss_truth_mcp.db.neo4j_client import get_session, close_driver
    from swiss_truth_mcp.db.schema import setup_schema

    async with get_session() as session:
        await setup_schema(session)

    async with get_session() as session:
        yield session

    await close_driver()


# ---------------------------------------------------------------------------
# Schema & Domain Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_setup(neo4j_session):
    """Schema setup should create constraints and seed domains."""
    from swiss_truth_mcp.db import queries

    domains = await queries.list_domains(neo4j_session)
    assert len(domains) >= 20, f"Expected 20+ domains, got {len(domains)}"

    domain_ids = {d["id"] for d in domains}
    assert "ai-ml" in domain_ids
    assert "swiss-health" in domain_ids
    assert "swiss-law" in domain_ids


# ---------------------------------------------------------------------------
# Claim CRUD Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_claim(neo4j_session):
    """Create a claim and retrieve it by ID."""
    from swiss_truth_mcp.db import queries

    claim_id = f"test-{uuid.uuid4()}"
    claim = {
        "id": claim_id,
        "text": "Integration test claim — water boils at 100°C at sea level.",
        "question": "At what temperature does water boil?",
        "domain_id": "world-science",
        "confidence_score": 0.95,
        "status": "draft",
        "language": "en",
        "hash_sha256": "test_hash_" + claim_id[:8],
        "created_at": "2026-04-21T12:00:00Z",
        "last_reviewed": "2026-04-21T12:00:00Z",
        "expires_at": "2027-04-21T12:00:00Z",
        "embedding": [0.1] * 384,
        "source_urls": ["https://example.com/science"],
    }

    await queries.create_claim(neo4j_session, claim)
    retrieved = await queries.get_claim_by_id(neo4j_session, claim_id)

    assert retrieved is not None
    assert retrieved["id"] == claim_id
    assert retrieved["text"] == claim["text"]
    assert retrieved["status"] == "draft"
    assert len(retrieved["source_references"]) >= 1

    # Cleanup
    await neo4j_session.run("MATCH (c:Claim {id: $id}) DETACH DELETE c", {"id": claim_id})


@pytest.mark.asyncio
async def test_update_claim_status(neo4j_session):
    """Update claim status from draft to certified."""
    from swiss_truth_mcp.db import queries

    claim_id = f"test-{uuid.uuid4()}"
    claim = {
        "id": claim_id,
        "text": "Test claim for status update.",
        "question": "",
        "domain_id": "ai-ml",
        "confidence_score": 0.85,
        "status": "draft",
        "language": "en",
        "hash_sha256": "hash_" + claim_id[:8],
        "created_at": "2026-04-21T12:00:00Z",
        "last_reviewed": "2026-04-21T12:00:00Z",
        "expires_at": "2027-04-21T12:00:00Z",
        "embedding": [0.1] * 384,
        "source_urls": [],
    }

    await queries.create_claim(neo4j_session, claim)
    await queries.update_claim_status(neo4j_session, claim_id, "certified", 0.92)

    updated = await queries.get_claim_by_id(neo4j_session, claim_id)
    assert updated["status"] == "certified"
    assert updated["confidence_score"] == 0.92

    # Cleanup
    await neo4j_session.run("MATCH (c:Claim {id: $id}) DETACH DELETE c", {"id": claim_id})


# ---------------------------------------------------------------------------
# Validation Workflow Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_claim(neo4j_session):
    """Full validation workflow: create → validate → check certified."""
    from swiss_truth_mcp.db import queries

    claim_id = f"test-{uuid.uuid4()}"
    claim = {
        "id": claim_id,
        "text": "Test claim for validation workflow.",
        "question": "",
        "domain_id": "swiss-law",
        "confidence_score": 0.80,
        "status": "peer_review",
        "language": "de",
        "hash_sha256": "hash_" + claim_id[:8],
        "created_at": "2026-04-21T12:00:00Z",
        "last_reviewed": "2026-04-21T12:00:00Z",
        "expires_at": "2027-04-21T12:00:00Z",
        "embedding": [0.1] * 384,
        "source_urls": [],
    }

    await queries.create_claim(neo4j_session, claim)
    await queries.validate_claim(
        neo4j_session,
        claim_id=claim_id,
        expert_name="Test Expert",
        expert_institution="Test University",
        verdict="approved",
        confidence_score=0.95,
        reviewed_at="2026-04-21T13:00:00Z",
    )

    validated = await queries.get_claim_by_id(neo4j_session, claim_id)
    assert validated["status"] == "certified"
    assert validated["confidence_score"] == 0.95
    assert any(v["name"] == "Test Expert" for v in validated["validated_by"])

    # Cleanup
    await neo4j_session.run(
        "MATCH (c:Claim {id: $id}) DETACH DELETE c", {"id": claim_id}
    )
    await neo4j_session.run(
        "MATCH (e:Expert {id: 'expert-test-expert'}) DETACH DELETE e"
    )


# ---------------------------------------------------------------------------
# API Key Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_key_crud(neo4j_session):
    """Create, retrieve, and revoke an API key."""
    from swiss_truth_mcp.db import queries
    import hashlib

    key_id = f"key-{uuid.uuid4()}"
    raw_key = f"sk-pro-test{uuid.uuid4().hex[:16]}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    key_data = {
        "id": key_id,
        "key_hash": key_hash,
        "key_prefix": raw_key[:12],
        "tier": "pro",
        "owner_name": "Test User",
        "owner_email": "test@example.com",
        "tenant_id": "",
        "active": True,
        "created_at": "2026-04-21T12:00:00Z",
        "expires_at": "2027-04-21T12:00:00Z",
        "request_count": 0,
        "last_used_at": "",
    }

    await queries.create_api_key(neo4j_session, key_data)

    # Retrieve by hash
    retrieved = await queries.get_api_key_by_hash(neo4j_session, key_hash)
    assert retrieved is not None
    assert retrieved["tier"] == "pro"

    # Revoke
    revoked = await queries.revoke_api_key(neo4j_session, key_id)
    assert revoked is True

    # Verify revoked
    after_revoke = await queries.get_api_key_by_hash(neo4j_session, key_hash)
    assert after_revoke is None  # active=false, query filters active=true

    # Cleanup
    await neo4j_session.run("MATCH (k:ApiKey {id: $id}) DELETE k", {"id": key_id})


# ---------------------------------------------------------------------------
# Tenant Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_crud(neo4j_session):
    """Create, retrieve, update, and list tenants."""
    from swiss_truth_mcp.db import queries

    tenant_id = f"tenant-{uuid.uuid4()}"
    slug = f"test-{uuid.uuid4().hex[:8]}"

    await queries.create_tenant(neo4j_session, {
        "id": tenant_id,
        "name": "Test Tenant",
        "slug": slug,
        "plan": "free",
        "active": True,
        "created_at": "2026-04-21T12:00:00Z",
        "settings_json": {"feature_x": True},
    })

    # Get by ID
    tenant = await queries.get_tenant_by_id(neo4j_session, tenant_id)
    assert tenant is not None
    assert tenant["name"] == "Test Tenant"
    assert tenant["settings_json"]["feature_x"] is True

    # Get by slug
    by_slug = await queries.get_tenant_by_slug(neo4j_session, slug)
    assert by_slug is not None
    assert by_slug["id"] == tenant_id

    # Update
    await queries.update_tenant(neo4j_session, tenant_id, {"plan": "pro"})
    updated = await queries.get_tenant_by_id(neo4j_session, tenant_id)
    assert updated["plan"] == "pro"

    # List
    all_tenants = await queries.list_tenants(neo4j_session)
    assert any(t["id"] == tenant_id for t in all_tenants)

    # Cleanup
    await neo4j_session.run("MATCH (t:Tenant {id: $id}) DELETE t", {"id": tenant_id})


# ---------------------------------------------------------------------------
# Dashboard Stats Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_stats(neo4j_session):
    """Dashboard stats should return valid structure."""
    from swiss_truth_mcp.db import queries

    stats = await queries.get_dashboard_stats(neo4j_session)
    assert "total" in stats
    assert "certified" in stats
    assert "domains" in stats
    assert "validators" in stats
    assert isinstance(stats["domains"], list)


@pytest.mark.asyncio
async def test_trust_stats(neo4j_session):
    """Trust page stats should return valid structure."""
    from swiss_truth_mcp.db import queries

    stats = await queries.get_trust_stats(neo4j_session)
    assert "total" in stats
    assert "certified" in stats
    assert "languages" in stats
    assert "domains" in stats
