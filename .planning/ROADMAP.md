# Roadmap: Swiss Truth MCP

*Reconstructed from GSD session `hungry-babbage-aa6eb1` + git history*
*Last updated: 2026-04-20*

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

## Phase 4: Enterprise & Compliance 🔲

**Goal:** Enterprise features — API keys, usage tiers, SLA monitoring, full EU AI Act compliance attestation.

**Plans:**
- [ ] API key management with usage tiers
- [ ] SLA monitoring and alerting
- [ ] Full EU AI Act compliance report generation
- [ ] Audit trail export (JSON-LD)
- [ ] Multi-tenant support

**Status:** Not Started
