# State: Swiss Truth MCP

*Last updated: 2026-04-23*

---

## Current Phase: Phase 9 ✅ — AI Agent Discovery & Findability

**Milestone:** *"Agents find us, not the other way around."*

**Status:** Complete

---

## What was just built (Phase 9)

### New Discovery Endpoints

| Endpoint | Standard | Purpose |
|---|---|---|
| `/.well-known/mcp.json` | RFC 8615 | MCP auto-discovery — extended with 14 tools, keywords, categories, agent_frameworks, example_queries, capabilities, integrations |
| `/.well-known/ai-plugin.json` | OpenAI | GPT / Assistants API / ChatGPT Plugin auto-discovery |
| `/agents.json` | Swiss Truth | Machine-readable agent capability manifest (problems_solved, tools, domains, quick_start, agent_personas) |
| `/llms.txt` | llmstxt.org | LLM crawler discovery (Perplexity, SearchGPT, etc.) |
| `/openai-tools.json` | OpenAI | 14 OpenAI function-calling tool definitions (was 9, now 14) |

### README.md — Agent-First Rewrite
- Badges: MCP, Domains, Claims, Languages, EU AI Act, Auth, LangChain, CrewAI, AutoGen
- "Why agents use Swiss Truth" table (6 problems → 6 tools)
- Quick Setup for all 5 integration paths
- 14 MCP Tools table (4 categories: Retrieval, Verification, Citation & Quality, Contribution)
- 30 Knowledge Domains (4 groups)
- Agent Personas table (6 types)
- Discovery Endpoints table
- Validation Pipeline diagram
- Knowledge Stats table

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

---

## Current System State

### MCP Server
- **14 tools** registered and live at `https://swisstruth.org/mcp`
- Transport: StreamableHTTP
- Auth: None required

### Knowledge Base
- **2000+ certified claims** across **30 domains**
- **10 languages** (DE, EN, FR, IT, ES, ZH, AR, RU, JA, KO)
- 5-stage validation pipeline
- SHA256 integrity hashes
- Weekly blockchain anchoring (Merkle root)
- Daily auto-renewal (Claude Haiku)

### Integrations
- `swiss-truth-langchain` — PyPI, 9 tools + SwissTruthRetriever + SwissTruthToolkit
- `swiss-truth-crewai` — PyPI, 8 tools
- `swiss-truth-autogen` — PyPI, 8 functions
- `swiss-truth-mcp` — npm, `npx -y mcp-remote https://swisstruth.org/mcp`
- Smithery — listed

### Discovery Coverage
- MCP clients (Claude Desktop, Cursor, Windsurf): `/.well-known/mcp.json` ✅
- OpenAI GPTs / Assistants API: `/.well-known/ai-plugin.json` ✅
- LLM crawlers (Perplexity, SearchGPT): `/llms.txt` ✅
- Agent frameworks: `/agents.json` ✅
- Direct function-calling: `/openai-tools.json` ✅ (14 tools)
- Smithery directory: ✅ listed
- modelcontextprotocol/servers: 🔄 PR pending
- awesome-mcp-servers: 🔄 PR pending
- Glama: 🔄 pending
- LangChain/CrewAI Discord: 🔄 pending

---

## Next Actions (Phase 10 candidates)

### Outreach (from Phase 7 checklist)
1. **PR: modelcontextprotocol/servers** — official MCP server list (highest impact)
2. **PR: awesome-mcp-servers** — most-starred MCP directory
3. **Glama listing** — `https://glama.ai/mcp/servers/submit`
4. **LangChain Discord** — `#tools-and-integrations` channel
5. **CrewAI Discord** — `#tools` channel
6. **Reddit r/LocalLLaMA** — "I built a verified knowledge base MCP server"
7. **HuggingFace Space** — interactive demo

### Technical
- LlamaIndex integration package (`swiss-truth-llamaindex`)
- Haystack integration package (`swiss-truth-haystack`)
- smolagents integration
- GitHub repository topics: `mcp`, `fact-checking`, `ai-agents`, `hallucination-prevention`, `swiss-law`, `rag`, `langchain`, `crewai`, `autogen`
- Smithery listing optimization (description, tags, examples)

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
