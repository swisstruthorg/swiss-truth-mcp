# Roadmap: Swiss Truth MCP

*Reconstructed from GSD session `hungry-babbage-aa6eb1` + git history*
*Last updated: 2026-04-21*

---

## Phase 0: Agent Instrumentation ✅

**Goal:** Add observability to MCP tool calls — track which tools are used, how often, and by whom.

**Plans:**
- [x] 00-01: Instrumentation Utility + QueryEvent Schema
- [x] 00-02: MCP tool handler wrapping with event logging
- [x] 00-03: Analytics dashboard with human-verify checkpoint
- [x] 00-04: Pre-Smithery baseline documentation

**Status:** Complete

---

## Phase 1: Critical Fixes ✅

**Goal:** Harden security and reliability — fix timeout issues, expired claim leaks, SSRF vectors, unsigned webhooks, and unbounded API costs.

**Plans:**
- [x] 01-01: SEC-01 Anthropic API Timeout + SEC-02 Expired Claims Filter
- [x] 01-02: SEC-03 SSRF Validation + SEC-04 HMAC Webhook Signatures
- [x] 01-03: SEC-05 Renewal Cost Cap + APScheduler daily reset
- [x] 01-04: Fix ImportError in verify_response, wire httpx timeout, remove dead Lock
- [x] 01-05: Post-merge bug fixes (duplicate import, expires_at freshness logic, get_claim_status only_live, markdown codeblock parsing)

**Success Criteria:**
- ✅ All API calls have configurable timeout (default 30s)
- ✅ Expired claims filtered from search and get_claim
- ✅ Private IPs blocked in webhook URLs (SSRF)
- ✅ All outgoing webhooks HMAC-SHA256 signed
- ✅ Daily API cost cap with APScheduler reset
- ✅ get_claim_status shows all claims including expired
- ✅ Markdown code fence parsing robust against missing `json` prefix

**Status:** Complete

---

## Phase 2: Growth & Integrations ✅

**Goal:** Expand reach — npm package, Smithery listing, LangChain integration, OpenAI function-calling compatibility, EU AI Act compliance.

**Research completed:** Stack, Architecture, Features, Pitfalls (via GSD agents)

**Plans:**
- [x] npm package published (swiss-truth-mcp v0.1.4)
- [x] Smithery configuration (smithery.yaml)
- [x] OpenAI tools endpoint (/openai-tools.json)
- [x] MCP auto-discovery (/.well-known/mcp.json)
- [x] LangChain integration package (integrations/langchain-pkg/)
  - 9 tools matching MCP server (search, verify, submit, list_domains, get_claim_status, batch_verify, verify_response, find_contradictions, compliance)
  - SwissTruthRetriever for RAG pipelines (LangChain BaseRetriever)
  - SwissTruthToolkit with read_only mode
  - Proper package structure (swiss-truth-langchain v0.2.0)
- [x] EU AI Act compliance endpoint improvements
  - Refactored into dedicated compliance router (api/routes/compliance.py)
  - Single claim attestation (GET /api/compliance/eu-ai-act/{claim_id})
  - Batch attestation (POST /api/compliance/eu-ai-act/batch) — up to 50 claims
  - Domain-level compliance summary (GET /api/compliance/eu-ai-act/domain/{domain_id})
  - System-wide compliance report (GET /api/compliance/eu-ai-act/report)
  - Attestation version bumped to 1.1

**Status:** Complete

---

## Phase 3: Scale & Quality ✅

**Goal:** Improve claim quality, add multi-language seed data, automated renewal pipeline, blockchain anchoring.

**Plans:**
- [x] 03-01: Automated renewal pipeline with cost-capped AI re-verification
  - `renewal/worker.py` — daily batch job re-verifies expiring claims via Claude Haiku
  - Respects daily cost cap (SEC-05), processes up to 20 claims/batch
  - APScheduler job at 03:00 UTC + manual trigger via `POST /admin/renewal`
  - Status endpoint: `GET /admin/renewal/status`
- [x] 03-02: Blockchain anchoring weekly cron
  - APScheduler job every Sunday 02:00 UTC (auto dry-run if no ETH keys configured)
  - Existing anchor infrastructure fully wired (Merkle root, Polygon/Base, audit trail)
- [x] 03-03: Multi-language claim generation (FR, IT, ES, ZH)
  - `seed/multilang.py` — translates certified claims via Claude Haiku
  - CLI: `python -m swiss_truth_mcp.seed.multilang --domain swiss-health --lang fr`
  - Preserves source URLs, adjusts confidence by -0.01
