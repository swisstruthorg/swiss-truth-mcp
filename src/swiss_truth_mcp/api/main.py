from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

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
from swiss_truth_mcp.api.routes.anchor import router as anchor_router
from swiss_truth_mcp.api.routes.kanban import router as kanban_router
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from swiss_truth_mcp.db.neo4j_client import close_driver, get_session
from swiss_truth_mcp.db import queries, schema
from swiss_truth_mcp.mcp_server.http_server import mcp_session_manager, handle_mcp_request
from swiss_truth_mcp.middleware.rate_limiter import RateLimitMiddleware
from swiss_truth_mcp.renewal.cost_cap import daily_cap


@asynccontextmanager
async def lifespan(api_app: FastAPI):
    # Schema + Indizes in Neo4j sicherstellen
    async with get_session() as session:
        await schema.setup_schema(session)

    # APScheduler: täglicher Reset des Renewal-Kosten-Caps um Mitternacht UTC (SEC-05)
    scheduler = AsyncIOScheduler()

    def _reset_daily_cap() -> None:
        """Setzt den täglichen API-Kosten-Cap zurück. Läuft um 00:00 UTC."""
        daily_cap.reset()

    scheduler.add_job(
        _reset_daily_cap,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="daily_cap_reset",
        replace_existing=True,
    )
    scheduler.start()

    # MCP Session Manager starten (stateless, SSE streaming)
    try:
        async with mcp_session_manager.run():
            yield
    finally:
        scheduler.shutdown(wait=False)
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
_api_app.include_router(anchor_router)
_api_app.include_router(kanban_router)

_TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).parent.parent / "templates")
)

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/trust")


