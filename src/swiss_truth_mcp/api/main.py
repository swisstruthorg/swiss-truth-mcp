from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.types import Receive, Scope, Send

from swiss_truth_mcp.api.models import DomainResponse
from swiss_truth_mcp.api.routes.claims import router as claims_router
from swiss_truth_mcp.api.routes.search import router as search_router
from swiss_truth_mcp.api.routes.review import router as review_router
from swiss_truth_mcp.api.routes.n8n import router as n8n_router
from swiss_truth_mcp.api.routes.dashboard import router as dashboard_router
from swiss_truth_mcp.api.routes.auth import router as auth_router
from swiss_truth_mcp.api.routes.users import router as users_router
from swiss_truth_mcp.api.routes.generate import router as generate_router
from swiss_truth_mcp.api.routes.feed import router as feed_router
from swiss_truth_mcp.db.neo4j_client import close_driver, get_session
from swiss_truth_mcp.db import queries, schema
from swiss_truth_mcp.mcp_server.http_server import mcp_session_manager, handle_mcp_request


@asynccontextmanager
async def lifespan(api_app: FastAPI):
    # Schema + Indizes in Neo4j sicherstellen
    async with get_session() as session:
        await schema.setup_schema(session)
    # MCP Session Manager starten (stateless, SSE streaming)
    async with mcp_session_manager.run():
        yield
    await close_driver()


# ─── FastAPI (REST API + Dashboard + Review UI) ───────────────────────────────

_api_app = FastAPI(
    title="Swiss Truth MCP — REST API",
    description="Validierter Ground-Truth Layer für KI-Agenten",
    version="0.1.0",
    lifespan=lifespan,
)

_api_app.include_router(auth_router)
_api_app.include_router(claims_router)
_api_app.include_router(search_router)
_api_app.include_router(review_router)
_api_app.include_router(n8n_router)
_api_app.include_router(dashboard_router)
_api_app.include_router(users_router)
_api_app.include_router(generate_router)
_api_app.include_router(feed_router)

_TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/dashboard")


@meta_router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@meta_router.get("/.well-known/mcp.json", include_in_schema=False)
async def mcp_discovery():
    """
    MCP Auto-Discovery Endpoint (RFC 8615).
    Erlaubt KI-Agenten und Tools den Server automatisch zu finden und zu konfigurieren.
    """
    return {
        "schema_version": "1",
        "name": "Swiss Truth MCP",
        "description": (
            "Verified knowledge base for AI agents. "
            "Certified facts with source references, confidence scores, "
            "and SHA256 integrity hashes. Covers Swiss law, health, finance, "
            "education, energy, politics, climate, AI/ML, and world science."
        ),
        "version": "0.1.0",
        "homepage": "https://swisstruth.org",
        "transport": {
            "type": "streamable-http",
            "url": "https://swisstruth.org/mcp",
        },
        "tools": [
            {
                "name": "search_knowledge",
                "description": "Search verified claims by natural language query. Auto-detects language (DE/EN/FR/IT/ES/ZH/AR and more). Returns confidence score, source references, and SHA256 hash.",
            },
            {
                "name": "get_claim",
                "description": "Retrieve a single claim with full provenance (validator, institution, review date).",
            },
            {
                "name": "list_domains",
                "description": "List all available knowledge domains with certified claim counts.",
            },
            {
                "name": "submit_claim",
                "description": "Submit a new claim for expert review. Triggers AI pre-screening and URL verification.",
            },
            {
                "name": "verify_claim",
                "description": "Fact-check a statement against the knowledge base. Returns verdict: supported / contradicted / unknown, with confidence score and source evidence.",
            },
            {
                "name": "get_claim_status",
                "description": "Check the validation status of a submitted claim (draft → peer_review → certified).",
            },
        ],
        "authentication": {
            "required": False,
            "note": "Fully public. No API key needed for any tool.",
        },
        "claude_desktop_config": {
            "mcpServers": {
                "swiss-truth": {
                    "type": "http",
                    "url": "https://swisstruth.org/mcp",
                }
            }
        },
    }


@meta_router.get("/trust", response_class=HTMLResponse, include_in_schema=False)
async def trust_page(request: Request):
    """Öffentliche Trust-Page — keine Authentifizierung erforderlich."""
    async with get_session() as session:
        stats = await queries.get_trust_stats(session)
    return _TEMPLATES.TemplateResponse(request, "trust.html", {"request": request, "s": stats})


@meta_router.get("/domains", response_model=list[DomainResponse])
async def list_domains():
    async with get_session() as session:
        return await queries.list_domains(session)


_api_app.include_router(meta_router)


# ─── Kombinierter ASGI-Wrapper ────────────────────────────────────────────────
# Fängt /mcp-Requests VOR FastAPI's Router ab — kein Routing-Konflikt möglich.

class _SwissTruthASGI:
    """
    Äusserstes ASGI-App:
      • /mcp* → MCP StreamableHTTP Session Manager (Swiss Truth Knowledge API)
      • alles andere → FastAPI (_api_app) mit Dashboard, Review UI, REST API
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("path", "").startswith("/mcp"):
            await handle_mcp_request(scope, receive, send)
        else:
            await _api_app(scope, receive, send)


# `app` ist der uvicorn-Einstiegspunkt ("swiss_truth_mcp.api.main:app")
app = _SwissTruthASGI()


def main():
    uvicorn.run("swiss_truth_mcp.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
