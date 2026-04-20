"""
Swiss Truth LangChain Tools — 9 tools matching the MCP server.
"""
from __future__ import annotations
from typing import Any, Optional, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr
from swiss_truth_langchain.client import SwissTruthClient
from swiss_truth_langchain._schemas import (
    SearchInput, VerifyInput, SubmitInput, ClaimIdInput,
    BatchVerifyInput, VerifyResponseInput, FindContradictionsInput, EmptyInput,
)


def _fmt_search(results: dict) -> str:
    items = results.get("results", results) if isinstance(results, dict) else results
    if not items:
        return "No certified claims found for this query."
    lines = []
    for i, item in enumerate(items[:20], 1):
        text = item.get("text", item.get("claim", ""))
        conf = item.get("confidence_score", item.get("confidence", 0.0))
        srcs = item.get("source_references", [])
        src = srcs[0] if srcs else item.get("source_url", "")
        dom = item.get("domain_id", item.get("domain", ""))
        line = f"{i}. [{dom}] {text} (confidence: {conf:.0%})"
        if src:
            line += f"\n   Source: {src}"
        lines.append(line)
    return "\n".join(lines)


class SearchKnowledgeTool(BaseTool):
    """Semantic search over Swiss Truth's certified knowledge base."""
    name: str = "swiss_truth_search"
    description: str = (
        "Search Swiss Truth's certified knowledge base using a natural-language query. "
        "Returns the most relevant certified facts with source URLs and confidence scores."
    )
    args_schema: Type[BaseModel] = SearchInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, query: str, domain: Optional[str] = None, limit: int = 5, min_confidence: float = 0.8) -> str:
        try:
            params: dict = {"q": query, "limit": min(limit, 20)}
            if domain:
                params["domain"] = domain
            results = self._client.get("/search", **params)
            return _fmt_search(results)
        except Exception as e:
            return f"Error searching knowledge base: {e}"


class VerifyClaimTool(BaseTool):
    """Fact-check a statement against Swiss Truth's certified knowledge base."""
    name: str = "swiss_truth_verify"
    description: str = (
        "Verify a factual claim against Swiss Truth's certified knowledge base. "
        "Returns SUPPORTED, CONTRADICTED, or UNKNOWN with confidence and source evidence."
    )
    args_schema: Type[BaseModel] = VerifyInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, claim_text: str, domain: Optional[str] = None) -> str:
        try:
            body: dict = {"text": claim_text}
            if domain:
                body["domain_id"] = domain
            result = self._client.post("/n8n/fact-check", body)
            verdict = result.get("verdict", "unknown")
            trust = result.get("trust_score", 0.0)
            verified = result.get("verified", False)
            supporters = result.get("supporting_claims", [])
            lines = [f"Verdict: {verdict}", f"Trust score: {trust:.0%}", f"Verified: {verified}"]
            if supporters:
                top = supporters[0]
                lines.append(f"Closest match: {top.get('text', '')[:120]}")
                srcs = top.get("source_references", [])
                if srcs:
                    lines.append(f"Source: {srcs[0]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error verifying claim: {e}"


class SubmitClaimTool(BaseTool):
    """Submit a new factual claim for peer review and certification."""
    name: str = "swiss_truth_submit"
    description: str = (
        "Submit a new factual claim to Swiss Truth for verification and certification. "
        "Claims with confidence >= 0.88 from reliable primary sources get auto-certified."
    )
    args_schema: Type[BaseModel] = SubmitInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, text: str, domain_id: str, question: str = "", source_url: str = "", confidence: float = 0.90) -> str:
        try:
            body = {"text": text, "question": question, "source_url": source_url, "domain_id": domain_id, "confidence": confidence}
            result = self._client.post("/n8n/submit", body)
            cid = result.get("claim_id", result.get("id", ""))
            status = result.get("status", "submitted")
            return f"Submitted: {cid} | Status: {status}"
        except Exception as e:
            return f"Error submitting claim: {e}"


class ListDomainsTool(BaseTool):
    """List all available knowledge domains in Swiss Truth."""
    name: str = "swiss_truth_list_domains"
    description: str = "List all certified knowledge domains available in Swiss Truth with claim counts."
    args_schema: Type[BaseModel] = EmptyInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self) -> str:
        try:
            domains = self._client.get("/domains")
            lines = []
            for d in sorted(domains, key=lambda x: -x.get("certified_claims", 0)):
                did = d.get("id", "")
                name = d.get("name", "")
                count = d.get("certified_claims", 0)
                lines.append(f"  {did:<24} {name} ({count} claims)")
            return "Available Swiss Truth domains:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing domains: {e}"


