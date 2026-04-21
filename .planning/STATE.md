# Project State: Swiss Truth MCP

**Current Milestone:** v1.0
**Current Phase:** Phase 4 — Enterprise & Compliance
**Status:** Not Started
**Last Activity:** 2026-04-20

## Phase Progress

| Phase | Name | Status |
|-------|------|--------|
| 0 | Agent Instrumentation | ✅ Complete |
| 1 | Critical Fixes | ✅ Complete |
| 2 | Growth & Integrations | ✅ Complete |
| 3 | Scale & Quality | ✅ Complete |
| 4 | Enterprise & Compliance | 🔲 Not Started |

## Accumulated Context

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
