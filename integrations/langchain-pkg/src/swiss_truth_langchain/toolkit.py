"""
Swiss Truth Toolkit — convenient factory for all tools.

Usage:
    from swiss_truth_langchain import SwissTruthToolkit

    toolkit = SwissTruthToolkit(api_key="your-key")
    tools = toolkit.get_tools()

    # With LangGraph agent:
    from langgraph.prebuilt import create_react_agent
    agent = create_react_agent(llm, tools)
"""
from __future__ import annotations

from langchain_core.tools import BaseTool

from swiss_truth_langchain.client import SwissTruthClient
from swiss_truth_langchain.tools import (
    SearchKnowledgeTool,
    VerifyClaimTool,
    SubmitClaimTool,
    ListDomainsTool,
    GetClaimStatusTool,
    BatchVerifyTool,
    VerifyResponseTool,
    FindContradictionsTool,
    GetComplianceTool,
)


class SwissTruthToolkit:
    """
    Convenient factory that returns all Swiss Truth tools pre-configured.

    Args:
        api_key: Optional API key for write operations (submit_claim).
        base_url: Swiss Truth API base URL (default: https://swisstruth.org).
        timeout: HTTP timeout in seconds (default: 60).

    Example:
        toolkit = SwissTruthToolkit()
        tools = toolkit.get_tools()

        # Minimal set (read-only):
        tools = toolkit.get_tools(read_only=True)
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://swisstruth.org",
        timeout: int = 60,
    ) -> None:
        self._client = SwissTruthClient(
            base_url=base_url, api_key=api_key, timeout=timeout
        )

    def get_tools(self, read_only: bool = False) -> list[BaseTool]:
        """
        Return all Swiss Truth tools.

        Args:
            read_only: If True, exclude write tools (submit_claim).
                       Useful for public-facing agents.
        """
        c = self._client
        tools: list[BaseTool] = [
            SearchKnowledgeTool(client=c),
            VerifyClaimTool(client=c),
            ListDomainsTool(client=c),
            GetClaimStatusTool(client=c),
            BatchVerifyTool(client=c),
            VerifyResponseTool(client=c),
            FindContradictionsTool(client=c),
            GetComplianceTool(client=c),
        ]
        if not read_only:
            tools.append(SubmitClaimTool(client=c))
        return tools