class GetClaimStatusTool(BaseTool):
    """Check the validation status of a submitted claim."""
    name: str = "swiss_truth_claim_status"
    description: str = "Check the current validation status of a claim: draft -> peer_review -> certified."
    args_schema: Type[BaseModel] = ClaimIdInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, claim_id: str) -> str:
        try:
            result = self._client.get(f"/claims/{claim_id}")
            status = result.get("status", "unknown")
            conf = result.get("confidence_score", 0.0)
            return f"Claim {claim_id}: status={status}, confidence={conf:.0%}"
        except Exception as e:
            return f"Error getting claim status: {e}"


class BatchVerifyTool(BaseTool):
    """Verify multiple claims in parallel."""
    name: str = "swiss_truth_batch_verify"
    description: str = (
        "Verify multiple factual claims in parallel. Returns per-claim verdict "
        "(supported/contradicted/unknown) and a summary."
    )
    args_schema: Type[BaseModel] = BatchVerifyInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, claims: list[str], domain: Optional[str] = None) -> str:
        try:
            body: dict = {"claims": claims[:20]}
            if domain:
                body["domain"] = domain
            result = self._client.post("/n8n/batch-verify", body)
            lines = []
            for r in result.get("results", []):
                v = r.get("verdict", "unknown")
                c = r.get("confidence", 0.0)
                t = r.get("claim", "")[:80]
                lines.append(f"  [{v}] {t} ({c:.0%})")
            s = result.get("summary", {})
            lines.append(f"\nSummary: {s.get('supported',0)} supported, {s.get('contradicted',0)} contradicted, {s.get('unknown',0)} unknown")
            return "\n".join(lines)
        except Exception as e:
            return f"Error in batch verify: {e}"


class VerifyResponseTool(BaseTool):
    """Check a full AI response for hallucination risk."""
    name: str = "swiss_truth_verify_response"
    description: str = (
        "Check a full AI response paragraph for hallucination risk. "
        "Atomizes text into claims, verifies each, returns risk score (low/medium/high)."
    )
    args_schema: Type[BaseModel] = VerifyResponseInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, text: str, domain: Optional[str] = None) -> str:
        try:
            body: dict = {"text": text}
            if domain:
                body["domain"] = domain
            result = self._client.post("/n8n/verify-response", body)
            risk = result.get("hallucination_risk", "unknown")
            v = result.get("verified", 0)
            u = result.get("unverified", 0)
            c = result.get("contradicted", 0)
            cov = result.get("coverage_rate", 0.0)
            return f"Hallucination risk: {risk}\nVerified: {v}, Unverified: {u}, Contradicted: {c}\nCoverage: {cov:.0%}"
        except Exception as e:
            return f"Error verifying response: {e}"


class FindContradictionsTool(BaseTool):
    """Find certified claims that contradict a given statement."""
    name: str = "swiss_truth_find_contradictions"
    description: str = (
        "Find certified claims that contradict a given statement. "
        "Safety check before publishing facts."
    )
    args_schema: Type[BaseModel] = FindContradictionsInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, claim_text: str, domain: Optional[str] = None) -> str:
        try:
            body: dict = {"claim_text": claim_text}
            if domain:
                body["domain"] = domain
            result = self._client.post("/n8n/find-contradictions", body)
            contras = result.get("contradictions", [])
            if not contras:
                return "No contradictions found. Claim is consistent with the knowledge base."
            lines = [f"Found {len(contras)} contradiction(s):"]
            for c in contras:
                lines.append(f"  - {c.get('certified_claim', '')[:120]}")
                lines.append(f"    Confidence: {c.get('contradiction_confidence', 0):.0%}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error finding contradictions: {e}"


class GetComplianceTool(BaseTool):
    """Get EU AI Act compliance attestation for a certified claim."""
    name: str = "swiss_truth_compliance"
    description: str = (
        "Get EU AI Act compliance attestation for a certified claim. "
        "Returns structured compliance data for Articles 9, 13, and 17."
    )
    args_schema: Type[BaseModel] = ClaimIdInput
    _client: SwissTruthClient = PrivateAttr()

    def __init__(self, client: SwissTruthClient, **kw: Any) -> None:
        super().__init__(**kw)
        self._client = client

    def _run(self, claim_id: str) -> str:
        try:
            result = self._client.get(f"/api/compliance/eu-ai-act/{claim_id}")
            compliant = result.get("summary", {}).get("is_compliant", False)
            risk = result.get("summary", {}).get("risk_level", "unknown")
            quality = result.get("summary", {}).get("data_quality", "unknown")
            arts = ", ".join(result.get("compliant_with", []))
            lines = [
                f"EU AI Act Compliance: {'COMPLIANT' if compliant else 'NON-COMPLIANT'}",
                f"Risk level: {risk}",
                f"Data quality: {quality}",
                f"Articles: {arts}",
                f"Claim: {result.get('claim_text', '')[:120]}",
            ]
            return "\n".join(lines)
        except Exception as e:
            return f"Error getting compliance data: {e}"
