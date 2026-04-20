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

## Phase 2: Growth & Integrations 🔲

**Goal:** Expand reach — npm package, Smithery listing, LangChain integration, OpenAI function-calling compatibility.

**Research completed:** Stack, Architecture, Features, Pitfalls (via GSD agents)

**Plans:**
- [x] npm package published (swiss-truth-mcp v0.1.4)
- [x] Smithery configuration (smithery.yaml)
- [x] OpenAI tools endpoint (/openai-tools.json)
- [x] MCP auto-discovery (/.well-known/mcp.json)
- [ ] LangChain integration package (integrations/langchain-pkg/)
- [ ] EU AI Act compliance endpoint improvements

**Status:** In Progress

---

## Phase 3: Scale & Quality 🔲

**Goal:** Improve claim quality, add multi-language seed data, automated renewal pipeline, blockchain anchoring.

**Plans:**
- [ ] Automated renewal pipeline with cost-capped AI re-verification
- [ ] Blockchain anchoring (Polygon/Base) for certified claim hashes
- [ ] Multi-language claim generation (FR, IT, ES, ZH)
- [ ] Coverage analysis per domain (gap detection)
- [ ] Advanced conflict detection with explanation

**Status:** Not Started

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
