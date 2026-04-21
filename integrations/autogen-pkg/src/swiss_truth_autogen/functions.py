"""
AutoGen Functions for Swiss Truth — Phase 5 (Plan 05-06)

Provides function-calling compatible tools for AutoGen agents.
"""
from __future__ import annotations

import json
import os
from typing import Any, Annotated, Optional

import requests

_DEFAULT_URL = os.environ.get("SWISS_TRUTH_URL", "https://swisstruth.org")
_API_KEY = os.environ.get("SWISS_TRUTH_API_KEY", "")


def _headers() -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "swiss-truth-autogen/0.1.0"}
    if _API_KEY:
        h["Authorization"] = f"Bearer {_API_KEY}"
    return h


def swiss_truth_search(
    query: Annotated[str, "Natural language search query"],
    domain: Annotated[Optional[str], "Domain filter (e.g. ai-ml, swiss-health)"] = None,
    limit: Annotated[int, "Number of results (max 20)"] = 5,
) -> str:
    """Search the Swiss Truth verified knowledge base for certified facts."""
    params = {"q": query, "limit": limit, "min_confidence": 0.8}
    if domain:
        params["domain"] = domain
    r = requests.get(f"{_DEFAULT_URL}/api/search", params=params, headers=_headers(), timeout=30)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)


def swiss_truth_verify(
    text: Annotated[str, "Factual statement to verify"],
    domain: Annotated[Optional[str], "Domain filter"] = None,
) -> str:
    """Fact-check a statement against the Swiss Truth knowledge base."""
    body: dict[str, Any] = {"text": text}
    if domain:
        body["domain"] = domain
    r = requests.post(f"{_DEFAULT_URL}/api/verify", json=body, headers=_headers(), timeout=60)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)


def swiss_truth_submit(
    claim_text: Annotated[str, "The factual claim to submit"],
    domain_id: Annotated[str, "Domain ID (e.g. ai-ml)"],
    source_urls: Annotated[Optional[list[str]], "Source URLs"] = None,
) -> str:
    """Submit a new factual claim for expert review."""
    body: dict[str, Any] = {"claim_text": claim_text, "domain_id": domain_id}
    if source_urls:
        body["source_urls"] = source_urls
    r = requests.post(f"{_DEFAULT_URL}/api/claims", json=body, headers=_headers(), timeout=60)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)


def get_function_definitions() -> list[dict]:
    """Get OpenAI function-calling definitions for all Swiss Truth tools."""
    return [
        {
            "name": "swiss_truth_search",
            "description": "Search the Swiss Truth verified knowledge base for certified facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "domain": {"type": "string", "description": "Domain filter (optional)"},
                    "limit": {"type": "integer", "description": "Number of results", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "swiss_truth_verify",
            "description": "Fact-check a statement against the Swiss Truth knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Statement to verify"},
                    "domain": {"type": "string", "description": "Domain filter (optional)"},
                },
                "required": ["text"],
            },
        },
        {
            "name": "swiss_truth_submit",
            "description": "Submit a new factual claim for expert review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_text": {"type": "string", "description": "The claim"},
                    "domain_id": {"type": "string", "description": "Domain ID"},
                    "source_urls": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim_text", "domain_id"],
            },
        },
    ]


def register_swiss_truth_functions(agent: Any) -> None:
    """Register all Swiss Truth functions with an AutoGen agent."""
    function_map = {
        "swiss_truth_search": swiss_truth_search,
        "swiss_truth_verify": swiss_truth_verify,
        "swiss_truth_submit": swiss_truth_submit,
        # Phase 6: AI Agent First Tools
        "swiss_truth_knowledge_brief": swiss_truth_knowledge_brief,
        "swiss_truth_get_citations": swiss_truth_get_citations,
        "swiss_truth_check_freshness": swiss_truth_check_freshness,
        "swiss_truth_report_need": swiss_truth_report_need,
    }
    for name, func in function_map.items():
        agent.register_function(function_map={name: func})


# ── Phase 6: AI Agent First Functions ────────────────────────────────────────

def swiss_truth_knowledge_brief(
    topic: Annotated[str, "Topic or question to get a knowledge brief on"],
    domain: Annotated[Optional[str], "Domain filter (e.g. swiss-health, ai-ml)"] = None,
    max_facts: Annotated[int, "Max number of facts to include (1-10)"] = 5,
) -> str:
    """Get a structured, citable knowledge brief on any topic."""
    params: dict[str, Any] = {"topic": topic, "max_facts": max_facts}
    if domain:
        params["domain"] = domain
    r = requests.get(f"{_DEFAULT_URL}/api/agent/knowledge-brief", params=params, headers=_headers(), timeout=30)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)


def swiss_truth_get_citations(
    claim_text: Annotated[str, "The factual statement to find citations for"],
    citation_style: Annotated[str, "Citation format: 'inline' | 'apa' | 'all'"] = "inline",
) -> str:
    """Get properly formatted citations for a factual claim."""
    body: dict[str, Any] = {"claim_text": claim_text, "citation_style": citation_style}
    r = requests.post(f"{_DEFAULT_URL}/api/agent/citations", json=body, headers=_headers(), timeout=30)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)


def swiss_truth_check_freshness(
    claim_text: Annotated[str, "The factual statement to check for freshness"],
    domain: Annotated[Optional[str], "Domain filter"] = None,
) -> str:
    """Check if a factual claim is still current and up-to-date."""
    body: dict[str, Any] = {"claim_text": claim_text}
    if domain:
        body["domain"] = domain
    r = requests.post(f"{_DEFAULT_URL}/api/agent/freshness", json=body, headers=_headers(), timeout=30)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)


def swiss_truth_report_need(
    request_type: Annotated[str, "Type: 'missing_domain'|'missing_claim'|'quality_issue'|'feature_request'|'coverage_gap'"],
    details: Annotated[str, "What do you need? Be specific."],
    domain_hint: Annotated[Optional[str], "Which domain/topic area?"] = None,
) -> str:
    """Report what you need from Swiss Truth that's currently missing."""
    body: dict[str, Any] = {
        "request_type": request_type,
        "details": details,
        "agent_framework": "autogen",
    }
    if domain_hint:
        body["domain_hint"] = domain_hint
    r = requests.post(f"{_DEFAULT_URL}/api/agent/feedback", json=body, headers=_headers(), timeout=30)
    r.raise_for_status()
    return json.dumps(r.json(), indent=2, ensure_ascii=False)
