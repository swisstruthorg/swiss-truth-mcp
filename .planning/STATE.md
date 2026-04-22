# Project State: Swiss Truth MCP

**Current Milestone:** v1.3
**Current Phase:** Phase 7 — Agent Outreach & Discovery
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
| 5 | Production Hardening & Developer Experience | ✅ Complete |
| 6 | AI Agent First | ✅ Complete |
| 7 | Agent Outreach & Discovery | ✅ Complete |

## Phase 7 Plan Overview

| Plan | Name | Status | Priority |
|------|------|--------|----------|
| 07-01 | Agent Ecosystem Database | ✅ Complete | P0 — Market Intelligence |
| 07-02 | Outreach Tracker | ✅ Complete | P0 — Execution |
| 07-03 | Agent Persona Profiles | ✅ Complete | P0 — Messaging |
| 07-04 | Competitive Intelligence | ✅ Complete | P1 — Positioning |
| 07-05 | Discovery Checklist | ✅ Complete | P0 — Action Plan |

### Phase 7 Completion Notes (2026-04-21)

**Agent Ecosystem Database (Plan 07-01):**
- `data/agent_ecosystem.json` — comprehensive database of the AI agent ecosystem
- 10 frameworks: LangChain (✅ integrated), CrewAI (✅), AutoGen (✅), LlamaIndex, Haystack, DSPy, smolagents, Pydantic AI, Agno, OpenAI Agents SDK
- 7 platforms: Claude, Cursor, Windsurf, OpenAI GPT Store, n8n, Flowise, Dify
- 7 MCP directories: Smithery (✅ listed), modelcontextprotocol/servers, Glama, mcp.run, PulseMCP, mcpservers.org, awesome-mcp-servers
- 11 communities: LangChain Discord, CrewAI Discord, AutoGen Discord, HN, Reddit, Dev.to, TDS, HuggingFace, AI Engineer Foundation
- 4 package registries: PyPI (3 packages), npm (1 package), LlamaHub (planned), Haystack Hub (planned)
- 5 awesome lists: awesome-mcp-servers, awesome-langchain, awesome-llm-apps, awesome-ai-agents, modelcontextprotocol/servers

**Outreach Tracker (Plan 07-02):**
- `data/outreach_tracker.json` — 27 channels tracked, 1 done (Smithery), 26 todo
- Priority this week: modelcontextprotocol/servers PR, awesome-mcp-servers PR, LangChain Discord, CrewAI Discord, Glama listing
- Draft messages ready for all Discord/Reddit posts
- PR text ready for all awesome list submissions
- Package optimization actions listed for all 4 packages

**Agent Persona Profiles (Plan 07-03):**
- `data/agent_personas.json` — 8 agent personas with full profiles
- Each persona: description, frameworks, use cases, pain points, Swiss Truth value, key message, before/after examples
- Personas: Research Agent, Legal Compliance Agent, Health Advisory Agent, Financial Agent, RAG Pipeline, Content Generation Agent, Multi-Agent Orchestrator, Developer Building Agents

**Competitive Intelligence (Plan 07-04):**
- `data/competitors.json` — 8 competitors analyzed
- Competitors: Google Fact Check, ClaimBuster, Wolfram Alpha, Perplexity, Exa AI, Tavily, Wikipedia, other MCP servers
- Highest threat: Perplexity (medium) — differentiated by human validation vs. AI synthesis
- Positioning statement: Swiss Truth is the only MCP server with 5-stage human+AI validation + Swiss/EU regulatory focus + SHA256 hashes + EU AI Act compliance
- Battlecards for top 4 competitors

**Discovery Checklist (Plan 07-05):**
- `data/discovery_checklist.md` — 30+ action items across P0/P1/P2 priority
- P0 (this week): Official MCP server list PR, awesome-mcp-servers PR, Glama listing, LangChain/CrewAI Discord posts, package metadata optimization
- P1 (next week): ai-plugin.json, llms.txt, GitHub topics, more directory listings, community posts
- P2 (2-4 weeks): Dev.to tutorial, HuggingFace Space demo, TDS article, LlamaIndex/Haystack/smolagents integrations, GPT Action, n8n template

