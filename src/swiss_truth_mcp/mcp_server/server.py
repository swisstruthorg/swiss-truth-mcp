"""
Swiss Truth MCP Server — Ground Truth Layer für KI-Agenten

Starte via: swiss-truth-mcp
Oder für Claude Desktop: python -m swiss_truth_mcp.mcp_server.server
"""
import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from swiss_truth_mcp.mcp_server.tools import (
    search_knowledge,
    get_claim,
    list_domains,
    submit_claim,
    get_claim_status,
    verify_claim,
    verify_claims_batch,
    verify_response,
    find_contradictions,
)

app = Server("swiss-truth")

# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

@app.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_knowledge",
            description=(
                "Search the Swiss Truth verified knowledge base for certified facts. "
                "USE THIS TOOL when you need reliable, source-backed information to avoid hallucination — "
                "covering 22+ domains: Swiss law, health, finance, politics, education, energy, transport, "
                "EU law & regulation, EU health, global science, AI/ML, AI safety, quantum computing, "
                "cybersecurity, biotech, renewable energy, space science, economics, international law, "
                "US law, climate, world history, and Swiss digitalization. "
                "Call this before answering factual questions where being wrong would matter. "
                "\n\nReturns per result:"
                "\n- 'claim': the verified statement"
                "\n- 'canonical_question': the exact question this claim answers (high match = high relevance)"
                "\n- 'confidence': certified score (0–1)"
                "\n- 'effective_confidence': age-adjusted score — lower means renewal is overdue"
                "\n- 'source_references': validated primary sources (no Wikipedia)"
                "\n- 'validated_by': expert name + institution"
                "\n- 'hash': SHA256 for tamper detection"
                "\n\nExamples: 'How does Swiss health insurance work?', "
                "'What does the EU AI Act require?', "
                "'How does RAG reduce hallucinations?', "
                "'What are CRISPR gene therapy safety limits?', "
                "'What is the current state of quantum error correction?'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query in DE, EN, FR, or IT. Phrase it as a question for best results.",
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional domain filter. Available domains: "
                            "Swiss: 'swiss-health', 'swiss-law', 'swiss-finance', 'swiss-education', "
                            "'swiss-energy', 'swiss-transport', 'swiss-politics', 'swiss-agriculture', 'swiss-digital'. "
                            "EU & Global: 'eu-law', 'eu-health', 'global-science', 'international-law', 'economics'. "
                            "Science & Tech: 'ai-ml', 'ai-safety', 'quantum-computing', 'cybersecurity', "
                            "'biotech', 'renewable-energy', 'space-science'. "
                            "General: 'climate', 'world-science', 'world-history', 'us-law'. "
                            "Omit to search across all domains."
                        ),
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": "Minimum confidence threshold 0.0–1.0. Default 0.8. Use 0.95+ for critical facts.",
                        "default": 0.8,
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional language override: 'de', 'en', 'fr', 'it', 'es', 'zh'. If omitted, language is auto-detected from the query. Response includes 'detected_language' and 'language_fallback' (true if no results were found in detected language).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return (max 20, default 5).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_claim",
            description=(
                "Retrieve a single verified claim with full provenance by its ID. "
                "USE THIS TOOL after search_knowledge when you need the complete citation: "
                "who validated it, which institution, on what date, and the SHA256 integrity hash. "
                "Also returns 'effective_confidence' (age-adjusted) to assess if renewal is needed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": "UUID of the claim, obtained from search_knowledge results.",
                    }
                },
                "required": ["claim_id"],
            },
        ),
        types.Tool(
            name="list_domains",
            description=(
                "List all available knowledge domains with certified claim counts. "
                "USE THIS TOOL at the start of a session or when unsure which domain to search. "
                "Returns domain IDs (use in search_knowledge 'domain' parameter), names, and descriptions. "
                "Domains cover: Swiss law, health, finance, education, energy, transport, politics, "
                "agriculture, climate, AI/ML, world science, and world history."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="submit_claim",
            description=(
                "Submit a new factual claim for expert review and certification. "
                "USE THIS TOOL when you identify a knowledge gap — a fact that should be in the "
                "knowledge base but isn't. "
                "The claim goes through: AI pre-screening → URL verification → source content check → "
                "human expert peer review → certification. "
                "Requirements: one atomic statement (not compound), factual (not opinion), "
                "at least one primary source URL (not Wikipedia). "
                "Returns a claim_id — use get_claim_status to track progress."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim_text": {
                        "type": "string",
                        "description": "The factual statement — one single, clear, verifiable claim. Max 2000 characters.",
                    },
                    "domain_id": {
                        "type": "string",
                        "description": "Domain ID (e.g. 'ai-ml', 'swiss-health', 'climate'). Use list_domains to see all options.",
                    },
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Primary source URLs that directly support the claim (e.g. arxiv.org, bag.admin.ch). Strongly recommended. No Wikipedia.",
                    },
                    "language": {
                        "type": "string",
                        "description": "Language code: 'de', 'en', 'fr', or 'it'. Default: 'de'.",
                        "default": "de",
                    },
                    "question": {
                        "type": "string",
                        "description": "The canonical question this claim answers (e.g. 'How does Swiss mandatory health insurance work?'). Significantly improves retrieval quality.",
                    },
                },
                "required": ["claim_text", "domain_id"],
            },
        ),
        types.Tool(
            name="verify_claim",
            description=(
                "Fact-check a claim against the Swiss Truth knowledge base. "
                "USE THIS TOOL in ReAct loops when you need to verify whether a statement is true, false, or unknown. "
                "Ideal for: checking AI-generated content, validating user inputs, or grounding responses. "
                "\n\nReturns:"
                "\n- 'verdict': 'supported' | 'contradicted' | 'unknown'"
                "\n- 'confidence': 0.0–1.0 — how certain the verdict is"
                "\n- 'explanation': brief reason"
                "\n- 'evidence': list of certified claims that support or contradict, each with source_references"
                "\n\nExamples: 'Health insurance is mandatory in Switzerland', "
                "'The SNB sets negative interest rates', 'GPT-4 uses 1 trillion parameters'"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The factual statement to verify. One clear, atomic claim.",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter (e.g. 'swiss-health', 'ai-ml'). Omit to search all domains.",
                    },
                    "language": {
                        "type": "string",
                        "description": "Optional language override ('de', 'en', 'fr', etc.). Auto-detected if omitted.",
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="get_claim_status",
            description=(
                "Check the current validation status of a submitted claim. "
                "USE THIS TOOL after submit_claim to track progress through the review pipeline: "
                "'draft' → 'peer_review' → 'certified' (or back to 'draft' if rejected). "
                "Also returns confidence score and validator info once certified."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim_id": {
                        "type": "string",
                        "description": "UUID returned by submit_claim.",
                    }
                },
                "required": ["claim_id"],
            },
        ),
        types.Tool(
            name="verify_claims_batch",
            description=(
                "Verify multiple factual claims in parallel against the Swiss Truth knowledge base. "
                "USE THIS TOOL when you need to fact-check several statements at once — "
                "e.g. before sending a response that contains multiple factual assertions. "
                "Much faster than calling verify_claim repeatedly. "
                "\n\nReturns per claim:"
                "\n- 'verdict': 'supported' | 'contradicted' | 'unknown'"
                "\n- 'confidence': 0.0–1.0"
                "\n- 'evidence': certified claims that support or contradict"
                "\n\nAlso returns a 'summary' with counts of supported/contradicted/unknown."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claims": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of factual statements to verify. Max 20 items.",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter applied to all claims (e.g. 'swiss-health', 'ai-ml').",
                    },
                },
                "required": ["claims"],
            },
        ),
        types.Tool(
            name="verify_response",
            description=(
                "Check a full AI response paragraph for hallucination risk. "
                "USE THIS TOOL before sending a multi-sentence response to a user — "
                "it atomizes the text into individual claims, verifies each against the knowledge base, "
                "and returns an overall hallucination risk score. "
                "\n\nReturns:"
                "\n- 'hallucination_risk': 'low' | 'medium' | 'high'"
                "\n- 'verified': number of statements backed by certified facts"
                "\n- 'contradicted': number of statements contradicted by certified facts"
                "\n- 'unverified': number of statements with no evidence (knowledge gap)"
                "\n- 'coverage_rate': fraction of statements that are verified (0.0–1.0)"
                "\n- 'statements': per-statement breakdown with verdict and sources"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The full response text to check. Can be a paragraph or multiple sentences.",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter (e.g. 'swiss-health'). Omit to search all domains.",
                    },
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="find_contradictions",
            description=(
                "Find certified claims in the knowledge base that contradict a given statement. "
                "USE THIS TOOL as a safety check before publishing facts, or to surface knowledge conflicts. "
                "Unlike verify_claim (which gives a single verdict), this tool returns ALL contradicting "
                "certified claims with explanations — useful for understanding why a claim is disputed. "
                "\n\nReturns:"
                "\n- 'contradictions': list of certified claims that contradict the input"
                "\n- 'contradiction_confidence': how strongly each certified claim contradicts"
                "\n- 'explanation': why the certified claim contradicts"
                "\n- 'total': number of contradictions found"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "claim_text": {
                        "type": "string",
                        "description": "The factual statement to check for contradictions.",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional domain filter (e.g. 'swiss-law', 'ai-ml').",
                    },
                },
                "required": ["claim_text"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------

@app.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    tool_map = {
        "search_knowledge": search_knowledge,
        "get_claim": get_claim,
        "list_domains": list_domains,
        "submit_claim": submit_claim,
        "get_claim_status": get_claim_status,
        "verify_claim": verify_claim,
        "verify_claims_batch": verify_claims_batch,
        "verify_response": verify_response,
        "find_contradictions": find_contradictions,
    }

    if name not in tool_map:
        return [types.TextContent(type="text", text=f"Unbekanntes Tool: {name}")]

    try:
        result = await tool_map[name](**arguments)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def _run():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
