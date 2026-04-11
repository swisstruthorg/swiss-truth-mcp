# Swiss Truth MCP

**Stop your AI agent from hallucinating facts.** Swiss Truth is a verified, source-backed knowledge base accessible via MCP — certified claims with confidence scores, primary source URLs, and SHA256 integrity hashes.

No API key. No setup. Connect in 30 seconds.

---

## Why agents need this

LLMs hallucinate facts, especially for **country-specific, regulatory, and scientific** topics. Swiss Truth gives your agent a **ground-truth layer** it can query before answering — returning only claims that have passed a 5-stage human + AI validation pipeline.

| Without Swiss Truth | With Swiss Truth |
|---------------------|-----------------|
| "Health insurance in Switzerland is optional, I think..." | "Health insurance is mandatory (KVG Art. 3) — confidence 0.99, source: bag.admin.ch" |
| Unknown answer on Swiss VAT rates | Certified claim with current rate + legal source |
| Unverified AI/ML definition | Peer-reviewed explanation with academic citation |

---

## Quick Setup — Claude Desktop

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

Restart Claude Desktop — done.

---

## 6 MCP Tools

### `search_knowledge` — Semantic search over certified facts

```
search_knowledge("How does health insurance work in Switzerland?")
search_knowledge("Was ist RAG in der KI?")          # DE auto-detected
search_knowledge("三权分立原则")                       # ZH auto-detected
```

**Returns:** ranked list of certified claims, each with:
- `confidence_score` (0.0 – 1.0)
- `source_urls` (gov, academic, institutional — no Wikipedia)
- `hash` (SHA256 for tamper detection)
- `language`, `domain`, `last_reviewed`

Supports: **DE · EN · FR · IT · ES · ZH · AR · RU · JA · KO**

---

### `verify_claim` — Fact-check any statement

```
verify_claim("Die Krankenversicherung in der Schweiz ist freiwillig.")
```

```json
{
  "verdict": "contradicted",
  "confidence": 0.879,
  "explanation": "Swiss law (KVG Art. 3) mandates health insurance for all residents.",
  "evidence": [...],
  "sources": ["https://www.bag.admin.ch/..."]
}
```

Returns: `supported` · `contradicted` · `unknown`

---

### `get_claim` — Full provenance for a single claim

```
get_claim("sha256:d21321db714d...")
```

Returns: claim text, domain, language, confidence, validator, institution, review date, all source URLs, SHA256 hash.

---

### `list_domains` — Browse the knowledge base

```
list_domains()
```

Returns all 12 domains with certified claim counts. Use to understand coverage before querying.

---

### `submit_claim` — Contribute to the knowledge base

Submit a claim for expert review. Automatically triggers the full validation pipeline (dedup → AI pre-screen → source verification → human review → signing).

---

### `get_claim_status` — Track validation progress

Check where your submitted claim is: `draft` → `peer_review` → `certified`

---

## Knowledge Domains

| Domain | ID | Focus |
|--------|----|-------|
| Swiss Health | `swiss-health` | KVG, mandatory insurance, Krankenkasse |
| Swiss Law | `swiss-law` | Federal law, cantonal rules, civil code |
| Swiss Finance | `swiss-finance` | AHV, 3-pillar system, taxes, banking |
| Swiss Politics | `swiss-politics` | Federal Council, direct democracy, elections |
| Swiss Education | `swiss-education` | University system, apprenticeships, Bologna |
| Swiss Energy | `swiss-energy` | Nuclear, renewables, energy strategy 2050 |
| Swiss Transport | `swiss-transport` | SBB, highways, LSVA |
| Swiss Agriculture | `swiss-agriculture` | Direct payments, organic, food sovereignty |
| Climate Science | `climate` | IPCC findings, temperature data, emissions |
| AI / ML | `ai-ml` | RAG, transformers, LLM concepts, benchmarks |
| Natural Sciences | `world-science` | Physics, chemistry, biology fundamentals |
| World History | `world-history` | Verified historical facts and dates |

---

## Agent Use Cases

**RAG grounding** — Before answering a user question, call `search_knowledge` to retrieve certified context. Pass it as system context to prevent hallucination.

**Fact-checking pipeline** — Use `verify_claim` as a post-processing step to validate claims in generated text before showing them to users.

**Compliance checks** — For Swiss regulatory topics (insurance, taxes, legal obligations), retrieve ground truth with source references your users can verify.

**Multi-language support** — One agent, 10+ languages. The query language is auto-detected — no need to specify it.

---

## Trust & Methodology

Every claim passes a **5-stage validation pipeline**:

1. **Semantic dedup** — vector similarity ≥ 95% blocks redundant submissions
2. **AI pre-screen** — Claude Haiku checks atomicity, factuality, source presence
3. **Source verification** — each URL fetched and verified to support the claim
4. **Expert peer review** — human validation with confidence score assignment
5. **SHA256 signing + annual expiry** — confidence decays 1%/month until renewed

Full transparency: [swisstruth.org/trust](https://swisstruth.org/trust)

---

## Endpoints

| | |
|--|--|
| MCP endpoint | `https://swisstruth.org/mcp` |
| MCP discovery | `https://swisstruth.org/.well-known/mcp.json` |
| Trust & stats | `https://swisstruth.org/trust` |
| REST API docs | `https://swisstruth.org/docs` |
| RSS feed | `https://swisstruth.org/feed.rss` |
| Webhook subscriptions | `POST https://swisstruth.org/webhooks` |

---

## Subscribe to new certified claims

**RSS** — poll or subscribe in any feed reader:
```
https://swisstruth.org/feed.rss
https://swisstruth.org/feed.rss?domain=swiss-health
```

**Webhook** — get notified on every certification:
```bash
curl -X POST https://swisstruth.org/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-agent.example.com/hook", "domain": "swiss-health"}'
```

---

Built with [FastAPI](https://fastapi.tiangolo.com) · [Neo4j](https://neo4j.com) · [MCP](https://modelcontextprotocol.io) · [Claude](https://anthropic.com)
