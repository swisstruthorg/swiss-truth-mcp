# Swiss Truth MCP

**Verified knowledge base for AI agents.** Certified facts with source references, confidence scores, and SHA256 integrity hashes — ready to use via the Model Context Protocol (MCP).

No API key required. Fully public. Connect in 30 seconds.

---

## Quick Setup — Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "swiss-truth": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://swisstruth.org/mcp"]
    }
  }
}
```

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop — Swiss Truth is ready.

---

## What it does

Swiss Truth gives AI agents access to a curated, expert-reviewed knowledge base covering Swiss law, health, finance, education, energy, transport, politics, climate, AI/ML, and world science.

Every claim has passed a 5-stage validation pipeline:

1. **Semantic deduplication** — vector similarity ≥ 95% blocks redundant submissions
2. **AI pre-screen** — Claude Haiku checks atomicity, factuality, and source presence
3. **Source verification** — each URL is fetched and verified to support the claim
4. **Expert peer review** — human validation with confidence score assignment
5. **SHA256 integrity signing** — tamper detection + annual expiry with confidence decay

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_knowledge` | Semantic search over certified claims. Supports DE, EN, FR, IT, ES, ZH. Returns confidence score, source references, and SHA256 hash. |
| `verify_claim` | Fact-check a statement → `supported` / `contradicted` / `unknown` with evidence and sources. |
| `get_claim` | Retrieve a single claim with full provenance (validator, institution, review date). |
| `list_domains` | List all knowledge domains with certified claim counts. |
| `submit_claim` | Submit a new claim for expert review. Triggers the full validation pipeline automatically. |
| `get_claim_status` | Check the validation status of a submitted claim (`draft` → `peer_review` → `certified`). |

---

## Example usage

**Search (any language — auto-detected):**
```
How does health insurance work in Switzerland?
Wie funktioniert die Krankenversicherung in der Schweiz?
¿Cómo funciona el seguro médico en Suiza?
```

**Fact-check:**
```
verify_claim("Die Krankenversicherung in der Schweiz ist freiwillig.")
→ verdict: "contradicted", confidence: 0.879
```

---

## Why trust Swiss Truth?

- **Source-backed**: Every claim requires primary sources (gov, academic, institutional). Wikipedia excluded.
- **Confidence decay**: Scores decrease 1%/month until renewed — no stale data silently served.
- **Cryptographic integrity**: SHA256 hash over canonical claim content for tamper detection.
- **Multi-language**: Auto-detects query language (DE/EN/FR/IT/ES/ZH/AR/RU/JA/KO) and searches in the detected language with automatic fallback.
- **Public pipeline**: Full methodology at [swisstruth.org/trust](https://swisstruth.org/trust).

---

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `https://swisstruth.org/mcp` | MCP StreamableHTTP endpoint |
| `https://swisstruth.org/.well-known/mcp.json` | MCP auto-discovery (RFC 8615) |
| `https://swisstruth.org/trust` | Public trust & transparency page |
| `https://swisstruth.org/feed.rss` | RSS feed of new certified claims |
| `https://swisstruth.org/webhooks` | Webhook subscription API |
| `https://swisstruth.org/docs` | REST API reference |

---

## Subscribe to new claims

**RSS** (poll or subscribe):
```
https://swisstruth.org/feed.rss
https://swisstruth.org/feed.rss?domain=swiss-health
```

**Webhook** (push on certification):
```bash
curl -X POST https://swisstruth.org/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-agent.example.com/hook", "domain": "swiss-health"}'
```

---

## Knowledge domains

- Swiss Health (`swiss-health`)
- Swiss Law (`swiss-law`)
- Swiss Finance (`swiss-finance`)
- Swiss Education (`swiss-education`)
- Swiss Energy (`swiss-energy`)
- Swiss Transport (`swiss-transport`)
- Swiss Politics (`swiss-politics`)
- Swiss Agriculture (`swiss-agriculture`)
- Climate Science (`climate`)
- AI/ML (`ai-ml`)
- Natural Sciences (`world-science`)
- World History (`world-history`)

---

**Trust page:** [swisstruth.org/trust](https://swisstruth.org/trust) · **MCP Discovery:** [swisstruth.org/.well-known/mcp.json](https://swisstruth.org/.well-known/mcp.json)
