#!/usr/bin/env python3
"""
Phase 10-06: Agent-Attraktivitäts-Benchmark
============================================
Testet ob Swiss Truth für alle 8 Agent-Personas beim ersten Request
echten Wert liefert. Ziel: ≥80% Hit-Rate pro Persona.

Verwendung:
    python3 phase10_benchmark.py
    python3 phase10_benchmark.py --api-base https://swisstruth.org
    python3 phase10_benchmark.py --persona research
    python3 phase10_benchmark.py --output benchmark_results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

import requests

# ─── Config ──────────────────────────────────────────────────
API_BASE = os.environ.get("SWISS_TRUTH_API_BASE", "https://swisstruth.org")
API_KEY  = os.environ.get("SWISS_TRUTH_API_KEY", "dev-key-change-in-prod")


def _headers() -> dict:
    return {
        "X-Swiss-Truth-Key": API_KEY,
        "Content-Type": "application/json",
    }


# ─── Test Definitions ────────────────────────────────────────

@dataclass
class TestQuery:
    query: str
    domain: Optional[str] = None
    min_results: int = 1          # minimum results expected
    min_confidence: float = 0.7   # minimum confidence expected


@dataclass
class PersonaBenchmark:
    name: str
    description: str
    queries: list[TestQuery]
    target_hit_rate: float = 0.80  # ≥80% of queries must succeed


# 8 Agent-Personas from the roadmap
PERSONAS: list[PersonaBenchmark] = [
    PersonaBenchmark(
        name="research",
        description="Research Agent — allgemeine Fakten-Recherche",
        queries=[
            TestQuery("Klimawandel Schweiz CO2 Emissionen", domain="climate"),
            TestQuery("Künstliche Intelligenz Grundlagen", domain="ai-ml"),
            TestQuery("Weltgeschichte erste Weltkrieg", domain="world-history"),
            TestQuery("Quantencomputing Qubit", domain="quantum-computing"),
            TestQuery("Weltraumforschung NASA Raumstation", domain="space-science"),
        ],
    ),
    PersonaBenchmark(
        name="legal_compliance",
        description="Legal & Compliance Agent — Recht und Regulierung",
        queries=[
            TestQuery("Schweizer Mietrecht Kündigung", domain="swiss-law"),
            TestQuery("DSGVO Datenschutz Grundverordnung", domain="eu-law"),
            TestQuery("EU AI Act Anforderungen", domain="eu-law"),
            TestQuery("Arbeitsrecht Schweiz Ferien", domain="labor-employment"),
            TestQuery("internationales Recht UNO", domain="international-law"),
        ],
    ),
    PersonaBenchmark(
        name="health_advisory",
        description="Health Advisory Agent — Gesundheit und Medizin",
        queries=[
            TestQuery("KVG Krankenversicherung Schweiz Grundversicherung", domain="swiss-health"),
            TestQuery("WHO Impfempfehlungen", domain="swiss-health"),
            TestQuery("Diabetes Behandlung Medikamente", domain="eu-health"),
            TestQuery("psychische Gesundheit Depression", domain="mental-health"),
            TestQuery("Ernährung Vitamine Mineralien", domain="nutrition-food"),
        ],
    ),
    PersonaBenchmark(
        name="financial",
        description="Financial Agent — Finanzen und Wirtschaft",
        queries=[
            TestQuery("SNB Schweizerische Nationalbank Leitzins", domain="swiss-finance"),
            TestQuery("FINMA Regulierung Banken", domain="swiss-finance"),
            TestQuery("Steuern Schweiz Einkommenssteuer", domain="swiss-finance"),
            TestQuery("Inflation Schweiz Teuerung", domain="economics"),
            TestQuery("Bitcoin Blockchain Kryptowährung", domain="blockchain-crypto"),
        ],
    ),
    PersonaBenchmark(
        name="rag_pipeline",
        description="RAG Pipeline — Semantische Suche über mehrere Domains",
        queries=[
            TestQuery("renewable energy solar wind Switzerland"),
            TestQuery("cybersecurity data breach prevention"),
            TestQuery("biotech gene therapy clinical trials"),
            TestQuery("Swiss education system university"),
            TestQuery("global science research collaboration"),
        ],
    ),
    PersonaBenchmark(
        name="content_generation",
        description="Content Generation Agent — Fakten-Checks zu Artikeln",
        queries=[
            TestQuery("5G Mobilfunk Strahlung Gesundheit", domain="swiss-digital"),
            TestQuery("Atomenergie Kernkraft Schweiz", domain="swiss-energy"),
            TestQuery("Landwirtschaft Pestizide Bio", domain="swiss-agriculture"),
            TestQuery("Elektroauto Batterie Reichweite", domain="renewable-energy"),
            TestQuery("KI Halluzination Sprachmodell"),
        ],
    ),
    PersonaBenchmark(
        name="multi_agent_orchestrator",
        description="Multi-Agent Orchestrator — Batch-Verify, Cross-Domain",
        queries=[
            TestQuery("Schweiz Umweltpolitik Klimaziele", domain="swiss-environment"),
            TestQuery("EU Gesundheitspolitik Arzneimittel", domain="eu-health"),
            TestQuery("US Recht Supreme Court", domain="us-law"),
            TestQuery("Biotechnologie CRISPR Genomeditierung", domain="biotech"),
            TestQuery("Weltwissenschaft Forschung Nobelpreis", domain="world-science"),
        ],
    ),
    PersonaBenchmark(
        name="developer",
        description="Developer Building Agents — API, Quick-Setup, Docs",
        queries=[
            TestQuery("MCP Model Context Protocol"),
            TestQuery("LangChain RAG retrieval augmented generation"),
            TestQuery("AI safety alignment principles", domain="ai-safety"),
            TestQuery("Swiss transport infrastructure rail", domain="swiss-transport"),
            TestQuery("Swiss politics federal council", domain="swiss-politics"),
        ],
    ),
]


# ─── Benchmark Runner ────────────────────────────────────────

@dataclass
class QueryResult:
    query: str
    domain: Optional[str]
    success: bool
    result_count: int
    top_confidence: float
    latency_ms: float
    error: Optional[str] = None


@dataclass
class PersonaResult:
    persona: str
    description: str
    target_hit_rate: float
    queries_run: int
    queries_passed: int
    hit_rate: float
    passed: bool
    avg_latency_ms: float
    avg_confidence: float
    query_results: list[QueryResult] = field(default_factory=list)


def search_claims(query: str, domain: Optional[str] = None, limit: int = 5) -> dict:
    """Calls the Swiss Truth search API."""
    params: dict = {"q": query, "limit": limit}
    if domain:
        params["domain"] = domain
    r = requests.get(
        f"{API_BASE}/api/search",
        headers=_headers(),
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def run_query(tq: TestQuery) -> QueryResult:
    """Runs a single test query and returns result."""
    start = time.time()
    try:
        data = search_claims(tq.query, tq.domain)
        latency_ms = (time.time() - start) * 1000

        # Normalize response format
        if isinstance(data, list):
            results = data
        elif isinstance(data, dict):
            results = data.get("results", data.get("claims", data.get("items", [])))
        else:
            results = []

        result_count = len(results)
        top_confidence = 0.0
        if results:
            first = results[0]
            if isinstance(first, dict):
                top_confidence = float(first.get("confidence", first.get("confidence_score", 0.0)))

        success = (
            result_count >= tq.min_results
            and (top_confidence >= tq.min_confidence or top_confidence == 0.0)
        )

        return QueryResult(
            query=tq.query,
            domain=tq.domain,
            success=success,
            result_count=result_count,
            top_confidence=top_confidence,
            latency_ms=latency_ms,
        )
    except Exception as e:
        latency_ms = (time.time() - start) * 1000
        return QueryResult(
            query=tq.query,
            domain=tq.domain,
            success=False,
            result_count=0,
            top_confidence=0.0,
            latency_ms=latency_ms,
            error=str(e),
        )


def run_persona_benchmark(persona: PersonaBenchmark, verbose: bool = True) -> PersonaResult:
    """Runs all queries for a persona."""
    if verbose:
        print(f"\n  🤖 {persona.name.upper()} — {persona.description}")
        print(f"     Target hit rate: {persona.target_hit_rate*100:.0f}%")

    query_results: list[QueryResult] = []
    for tq in persona.queries:
        qr = run_query(tq)
        query_results.append(qr)
        if verbose:
            status = "✅" if qr.success else "❌"
            domain_str = f"[{qr.domain}] " if qr.domain else ""
            conf_str = f"conf={qr.top_confidence:.2f}" if qr.top_confidence > 0 else "conf=N/A"
            print(f"     {status} {domain_str}{qr.query[:55]:<55} "
                  f"hits={qr.result_count} {conf_str} {qr.latency_ms:.0f}ms"
                  + (f" ERROR: {qr.error}" if qr.error else ""))
        time.sleep(0.3)  # rate limit safety

    passed = sum(1 for r in query_results if r.success)
    total = len(query_results)
    hit_rate = passed / total if total > 0 else 0.0
    avg_latency = sum(r.latency_ms for r in query_results) / total if total > 0 else 0.0
    avg_conf = sum(r.top_confidence for r in query_results) / total if total > 0 else 0.0

    result = PersonaResult(
        persona=persona.name,
        description=persona.description,
        target_hit_rate=persona.target_hit_rate,
        queries_run=total,
        queries_passed=passed,
        hit_rate=hit_rate,
        passed=hit_rate >= persona.target_hit_rate,
        avg_latency_ms=avg_latency,
        avg_confidence=avg_conf,
        query_results=query_results,
    )

    if verbose:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"     → {status}: {passed}/{total} queries ({hit_rate*100:.0f}% hit rate)")

    return result


# ─── Main ────────────────────────────────────────────────────

def run_benchmark(
    only_persona: Optional[str] = None,
    output_file: Optional[str] = None,
    verbose: bool = True,
) -> dict:
    start_time = datetime.now()

    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║   Swiss Truth — Phase 10-06: Agent-Attraktivitäts-Benchmark  ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"  API Base: {API_BASE}")
    print(f"  Started:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Filter personas if requested
    personas_to_run = PERSONAS
    if only_persona:
        personas_to_run = [p for p in PERSONAS if p.name == only_persona]
        if not personas_to_run:
            print(f"  ❌ Unknown persona '{only_persona}'. Available: {[p.name for p in PERSONAS]}")
            sys.exit(1)

    # Check API connectivity
    try:
        r = requests.get(f"{API_BASE}/domains", headers=_headers(), timeout=10)
        domain_count = len(r.json()) if r.ok else "?"
        print(f"  API reachable ✓ (domains: {domain_count})")
    except Exception as e:
        print(f"  ⚠️  API check failed: {e}")
        print("  Make sure the API is running: docker-compose up -d")

    print()

    # Run all persona benchmarks
    persona_results: list[PersonaResult] = []
    for persona in personas_to_run:
        pr = run_persona_benchmark(persona, verbose=verbose)
        persona_results.append(pr)

    # ─── Summary ─────────────────────────────────────────────
    end_time = datetime.now()
    duration_s = (end_time - start_time).total_seconds()

    print()
    print("════════════════════════════════════════════════════════════")
    print("  BENCHMARK SUMMARY")
    print("════════════════════════════════════════════════════════════")

    total_queries = sum(pr.queries_run for pr in persona_results)
    total_passed = sum(pr.queries_passed for pr in persona_results)
    overall_hit_rate = total_passed / total_queries if total_queries > 0 else 0.0
    personas_passed = sum(1 for pr in persona_results if pr.passed)
    avg_latency = sum(pr.avg_latency_ms for pr in persona_results) / len(persona_results) if persona_results else 0.0

    print(f"  {'Persona':<28} {'Queries':<10} {'Hit Rate':<12} {'Avg Latency':<14} Status")
    print(f"  {'─'*28} {'─'*10} {'─'*12} {'─'*14} {'─'*6}")
    for pr in persona_results:
        status = "✅ PASS" if pr.passed else "❌ FAIL"
        print(f"  {pr.persona:<28} {pr.queries_passed}/{pr.queries_run:<8} "
              f"{pr.hit_rate*100:>6.0f}%{'':>5} {pr.avg_latency_ms:>8.0f}ms{'':>5} {status}")
    print(f"  {'─'*28} {'─'*10} {'─'*12} {'─'*14} {'─'*6}")
    print(f"  {'TOTAL':<28} {total_passed}/{total_queries:<8} "
          f"{overall_hit_rate*100:>6.0f}%{'':>5} {avg_latency:>8.0f}ms")
    print()

    overall_pass = personas_passed == len(persona_results)
    overall_status = "✅ ALL PERSONAS PASS" if overall_pass else f"⚠️  {personas_passed}/{len(persona_results)} personas pass"
    print(f"  {overall_status}")
    print(f"  Duration: {duration_s:.1f}s")
    print("════════════════════════════════════════════════════════════")

    # KPI Assessment
    print()
    print("  KPI Check (Phase 10 Targets):")
    kpis = [
        ("Overall hit rate ≥80%",   overall_hit_rate >= 0.80, f"{overall_hit_rate*100:.0f}%"),
        ("All personas ≥80%",       all(pr.passed for pr in persona_results), f"{personas_passed}/{len(persona_results)} pass"),
        ("Avg latency <2000ms",     avg_latency < 2000,       f"{avg_latency:.0f}ms"),
        ("Total queries run",       True,                      f"{total_queries}"),
    ]
    for label, ok, value in kpis:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {label:<35} {value}")

    print()
    if overall_pass and overall_hit_rate >= 0.80:
        print("  🎉 Agent-Attraktivitäts-Benchmark BESTANDEN!")
        print("     → Phase 10 Content Foundation erfolgreich!")
        print("     → Bereit für Phase 11: Agent Acquisition Blitz")
    else:
        print("  ⚠️  Benchmark noch nicht vollständig bestanden.")
        print("     → Fehlende Domains weiter befüllen (phase10_run.sh --step 10-02/10-03)")
        failing = [pr.persona for pr in persona_results if not pr.passed]
        if failing:
            print(f"     → Schwache Personas: {', '.join(failing)}")

    print()

    # Build result dict
    result = {
        "timestamp": start_time.isoformat(),
        "api_base": API_BASE,
        "duration_seconds": duration_s,
        "summary": {
            "total_queries": total_queries,
            "total_passed": total_passed,
            "overall_hit_rate": round(overall_hit_rate, 4),
            "personas_passed": personas_passed,
            "personas_total": len(persona_results),
            "avg_latency_ms": round(avg_latency, 1),
            "benchmark_passed": overall_pass and overall_hit_rate >= 0.80,
        },
        "personas": [asdict(pr) for pr in persona_results],
    }

    # Save output
    if output_file:
        with open(output_file, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  Results saved to: {output_file}")
    else:
        default_out = f"benchmark_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(default_out, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"  Results saved to: {default_out}")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Swiss Truth Phase 10-06: Agent-Attraktivitäts-Benchmark"
    )
    parser.add_argument("--api-base", default=None, help="API base URL")
    parser.add_argument("--api-key",  default=None, help="API key")
    parser.add_argument("--persona",  default=None, help=f"Only run one persona: {[p.name for p in PERSONAS]}")
    parser.add_argument("--output",   default=None, help="Output JSON file")
    parser.add_argument("--quiet",    action="store_true", help="Less verbose output")
    args = parser.parse_args()

    global API_BASE, API_KEY
    if args.api_base:
        API_BASE = args.api_base
    if args.api_key:
        API_KEY = args.api_key

    result = run_benchmark(
        only_persona=args.persona,
        output_file=args.output,
        verbose=not args.quiet,
    )

    # Exit code: 0 = pass, 1 = fail
    sys.exit(0 if result["summary"]["benchmark_passed"] else 1)


if __name__ == "__main__":
    main()
