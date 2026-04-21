"""
Swiss Truth Base Client — Shared across all agent framework integrations.

Provides HTTP client for the Swiss Truth REST API.
Used by: LangChain, CrewAI, AutoGen integrations.
"""
from __future__ import annotations

from typing import Any, Optional

import requests


_DEFAULT_BASE_URL = "https://swisstruth.org"


class SwissTruthBaseClient:
    """Thin HTTP client for the Swiss Truth API."""

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = "",
        timeout: int = 60,
        user_agent: str = "swiss-truth-client/0.3.0",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": user_agent,
        })
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"

    # ── Core HTTP ──────────────────────────────────────────────────────────

    def get(self, path: str, **params: Any) -> Any:
        r = self._session.get(
            f"{self.base_url}{path}", params=params, timeout=self.timeout
        )
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict) -> Any:
        r = self._session.post(
            f"{self.base_url}{path}", json=body, timeout=self.timeout + 30
        )
        r.raise_for_status()
        return r.json()

    # ── High-level API methods ─────────────────────────────────────────────

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        min_confidence: float = 0.8,
        limit: int = 5,
    ) -> list[dict]:
        """Search verified claims."""
        params: dict[str, Any] = {
            "q": query,
            "min_confidence": min_confidence,
            "limit": limit,
        }
        if domain:
            params["domain"] = domain
        return self.get("/api/search", **params)

    def verify(self, text: str, domain: Optional[str] = None) -> dict:
        """Verify a single claim."""
        body: dict[str, Any] = {"text": text}
        if domain:
            body["domain"] = domain
        return self.post("/api/verify", body)

    def batch_verify(self, claims: list[str], domain: Optional[str] = None) -> dict:
        """Verify multiple claims."""
        body: dict[str, Any] = {"claims": claims}
        if domain:
            body["domain"] = domain
        return self.post("/api/verify/batch", body)

    def submit(
        self,
        claim_text: str,
        domain_id: str,
        source_urls: Optional[list[str]] = None,
        question: str = "",
    ) -> dict:
        """Submit a new claim."""
        body: dict[str, Any] = {
            "claim_text": claim_text,
            "domain_id": domain_id,
        }
        if source_urls:
            body["source_urls"] = source_urls
        if question:
            body["question"] = question
        return self.post("/api/claims", body)

    def get_claim(self, claim_id: str) -> dict:
        """Get a single claim by ID."""
        return self.get(f"/api/claims/{claim_id}")

    def list_domains(self) -> list[dict]:
        """List all domains."""
        return self.get("/domains")

    def get_claim_status(self, claim_id: str) -> dict:
        """Get claim validation status."""
        return self.get(f"/api/claims/{claim_id}/status")

    def verify_response(self, text: str, domain: Optional[str] = None) -> dict:
        """Check a full response for hallucination."""
        body: dict[str, Any] = {"text": text}
        if domain:
            body["domain"] = domain
        return self.post("/api/verify/response", body)

    def find_contradictions(self, claim_text: str, domain: Optional[str] = None) -> dict:
        """Find contradicting claims."""
        body: dict[str, Any] = {"claim_text": claim_text}
        if domain:
            body["domain"] = domain
        return self.post("/api/verify/contradictions", body)

    def compliance_check(self, claim_id: str) -> dict:
        """EU AI Act compliance check."""
        return self.get(f"/api/compliance/eu-ai-act/{claim_id}")

    # ── Phase 6: AI Agent First Tools ─────────────────────────────────────────

    def get_knowledge_brief(
        self,
        topic: str,
        domain: Optional[str] = None,
        language: Optional[str] = None,
        max_facts: int = 5,
    ) -> dict:
        """Get a structured, citable knowledge brief on a topic."""
        params: dict[str, Any] = {"topic": topic, "max_facts": max_facts}
        if domain:
            params["domain"] = domain
        if language:
            params["language"] = language
        return self.get("/api/agent/knowledge-brief", **params)

    def get_citations(
        self,
        claim_text: str,
        domain: Optional[str] = None,
        citation_style: str = "inline",
    ) -> dict:
        """Get formatted citations for a factual claim."""
        body: dict[str, Any] = {"claim_text": claim_text, "citation_style": citation_style}
        if domain:
            body["domain"] = domain
        return self.post("/api/agent/citations", body)

    def check_freshness(
        self,
        claim_text: str,
        domain: Optional[str] = None,
        known_as_of: Optional[str] = None,
    ) -> dict:
        """Check if a factual claim is still current."""
        body: dict[str, Any] = {"claim_text": claim_text}
        if domain:
            body["domain"] = domain
        if known_as_of:
            body["known_as_of"] = known_as_of
        return self.post("/api/agent/freshness", body)

    def check_regulatory_compliance(self, text: str, domain: str) -> dict:
        """Check if text complies with Swiss/EU regulations."""
        return self.post("/api/agent/regulatory-compliance", {"text": text, "domain": domain})

    def report_agent_need(
        self,
        request_type: str,
        details: str,
        agent_framework: str = "unknown",
        domain_hint: str = "",
        query_that_failed: str = "",
    ) -> dict:
        """Report what's missing from Swiss Truth."""
        return self.post("/api/agent/feedback", {
            "request_type": request_type,
            "details": details,
            "agent_framework": agent_framework,
            "domain_hint": domain_hint,
            "query_that_failed": query_that_failed,
        })

    def get_agent_capabilities(self) -> dict:
        """Get the full capability manifest for AI agents."""
        return self.get("/api/agent/capabilities")
