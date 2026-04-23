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
from swiss_truth_mcp.api.routes.compliance import router as compliance_router
from swiss_truth_mcp.api.routes.quality import router as quality_router
from swiss_truth_mcp.api.routes.api_keys import router as api_keys_router
from swiss_truth_mcp.api.routes.monitoring import router as monitoring_router
from swiss_truth_mcp.api.routes.audit import router as audit_router
from swiss_truth_mcp.api.routes.tenants import router as tenants_router
# Phase 5: Production Hardening & Developer Experience routers
from swiss_truth_mcp.api.routes.portal import router as portal_router
from swiss_truth_mcp.api.routes.graph import router as graph_router
from swiss_truth_mcp.api.routes.pipeline import router as pipeline_router
# Phase 6: AI Agent First routers
from swiss_truth_mcp.api.routes.agent import router as agent_router
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from swiss_truth_mcp.db.neo4j_client import close_driver, get_session
from swiss_truth_mcp.db import queries, schema
from swiss_truth_mcp.mcp_server.http_server import mcp_session_manager, handle_mcp_request
from swiss_truth_mcp.middleware.rate_limiter import RateLimitMiddleware
from swiss_truth_mcp.config import settings
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

    # Wöchentlicher Blockchain-Anchor: Sonntag 02:00 UTC (Plan 03-02)
    async def _weekly_anchor() -> None:
        """Berechnet Merkle-Root und verankert auf Chain (wenn konfiguriert)."""
        from swiss_truth_mcp.blockchain.anchor import run_anchor_job
        import logging
        _log = logging.getLogger("swiss_truth_mcp.anchor_cron")
        try:
            async with get_session() as session:
                record = await run_anchor_job(
                    session=session,
                    rpc_url=settings.eth_rpc_url,
                    private_key=settings.eth_private_key,
                    chain_id=settings.eth_chain_id,
                    chain_name=settings.eth_chain_name,
                    dry_run=not (settings.eth_rpc_url and settings.eth_private_key),
                )
            _log.info("Weekly anchor complete: %s claims, root=%s, status=%s",
                       record.get("claim_count"), record.get("merkle_root", "")[:16], record.get("status"))
        except Exception as e:
            _log.error("Weekly anchor failed: %s", e)

    scheduler.add_job(
        _weekly_anchor,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0, timezone="UTC"),
        id="weekly_anchor",
        replace_existing=True,
    )

    # Täglicher Renewal-Worker: 03:00 UTC (Plan 03-01)
    async def _daily_renewal() -> None:
        """Erneuert ablaufende Claims via AI re-verification."""
        from swiss_truth_mcp.renewal.worker import run_renewal_batch
        import logging
        _log = logging.getLogger("swiss_truth_mcp.renewal_cron")
        try:
            result = await run_renewal_batch()
            _log.info("Daily renewal: %d renewed, %d skipped, %d failed",
                       result.get("renewed", 0), result.get("skipped", 0), result.get("failed", 0))
        except Exception as e:
            _log.error("Daily renewal failed: %s", e)

    scheduler.add_job(
        _daily_renewal,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="daily_renewal",
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
_api_app.include_router(compliance_router)
_api_app.include_router(quality_router)
# Phase 4: Enterprise & Compliance routers
_api_app.include_router(api_keys_router)
_api_app.include_router(monitoring_router)
_api_app.include_router(audit_router)
_api_app.include_router(tenants_router)
# Phase 5: Production Hardening & Developer Experience routers
_api_app.include_router(portal_router)
_api_app.include_router(graph_router)
_api_app.include_router(pipeline_router)
# Phase 6: AI Agent First routers
_api_app.include_router(agent_router)

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
    """Health check with cache and SLA status."""
    result = {"status": "ok", "version": "0.1.0"}
    try:
        from swiss_truth_mcp.cache.redis_client import cache
        result["cache"] = await cache.health_check()
    except Exception:
        result["cache"] = {"backend": "unknown", "status": "error"}
    return result


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
            "and SHA256 integrity hashes. Covers 30 domains: Swiss law, health, finance, "
            "education, energy, politics, EU law, AI/ML, climate, biotech, quantum computing, "
            "cybersecurity, space science, economics, international law, and more."
        ),
        "version": "1.3.0",
        "homepage": "https://swisstruth.org",
        "keywords": [
            "mcp", "fact-checking", "hallucination-prevention", "knowledge-base",
            "ai-agents", "swiss-law", "eu-ai-act", "rag", "verified-facts",
            "citations", "compliance", "regulatory"
        ],
        "categories": ["knowledge", "fact-checking", "compliance", "research"],
        "agent_frameworks": ["langchain", "crewai", "autogen", "openai", "anthropic", "llamaindex"],
        "transport": {
            "type": "streamable-http",
            "url": "https://swisstruth.org/mcp",
        },
        "tools": [
            {
                "name": "search_knowledge",
                "description": "Semantic search over 2000+ certified facts across 30 domains. Auto-detects language (DE/EN/FR/IT/ES/ZH/AR). Returns confidence score, source references, SHA256 hash.",
                "use_when": "Need reliable, source-backed information before answering factual questions.",
            },
            {
                "name": "get_claim",
                "description": "Retrieve a single claim with full provenance (validator, institution, review date, SHA256).",
                "use_when": "Need complete citation details for a specific claim.",
            },
            {
                "name": "list_domains",
                "description": "List all 30 knowledge domains with certified claim counts.",
                "use_when": "Start of session or unsure which domain to search.",
            },
            {
                "name": "submit_claim",
                "description": "Submit a new claim for expert review. Triggers AI pre-screening and URL verification.",
                "use_when": "Identified a knowledge gap — fact that should be in the base but isn't.",
            },
            {
                "name": "verify_claim",
                "description": "Fact-check a statement. Returns verdict: supported / contradicted / unknown, with confidence and source evidence.",
                "use_when": "ReAct loops — verify whether a statement is true, false, or unknown.",
            },
            {
                "name": "get_claim_status",
                "description": "Check validation status: draft → peer_review → certified.",
                "use_when": "After submit_claim to track review progress.",
            },
            {
                "name": "verify_claims_batch",
                "description": "Verify up to 20 claims in parallel. Returns verdict, confidence, evidence per claim plus summary.",
                "use_when": "Fact-check several statements at once before sending a multi-assertion response.",
            },
            {
                "name": "verify_response",
                "description": "Check a full AI response for hallucination risk (low/medium/high). Atomizes text, verifies each statement.",
                "use_when": "Before sending a multi-sentence response to a user.",
            },
            {
                "name": "find_contradictions",
                "description": "Find ALL certified claims that contradict a given statement with explanations.",
                "use_when": "Safety check before publishing facts — surface all known conflicts.",
            },
            {
                "name": "get_knowledge_brief",
                "description": "Structured, citable knowledge brief with key facts, sources, and confidence scores. Optimized for RAG pipelines.",
                "use_when": "Enrich response with verified facts — better than search_knowledge for agent-ready output.",
            },
            {
                "name": "get_citations",
                "description": "Properly formatted citations (inline, APA) for any factual claim with verified source URLs.",
                "use_when": "Need to cite sources in a response — solves the #1 agent problem: unverifiable citations.",
            },
            {
                "name": "check_freshness",
                "description": "Check if a fact is still current. Detects stale training data for fast-changing topics.",
                "use_when": "Unsure if training data is outdated — especially for AI, regulations, statistics.",
            },
            {
                "name": "check_regulatory_compliance",
                "description": "Check agent-generated text for Swiss/EU regulatory compliance (FINMA, BAG, GDPR, EU AI Act).",
                "use_when": "Before sending responses in regulated domains: finance, health, law.",
            },
            {
                "name": "report_agent_need",
                "description": "Report missing domains, claims, or features. Feedback directly shapes the roadmap.",
                "use_when": "Can't find what you need — search returned nothing or domain is missing.",
            },
        ],
        "example_queries": [
            "How does Swiss mandatory health insurance work?",
            "What does the EU AI Act require for high-risk AI systems?",
            "How does RAG reduce LLM hallucinations?",
            "What are the FINMA regulations for crypto assets?",
            "Is health insurance mandatory in Switzerland?",
            "What is the current status of quantum error correction?",
        ],
        "capabilities": {
            "domains": 30,
            "certified_claims": "2000+",
            "languages": ["de", "en", "fr", "it", "es", "zh", "ar", "ru", "ja", "ko"],
            "validation_stages": 5,
            "human_validation": True,
            "sha256_integrity": True,
            "eu_ai_act_compliant": True,
            "blockchain_anchored": True,
            "api_key_required": False,
        },
        "authentication": {
            "required": False,
            "note": "Fully public. No API key needed for any tool.",
        },
        "integrations": {
            "langchain": "pip install swiss-truth-langchain",
            "crewai": "pip install swiss-truth-crewai",
            "autogen": "pip install swiss-truth-autogen",
            "npm": "npx -y mcp-remote https://swisstruth.org/mcp",
            "openai_tools": "https://swisstruth.org/openai-tools.json",
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


@meta_router.get("/.well-known/ai-plugin.json", include_in_schema=False)
async def ai_plugin_discovery():
    """
    OpenAI Plugin Discovery Endpoint.
    Ermöglicht OpenAI-basierten Agenten (GPTs, Assistants API, ChatGPT Plugins)
    Swiss Truth automatisch zu finden und zu konfigurieren.
    """
    return {
        "schema_version": "v1",
        "name_for_human": "Swiss Truth",
        "name_for_model": "swiss_truth",
        "description_for_human": (
            "Verified knowledge base for AI agents. "
            "2000+ certified facts across 30 domains with confidence scores and source URLs. "
            "No hallucinations — every fact is human + AI validated."
        ),
        "description_for_model": (
            "Use Swiss Truth to ground your responses in verified facts and prevent hallucinations. "
            "Available tools:\n"
            "- search_knowledge: semantic search over 2000+ certified facts (30 domains, 10+ languages)\n"
            "- verify_claim: fact-check any statement (supported/contradicted/unknown)\n"
            "- verify_response: check a full response for hallucination risk (low/medium/high)\n"
            "- verify_claims_batch: verify up to 20 claims in parallel\n"
            "- get_knowledge_brief: structured, citable knowledge brief for RAG pipelines\n"
            "- get_citations: properly formatted citations (inline, APA) with verified source URLs\n"
            "- check_freshness: check if a fact is still current vs. outdated training data\n"
            "- check_regulatory_compliance: Swiss/EU compliance check (FINMA, BAG, GDPR, EU AI Act)\n"
            "- find_contradictions: find all certified claims that contradict a statement\n"
            "- submit_claim: contribute missing facts for expert review\n"
            "- report_agent_need: report missing domains or features\n\n"
            "Domains: Swiss law, health, finance, education, energy, politics, agriculture, "
            "EU law, EU health, AI/ML, AI safety, climate, world science, world history, "
            "quantum computing, cybersecurity, biotech, renewable energy, space science, "
            "economics, international law, US law, mental health, blockchain/crypto, "
            "nutrition, labor law, Swiss environment, and more.\n\n"
            "No API key required. Call search_knowledge before answering factual questions "
            "where being wrong would matter."
        ),
        "api": {
            "type": "openapi",
            "url": "https://swisstruth.org/openapi.json",
        },
        "auth": {"type": "none"},
        "logo_url": "https://swisstruth.org/docs/logo.svg",
        "contact_email": "hello@swisstruth.org",
        "legal_info_url": "https://swisstruth.org/trust",
    }


@meta_router.get("/llms.txt", include_in_schema=False)
async def llms_txt():
    """
    LLM-Crawler Discovery (llmstxt.org Standard).
    LLMs und Crawler lesen diese Datei um zu verstehen was Swiss Truth bietet.
    """
    from fastapi.responses import PlainTextResponse
    content = """# Swiss Truth MCP
> Verified knowledge base for AI agents — certified facts, not hallucinations.

Swiss Truth provides 2000+ certified facts across 30 domains with confidence scores,
verified source URLs, and SHA256 integrity hashes. Every fact passes a 5-stage
human + AI validation pipeline. EU AI Act compliant. No API key required.

## Why agents use Swiss Truth

- **Prevent hallucinations**: Ground responses in verified facts before answering
- **Cite sources**: Get properly formatted citations (inline, APA) with verified URLs
- **Check compliance**: Swiss/EU regulatory compliance (FINMA, BAG, GDPR, EU AI Act)
- **Detect stale data**: Check if your training data is still current
- **Batch verification**: Verify up to 20 claims in parallel

## Quick Setup

MCP (Claude Desktop, Cursor, Windsurf):
```json
{"mcpServers": {"swiss-truth": {"command": "npx", "args": ["-y", "mcp-remote", "https://swisstruth.org/mcp"]}}}
```

LangChain: pip install swiss-truth-langchain
CrewAI:    pip install swiss-truth-crewai
AutoGen:   pip install swiss-truth-autogen

## MCP Tools (14 total)

- search_knowledge — semantic search, 10+ languages, auto-detected
- verify_claim — fact-check: supported / contradicted / unknown
- verify_response — hallucination risk score for full response text
- verify_claims_batch — verify up to 20 claims in parallel
- find_contradictions — find all certified contradictions
- get_knowledge_brief — structured, citable knowledge brief for RAG
- get_citations — inline + APA citations with verified source URLs
- check_freshness — detect stale training data
- check_regulatory_compliance — Swiss/EU compliance check
- report_agent_need — report missing domains or features
- get_claim — full provenance for a single claim
- list_domains — browse all 30 knowledge domains
- submit_claim — contribute missing facts for expert review
- get_claim_status — track review pipeline: draft → peer_review → certified

## Domains (30)

Swiss: swiss-health, swiss-law, swiss-finance, swiss-education, swiss-energy,
       swiss-transport, swiss-politics, swiss-agriculture, swiss-digital,
       swiss-environment, labor-employment

EU & Global: eu-law, eu-health, global-science, international-law, economics,
             us-law

Science & Tech: ai-ml, ai-safety, quantum-computing, cybersecurity, biotech,
                renewable-energy, space-science, blockchain-crypto

General: climate, world-science, world-history, mental-health, nutrition-food

## API Endpoints

- MCP:           https://swisstruth.org/mcp
- REST API:      https://swisstruth.org/api
- OpenAI tools:  https://swisstruth.org/openai-tools.json
- Discovery:     https://swisstruth.org/.well-known/mcp.json
- AI Plugin:     https://swisstruth.org/.well-known/ai-plugin.json
- Agent Manifest:https://swisstruth.org/agents.json
- Trust & Stats: https://swisstruth.org/trust

## Authentication

None required. Fully public. Connect in 30 seconds.
"""
    return PlainTextResponse(content=content, media_type="text/plain")


@meta_router.get("/agents.json", include_in_schema=False)
async def agents_manifest():
    """
    Agent Capability Manifest — maschinenlesbar für Agent-Frameworks.
    Erklärt was Swiss Truth für Agenten tut, wie man es nutzt, und welche Probleme es löst.
    """
    return {
        "schema_version": "1",
        "name": "Swiss Truth",
        "tagline": "Verified knowledge infrastructure for AI agents",
        "url": "https://swisstruth.org",
        "mcp_endpoint": "https://swisstruth.org/mcp",
        "api_key_required": False,
        "problems_solved": [
            {
                "problem": "LLM hallucination on factual questions",
                "solution": "search_knowledge — semantic search over 2000+ certified facts",
                "impact": "high",
            },
            {
                "problem": "Cannot cite sources or verify citations",
                "solution": "get_citations — returns inline + APA citations with verified source URLs",
                "impact": "high",
            },
            {
                "problem": "Stale training data on fast-changing topics",
                "solution": "check_freshness — detects outdated facts and returns current version",
                "impact": "high",
            },
            {
                "problem": "Non-compliant responses in regulated domains",
                "solution": "check_regulatory_compliance — Swiss/EU compliance check before responding",
                "impact": "high",
            },
            {
                "problem": "Verifying multiple claims in a response",
                "solution": "verify_claims_batch — verify up to 20 claims in parallel",
                "impact": "medium",
            },
            {
                "problem": "Full response hallucination risk",
                "solution": "verify_response — atomizes text and returns hallucination_risk: low/medium/high",
                "impact": "high",
            },
        ],
        "tools": [
            {"name": "search_knowledge", "category": "retrieval", "languages": 10, "domains": 30},
            {"name": "verify_claim", "category": "verification", "returns": "supported|contradicted|unknown"},
            {"name": "verify_response", "category": "verification", "returns": "low|medium|high risk"},
            {"name": "verify_claims_batch", "category": "verification", "max_claims": 20},
            {"name": "find_contradictions", "category": "verification"},
            {"name": "get_knowledge_brief", "category": "retrieval", "optimized_for": "rag"},
            {"name": "get_citations", "category": "citation", "formats": ["inline", "apa"]},
            {"name": "check_freshness", "category": "quality"},
            {"name": "check_regulatory_compliance", "category": "compliance", "regulators": ["FINMA", "BAG", "GDPR", "EU AI Act"]},
            {"name": "report_agent_need", "category": "feedback"},
            {"name": "get_claim", "category": "retrieval"},
            {"name": "list_domains", "category": "discovery"},
            {"name": "submit_claim", "category": "contribution"},
            {"name": "get_claim_status", "category": "tracking"},
        ],
        "domains": {
            "total": 30,
            "swiss": ["swiss-health", "swiss-law", "swiss-finance", "swiss-education", "swiss-energy",
                      "swiss-transport", "swiss-politics", "swiss-agriculture", "swiss-digital",
                      "swiss-environment", "labor-employment"],
            "eu_global": ["eu-law", "eu-health", "global-science", "international-law", "economics", "us-law"],
            "science_tech": ["ai-ml", "ai-safety", "quantum-computing", "cybersecurity", "biotech",
                             "renewable-energy", "space-science", "blockchain-crypto"],
            "general": ["climate", "world-science", "world-history", "mental-health", "nutrition-food"],
        },
        "quick_start": {
            "mcp_claude_desktop": {
                "config": {
                    "mcpServers": {
                        "swiss-truth": {
                            "command": "npx",
                            "args": ["-y", "mcp-remote", "https://swisstruth.org/mcp"],
                        }
                    }
                }
            },
            "langchain": {
                "install": "pip install swiss-truth-langchain",
                "example": "from swiss_truth_langchain import SwissTruthToolkit\ntoolkit = SwissTruthToolkit()\ntools = toolkit.get_tools()",
            },
            "crewai": {
                "install": "pip install swiss-truth-crewai",
                "example": "from swiss_truth_crewai import SwissTruthSearchTool\ntool = SwissTruthSearchTool()\nagent = Agent(tools=[tool])",
            },
            "autogen": {
                "install": "pip install swiss-truth-autogen",
                "example": "from swiss_truth_autogen import register_swiss_truth_functions\nregister_swiss_truth_functions(assistant, user_proxy)",
            },
            "openai_functions": {
                "url": "https://swisstruth.org/openai-tools.json",
                "example": "import requests\ntools = requests.get('https://swisstruth.org/openai-tools.json').json()",
            },
            "direct_mcp": {
                "url": "https://swisstruth.org/mcp",
                "protocol": "MCP StreamableHTTP",
            },
        },
        "knowledge_stats": {
            "certified_claims": "2000+",
            "domains": 30,
            "languages": 10,
            "validation_pipeline_stages": 5,
            "human_validated": True,
            "sha256_integrity": True,
            "eu_ai_act_compliant": True,
            "blockchain_anchored": True,
        },
        "agent_personas": [
            {
                "type": "Research Agent",
                "primary_tools": ["search_knowledge", "get_knowledge_brief", "get_citations"],
                "use_case": "Ground research in verified facts with proper citations",
            },
            {
                "type": "Legal Compliance Agent",
                "primary_tools": ["search_knowledge", "check_regulatory_compliance", "verify_claim"],
                "use_case": "Swiss/EU regulatory compliance (FINMA, BAG, GDPR, EU AI Act)",
                "domains": ["swiss-law", "swiss-finance", "swiss-health", "eu-law"],
            },
            {
                "type": "RAG Pipeline",
                "primary_tools": ["get_knowledge_brief", "search_knowledge", "get_citations"],
                "use_case": "Enrich retrieval with human-validated facts",
            },
            {
                "type": "Fact-Checking Agent",
                "primary_tools": ["verify_claim", "verify_claims_batch", "verify_response", "find_contradictions"],
                "use_case": "Prevent hallucinations in AI-generated content",
            },
            {
                "type": "Health Advisory Agent",
                "primary_tools": ["search_knowledge", "check_regulatory_compliance", "check_freshness"],
                "use_case": "Accurate Swiss health information (KVG, Krankenkasse, Swissmedic)",
                "domains": ["swiss-health", "eu-health", "mental-health", "nutrition-food"],
            },
            {
                "type": "Financial Agent",
                "primary_tools": ["search_knowledge", "check_regulatory_compliance", "verify_claim"],
                "use_case": "FINMA-compliant financial information",
                "domains": ["swiss-finance", "economics", "blockchain-crypto"],
            },
        ],
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
# Middleware stack (outermost → innermost):
#   1. RateLimitMiddleware — rate limiting per IP/key
#   2. SLATrackerMiddleware — latency + error tracking (Phase 4)
#   3. _SwissTruthASGI — MCP + FastAPI routing
from swiss_truth_mcp.middleware.sla_tracker import SLATrackerMiddleware
app = RateLimitMiddleware(SLATrackerMiddleware(_SwissTruthASGI()))


def main():
    uvicorn.run("swiss_truth_mcp.api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
