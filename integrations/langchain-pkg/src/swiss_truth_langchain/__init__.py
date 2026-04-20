"""
Swiss Truth — LangChain Tool Integration
=========================================
Full-featured LangChain toolkit for the Swiss Truth certified knowledge base.

Install:
    pip install swiss-truth-langchain

Usage:
    from swiss_truth_langchain import SwissTruthToolkit

    toolkit = SwissTruthToolkit(api_key="your-key")
    tools = toolkit.get_tools()

    # With LangGraph agent:
    from langgraph.prebuilt import create_react_agent
    agent = create_react_agent(llm, tools)

    # As a RAG retriever:
    from swiss_truth_langchain import SwissTruthRetriever
    retriever = SwissTruthRetriever()
    docs = retriever.invoke("How does Swiss health insurance work?")
"""
from __future__ import annotations

__version__ = "0.2.0"

from swiss_truth_langchain.client import SwissTruthClient
from swiss_truth_langchain.tools import (
    VerifyClaimTool,
    SearchKnowledgeTool,
    SubmitClaimTool,
    ListDomainsTool,
    GetClaimStatusTool,
    BatchVerifyTool,
    VerifyResponseTool,
    FindContradictionsTool,
    GetComplianceTool,
)
from swiss_truth_langchain.retriever import SwissTruthRetriever
from swiss_truth_langchain.toolkit import SwissTruthToolkit

__all__ = [
    # Toolkit (recommended entry point)
    "SwissTruthToolkit",
    # Individual tools
    "SearchKnowledgeTool",
    "VerifyClaimTool",
    "SubmitClaimTool",
    "ListDomainsTool",
    "GetClaimStatusTool",
    "BatchVerifyTool",
    "VerifyResponseTool",
    "FindContradictionsTool",
    "GetComplianceTool",
    # RAG retriever
    "SwissTruthRetriever",
    # Low-level client
    "SwissTruthClient",
]
