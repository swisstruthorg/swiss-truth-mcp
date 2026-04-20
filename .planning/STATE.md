# Project State: Swiss Truth MCP

**Current Milestone:** v1.0
**Current Phase:** Phase 3 — Scale & Quality
**Status:** Not Started
**Last Activity:** 2026-04-20

## Phase Progress

| Phase | Name | Status |
|-------|------|--------|
| 0 | Agent Instrumentation | ✅ Complete |
| 1 | Critical Fixes | ✅ Complete |
| 2 | Growth & Integrations | ✅ Complete |
| 3 | Scale & Quality | 🔲 Not Started |
| 4 | Enterprise & Compliance | 🔲 Not Started |

## Accumulated Context

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