- [x] 03-04: Coverage analysis per domain (gap detection)
  - `validation/coverage.py` — keyword-based topic coverage analysis
  - `GET /api/coverage/{domain_id}` — per-domain coverage report
  - `GET /api/coverage` — all-domains overview with gap counts
- [x] 03-05: Advanced conflict detection with explanation
  - Enhanced `conflict_detect.py` with AI-powered explanations via `compare_claims()`
  - `CONFLICTS_WITH` Neo4j relationship for persistent conflict tracking
  - `GET /api/conflicts` — list all known conflicts
  - `record_conflict()` for storing detected conflicts

**Status:** Complete

---

## Phase 4: Enterprise & Compliance ✅

**Goal:** Enterprise features — API keys, usage tiers, SLA monitoring, full EU AI Act compliance attestation, audit trail export, multi-tenant support.

**Plans:**
- [x] 04-01: API Key Management with Usage Tiers (admin-only, backend infrastructure)
  - `ApiKey` Neo4j node with SHA256 hashing, tier, owner, tenant_id
  - Admin CRUD: `POST/GET/DELETE /admin/api-keys`, `GET /admin/api-keys/{id}/usage`
  - Rate limiter updated with DB-backed key resolution (60s in-memory cache)
  - Key generation with prefixed format: `sk-{tier}-{random}`
  - Cache invalidation on key create/revoke
- [x] 04-02: SLA Monitoring and Alerting
  - `monitoring/sla.py` — in-memory ring-buffer tracker (288 × 5-min buckets = 24h)
  - `middleware/sla_tracker.py` — ASGI middleware capturing latency + status codes
  - Admin endpoints: `GET /admin/sla/status`, `/history`, `/alerts`
  - Configurable targets: `sla_uptime_target` (99.5%), `sla_p95_latency_ms` (500ms)
  - Optional webhook alerting via `SLA_ALERT_WEBHOOK_URL`
- [x] 04-03: Full EU AI Act Compliance Report Generation
  - Extended report: `GET /api/compliance/eu-ai-act/report/full` (v2.0)
  - Per-domain compliance metrics (confidence, quality distribution, renewal status)
  - Certification timeline (monthly counts, last 12 months)
  - Validator leaderboard with certification rates
  - Blockchain anchoring status integration
  - SLA monitoring status integration
  - New DB queries: `get_certification_timeline()`, `get_validator_stats()`
- [x] 04-04: Audit Trail Export (JSON-LD)
  - `audit/jsonld.py` — W3C PROV-O compatible JSON-LD serializer
  - Ontology: Claim→prov:Entity, Validation→prov:Activity, Expert→prov:Agent
  - `GET /api/audit/trail` — full system audit trail
  - `GET /api/audit/trail/{claim_id}` — single claim audit trail
  - `GET /api/audit/export` — bulk export with time/domain filters
  - New DB queries: `get_claim_validations()`, `get_all_certified_claims()`, `get_certified_claims_filtered()`
- [x] 04-05: Multi-Tenant Support
  - `Tenant` Neo4j node with slug, plan, settings_json
  - Admin CRUD: `POST/GET/PATCH /admin/tenants`, `GET /admin/tenants/{id}` (with usage stats)
  - API keys linked to tenants via `tenant_id`
  - Tenant usage stats: API key count, total requests
  - Schema constraints for Tenant id + slug uniqueness

**Success Criteria:**
- ✅ API keys with SHA256 hashing, 3 tiers (free/pro/enterprise), admin CRUD
- ✅ Rate limiter supports DB-backed keys with 60s cache
- ✅ SLA monitoring with p50/p95/p99 latency, uptime %, error rate
- ✅ SLA alerts via logging + optional webhook
- ✅ Full compliance report v2.0 with per-domain analysis, timeline, validators
- ✅ JSON-LD audit trail export (W3C PROV-O compatible)
- ✅ Multi-tenant infrastructure with plan-based isolation
- ✅ All new endpoints wired into FastAPI app

**Status:** Complete

---

## Phase 5: Production Hardening & Developer Experience 🔄

**Goal:** Make the platform production-grade — CI/CD, integration tests, developer portal with self-service API keys, Redis caching for horizontal scaling, and knowledge graph visualization.

**Plans:**

### 05-01: CI/CD Pipeline & Integration Tests
- [ ] GitHub Actions workflow: lint (ruff), type-check (mypy), unit tests (pytest)
- [ ] Integration test suite against real Neo4j (Docker Compose test profile)
- [ ] Test coverage for all API routes (minimum 80%)
- [ ] Auto-deploy to Hostinger on `main` push (via SSH + `deploy/update.sh`)
- [ ] Pre-commit hooks: ruff format + ruff check

