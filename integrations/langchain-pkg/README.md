# swiss-truth-langchain

LangChain tools & retriever for [Swiss Truth MCP](https://swisstruth.org) — a certified, source-backed knowledge base for AI agents.

## Install

```bash
pip install swiss-truth-langchain
```

## Quick Start — Toolkit

```python
from swiss_truth_langchain import SwissTruthToolkit

# Read-only — no API key needed
toolkit = SwissTruthToolkit()
tools = toolkit.get_tools()

# With LangGraph agent
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

llm = ChatOpenAI(model="gpt-4o")
agent = create_react_agent(llm, tools)
result = agent.invoke({"messages": [{"role": "user", "content": "Is health insurance mandatory in Switzerland?"}]})
```

## Quick Start — RAG Retriever

```python
from swiss_truth_langchain import SwissTruthRetriever

retriever = SwissTruthRetriever(domain="swiss-law", k=3)
docs = retriever.invoke("How does Swiss health insurance work?")

for doc in docs:
    print(f"[{doc.metadata['confidence']:.0%}] {doc.page_content}")
    print(f"  Source: {doc.metadata['source_url']}")
```

## Tools

| Tool | Name | Description |
|------|------|-------------|
| `SearchKnowledgeTool` | `swiss_truth_search` | Semantic search over 1000+ certified facts |
| `VerifyClaimTool` | `swiss_truth_verify` | Verify a claim — returns verdict + confidence |
| `ListDomainsTool` | `swiss_truth_list_domains` | List all 25+ knowledge domains |
| `GetClaimStatusTool` | `swiss_truth_claim_status` | Check claim validation status |
| `BatchVerifyTool` | `swiss_truth_batch_verify` | Verify multiple claims in parallel |
| `VerifyResponseTool` | `swiss_truth_verify_response` | Check AI response for hallucination risk |
| `FindContradictionsTool` | `swiss_truth_find_contradictions` | Find contradicting certified claims |
| `GetComplianceTool` | `swiss_truth_compliance` | EU AI Act compliance attestation |
| `SubmitClaimTool` | `swiss_truth_submit` | Submit a new claim (API key required) |

## Read-Only Mode

For public-facing agents, use `read_only=True` to exclude write tools:

```python
tools = toolkit.get_tools(read_only=True)  # excludes submit_claim
```

## EU AI Act Compliance

```python
from swiss_truth_langchain import SwissTruthToolkit

toolkit = SwissTruthToolkit()
compliance_tool = [t for t in toolkit.get_tools() if t.name == "swiss_truth_compliance"][0]
print(compliance_tool.run({"claim_id": "your-claim-uuid"}))
```

## Domains

25+ domains including `swiss-law`, `swiss-health`, `swiss-finance`, `eu-law`, `eu-health`, `global-science`, `quantum-computing`, `cybersecurity`, `ai-safety`, `ai-ml`, `us-law`, `climate`, and more.

## Links

- API: [swisstruth.org](https://swisstruth.org)
- MCP Server: `npx swiss-truth-mcp` (for Claude Desktop)
- GitHub: [swisstruthorg/swiss-truth-mcp](https://github.com/swisstruthorg/swiss-truth-mcp)
- Trust Page: [swisstruth.org/trust](https://swisstruth.org/trust)
