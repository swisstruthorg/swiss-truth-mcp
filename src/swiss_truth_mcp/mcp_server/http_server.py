"""
MCP HTTP Server — StreamableHTTP transport für Remote-Zugriff.

Stellt den /mcp Endpunkt bereit. Wird von api/main.py als ASGI-Wrapper
vor dem FastAPI-Router eingebunden.

Öffentlicher Zugriff (kein API-Key erforderlich):
  search_knowledge, get_claim, list_domains, get_claim_status

submit_claim ist durch mehrstufige Pipeline geschützt:
  AI Pre-Screen → URL-Validierung → Quellenverifikation → menschliches Peer-Review

Konfiguration für Claude Desktop (claude_desktop_config.json):
{
  "mcpServers": {
    "swiss-truth": {
      "type": "http",
      "url": "https://swisstruth.org/mcp"
    }
  }
}
"""

from starlette.types import Receive, Scope, Send

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from swiss_truth_mcp.mcp_server.server import app as mcp_server

# Stateless — jeder Request spawnt eine frische MCP Session.
mcp_session_manager = StreamableHTTPSessionManager(
    app=mcp_server,
    stateless=True,
    json_response=False,
)


async def handle_mcp_request(scope: Scope, receive: Receive, send: Send) -> None:
    """Leitet /mcp Requests direkt an den Session Manager weiter (öffentlich)."""
    await mcp_session_manager.handle_request(scope, receive, send)
