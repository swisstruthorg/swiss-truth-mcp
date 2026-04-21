# Project State: Swiss Truth MCP

**Current Milestone:** v1.0
**Current Phase:** Phase 4 — Enterprise & Compliance
**Status:** ✅ Complete
**Last Activity:** 2026-04-21

## Phase Progress

| Phase | Name | Status |
|-------|------|--------|
| 0 | Agent Instrumentation | ✅ Complete |
| 1 | Critical Fixes | ✅ Complete |
| 2 | Growth & Integrations | ✅ Complete |
| 3 | Scale & Quality | ✅ Complete |
| 4 | Enterprise & Compliance | ✅ Complete |

## Accumulated Context

### Phase 4 Completion Notes (2026-04-21)

**API Key Management (Plan 04-01):**
- `ApiKey` Neo4j node with SHA256 hashing, tier (free/pro/enterprise), owner, tenant_id
- Admin CRUD: `POST/GET/DELETE /admin/api-keys`, `GET /admin/api-keys/{id}/usage`
- Rate limiter (`middleware/rate_limiter.py`) updated with DB-backed key resolution
- 60s in-memory cache (`_db_key_cache`) to avoid DB hits on every request
- `invalidate_key_cache()` called on key create/revoke
- Key format: `sk-{tier[:3]}-{random}` (e.g. `sk-pro-abc123...`)

**SLA Monitoring (Plan 04-02):**
- `monitoring/sla.py` — in-memory ring-buffer (288 × 5-min buckets = 24h)
- `middleware/sla_tracker.py` — ASGI middleware between RateLimiter and app
- Tracks: request count, latency (p50/p95/p99), error rate, uptime %
- Admin endpoints: `GET /admin/sla/status`, `/history`, `/alerts`
- Config: `sla_uptime_target` (99.5%), `sla_p95_latency_ms` (500ms), `sla_alert_webhook_url`
- Alerts: logging-based + optional webhook (fire-and-forget via thread)

**Full Compliance Report (Plan 04-03):**
- `GET /api/compliance/eu-ai-act/report/full` — v2.0 extended report
- Per-domain: confidence, quality distribution (high/med/low), renewal status, human review rate
- Certification timeline: monthly counts + avg confidence (last 12 months)
- Validator leaderboard: total validations, certified, renewals, certification rate
- Blockchain anchoring status: latest anchor, recent anchors, chain info
- SLA monitoring status integrated
- Audit trail endpoints listed
- New queries: `get_certification_timeline()`, `get_validator_stats()`

**Audit Trail Export (Plan 04-04):**
- `audit/jsonld.py` — W3C PROV-O compatible JSON-LD serializer
- Ontology mapping: Claim→prov:Entity, Validation→prov:Activity, Expert→prov:Agent, Source→prov:wasDerivedFrom, Anchor→prov:Activity
- `GET /api/audit/trail` — full system audit trail (JSON-LD)
- `GET /api/audit/trail/{claim_id}` — single claim with validations + anchors
- `GET /api/audit/export` — bulk export with `since` and `domain` filters
- New queries: `get_claim_validations()`, `get_all_certified_claims()`, `get_certified_claims_filtered()`

**Multi-Tenant Support (Plan 04-05):**
- `Tenant` Neo4j node: id, name, slug (unique), plan, active, settings_json
- Admin CRUD: `POST/GET/PATCH /admin/tenants`, `GET /admin/tenants/{id}` (with usage stats)
- API keys linked to tenants via `tenant_id` field
- Tenant usage stats: API key count, total requests across all keys
- Schema constraints: `tenant_id` uniqueness, `tenant_slug` uniqueness

**New files created:**
- `api/routes/api_keys.py` — API key admin endpoints
- `api/routes/monitoring.py` — SLA monitoring admin endpoints
- `api/routes/audit.py` — Audit trail JSON-LD export endpoints
- `api/routes/tenants.py` — Multi-tenant admin endpoints
- `monitoring/__init__.py` + `monitoring/sla.py` — SLA tracker module
- `middleware/sla_tracker.py` — SLA ASGI middleware
- `audit/__init__.py` + `audit/jsonld.py` — JSON-LD serializer

**Modified files:**
- `config.py` — added SLA settings (uptime target, p95 latency, alert webhook)
- `db/schema.py` — added ApiKey + Tenant constraints
- `db/queries.py` — added ~15 new queries (API keys, tenants, audit, compliance)
- `middleware/rate_limiter.py` — DB-backed key resolution with cache
- `api/main.py` — wired 4 new routers + SLA middleware in ASGI stack
- `api/routes/compliance.py` — added full extended report endpoint (v2.0)

