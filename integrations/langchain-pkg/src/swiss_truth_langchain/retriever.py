"""
Swiss Truth LangChain Retriever — use as a RAG document source.

Usage:
    from swiss_truth_langchain import SwissTruthRetriever

    retriever = SwissTruthRetriever(domain="swiss-law")
    docs = retriever.invoke("How does Swiss health insurance work?")
    # Each doc has page_content (claim text) and metadata (source, confidence, etc.)
"""
from __future__ import annotations

from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field, PrivateAttr

from swiss_truth_langchain.client import SwissTruthClient


class SwissTruthRetriever(BaseRetriever):
    """
    LangChain retriever that fetches certified facts from Swiss Truth.

    Each returned Document contains:
    - page_content: the certified claim text
    - metadata: claim_id, domain, confidence, source_references, validated_by, hash
    """

    base_url: str = Field(default="https://swisstruth.org", description="Swiss Truth API base URL.")
    api_key: str = Field(default="", description="Optional API key.")
    domain: Optional[str] = Field(default=None, description="Optional domain filter.")
    min_confidence: float = Field(default=0.8, description="Minimum confidence threshold.")
    k: int = Field(default=5, description="Number of results to return.")

    _client: Optional[SwissTruthClient] = PrivateAttr(default=None)

    def _ensure_client(self) -> SwissTruthClient:
        if self._client is None:
            self._client = SwissTruthClient(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> List[Document]:
        client = self._ensure_client()

        params: dict[str, Any] = {"q": query, "limit": min(self.k, 20)}
        if self.domain:
            params["domain"] = self.domain

        try:
            response = client.get("/search", **params)
        except Exception:
            return []

        # Parse response
        if isinstance(response, dict):
            items = response.get("results", [])
        elif isinstance(response, list):
            items = response
        else:
            return []

        docs: List[Document] = []
        for item in items[:self.k]:
            text = item.get("text", item.get("claim", ""))
            conf = item.get("confidence_score", item.get("confidence", 0.0))

            if conf < self.min_confidence:
                continue

            srcs = item.get("source_references", [])
            metadata = {
                "claim_id": item.get("id", item.get("claim_id", "")),
                "domain": item.get("domain_id", item.get("domain", "")),
                "confidence": conf,
                "effective_confidence": item.get("effective_confidence", conf),
                "source_references": srcs,
                "source_url": srcs[0] if srcs else "",
                "validated_by": item.get("validated_by", []),
                "hash_sha256": item.get("hash_sha256", item.get("hash", "")),
                "language": item.get("language", ""),
                "status": item.get("status", ""),
                "canonical_question": item.get("question", item.get("canonical_question", "")),
            }
            docs.append(Document(page_content=text, metadata=metadata))

        return docs