**New files created (Phase 7):**
- `data/agent_ecosystem.json` — AI agent ecosystem database
- `data/outreach_tracker.json` — Outreach channel tracker with draft messages
- `data/agent_personas.json` — 8 agent persona profiles
- `data/competitors.json` — Competitive analysis with positioning and battlecards
- `data/discovery_checklist.md` — Prioritized action checklist (P0/P1/P2)

## Phase 6 Plan Overview

| Plan | Name | Status | Priority |
|------|------|--------|----------|
| 06-A | Agent Feedback Loop | ✅ Complete | P0 — Demand Signals |
| 06-01 | get_knowledge_brief MCP Tool | ✅ Complete | P0 — Agent Value |
| 06-02 | get_citations MCP Tool | ✅ Complete | P0 — Agent Value |
| 06-03 | check_freshness MCP Tool | ✅ Complete | P1 — Agent Value |
| 06-04 | check_regulatory_compliance MCP Tool | ✅ Complete | P1 — Agent Value |
| 06-05 | report_agent_need MCP Tool | ✅ Complete | P0 — Feedback Loop |
| 06-06 | Integration Updates (CrewAI/AutoGen/Shared) | ✅ Complete | P1 — Ecosystem |

### Phase 6 Completion Notes (2026-04-21)

**Agent Feedback Loop (Plan 06-A):**
- `agent/feedback.py` — AgentFeedback Neo4j node, CRUD, demand-signal aggregation
- `api/routes/agent.py` — 5 endpoints:
  - `POST /api/agent/feedback` — agents report what's missing (public)
  - `GET /api/agent/feedback` — list feedback (admin)
  - `GET /api/agent/feedback/stats` — aggregated demand signals (admin)
  - `PATCH /api/agent/feedback/{id}` — update status (admin)
  - `GET /api/agent/capabilities` — full capability manifest for agents (public)
- Feedback types: missing_domain, missing_claim, quality_issue, feature_request, integration_issue, coverage_gap
- Frameworks tracked: langchain, crewai, autogen, openai, anthropic, llamaindex, haystack, dspy, smolagents

**New MCP Tools (Plans 06-01 to 06-05):**
- `get_knowledge_brief` — structured, citable knowledge summary (RAG-optimized)
- `get_citations` — inline + APA citations with verified source URLs
- `check_freshness` — detects stale training data, returns current vs. changed status
- `check_regulatory_compliance` — Swiss/EU compliance check (FINMA, BAG, OR/ZGB, GDPR/AI Act)
- `report_agent_need` — agents report missing features/domains directly via MCP

**MCP Server now has 14 tools** (was 9):
- Original 9: search_knowledge, get_claim, list_domains, submit_claim, verify_claim, get_claim_status, verify_claims_batch, verify_response, find_contradictions
- New 5: get_knowledge_brief, get_citations, check_freshness, check_regulatory_compliance, report_agent_need

**Integration Updates (Plan 06-06):**
- `integrations/shared/base_client.py` — 6 new methods (get_knowledge_brief, get_citations, check_freshness, check_regulatory_compliance, report_agent_need, get_agent_capabilities)
- `integrations/crewai-pkg/tools.py` — 4 new tools: SwissTruthKnowledgeBriefTool, SwissTruthCitationsTool, SwissTruthFreshnessTool, SwissTruthReportNeedTool
- `integrations/autogen-pkg/functions.py` — 4 new functions + registered in function_map

**New files created (Phase 6):**
- `agent/__init__.py` — agent module init
- `agent/feedback.py` — feedback loop module
- `agent/knowledge_tools.py` — 5 new MCP tool implementations
- `api/routes/agent.py` — agent-focused REST endpoints

**Modified files:**
- `mcp_server/server.py` — 5 new tools registered (14 total)
- `api/main.py` — agent router wired
- `integrations/shared/base_client.py` — 6 new methods
- `integrations/crewai-pkg/tools.py` — 4 new tools
- `integrations/autogen-pkg/functions.py` — 4 new functions + updated register_swiss_truth_functions()

