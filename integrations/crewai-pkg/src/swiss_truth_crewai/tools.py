"""
CrewAI Tools for Swiss Truth — Phase 5 (Plan 05-06)

Provides CrewAI-compatible tools for searching, verifying, and submitting claims.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional, Type

try:
    from crewai.tools import BaseTool
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError(
        "crewai is required: pip install swiss-truth-crewai"
    )

import requests

_DEFAULT_URL = os.environ.get("SWISS_TRUTH_URL", "https://swisstruth.org")
_API_KEY = os.environ.get("SWISS_TRUTH_API_KEY", "")


def _headers() -> dict:
    h = {"Content-Type": "application/json", "User-Agent": "swiss-truth-crewai/0.1.0"}
    if _API_KEY:
        h["Authorization"] = f"Bearer {_API_KEY}"
    return h


# ─── Search Tool ───────────────────────────────────────────────────────────────

class _SearchInput(BaseModel):
    query: str = Field(description="Natural language search query")
    domain: Optional[str] = Field(default=None, description="Domain filter (e.g. ai-ml, swiss-health)")
    limit: int = Field(default=5, description="Number of results")


class SwissTruthSearchTool(BaseTool):
    name: str = "swiss_truth_search"
    description: str = (
        "Search the Swiss Truth verified knowledge base for certified facts. "
        "Use this to find reliable, source-backed information and avoid hallucination."
    )
    args_schema: Type[BaseModel] = _SearchInput

    def _run(self, query: str, domain: Optional[str] = None, limit: int = 5) -> str:
        params = {"q": query, "limit": limit, "min_confidence": 0.8}
        if domain:
            params["domain"] = domain
        r = requests.get(f"{_DEFAULT_URL}/api/search", params=params, headers=_headers(), timeout=30)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)


# ─── Verify Tool ───────────────────────────────────────────────────────────────

class _VerifyInput(BaseModel):
    text: str = Field(description="Factual statement to verify")
    domain: Optional[str] = Field(default=None, description="Domain filter")


class SwissTruthVerifyTool(BaseTool):
    name: str = "swiss_truth_verify"
    description: str = (
        "Fact-check a statement against the Swiss Truth knowledge base. "
        "Returns verdict: supported | contradicted | unknown."
    )
    args_schema: Type[BaseModel] = _VerifyInput

    def _run(self, text: str, domain: Optional[str] = None) -> str:
        body = {"text": text}
        if domain:
            body["domain"] = domain
        r = requests.post(f"{_DEFAULT_URL}/api/verify", json=body, headers=_headers(), timeout=60)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)


# ─── Submit Tool ───────────────────────────────────────────────────────────────

class _SubmitInput(BaseModel):
    claim_text: str = Field(description="The factual claim to submit")
    domain_id: str = Field(description="Domain ID (e.g. ai-ml)")
    source_urls: list[str] = Field(default=[], description="Source URLs")


class SwissTruthSubmitTool(BaseTool):
    name: str = "swiss_truth_submit"
    description: str = (
        "Submit a new factual claim for expert review and certification."
    )
    args_schema: Type[BaseModel] = _SubmitInput

    def _run(self, claim_text: str, domain_id: str, source_urls: list[str] = []) -> str:
        body = {"claim_text": claim_text, "domain_id": domain_id}
        if source_urls:
            body["source_urls"] = source_urls
        r = requests.post(f"{_DEFAULT_URL}/api/claims", json=body, headers=_headers(), timeout=60)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)


# ─── Phase 6: AI Agent First Tools ─────────────────────────────────────────────

class _KnowledgeBriefInput(BaseModel):
    topic: str = Field(description="Topic or question to get a knowledge brief on")
    domain: Optional[str] = Field(default=None, description="Domain filter (e.g. swiss-health)")
    max_facts: int = Field(default=5, description="Max number of facts (1-10)")


class SwissTruthKnowledgeBriefTool(BaseTool):
    name: str = "swiss_truth_knowledge_brief"
    description: str = (
        "Get a structured, citable knowledge brief on any topic. "
        "Returns verified facts with source URLs and confidence scores. "
        "Use this to enrich your responses with verified, citable content."
    )
    args_schema: Type[BaseModel] = _KnowledgeBriefInput

    def _run(self, topic: str, domain: Optional[str] = None, max_facts: int = 5) -> str:
        params = {"topic": topic, "max_facts": max_facts}
        if domain:
            params["domain"] = domain
        r = requests.get(f"{_DEFAULT_URL}/api/agent/knowledge-brief", params=params, headers=_headers(), timeout=30)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)


class _CitationsInput(BaseModel):
    claim_text: str = Field(description="The factual statement to find citations for")
    citation_style: str = Field(default="inline", description="'inline' | 'apa' | 'all'")


class SwissTruthCitationsTool(BaseTool):
    name: str = "swiss_truth_get_citations"
    description: str = (
        "Get properly formatted citations for a factual claim. "
        "Returns inline and APA citations with verified source URLs. "
        "Use this when you need to cite sources in your response."
    )
    args_schema: Type[BaseModel] = _CitationsInput

    def _run(self, claim_text: str, citation_style: str = "inline") -> str:
        body = {"claim_text": claim_text, "citation_style": citation_style}
        r = requests.post(f"{_DEFAULT_URL}/api/agent/citations", json=body, headers=_headers(), timeout=30)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)


class _FreshnessInput(BaseModel):
    claim_text: str = Field(description="The factual statement to check for freshness")
    domain: Optional[str] = Field(default=None, description="Domain filter")


class SwissTruthFreshnessTool(BaseTool):
    name: str = "swiss_truth_check_freshness"
    description: str = (
        "Check if a factual claim is still current and up-to-date. "
        "Returns: current | changed | unknown + latest verified version. "
        "Use when unsure if your training data is outdated."
    )
    args_schema: Type[BaseModel] = _FreshnessInput

    def _run(self, claim_text: str, domain: Optional[str] = None) -> str:
        body: dict = {"claim_text": claim_text}
        if domain:
            body["domain"] = domain
        r = requests.post(f"{_DEFAULT_URL}/api/agent/freshness", json=body, headers=_headers(), timeout=30)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)


class _ReportNeedInput(BaseModel):
    request_type: str = Field(description="'missing_domain'|'missing_claim'|'quality_issue'|'feature_request'|'coverage_gap'")
    details: str = Field(description="What do you need? Be specific.")
    domain_hint: str = Field(default="", description="Which domain/topic area?")


class SwissTruthReportNeedTool(BaseTool):
    name: str = "swiss_truth_report_need"
    description: str = (
        "Report what you need from Swiss Truth that's currently missing. "
        "Use when you can't find what you need — your feedback shapes what gets built next."
    )
    args_schema: Type[BaseModel] = _ReportNeedInput

    def _run(self, request_type: str, details: str, domain_hint: str = "") -> str:
        body = {
            "request_type": request_type,
            "details": details,
            "agent_framework": "crewai",
            "domain_hint": domain_hint,
        }
        r = requests.post(f"{_DEFAULT_URL}/api/agent/feedback", json=body, headers=_headers(), timeout=30)
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)
