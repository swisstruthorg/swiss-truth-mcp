# Swiss Truth MCP

> **Verified knowledge infrastructure for AI agents — certified facts, not hallucinations.**

[![MCP](https://img.shields.io/badge/MCP-StreamableHTTP-blue)](https://swisstruth.org/mcp)
[![Domains](https://img.shields.io/badge/domains-30-green)](https://swisstruth.org/.well-known/mcp.json)
[![Claims](https://img.shields.io/badge/certified_facts-2000%2B-brightgreen)](https://swisstruth.org/trust)
[![Languages](https://img.shields.io/badge/languages-10-blue)](https://swisstruth.org/mcp)
[![EU AI Act](https://img.shields.io/badge/EU_AI_Act-compliant-blue)](https://swisstruth.org/trust)
[![Auth](https://img.shields.io/badge/API_key-not_required-success)](https://swisstruth.org/mcp)
[![LangChain](https://img.shields.io/badge/LangChain-swiss--truth--langchain-orange)](https://pypi.org/project/swiss-truth-langchain)
[![CrewAI](https://img.shields.io/badge/CrewAI-swiss--truth--crewai-red)](https://pypi.org/project/swiss-truth-crewai)
[![AutoGen](https://img.shields.io/badge/AutoGen-swiss--truth--autogen-purple)](https://pypi.org/project/swiss-truth-autogen)

Swiss Truth is a **human + AI validated knowledge base** purpose-built for AI agents.
Every fact passes a 5-stage validation pipeline, carries a confidence score, verified source URLs, and a SHA256 integrity hash.
Connect in 30 seconds. No API key required.

---

## Why agents use Swiss Truth

| Problem | Swiss Truth Tool |
|---|---|
| 🧠 **LLM hallucination** on factual questions | `search_knowledge` — 2000+ certified facts, 30 domains |
| 📎 **Cannot cite sources** or verify citations | `get_citations` — inline + APA with verified URLs |
| ⏰ **Stale training data** on fast-changing topics | `check_freshness` — detect outdated facts |
| ⚖️ **Non-compliant responses** in regulated domains | `check_regulatory_compliance` — FINMA, BAG, GDPR, EU AI Act |
| ✅ **Verify multiple claims** before sending a response | `verify_claims_batch` — up to 20 claims in parallel |
| 🔍 **Full response hallucination risk** | `verify_response` — low / medium / high risk score |

---

## Quick Setup

### MCP (Claude Desktop, Cursor, Windsurf, any MCP client)

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

Or directly via HTTP:
```json
{
  "mcpServers": {
    "swiss-truth": {
      "type": "http",
      "url": "https://swisstruth.org/mcp"
    }
  }
}
```

### LangChain
```bash
pip install swiss-truth-langchain
```
```python
from swiss_truth_langchain import SwissTruthToolkit

toolkit = SwissTruthToolkit()
tools = toolkit.get_tools()  # search, verify, batch verify, citations, freshness, compliance
```

### CrewAI
```bash
pip install swiss-truth-crewai
```
```python
from swiss_truth_crewai import SwissTruthSearchTool, SwissTruthVerifyTool
from crewai import Agent

researcher = Agent(
    role="Research Agent",
    tools=[SwissTruthSearchTool(), SwissTruthVerifyTool()]
)
```

### AutoGen
```bash
pip install swiss-truth-autogen
```
```python
from swiss_truth_autogen import register_swiss_truth_functions

register_swiss_truth_functions(assistant, user_proxy)
# Adds: search_knowledge, verify_claim, verify_claims_batch, get_knowledge_brief
```

### OpenAI function-calling
```python
import requests

tools = requests.get("https://swisstruth.org/openai-tools.json").json()
# Ready-to-use tool definitions for OpenAI API, LlamaIndex, etc.
```

---

## 14 MCP Tools

### 🔍 Retrieval
| Tool | Description |
|---|---|
| `search_knowledge` | Semantic search over 2000+ certified facts. Auto-detects language (DE/EN/FR/IT/ES/ZH/AR/RU/JA/KO). Returns confidence score, source URLs, SHA256 hash. |
| `get_claim` | Full provenance for a single claim: validator, institution, review date, SHA256. |
| `get_knowledge_brief` | Structured, citable knowledge brief optimized for RAG pipelines. |
| `list_domains` | Browse all 30 knowledge domains with certified claim counts. |

### ✅ Verification
| Tool | Description |
|---|---|
| `verify_claim` | Fact-check a statement: `supported` / `contradicted` / `unknown` with confidence + evidence. |
| `verify_claims_batch` | Verify up to 20 claims in parallel. Returns per-claim verdict + summary. |
| `verify_response` | Check a full AI response for hallucination risk: `low` / `medium` / `high`. |
| `find_contradictions` | Find all certified claims that contradict a statement. |

### 📎 Citation & Quality
| Tool | Description |
|---|---|
| `get_citations` | Properly formatted inline + APA citations with verified source URLs. |
| `check_freshness` | Detect stale training data. Returns `current` / `changed` / `unknown`. |
| `check_regulatory_compliance` | Swiss/EU compliance check (FINMA, BAG, GDPR, EU AI Act). |

### 📥 Contribution & Feedback
| Tool | Description |
|---|---|
| `submit_claim` | Submit a missing fact for expert review. Triggers AI pre-screening + URL verification. |
| `get_claim_status` | Track review pipeline: `draft` → `peer_review` → `certified`. |
| `report_agent_need` | Report missing domains or features — feedback shapes the roadmap. |

---

## 30 Knowledge Domains

**🇨🇭 Swiss (11):** `swiss-health` · `swiss-law` · `swiss-finance` · `swiss-education` · `swiss-energy` · `swiss-transport` · `swiss-politics` · `swiss-agriculture` · `swiss-digital` · `swiss-environment` · `labor-employment`

**🇪🇺 EU & Global (6):** `eu-law` · `eu-health` · `global-science` · `international-law` · `economics` · `us-law`

**🔬 Science & Tech (8):** `ai-ml` · `ai-safety` · `quantum-computing` · `cybersecurity` · `biotech` · `renewable-energy` · `space-science` · `blockchain-crypto`

**🌍 General (5):** `climate` · `world-science` · `world-history` · `mental-health` · `nutrition-food`

---

## Agent Personas

| Agent Type | Primary Tools | Use Case |
|---|---|---|
| **Research Agent** | `search_knowledge`, `get_knowledge_brief`, `get_citations` | Ground research in verified facts |
| **Legal Compliance** | `search_knowledge`, `check_regulatory_compliance`, `verify_claim` | FINMA, BAG, GDPR, EU AI Act |
| **RAG Pipeline** | `get_knowledge_brief`, `search_knowledge`, `get_citations` | Enrich retrieval with validated facts |
| **Fact-Checking** | `verify_claim`, `verify_claims_batch`, `verify_response` | Prevent hallucinations |
| **Health Advisory** | `search_knowledge`, `check_regulatory_compliance`, `check_freshness` | KVG, Krankenkasse, Swissmedic |
| **Financial Agent** | `search_knowledge`, `check_regulatory_compliance`, `verify_claim` | FINMA-compliant information |

---

## Discovery Endpoints

Swiss Truth is discoverable by agents and crawlers via standard endpoints:

| Endpoint | Standard | Purpose |
|---|---|---|
| `/.well-known/mcp.json` | RFC 8615 | MCP auto-discovery |
| `/.well-known/ai-plugin.json` | OpenAI | GPT / Assistants API integration |
| `/agents.json` | Swiss Truth | Agent capability manifest |
| `/llms.txt` | llmstxt.org | LLM crawler discovery |
| `/openai-tools.json` | OpenAI | Function-calling tool definitions |

---

## Validation Pipeline

Every claim passes a 5-stage pipeline before certification:

```
Submit → AI Pre-Screen → URL Verification → Expert Review → Peer Review → Certified ✓
```

- **SHA256 integrity hash** — detect tampering
- **Blockchain anchoring** — weekly Merkle root on-chain
- **Confidence scoring** — multi-dimensional quality score
- **Auto-renewal** — expired claims re-verified daily
- **EU AI Act compliant** — full audit trail

---

## Knowledge Stats

| Metric | Value |
|---|---|
| Certified claims | 2000+ |
| Domains | 30 |
| Languages | 10 |
| Validation stages | 5 |
| Human validated | ✓ |
| SHA256 integrity | ✓ |
| Blockchain anchored | ✓ |
| EU AI Act compliant | ✓ |
| API key required | ✗ |

---

## Example Queries

```
"Is health insurance mandatory in Switzerland?"
"What does the EU AI Act require for high-risk AI systems?"
"How does RAG reduce LLM hallucinations?"
"What are the FINMA regulations for crypto assets?"
"What is the current status of quantum error correction?"
"How does Swiss mandatory health insurance work?"
```

---

## Links

- 🌐 **Website:** [swisstruth.org](https://swisstruth.org)
- 📊 **Trust & Stats:** [swisstruth.org/trust](https://swisstruth.org/trust)
- 🔌 **MCP Endpoint:** `https://swisstruth.org/mcp`
- 📦 **npm package:** `npx -y mcp-remote https://swisstruth.org/mcp`
- 🐍 **PyPI LangChain:** `pip install swiss-truth-langchain`
- 🐍 **PyPI CrewAI:** `pip install swiss-truth-crewai`
- 🐍 **PyPI AutoGen:** `pip install swiss-truth-autogen`