**Files:** `.github/workflows/ci.yml`, `tests/test_integration.py`, `tests/docker-compose.test.yml`, `.pre-commit-config.yaml`

### 05-02: Redis Cache Layer (Multi-Instance Ready)
- [ ] Replace in-memory caches (SLA ring-buffer, rate limiter key cache) with Redis
- [ ] Redis-backed rate limiting (sliding window per API key)
- [ ] Redis pub/sub for SSE broadcast across multiple API instances
- [ ] Configurable: fallback to in-memory if `REDIS_URL` not set
- [ ] Health check includes Redis connectivity

**Files:** `cache/redis_client.py`, `middleware/rate_limiter.py` (update), `monitoring/sla.py` (update), `config.py` (update)

### 05-03: Developer Portal & Self-Service API Keys
- [ ] Public registration page: email + password → tenant + free-tier API key
- [ ] Dashboard: usage stats, key management, upgrade to pro/enterprise
- [ ] Interactive API explorer (Swagger UI with pre-filled API key)
- [ ] Webhook management UI: register/test/delete webhook endpoints
- [ ] Email verification flow (SMTP or SendGrid)

**Files:** `api/routes/portal.py`, `templates/portal/`, `auth/registration.py`, `auth/email_verify.py`

### 05-04: Claim Clustering & Knowledge Graph Visualization
- [ ] Semantic clustering: group similar claims using embedding cosine similarity
- [ ] `ClusterOf` Neo4j relationship between related claims
- [ ] `GET /api/clusters/{domain_id}` — clustered claims per domain
- [ ] Interactive graph visualization (D3.js or Cytoscape.js) at `/graph`
- [ ] Filter by domain, confidence, certification status

**Files:** `validation/clustering.py`, `api/routes/graph.py`, `templates/graph.html`, `static/js/graph.js`

### 05-05: Source Quality Scoring & Automated Fact-Check Pipeline
- [ ] Source reputation scoring: domain age, citation count, known-reliable list
- [ ] `SourceScore` Neo4j node linked to Source nodes
- [ ] Weighted confidence: source quality feeds into claim confidence calculation
- [ ] Fully automated fact-check pipeline: submit → pre-screen → AI verify → human review queue
- [ ] `POST /api/pipeline/auto-verify` — trigger automated pipeline for a claim
- [ ] Human-in-the-loop only when AI confidence < 0.7

**Files:** `validation/source_scoring.py`, `validation/auto_pipeline.py`, `api/routes/pipeline.py`, `db/queries.py` (update)

### 05-06: Additional Agent Framework Integrations
- [ ] CrewAI integration package (`integrations/crewai-pkg/`)
- [ ] AutoGen integration package (`integrations/autogen-pkg/`)
- [ ] Shared base client extracted from LangChain package
- [ ] Integration test matrix: LangChain + CrewAI + AutoGen against live API

**Files:** `integrations/crewai-pkg/`, `integrations/autogen-pkg/`, `integrations/shared/base_client.py`

**Success Criteria:**
- [ ] CI pipeline green on every PR, auto-deploy on merge to main
- [ ] Integration tests pass against real Neo4j (Docker)
- [ ] Redis cache operational, API stateless and horizontally scalable
- [ ] Developer portal live with self-service registration
- [ ] Knowledge graph visualization accessible at /graph
- [ ] Source quality scoring integrated into confidence calculation
- [ ] At least 2 additional agent framework integrations published

**Status:** ✅ Complete

---

## Phase 7: Agent Outreach & Discovery 🔄

**Goal:** Collect and structure all data relevant for reaching AI agent developers — who builds agents, where they are, what they need, and how to get Swiss Truth in front of them.

**Plans:**

### 07-01: Agent Ecosystem Database
- [x] `data/agent_ecosystem.json` — 10 frameworks, 7 platforms, 7 MCP directories, 11 communities, 4 registries, 5 awesome lists
- Frameworks: LangChain, CrewAI, AutoGen, LlamaIndex, Haystack, DSPy, smolagents, Pydantic AI, Agno, OpenAI Agents SDK
- Platforms: Claude, Cursor, Windsurf, OpenAI GPT Store, n8n, Flowise, Dify
- MCP Directories: Smithery (✅ listed), modelcontextprotocol/servers, Glama, mcp.run, PulseMCP, mcpservers.org, awesome-mcp-servers

### 07-02: Outreach Tracker
- [x] `data/outreach_tracker.json` — 27 channels tracked, 1 done (Smithery), 26 todo
- Priority this week: modelcontextprotocol/servers PR, awesome-mcp-servers PR, LangChain Discord, CrewAI Discord, Glama listing
- Includes: draft messages for all Discord/Reddit posts, PR text for awesome lists, package optimization actions