### Phase 3 Completion Notes (2026-04-20)

**Automated renewal pipeline (Plan 03-01):**
- `renewal/worker.py` — daily batch re-verification of expiring claims via Claude Haiku
- Respects daily cost cap (SEC-05), processes up to 20 claims/batch
- APScheduler cron at 03:00 UTC + manual trigger `POST /admin/renewal`

**Blockchain anchoring weekly cron (Plan 03-02):**
- APScheduler job every Sunday 02:00 UTC (auto dry-run if no ETH keys)
- Wired existing `run_anchor_job()` into lifespan scheduler

**Multi-language claim generation (Plan 03-03):**
- `seed/multilang.py` — translates certified claims to FR/IT/ES/ZH via Claude
- CLI: `python -m swiss_truth_mcp.seed.multilang --domain swiss-health --lang fr`

**Coverage analysis (Plan 03-04):**
- `validation/coverage.py` — keyword-based topic coverage per domain
- Endpoints: `GET /api/coverage/{domain_id}`, `GET /api/coverage`

**Advanced conflict detection (Plan 03-05):**
- Enhanced `conflict_detect.py` with AI explanations via `compare_claims()`
- `CONFLICTS_WITH` Neo4j relationship, `GET /api/conflicts`

**New API routes:** `api/routes/quality.py` — coverage, conflicts, renewal admin

### Phase 2 Completion Notes (2026-04-20)

**LangChain integration package (swiss-truth-langchain v0.2.0):**
- Full rewrite from single-file copy to proper multi-module package
- 9 LangChain tools matching all MCP server tools (search, verify, submit, list_domains, get_claim_status, batch_verify, verify_response, find_contradictions, compliance)
- `SwissTruthRetriever` — LangChain `BaseRetriever` for RAG pipelines
- `SwissTruthToolkit` with `read_only=True` mode for public-facing agents
- Modular structure: `client.py`, `_schemas.py`, `tools.py`, `retriever.py`, `toolkit.py`
- Updated `pyproject.toml` (v0.2.0, Python 3.9-3.13, new keywords)

**EU AI Act compliance endpoint improvements:**
- Extracted inline endpoint from `main.py` into dedicated `api/routes/compliance.py`
- 4 endpoints:
  - `GET /api/compliance/eu-ai-act/{claim_id}` — single claim attestation
  - `POST /api/compliance/eu-ai-act/batch` — batch attestation (up to 50 claims)
  - `GET /api/compliance/eu-ai-act/domain/{domain_id}` — domain-level compliance summary
  - `GET /api/compliance/eu-ai-act/report` — full system-wide compliance report
- New query: `get_certified_claims_by_domain()` in `db/queries.py`
- Attestation version bumped from 1.0 to 1.1

### Phase 1 Completion Notes (2026-04-20)

**Bug fixes applied (Plan 01-05):**
1. Duplicate `from pathlib import Path` import in `api/main.py`
2. `expires_at=None` freshness logic — claims without expiry incorrectly marked as `renewal_recommended`
3. `get_claim_status` used `only_live=True` — expired claims reported as "not found" instead of showing their actual status
4. Markdown code fence parsing in `tools.py` and `pre_screen.py` (4 locations) — `raw.split("```")[1]` failed when API returned fences without `json` prefix

### Roadmap Evolution

- 2026-04-20: Reconstructed `.planning/` from GSD session `hungry-babbage-aa6eb1` + git history. Original worktree artifacts were lost during cleanup.

## Blockers

None currently.

## Session History

| Date | Session | Activity |
|------|---------|----------|
| 2026-04-20 | hungry-babbage-aa6eb1 | Phase 0+1 execution (GSD full pipeline) |
| 2026-04-20 | session-2 | Phase 1 post-merge bug fixes + .planning/ reconstruction |
| 2026-04-20 | session-3 | Phase 2 completion: LangChain pkg + EU AI Act compliance endpoints |
| 2026-04-20 | session-4 | Phase 3 completion: renewal pipeline, anchor cron, multilang, coverage, conflicts |
| 2026-04-21 | session-5 | Phase 4 completion: API keys, SLA monitoring, compliance report v2, audit trail JSON-LD, multi-tenant |