@meta_router.get("/factcheck", response_class=HTMLResponse, include_in_schema=False)
async def factcheck_page(request: Request):
    """Öffentliche Fact-Check Q&A Demo-Seite."""
    return _TEMPLATES.TemplateResponse(request, "factcheck.html", {"request": request})


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
            {
                "name": "verify_claims_batch",
                "description": "Verify multiple claims in parallel. Returns verdict, confidence, and evidence per claim plus a summary.",
            },
            {
                "name": "verify_response",
                "description": "Check a full AI response paragraph for hallucination risk (low/medium/high). Atomizes text and verifies each statement.",
            },
            {
                "name": "find_contradictions",
                "description": "Find certified claims that contradict a given statement. Safety check before publishing facts.",
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


@meta_router.get("/validators", response_class=HTMLResponse, include_in_schema=False)
async def validators_page(request: Request):
    """Öffentliches Validator-Leaderboard — keine Authentifizierung erforderlich."""
    async with get_session() as session:
        stats = await queries.get_dashboard_stats(session)
    return _TEMPLATES.TemplateResponse(request, "validators.html", {
        "request": request,
        "validators": stats["validators"],
        "certified": stats["certified"],
        "total": stats["total"],
    })


@meta_router.get("/stats", response_class=HTMLResponse, include_in_schema=False)
async def stats_page(request: Request):
    """Öffentliches Stats-Dashboard — keine Authentifizierung erforderlich."""
    async with get_session() as session:
        dash = await queries.get_dashboard_stats(session)
        analytics = await queries.get_query_analytics(session)
    return _TEMPLATES.TemplateResponse(request, "stats.html", {
        "request": request,
        "s": dash,
        "a": analytics,
    })


@meta_router.get("/openai-tools.json", include_in_schema=False)
async def openai_tools():
    """
    Swiss Truth Tools im OpenAI function-calling Format.
    Für Agenten die nicht MCP nutzen (OpenAI API, LangChain, LlamaIndex, etc.).
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": (
                    "Search the Swiss Truth verified knowledge base for certified facts. "
                    "Use this when you need reliable, source-backed information to avoid hallucination — "
                    "especially for Swiss law, health, finance, politics, education, energy, transport, "
                    "climate, AI/ML, and world science topics. "
                    "Call this before answering factual questions where being wrong would matter."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query in DE, EN, FR, or IT. Phrase it as a question for best results.",
                        },
                        "domain": {
                            "type": "string",
                            "description": (
                                "Optional domain filter. "
                                "Swiss: swiss-health, swiss-law, swiss-finance, swiss-education, "
                                "swiss-energy, swiss-transport, swiss-politics, swiss-agriculture, swiss-digital. "
                                "EU & Global: eu-law, eu-health, global-science, international-law, economics. "
                                "Science & Tech: ai-ml, ai-safety, quantum-computing, cybersecurity, "
                                "biotech, renewable-energy, space-science. "
                                "General: climate, world-science, world-history, us-law. "
                                "Omit to search across all domains."
                            ),
                        },
                        "min_confidence": {
                            "type": "number",
                            "description": "Minimum confidence threshold 0.0–1.0. Default 0.8. Use 0.95+ for critical facts.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of results to return (max 20, default 5).",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_claim",
                "description": (
                    "Fact-check a statement against the Swiss Truth knowledge base. "
                    "Returns verdict: supported | contradicted | unknown, "
                    "with confidence score and source evidence. "
                    "Use this to verify AI-generated content or ground responses."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The factual statement to verify. One clear, atomic claim.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional domain filter (e.g. swiss-health, ai-ml). Omit to search all domains.",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_claim",
                "description": (
                    "Retrieve a single verified claim with full provenance by its ID. "
                    "Returns validator name, institution, review date, SHA256 hash, and effective confidence."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {
                            "type": "string",
                            "description": "UUID of the claim, obtained from search_knowledge results.",
                        },
                    },
                    "required": ["claim_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_domains",
                "description": (
                    "List all available knowledge domains with certified claim counts. "
                    "Use at the start of a session or when unsure which domain to search."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_claim",
                "description": (
                    "Submit a new factual claim for expert review and certification. "
                    "Use when you identify a knowledge gap. "
                    "Requirements: one atomic statement, at least one primary source URL (not Wikipedia)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_text": {
                            "type": "string",
                            "description": "The factual statement — one single, clear, verifiable claim. Max 2000 characters.",
                        },
                        "domain_id": {
                            "type": "string",
                            "description": "Domain ID (e.g. ai-ml, swiss-health, climate). Use list_domains to see all options.",
                        },
                        "source_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Primary source URLs that directly support the claim. No Wikipedia.",
                        },
                        "question": {
                            "type": "string",
                            "description": "The canonical question this claim answers. Improves retrieval quality.",
                        },
                    },
                    "required": ["claim_text", "domain_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_claim_status",
                "description": (
                    "Check the validation status of a submitted claim: "
                    "draft → peer_review → certified."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_id": {
                            "type": "string",
                            "description": "UUID returned by submit_claim.",
                        },
                    },
                    "required": ["claim_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_claims_batch",
                "description": (
                    "Verify multiple factual claims in parallel against the Swiss Truth knowledge base. "
                    "Much faster than calling verify_claim repeatedly. "
                    "Returns per claim: verdict (supported|contradicted|unknown), confidence, and evidence. "
                    "Also returns a summary with counts of supported/contradicted/unknown."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claims": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of factual statements to verify. Max 20 items.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional domain filter applied to all claims (e.g. swiss-health, ai-ml).",
                        },
                    },
                    "required": ["claims"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_response",
                "description": (
                    "Check a full AI response paragraph for hallucination risk. "
                    "Atomizes the text into individual claims, verifies each against the knowledge base, "
                    "and returns an overall hallucination risk score: low | medium | high. "
                    "Returns verified/contradicted/unverified counts and per-statement breakdown."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The full response text to check. Can be a paragraph or multiple sentences.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional domain filter (e.g. swiss-health). Omit to search all domains.",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_contradictions",
                "description": (
                    "Find certified claims in the knowledge base that contradict a given statement. "
                    "Use as a safety check before publishing facts. "
                    "Returns all contradicting certified claims with explanations and contradiction confidence."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim_text": {
                            "type": "string",
                            "description": "The factual statement to check for contradictions.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional domain filter (e.g. swiss-law, ai-ml).",
                        },
                    },
                    "required": ["claim_text"],
                },
            },
        },
    ]


@meta_router.get("/api/compliance/eu-ai-act/{claim_id}", include_in_schema=True)
async def eu_ai_act_compliance(claim_id: str):
    """
    EU AI Act Compliance Attestation für einen zertifizierten Claim.

    Gibt eine strukturierte JSON-Attestierung zurück, die dokumentiert dass der Claim
    die Anforderungen der EU AI Act Articles 9, 13 und 17 erfüllt:
    - Art. 9: Risikomanagement (5-stufige Validierungs-Pipeline)
    - Art. 13: Transparenz (Provenienz, Validator, Konfidenz, Quellen)
    - Art. 17: Qualitätsmanagement (SHA256-Integrität, Expiry, Confidence-Decay)

    Geeignet für regulierte Industrien (Finanz, Gesundheit, Recht) die
    AI-Outputs für Compliance-Zwecke dokumentieren müssen.
    """
    from swiss_truth_mcp.validation.trust import decay_confidence
    from datetime import datetime, timezone

    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id)

    if claim is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    if claim["status"] != "certified":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"Claim is not certified (status: {claim['status']}). Only certified claims qualify for compliance attestation."
        )

    effective_conf = decay_confidence(claim["confidence_score"], claim.get("last_reviewed"))
    validators = claim.get("validated_by", [])
    sources = claim.get("source_references", [])
    now = datetime.now(timezone.utc).isoformat()

    return {
        "attestation_version": "1.0",
        "attested_at": now,
        "attested_by": "Swiss Truth MCP — swisstruth.org",

        # Claim identity
        "claim_id": claim_id,
        "claim_text": claim["text"],
        "domain": claim["domain_id"],
        "language": claim.get("language", "unknown"),

        # EU AI Act compliance fields
        "compliant_with": [
            "EU-AI-Act-Art-9",   # Risk management system
            "EU-AI-Act-Art-13",  # Transparency and information provision
            "EU-AI-Act-Art-17",  # Quality management system
        ],

        # Art. 9 — Risk Management: validation pipeline
        "risk_management": {
            "article": "EU AI Act Article 9",
            "validation_stages_passed": 5,
            "stages": [
                "1. Semantic deduplication (cosine similarity ≥ 0.95)",
                "2. AI pre-screen (Claude Haiku — atomicity, factuality, source check)",
                "3. Source URL verification (content fetched and validated)",
                "4. Expert peer review (human validation with confidence score)",
                "5. SHA256 cryptographic signing + expiry assignment",
            ],
            "human_review_confirmed": len(validators) > 0,
            "expert_count": len(validators),
        },

        # Art. 13 — Transparency: full provenance
        "transparency": {
            "article": "EU AI Act Article 13",
            "validators": validators,
            "source_count": len(sources),
            "source_references": sources,
            "confidence_score": claim["confidence_score"],
            "effective_confidence": round(effective_conf, 4),
            "last_reviewed": claim.get("last_reviewed"),
            "expires_at": claim.get("expires_at"),
        },

        # Art. 17 — Quality Management: integrity & freshness
        "quality_management": {
            "article": "EU AI Act Article 17",
            "cryptographic_integrity": claim.get("hash_sha256", ""),
            "integrity_method": "SHA256 over canonical claim content",
            "confidence_decay_rate": "1% per month since last review (floor: 50%)",
            "ttl_days": 365,
            "knowledge_cutoff": claim.get("last_reviewed"),
            "renewal_required_after": claim.get("expires_at"),
        },

        # Machine-readable summary
        "summary": {
            "is_compliant": True,
            "risk_level": "minimal",
            "data_quality": "high" if effective_conf >= 0.90 else "medium" if effective_conf >= 0.75 else "low",
            "freshness": "current" if (claim.get("expires_at") is None or claim.get("expires_at", "") > now[:10]) else "renewal_recommended",
        },

        "verification_url": f"https://swisstruth.org/api/claims/{claim_id}",
        "methodology_url": "https://swisstruth.org/trust",
    }


@meta_router.get("/domains", response_model=list[DomainResponse])
async def list_domains():
    async with get_session() as session:
        return await queries.list_domains(session)


_api_app.include_router(meta_router)

_STATIC_DIR = Path(__file__).parent.parent / "static"
_api_app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


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
# RateLimitMiddleware ist die äusserste Schicht — prüft jeden Request vor MCP und FastAPI.
app = RateLimitMiddleware(_SwissTruthASGI())


def main():
    uvicorn.run("swiss_truth_mcp.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
