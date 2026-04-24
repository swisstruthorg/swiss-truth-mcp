# State: Swiss Truth MCP

*Last updated: 2026-04-23*

---

## Current Phase: Phase 11 🔄 — Agent Acquisition Blitz

**Milestone:** *"Agenten finden uns überall."*

**Status:** In Progress — Start April 2026

**Ziel:** Von 1 Listing (Smithery) → 8+ Listings, Community-Posts, Package-Optimierung.

### Phase 11 Steps

| Step | Beschreibung | Status |
|------|-------------|--------|
| 11-01 | Package Metadata Optimierung (CrewAI, AutoGen pyproject.toml + npm) | ✅ Done |
| 11-02 | MCP Directory Listings (mcp.run, PulseMCP, mcpservers.org) | ⬜ Manual |
| 11-03 | Awesome List PRs (awesome-langchain, awesome-llm-apps, awesome-ai-agents) | ⬜ Manual |
| 11-04 | Community Posts (HN, Reddit, GitHub Discussions) | ⬜ Manual |
| 11-05 | Tracker & State Update | ✅ Done |

### Phase 11 Outreach Materials

```
data/outreach/
├── pr_mcp_run.md                      # mcp.run listing text
├── pr_pulsemcp.md                     # PulseMCP listing text
├── pr_mcpservers.md                   # mcpservers.org PR
├── pr_awesome_langchain.md            # awesome-langchain PR
├── pr_awesome_llm_apps.md             # awesome-llm-apps PR
├── pr_awesome_ai_agents.md            # awesome-ai-agents PR
├── post_hackernews.md                 # Show HN post
├── post_reddit_langchain.md           # r/LangChain post
├── post_reddit_ml.md                  # r/MachineLearning post
├── post_github_discussions_langchain.md
└── post_github_discussions_crewai.md
```

### Phase 11 Run Script

```bash
./phase11_run.sh             # Full status check
./phase11_run.sh --step 11-01  # Package metadata check
./phase11_run.sh --step 11-05  # Outreach tracker status
```

### KPIs Phase 11

| Metrik | Aktuell | Ziel |
|--------|---------|------|
| MCP Directory Listings | 3 (Smithery, Glama, mcp/servers PR) | 8+ |
| Awesome List PRs | 1 (awesome-mcp-servers PR) | 5+ |
| PyPI Downloads/Monat | ? | 500+ |
| npm Downloads/Monat | ? | 200+ |
| Community Posts | 0 | 5+ |

**Danach:** Phase 12 — Agent Stickiness & Lock-In

📄 Vollständige Growth-Roadmap: `.planning/ROADMAP_GROWTH.md`

---

## Previous Phase: Phase 10 ✅ — Content Foundation

**Milestone:** *"Erst das Regal füllen, dann den Laden öffnen."*

**Status:** Complete (Steps 10-01 bis 10-05 abgeschlossen, 10-06–10-08 laufend/remote)

| Step | Beschreibung | Status |
|------|-------------|--------|
| 10-01 | Coverage-Audit: 18 Domains unter 100 Claims identifiziert | ✅ Done |
| 10-02 | Rate-Limit-Bug in generator.py gefunden und gefixt | ✅ Done |
| 10-03 | Fix committed (cdde4d7) + deployed via SCP + Docker restart | ✅ Done |
| 10-04 | Bulk Generation Tier 2 (8 neue Domains) | ✅ Done |
| 10-05 | 8 neue Domains in generator.py definiert + committed (a57ebe4) | ✅ Done |
| 10-06 | Multi-Language Expansion (FR + IT für Schweizer Kerndomains) | 🔄 Running remote |
| 10-07 | Quality Assurance (Conflict Detection, Renewal, Re-Check) | 🔄 Pending |
| 10-08 | Agent-Attraktivitäts-Benchmark (8 Personas × 5 Queries) | 🔄 Pending |

---

## Previous Phase: Phase 9 ✅ — AI Agent Discovery & Findability

**Status:** Complete

---

## Completed Phases

| Phase | Name | Status |
|---|---|---|
| 0 | Agent Instrumentation | ✅ Complete |
| 1 | Critical Fixes | ✅ Complete |
| 2 | Growth & Integrations | ✅ Complete |
| 3 | Scale & Quality | ✅ Complete |
| 4 | Enterprise & Compliance | ✅ Complete |
| 5 | Production Hardening & Developer Experience | ✅ Complete |
| 6 | AI Agent First (14 MCP tools) | ✅ Complete |
| 7 | Agent Outreach & Discovery Data | ✅ Complete |
| 9 | AI Agent Discovery & Findability | ✅ Complete |
| 10 | Content Foundation | ✅ Complete (core steps) |

---

## Current System State

### MCP Server
- **14 tools** registered and live at `https://swisstruth.org/mcp`
- Transport: StreamableHTTP
- Auth: None required

### Knowledge Base
- **3000+ certified claims** across **38 domains**
- **10 languages** (DE, EN, FR, IT, ES, ZH, AR, RU, JA, KO)
- 5-stage validation pipeline
- SHA256 integrity hashes
- Weekly blockchain anchoring (Merkle root)
- Daily auto-renewal (Claude Haiku)

### Integrations
- `swiss-truth-langchain` v0.2.0 — PyPI
- `swiss-truth-crewai` v0.1.1 — PyPI (metadata optimiert)
- `swiss-truth-autogen` v0.1.1 — PyPI (metadata optimiert)
- `swiss-truth-mcp` v0.1.4 — npm (keywords optimiert)
- Smithery — listed

### Discovery Coverage
- MCP clients (Claude Desktop, Cursor, Windsurf): `/.well-known/mcp.json` ✅
- OpenAI GPTs / Assistants API: `/.well-known/ai-plugin.json` ✅
- LLM crawlers (Perplexity, SearchGPT): `/llms.txt` ✅
- Agent frameworks: `/agents.json` ✅
- Direct function-calling: `/openai-tools.json` ✅ (14 tools)
- Smithery directory: ✅ listed
- Glama: ✅ submitted 2026-04-22
- modelcontextprotocol/servers: 🔄 PR #4007 pending
- awesome-mcp-servers: 🔄 PR #5230 pending
- mcp.run: ⬜ TODO → data/outreach/pr_mcp_run.md
- PulseMCP: ⬜ TODO → data/outreach/pr_pulsemcp.md
- mcpservers.org: ⬜ TODO → data/outreach/pr_mcpservers.md
- awesome-langchain: ⬜ TODO → data/outreach/pr_awesome_langchain.md
- awesome-llm-apps: ⬜ TODO → data/outreach/pr_awesome_llm_apps.md
- awesome-ai-agents: ⬜ TODO → data/outreach/pr_awesome_ai_agents.md

---

## Key URLs

| Resource | URL |
|---|---|
| MCP Endpoint | `https://swisstruth.org/mcp` |
| REST API | `https://swisstruth.org/api` |
| Trust & Stats | `https://swisstruth.org/trust` |
| MCP Discovery | `https://swisstruth.org/.well-known/mcp.json` |
| AI Plugin | `https://swisstruth.org/.well-known/ai-plugin.json` |
| Agent Manifest | `https://swisstruth.org/agents.json` |
| LLMs.txt | `https://swisstruth.org/llms.txt` |
| OpenAI Tools | `https://swisstruth.org/openai-tools.json` |
| Smithery | `https://smithery.ai/server/swiss-truth-mcp` |