## Phase 5 Plan Overview

| Plan | Name | Status | Priority |
|------|------|--------|----------|
| 05-01 | CI/CD Pipeline & Integration Tests | ✅ Complete | P0 — Foundation |
| 05-02 | Redis Cache Layer (Multi-Instance Ready) | ✅ Complete | P1 — Scale |
| 05-03 | Developer Portal & Self-Service API Keys | ✅ Complete | P1 — Growth |
| 05-04 | Claim Clustering & Knowledge Graph Visualization | ✅ Complete | P2 — Intelligence |
| 05-05 | Source Quality Scoring & Automated Fact-Check Pipeline | ✅ Complete | P2 — Intelligence |
| 05-06 | Additional Agent Framework Integrations | ✅ Complete | P2 — Growth |

## Accumulated Context

### Phase 5 Completion Notes (2026-04-21)

**CI/CD Pipeline & Integration Tests (Plan 05-01):**
- `.github/workflows/ci.yml` — GitHub Actions: lint (ruff), type-check (mypy), unit tests, integration tests
- Integration tests against real Neo4j (Docker service in CI)
- Auto-deploy to Hostinger on `main` push via SSH
- `.pre-commit-config.yaml` — ruff format + ruff check hooks
- `tests/test_integration.py` — 8 integration tests (schema, CRUD, validation, API keys, tenants, stats)
- `tests/docker-compose.test.yml` — local test environment (Neo4j + Redis)

**Redis Cache Layer (Plan 05-02):**
- `cache/redis_client.py` — unified Cache class with Redis backend + in-memory fallback
- Supports: get/set/delete/incr/exists/flush_pattern with TTL
- JSON helpers: `get_json()`, `set_json()` for structured data
- `health_check()` returns backend type + memory usage
- Config: `REDIS_URL` env var (empty = in-memory fallback, zero-config)
- Health endpoint updated to include cache status

**Developer Portal & Self-Service API Keys (Plan 05-03):**
- `auth/registration.py` — register_developer() + login_developer()
- Creates User + Tenant + free-tier API key in one transaction
- Password hashing via bcrypt, slug generation from email
- `api/routes/portal.py` — 6 endpoints:
  - `POST /portal/register` — self-service registration
  - `POST /portal/login` — authentication
  - `GET /portal/keys` — list API keys for tenant
  - `POST /portal/keys` — create new key (max 5 for free tier)
  - `DELETE /portal/keys/{key_id}` — revoke key
  - `GET /portal/usage` — usage dashboard with tier limits

**Claim Clustering & Knowledge Graph Visualization (Plan 05-04):**
- `validation/clustering.py` — cosine similarity clustering with configurable threshold
- `CLUSTER_OF` Neo4j relationship between cluster members and center
- `api/routes/graph.py` — 3 endpoints:
  - `GET /api/clusters/{domain_id}` — get/compute clusters
  - `POST /api/clusters/{domain_id}/recompute` — force recompute
  - `GET /api/graph/{domain_id}` — full graph data (nodes + edges) for D3/Cytoscape

**Source Quality Scoring & Automated Fact-Check Pipeline (Plan 05-05):**
- `validation/source_scoring.py` — URL reputation scoring with 30+ known-reliable domains
- Categories: government, academic, international, news, other
- `compute_weighted_confidence()` — blends base confidence with source quality (15% weight)
- `validation/auto_pipeline.py` — full automated pipeline: pre-screen → source score → AI verify → auto-certify/queue
- Auto-certify threshold: 0.70 confidence (below → human review queue)
- `api/routes/pipeline.py` — 4 endpoints:
  - `POST /api/pipeline/auto-verify` — trigger full pipeline
  - `GET /api/sources/score/{claim_id}` — score claim sources
  - `GET /api/sources/domain/{domain_id}` — domain source quality
  - `POST /api/sources/score-url` — score single URL

