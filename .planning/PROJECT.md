# Swiss Truth MCP

**Type:** MCP Server + REST API + Dashboard
**Stack:** Python 3.12, FastAPI, Neo4j, MCP SDK, Claude API, Sentence-Transformers
**Status:** Production (swisstruth.org)

## Description

Verified knowledge base for AI agents — certified facts with confidence scores, primary source URLs, and SHA256 integrity hashes. Prevents LLM hallucination through a 5-stage human + AI validation pipeline covering 22+ domains (Swiss law, health, finance, AI/ML, climate, world science, etc.).

## Architecture

- **MCP Server** — StreamableHTTP transport at `/mcp` (9 tools)
- **REST API** — FastAPI with dashboard, review UI, stats, trust page
- **Database** — Neo4j graph DB with vector index for semantic search
- **Embeddings** — paraphrase-multilingual-MiniLM-L12-v2
- **AI Pipeline** — Claude Haiku for pre-screening, claim comparison, atomization
- **Kanban Service** — Standalone SQLite-based task board with AI agents

## Key Decisions

- Neo4j for graph relationships (Expert→validates→Claim→references→Source)
- SHA256 hashing for tamper-evident claims
- Confidence decay: 1%/month since last review (floor 50%)
- Annual expiry with renewal workflow
- HMAC-SHA256 signed webhooks (SEC-04)
- SSRF protection on webhook URLs (SEC-03)
- Daily API cost cap for renewal loop (SEC-05)
