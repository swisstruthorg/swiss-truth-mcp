# Swiss Truth MCP

**Type:** MCP Server + REST API + Dashboard
**Stack:** Python 3.12, FastAPI, Neo4j, MCP SDK, Claude API, Sentence-Transformers
**Status:** Production (swisstruth.org) — v1.2 complete, Phase 6 done

## Description

Verified knowledge base for AI agents — certified facts with confidence scores, primary source URLs, and SHA256 integrity hashes. Prevents LLM hallucination through a 5-stage human + AI validation pipeline covering 22+ domains (Swiss law, health, finance, AI/ML, climate, world science, etc.).

## Architecture

- **MCP Server** — StreamableHTTP transport at `/mcp` (14 tools)
- **REST API** — FastAPI with dashboard, review UI, stats, trust page
- **Database** — Neo4j graph DB with vector index for semantic search
- **Embeddings** — paraphrase-multilingual-MiniLM-L12-v2
- **AI Pipeline** — Claude Haiku for pre-screening, claim comparison, atomization
- **Kanban Service** — Standalone SQLite-based task board with AI agents
- **Integrations** — LangChain (v0.2.0), CrewAI, AutoGen, npm (v0.1.4), Smithery, OpenAI tools
- **Agent Module** — Feedback loop, knowledge tools, regulatory compliance

## Key Decisions

- Neo4j for graph relationships (Expert→validates→Claim→references→Source)
- SHA256 hashing for tamper-evident claims
- Confidence decay: 1%/month since last review (floor 50%)
- Annual expiry with renewal workflow
- HMAC-SHA256 signed webhooks (SEC-04)
- SSRF protection on webhook URLs (SEC-03)
- Daily API cost cap for renewal loop (SEC-05)
- API keys with SHA256 hashing, 3 tiers (free/pro/enterprise)
- W3C PROV-O compatible JSON-LD audit trail
- Multi-tenant support with plan-based isolation
- Agent feedback loop: agents report what's missing → shapes roadmap

## Current Focus (v1.2)

Phase 6: AI Agent First — Complete ✅
- **Agent Feedback Loop** — agents report missing domains/claims/features via MCP
- **get_knowledge_brief** — structured, citable knowledge summary for RAG
- **get_citations** — inline + APA citations with verified source URLs
- **check_freshness** — detects stale training data
- **check_regulatory_compliance** — Swiss/EU compliance guard (FINMA, BAG, GDPR, AI Act)
- **report_agent_need** — demand-signal loop via MCP tool
- **Integration updates** — CrewAI (7 tools), AutoGen (7 functions), shared base client

## MCP Tools (14 total)

| Tool | Purpose |
|------|---------|
| search_knowledge | Hybrid vector+fulltext search across 22+ domains |
| get_claim | Full provenance retrieval by ID |
| list_domains | Available domains with claim counts |
| submit_claim | Submit for expert review pipeline |
| verify_claim | Fact-check: supported/contradicted/unknown |
| get_claim_status | Track submission through review pipeline |
| verify_claims_batch | Parallel verification of up to 20 claims |
| verify_response | Hallucination risk check for full paragraphs |
| find_contradictions | Safety check before publishing facts |
| get_knowledge_brief | Structured, citable knowledge summary (Phase 6) |
| get_citations | Formatted citations with verified sources (Phase 6) |
| check_freshness | Detect stale training data (Phase 6) |
| check_regulatory_compliance | Swiss/EU compliance guard (Phase 6) |
| report_agent_need | Demand-signal feedback loop (Phase 6) |