### 07-03: Agent Persona Profiles
- [x] `data/agent_personas.json` — 8 agent personas with pain points, Swiss Truth value, and key messages
- Personas: Research Agent, Legal Compliance Agent, Health Advisory Agent, Financial Agent, RAG Pipeline, Content Generation Agent, Multi-Agent Orchestrator, Developer Building Agents

### 07-04: Competitive Intelligence
- [x] `data/competitors.json` — 8 competitors analyzed (Google Fact Check, ClaimBuster, Wolfram, Perplexity, Exa, Tavily, Wikipedia, other MCP servers)
- Positioning: Swiss Truth is the only MCP server with 5-stage human+AI validation + Swiss/EU regulatory focus + SHA256 hashes + EU AI Act compliance
- Highest threat: Perplexity (medium) — differentiated by human validation vs. AI synthesis

### 07-05: Discovery Checklist
- [x] `data/discovery_checklist.md` — 30+ action items across P0/P1/P2 priority
- P0: Official MCP server list PR, awesome-mcp-servers PR, Glama listing, LangChain/CrewAI Discord posts, package metadata optimization
- P1: Technical improvements (ai-plugin.json, llms.txt, GitHub topics), more directory listings, community posts
- P2: Content marketing (Dev.to, HuggingFace Space, TDS article), new integrations (LlamaIndex, Haystack, smolagents)

**New files created (Phase 7):**
- `data/agent_ecosystem.json` — AI agent ecosystem database (10 frameworks, 7 platforms, 7 MCP dirs, 11 communities)
- `data/outreach_tracker.json` — Outreach channel tracker with draft messages
- `data/agent_personas.json` — 8 agent persona profiles with pain points and messaging
- `data/competitors.json` — Competitive analysis with positioning and battlecards
- `data/discovery_checklist.md` — Prioritized action checklist (P0/P1/P2)

**Status:** ✅ Complete

---

## Phase 6: AI Agent First 🔄

**Goal:** Make Swiss Truth the indispensable knowledge infrastructure for AI agents — not just fact-checking, but a full agent toolkit. Agents tell us what they need, we build it.

**Plans:**

### 06-A: Agent Feedback Loop
- [x] `agent/feedback.py` — AgentFeedback Neo4j node, CRUD operations, demand-signal aggregation
- [x] `api/routes/agent.py` — 5 endpoints:
  - `POST /api/agent/feedback` — agents report what's missing
  - `GET /api/agent/feedback` — list feedback (admin)
  - `GET /api/agent/feedback/stats` — aggregated demand signals
  - `PATCH /api/agent/feedback/{id}` — update status
  - `GET /api/agent/capabilities` — full capability manifest for agents

### 06-01: get_knowledge_brief MCP Tool
- [x] Returns structured, citable knowledge summary with key facts, sources, confidence
- [x] Optimized for RAG pipelines and agent response enrichment

### 06-02: get_citations MCP Tool
- [x] Solves #1 agent problem: inability to cite sources
- [x] Returns inline + APA citations with verified source URLs

### 06-03: check_freshness MCP Tool
- [x] Checks if a fact is still current vs. changed/outdated
- [x] Detects when agent training data may be stale

### 06-04: check_regulatory_compliance MCP Tool
- [x] Swiss/EU compliance check for agent-generated text
- [x] Domains: swiss-finance (FINMA), swiss-health (BAG), swiss-law, eu-law (GDPR/AI Act)

### 06-05: report_agent_need MCP Tool
- [x] Agents can report missing domains, claims, features directly via MCP
- [x] Creates demand-signal loop: agents → feedback → platform roadmap

### 06-06: Integration Updates
- [x] `integrations/shared/base_client.py` — 6 new methods for Phase 6 tools
- [x] `integrations/crewai-pkg/` — 4 new CrewAI tools (KnowledgeBrief, Citations, Freshness, ReportNeed)
- [x] `integrations/autogen-pkg/` — 4 new AutoGen functions + registered in function_map

**New files created (Phase 6):**
- `agent/__init__.py` + `agent/feedback.py` — feedback loop module
- `agent/knowledge_tools.py` — 5 new MCP tool implementations
- `api/routes/agent.py` — agent-focused REST endpoints

**Modified files:**
- `mcp_server/server.py` — 5 new tools registered (14 total)
- `api/main.py` — agent router wired
- `integrations/shared/base_client.py` — 6 new methods
- `integrations/crewai-pkg/tools.py` — 4 new tools
- `integrations/autogen-pkg/functions.py` — 4 new functions

**Status:** ✅ Complete