**Additional Agent Framework Integrations (Plan 05-06):**
- `integrations/shared/base_client.py` — shared HTTP client with all API methods
- `integrations/crewai-pkg/` — CrewAI integration (swiss-truth-crewai v0.1.0)
  - 3 tools: SwissTruthSearchTool, SwissTruthVerifyTool, SwissTruthSubmitTool
  - CrewAI BaseTool compatible with Pydantic schemas
- `integrations/autogen-pkg/` — AutoGen integration (swiss-truth-autogen v0.1.0)
  - 3 functions: swiss_truth_search, swiss_truth_verify, swiss_truth_submit
  - `get_function_definitions()` for OpenAI function-calling format
  - `register_swiss_truth_functions()` for agent registration

**New files created (Phase 5):**
- `.github/workflows/ci.yml` — CI/CD pipeline
- `.pre-commit-config.yaml` — pre-commit hooks
- `tests/test_integration.py` — integration test suite
- `tests/docker-compose.test.yml` — test environment
- `cache/__init__.py` + `cache/redis_client.py` — Redis cache layer
- `auth/__init__.py` + `auth/registration.py` — developer registration
- `api/routes/portal.py` — developer portal endpoints
- `api/routes/graph.py` — graph/clustering endpoints
- `api/routes/pipeline.py` — auto-verify pipeline endpoints
- `validation/clustering.py` — claim clustering
- `validation/source_scoring.py` — source quality scoring
- `validation/auto_pipeline.py` — automated fact-check pipeline
- `integrations/shared/base_client.py` — shared HTTP client
- `integrations/crewai-pkg/` — CrewAI integration package
- `integrations/autogen-pkg/` — AutoGen integration package

**Modified files:**
- `config.py` — added redis_url, SMTP settings
- `api/main.py` — wired 3 new routers (portal, graph, pipeline) + cache health check

### Phase 5 Planning Notes (2026-04-21)

**Rationale:** v1.0 feature set is complete (Phases 0–4). The platform needs production hardening before scaling user adoption. Key gaps:
1. **No CI/CD** — manual testing and deployment, risk of regressions
2. **In-memory state** — SLA tracker and rate limiter caches lost on restart, no horizontal scaling
3. **Admin-only key management** — no self-service, blocks developer adoption
4. **No automated quality pipeline** — manual fact-checking bottleneck
5. **Single framework** — only LangChain integration, missing CrewAI/AutoGen ecosystem

**Dependencies:**
- 05-01 (CI/CD) is prerequisite for all other plans — ensures quality gate
- 05-02 (Redis) enables 05-03 (Portal) — session storage, rate limiting at scale
- 05-05 (Source Scoring) feeds into 05-04 (Clustering) — quality data enriches graph

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
- 2026-04-21: Phase 5 roadmap defined — Production Hardening & Developer Experience (6 plans).

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
| 2026-04-21 | session-6 | Phase 5 roadmap planning: CI/CD, Redis, Developer Portal, Graph Viz, Source Scoring, Agent Integrations |
| 2026-04-21 | session-7 | Phase 5 implementation: all 6 plans (CI/CD, Redis, Portal, Clustering, Source Scoring, CrewAI+AutoGen) |
| 2026-04-21 | session-8 | Phase 6 implementation: AI Agent First — Feedback Loop, 5 new MCP tools, integration updates |
| 2026-04-21 | session-9 | Phase 7 implementation: Agent Outreach & Discovery — ecosystem DB, outreach tracker, personas, competitive analysis, discovery checklist |

## 2026-04-22 — Session 10: Phase 7 Outreach Execution

### PRs submitted
- PR #4007 modelcontextprotocol/servers: https://github.com/modelcontextprotocol/servers/pull/4007
- PR #5230 punkpeye/awesome-mcp-servers: https://github.com/punkpeye/awesome-mcp-servers/pull/5230

### Claims generator (local run)
- manage_claims.py --domain eu-law: OK (1898 total certified, 7/38 green)
- manage_claims.py --domain ai-safety: OK
- manage_claims.py --domain swiss-health: OK

### Pending manual actions
- Glama listing: https://glama.ai/mcp/servers/submit
- LangChain Discord #tools-and-integrations: draft in outreach_tracker.json
- CrewAI Discord #tools: draft in outreach_tracker.json
