"""
Swiss Truth — LangChain Tool Integration
=========================================
Wraps the Swiss Truth REST API as LangChain BaseTool subclasses.

Install:
    pip install langchain-core requests

Usage:
    from swiss_truth_tools import VerifyClaimTool, SearchKnowledgeTool, SwissTruthToolkit

    tools = SwissTruthToolkit(api_key="your-key").get_tools()
    agent = create_react_agent(llm, tools, prompt)
"""
from __future__ import annotations

import json
from typing import Any, Optional, Type

import requests
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

# ─── Config ──────────────────────────────────────────────────────────────────

_DEFAULT_BASE_URL = "https://swisstruth.org"


class _Client:
    """Thin HTTP client for the Swiss Truth API."""

    def __init__(self, base_url: str = _DEFAULT_BASE_URL, api_key: str = "") -> None:
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        if api_key:
            self._session.headers["X-Swiss-Truth-Key"] = api_key

    def get(self, path: str, **params: Any) -> Any:
        r = self._session.get(f"{self._base}{path}", params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> Any:
        r = self._session.post(f"{self._base}{path}", json=body, timeout=90)
        r.raise_for_status()
        return r.json()


# ─── Input Schemas ────────────────────────────────────────────────────────────

class _VerifyInput(BaseModel):
    claim_text: str = Field(
        description="The factual claim to verify, e.g. 'The WHO was founded in 1948.'"
    )
    domain: Optional[str] = Field(
        default=None,
        description="Optional domain hint (e.g. 'eu-health', 'swiss-law'). Speeds up lookup."
    )


class _SearchInput(BaseModel):
    query: str = Field(
        description="Natural-language question or keyword to search the certified knowledge base."
    )
    domain: Optional[str] = Field(
        default=None,
        description="Optional domain filter (e.g. 'quantum-computing', 'ai-ml')."
    )
    limit: int = Field(default=5, description="Max results to return (1–20).")


class _SubmitInput(BaseModel):
    text: str = Field(description="The factual claim text (one atomic fact per claim).")
    question: str = Field(description="The question this claim answers.")
    source_url: str = Field(description="Primary source URL backing this claim.")
    domain_id: str = Field(description="Domain to file it under, e.g. 'eu-law'.")
    confidence: float = Field(
        default=0.90,
        description="Your confidence score (0.0–1.0). Only claims ≥ 0.88 get certified."
    )


class _ListDomainsInput(BaseModel):
    pass


# ─── Tools ───────────────────────────────────────────────────────────────────

class VerifyClaimTool(BaseTool):
    """Check whether a statement is supported by Swiss Truth's certified knowledge base."""

    name: str = "swiss_truth_verify"
    description: str = (
        "Verify a factual claim against Swiss Truth's certified, source-backed knowledge base. "
        "Returns SUPPORTED, CONTRADICTED, or NOT_FOUND with a confidence score and source URL. "
        "Use this to fact-check any statement before presenting it to users."
    )
    args_schema: Type[BaseModel] = _VerifyInput

    _client: _Client = PrivateAttr()

    def __init__(self, client: _Client, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client

    def _run(self, claim_text: str, domain: Optional[str] = None) -> str:
        try:
            body: dict = {"text": claim_text}
            if domain:
                body["domain_id"] = domain
            result = self._client.post("/n8n/fact-check", body)
            # Response: {verified, trust_score, verdict, supporting_claims, query_text}
            verdict    = result.get("verdict", "nicht_belegt")
            trust      = result.get("trust_score", 0.0)
            verified   = result.get("verified", False)
            supporters = result.get("supporting_claims", [])
            lines = [
                f"Verdict: {verdict}",
                f"Trust score: {trust:.0%}",
                f"Verified: {verified}",
            ]
            if supporters:
                top = supporters[0]
                lines.append(f"Closest match: {top.get('text', '')[:120]}")
                srcs = top.get("source_references", [])
                if srcs:
                    lines.append(f"Source: {srcs[0]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error verifying claim: {e}"


class SearchKnowledgeTool(BaseTool):
    """Semantic search over Swiss Truth's certified knowledge base."""

    name: str = "swiss_truth_search"
    description: str = (
        "Search Swiss Truth's certified knowledge base using a natural-language query. "
        "Returns the most relevant certified facts with their source URLs and confidence scores. "
        "Use this to retrieve accurate context before answering questions."
    )
    args_schema: Type[BaseModel] = _SearchInput

    _client: _Client = PrivateAttr()

    def __init__(self, client: _Client, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client

    def _run(self, query: str, domain: Optional[str] = None, limit: int = 5) -> str:
        try:
            params: dict = {"q": query, "limit": min(limit, 20)}
            if domain:
                params["domain"] = domain
            results = self._client.get("/search", **params)
            if not results:
                return "No certified claims found for this query."
            # Response: {query, results: [...], total}
            items = (results.get("results") or results) if isinstance(results, dict) else results
            if not items:
                return "No certified claims found for this query."
            lines = []
            for i, item in enumerate(items[:limit], 1):
                text  = item.get("text", item.get("claim", ""))
                conf  = item.get("confidence_score", item.get("confidence", 0.0))
                srcs  = item.get("source_references", [])
                src   = srcs[0] if srcs else item.get("source_url", "")
                dom   = item.get("domain_id", "")
                line  = f"{i}. [{dom}] {text} (confidence: {conf:.0%})"
                if src:
                    line += f"\n   Source: {src}"
                lines.append(line)
            return "\n".join(lines)
        except Exception as e:
            return f"Error searching knowledge base: {e}"


class SubmitClaimTool(BaseTool):
    """Submit a new factual claim to Swiss Truth for peer review and certification."""

    name: str = "swiss_truth_submit"
    description: str = (
        "Submit a new factual claim to Swiss Truth for verification and certification. "
        "Claims with confidence ≥ 0.88 from reliable primary sources get auto-certified. "
        "Use this to contribute verified facts to the knowledge base."
    )
    args_schema: Type[BaseModel] = _SubmitInput

    _client: _Client = PrivateAttr()

    def __init__(self, client: _Client, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client

    def _run(
        self,
        text: str,
        question: str,
        source_url: str,
        domain_id: str,
        confidence: float = 0.90,
    ) -> str:
        try:
            result = self._client.post("/n8n/submit", {
                "text": text,
                "question": question,
                "source_url": source_url,
                "domain_id": domain_id,
                "confidence": confidence,
            })
            claim_id = result.get("claim_id", result.get("id", ""))
            status   = result.get("status", "submitted")
            return f"Submitted: {claim_id} | Status: {status}"
        except Exception as e:
            return f"Error submitting claim: {e}"


class ListDomainsTool(BaseTool):
    """List all available knowledge domains in Swiss Truth."""

    name: str = "swiss_truth_list_domains"
    description: str = (
        "List all certified knowledge domains available in Swiss Truth "
        "(e.g. 'swiss-law', 'eu-health', 'quantum-computing'). "
        "Use this to discover what topics are covered before searching."
    )
    args_schema: Type[BaseModel] = _ListDomainsInput

    _client: _Client = PrivateAttr()

    def __init__(self, client: _Client, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client

    def _run(self) -> str:
        try:
            domains = self._client.get("/domains")
            lines = []
            for d in sorted(domains, key=lambda x: -x.get("certified_claims", 0)):
                did   = d.get("id", "")
                name  = d.get("name", "")
                count = d.get("certified_claims", 0)
                lang  = d.get("language", "")
                lines.append(f"  {did:<24} {name} ({count} claims, {lang})")
            return "Available Swiss Truth domains:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing domains: {e}"


# ─── Toolkit ─────────────────────────────────────────────────────────────────

class SwissTruthToolkit:
    """
    Convenient factory that returns all Swiss Truth tools pre-configured.

    Example:
        from swiss_truth_tools import SwissTruthToolkit

        toolkit = SwissTruthToolkit(api_key="your-key")
        tools = toolkit.get_tools()

        # With LangChain agent:
        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(llm, tools)
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self._client = _Client(base_url=base_url, api_key=api_key)

    def get_tools(self) -> list[BaseTool]:
        return [
            SearchKnowledgeTool(client=self._client),
            VerifyClaimTool(client=self._client),
            ListDomainsTool(client=self._client),
            SubmitClaimTool(client=self._client),
        ]
