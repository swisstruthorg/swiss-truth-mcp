"""
Die 5 MCP Tools des Swiss Truth Servers.
Jede Funktion wird als MCP Tool registriert.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries, schema
from swiss_truth_mcp.embeddings import embed_text
from swiss_truth_mcp.validation.trust import sign_claim, now_iso, expiry_iso
from swiss_truth_mcp.validation.pre_screen import pre_screen_claim, compare_claims
from swiss_truth_mcp.validation.conflict_detect import detect_conflicts


# ---------------------------------------------------------------------------
# Sprach-Erkennung (kein externer Dienst — Unicode + Keywords)
# ---------------------------------------------------------------------------

_LANG_PATTERNS: list[tuple[str, object]] = [
    # Unicode-Ranges (zuverlässig)
    ("zh", lambda t: any('\u4e00' <= c <= '\u9fff' for c in t)),          # Chinesisch CJK
    ("ja", lambda t: any('\u3040' <= c <= '\u30ff' for c in t)),          # Japanisch
    ("ar", lambda t: any('\u0600' <= c <= '\u06ff' for c in t)),          # Arabisch
    ("ru", lambda t: any('\u0400' <= c <= '\u04ff' for c in t)),          # Russisch/Kyrillisch
    # Diakritika & Marker
    ("es", lambda t: 'ñ' in t or '¿' in t or '¡' in t),
    ("fr", lambda t: 'ç' in t.lower() or 'œ' in t.lower()),
    ("de", lambda t: any(c in t.lower() for c in ('ä', 'ö', 'ü', 'ß'))),
    # Häufige Wörter (Fallback, mindestens 2 Treffer)
    ("de", lambda t: sum(1 for w in ('wie', 'was', 'wer', 'ist', 'sind', 'die', 'der', 'das', 'und', 'nicht', 'kann', 'wird') if f' {w} ' in f' {t.lower()} ') >= 2),
    ("fr", lambda t: sum(1 for w in ('comment', 'est-ce', 'les', 'des', 'pour', 'avec', 'dans', 'sur', 'qui', 'que') if f' {w} ' in f' {t.lower()} ') >= 2),
    ("es", lambda t: sum(1 for w in ('cómo', 'qué', 'cuál', 'los', 'las', 'para', 'por', 'del', 'una', 'hay') if f' {w} ' in f' {t.lower()} ') >= 2),
    ("it", lambda t: sum(1 for w in ('come', 'che', 'per', 'con', 'del', 'una', 'sono', 'nel', 'alla') if f' {w} ' in f' {t.lower()} ') >= 2),
]


def _detect_language(text: str) -> str:
    """Erkennt die Sprache eines Texts anhand von Unicode-Ranges und häufigen Wörtern."""
    for lang, test in _LANG_PATTERNS:
        try:
            if test(text):
                return lang
        except Exception:
            continue
    return "en"  # Default: Englisch


async def search_knowledge(
    query: str,
    domain: Optional[str] = None,
    min_confidence: float = 0.8,
    language: Optional[str] = None,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Durchsucht die validierten Claims mit Hybrid-Suche (Vector + Graph).

    Args:
        query: Suchanfrage in natürlicher Sprache (DE, EN, FR, IT)
        domain: Optional — Domänen-ID Filter (z.B. 'ai-ml', 'climate')
        min_confidence: Mindestkonfidenz 0.0–1.0 (default 0.8)
        language: Optional — Sprachfilter (z.B. 'de', 'en')
        limit: Anzahl Ergebnisse (max 20)

    Returns:
        Dict mit 'results' Liste und 'total'
    """
    limit = min(limit, 20)

    # Sprach-Routing: explizit gesetzt → behalten, sonst auto-detektieren
    explicit_language = language is not None
    detected_language = _detect_language(query)
    effective_language = language if explicit_language else detected_language

    embedding = await embed_text(query)
    async with get_session() as session:
        raw = await queries.search_claims(
            session, embedding, query, domain,
            min_confidence, limit, language=effective_language
        )
        # Fallback: zu wenige Ergebnisse mit Sprachfilter → ohne Filter wiederholen
        language_fallback = False
        if not explicit_language and len(raw) < 2:
            raw = await queries.search_claims(
                session, embedding, query, domain,
                min_confidence, limit, language=None
            )
            language_fallback = True

    results = []
    for r in raw:
        result = {
            "claim": r["text"],
            "canonical_question": r.get("question") or None,
            "claim_id": r["id"],
            "confidence": r["confidence_score"],
            "effective_confidence": r.get("effective_confidence", r["confidence_score"]),
            "status": r["status"],
            "domain": r["domain_id"],
            "language": r["language"],
            "validated_by": r.get("validated_by", []),
            "last_reviewed": r.get("last_reviewed"),
            "source_references": r.get("source_references", []),
            "expires_at": r.get("expires_at"),
            "hash": r.get("hash_sha256"),
        }
        results.append(result)

    # Query-Analytics: fire-and-forget (blockiert nicht)
    if results:
        async def _track() -> None:
            async with get_session() as s:
                await queries.record_claim_queries(s, [r["claim_id"] for r in results])
        asyncio.create_task(_track())

    return {
        "query": query,
        "detected_language": detected_language,
        "language_fallback": language_fallback,
        "results": results,
        "total": len(results),
    }


async def get_claim(claim_id: str) -> dict[str, Any]:
    """
    Ruft einen einzelnen Claim mit voller Provenienz ab.

    Args:
        claim_id: UUID des Claims

    Returns:
        Vollständiger Claim mit Validierungs-Metadaten und Hash
    """
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id, only_live=True)

    if claim is None:
        return {"error": f"Claim '{claim_id}' nicht gefunden"}

    return {
        "claim": claim["text"],
        "canonical_question": claim.get("question") or None,
        "claim_id": claim["id"],
        "confidence": claim["confidence_score"],
        "effective_confidence": claim.get("effective_confidence", claim["confidence_score"]),
        "status": claim["status"],
        "domain": claim["domain_id"],
        "language": claim["language"],
        "validated_by": claim.get("validated_by", []),
        "last_reviewed": claim.get("last_reviewed"),
        "source_references": claim.get("source_references", []),
        "expires_at": claim.get("expires_at"),
        "hash": claim.get("hash_sha256"),
    }


async def list_domains() -> dict[str, Any]:
    """
    Listet alle verfügbaren Wissensdomänen mit Claim-Statistiken.

    Returns:
        Dict mit 'domains' Liste
    """
    async with get_session() as session:
        domains = await queries.list_domains(session)

    return {"domains": domains, "total": len(domains)}


async def submit_claim(
    claim_text: str,
    domain_id: str,
    source_urls: Optional[list[str]] = None,
    language: str = "de",
    question: Optional[str] = None,
) -> dict[str, Any]:
    """
    Reicht einen neuen Claim für Tier-1-Review ein.

    Args:
        claim_text: Die Aussage (atomar, sachlich, max 2000 Zeichen)
        domain_id: Domänen-ID (z.B. 'ai-ml')
        source_urls: Liste von Quellen-URLs (empfohlen)
        language: Sprachcode (default 'de')

    Returns:
        Submission-ID, Status und Vorprüfungsergebnis
    """
    source_urls = source_urls or []
    claim_id = str(uuid.uuid4())

    # Tier-1 Vorprüfung
    pre_screen = await pre_screen_claim(claim_text, domain_id, source_urls)

    # Embedding
    embedding = await embed_text(claim_text)

    claim_dict = {
        "id": claim_id,
        "text": claim_text,
        "question": question or "",
        "domain_id": domain_id,
        "confidence_score": 0.0,
        "status": "draft" if not pre_screen["passed"] else "peer_review",
        "language": language,
        "source_urls": source_urls,
        "created_at": now_iso(),
        "last_reviewed": None,
        "expires_at": None,
        "embedding": embedding,
    }
    claim_dict["hash_sha256"] = sign_claim(claim_dict)

    async with get_session() as session:
        conflicts = await detect_conflicts(session, embedding, claim_text)
        await queries.create_claim(session, claim_dict)

    return {
        "claim_id": claim_id,
        "status": claim_dict["status"],
        "pre_screen_passed": pre_screen["passed"],
        "issues": pre_screen.get("issues", []),
        "conflicts_found": len(conflicts),
        "message": (
            "Claim zur Peer-Review eingereicht." if pre_screen["passed"]
            else "Claim als Entwurf gespeichert. Bitte Probleme beheben und erneut einreichen."
        ),
    }


async def verify_claim(
    text: str,
    domain: Optional[str] = None,
    language: Optional[str] = None,
) -> dict[str, Any]:
    """
    Prüft eine Behauptung gegen die Swiss Truth Wissensbasis.
    Gibt zurück ob sie belegt, widerlegt oder unbekannt ist.
    """
    detected_language = language or _detect_language(text)
    embedding = await embed_text(text)

    async with get_session() as session:
        candidates = await queries.search_claims(
            session, embedding, text, domain,
            min_confidence=0.85, limit=5,
            language=detected_language,
        )
        # Fallback ohne Sprachfilter
        if len(candidates) < 2:
            candidates = await queries.search_claims(
                session, embedding, text, domain,
                min_confidence=0.85, limit=5,
                language=None,
            )

    if not candidates:
        return {
            "verdict": "unknown",
            "confidence": 0.0,
            "explanation": "No certified claims found on this topic.",
            "evidence": [],
            "checked_claim": text,
        }

    # Top-3 Kandidaten semantisch vergleichen
    evidence = []
    support_scores, contradict_scores = [], []

    for c in candidates[:3]:
        similarity = c.get("vector_score", 0.0)
        comparison = await compare_claims(submitted=text, certified=c["text"])
        relation = comparison.get("relation", "unrelated")
        conf = comparison.get("confidence", 0.5)

        if relation != "unrelated":
            evidence.append({
                "claim": c["text"],
                "claim_id": c["id"],
                "similarity": round(similarity, 3),
                "relation": relation,
                "comparison_confidence": conf,
                "source_references": c.get("source_references", []),
            })
        if relation == "supports":
            support_scores.append(conf * similarity)
        elif relation == "contradicts":
            contradict_scores.append(conf * similarity)

    # Verdict bestimmen
    if not evidence:
        verdict, confidence, explanation = "unknown", 0.0, "No sufficiently similar certified claims found."
    elif support_scores and (not contradict_scores or max(support_scores) > max(contradict_scores)):
        verdict = "supported"
        confidence = round(max(support_scores), 3)
        explanation = "Claim is consistent with certified knowledge."
    elif contradict_scores and (not support_scores or max(contradict_scores) >= max(support_scores)):
        verdict = "contradicted"
        confidence = round(max(contradict_scores), 3)
        explanation = "Claim conflicts with certified knowledge."
    else:
        verdict, confidence, explanation = "unknown", 0.0, "Mixed or inconclusive evidence."

    return {
        "verdict": verdict,
        "confidence": confidence,
        "explanation": explanation,
        "evidence": evidence,
        "checked_claim": text,
        "detected_language": detected_language,
    }


async def find_contradictions(
    claim_text: str,
    domain: Optional[str] = None,
) -> dict[str, Any]:
    """
    Sucht in der Wissensbasis nach zertifizierten Claims die der Behauptung widersprechen.
    Nützlich zur Qualitätsprüfung und als Safety-Check vor dem Publizieren von Fakten.

    Args:
        claim_text: Die zu prüfende Behauptung
        domain: Optionaler Domain-Filter

    Returns:
        Dict mit 'contradictions' (Liste der widersprechenden Claims) und 'total'
    """
    embedding = await embed_text(claim_text)

    async with get_session() as session:
        # Semantisch ähnliche Claims finden (niedrigerer Threshold = mehr Kandidaten)
        candidates = await queries.find_conflicting_claims(
            session, embedding, similarity_threshold=0.70
        )

    if not candidates:
        return {
            "contradictions": [],
            "total": 0,
            "checked_claim": claim_text,
            "message": "No similar claims found in the knowledge base.",
        }

    # Domain-Filter anwenden
    if domain:
        candidates = [c for c in candidates if c.get("domain_id") == domain]

    # Jeden Kandidaten semantisch vergleichen (parallel)
    async def _check(c: dict) -> Optional[dict]:
        comparison = await compare_claims(submitted=claim_text, certified=c["text"])
        if comparison.get("relation") == "contradicts":
            return {
                "certified_claim": c["text"],
                "claim_id": c["id"],
                "confidence_score": c.get("confidence_score", 0.0),
                "similarity": round(c.get("similarity", 0.0), 3),
                "contradiction_confidence": comparison.get("confidence", 0.0),
                "explanation": comparison.get("explanation", ""),
            }
        return None

    results = await asyncio.gather(*[_check(c) for c in candidates])
    contradictions = [r for r in results if r is not None]
    contradictions.sort(key=lambda x: x["contradiction_confidence"], reverse=True)

    return {
        "contradictions": contradictions,
        "total": len(contradictions),
        "checked_claim": claim_text,
        "candidates_checked": len(candidates),
        "message": (
            f"Found {len(contradictions)} contradiction(s) among {len(candidates)} similar claims."
            if contradictions else
            "No contradictions found. Claim is consistent with the knowledge base."
        ),
    }


async def verify_claims_batch(
    claims: list[str],
    domain: Optional[str] = None,
    language: Optional[str] = None,
) -> dict[str, Any]:
    """
    Prüft mehrere Claims parallel gegen die Swiss Truth Wissensbasis.

    Args:
        claims: Liste von Behauptungen (max 20)
        domain: Optionaler Domain-Filter für alle Claims
        language: Optionaler Sprachfilter

    Returns:
        Dict mit 'results' Liste (ein Eintrag pro Claim, gleiche Reihenfolge)
    """
    claims = claims[:20]  # Hard-Limit

    async def _verify_one(text: str, idx: int) -> dict[str, Any]:
        try:
            result = await verify_claim(text, domain=domain, language=language)
            return {"index": idx, "claim": text, **result}
        except Exception as e:
            return {
                "index": idx,
                "claim": text,
                "verdict": "unknown",
                "confidence": 0.0,
                "explanation": f"Verification error: {e}",
                "evidence": [],
            }

    tasks = [_verify_one(c, i) for i, c in enumerate(claims)]
    results = await asyncio.gather(*tasks)
    results = sorted(results, key=lambda r: r["index"])

    summary = {
        "supported": sum(1 for r in results if r["verdict"] == "supported"),
        "contradicted": sum(1 for r in results if r["verdict"] == "contradicted"),
        "unknown": sum(1 for r in results if r["verdict"] == "unknown"),
    }

    return {
        "results": results,
        "total": len(results),
        "summary": summary,
    }


_ATOMIZE_SYSTEM = """You are a fact extraction engine. Extract all atomic, verifiable factual claims from the given text.
Return ONLY valid JSON — an array of strings, each one a single atomic factual statement.
Rules:
- Each claim must be independently verifiable
- Remove opinions, predictions, and hedged statements ("I think...", "probably...")
- Split compound sentences into atomic claims
- Ignore greetings, transitions, and filler phrases
- Max 15 claims

Example output: ["The Eiffel Tower is 330 meters tall.", "It was built in 1889."]"""


async def verify_response(
    text: str,
    domain: Optional[str] = None,
) -> dict[str, Any]:
    """
    Prüft einen vollständigen Antwort-Paragraph auf Halluzinationen.
    Atomisiert den Text, verifiziert jeden Claim parallel, gibt Halluzinations-Score zurück.

    Args:
        text: Vollständiger Antwort-Text (Paragraph oder mehrere Sätze)
        domain: Optionaler Domain-Filter

    Returns:
        Dict mit hallucination_risk (low/medium/high), Statistiken und Details pro Statement
    """
    from swiss_truth_mcp.validation.pre_screen import _get_sdk_client as _get_client

    # Schritt 1: Atomisierung via Claude Haiku
    atomic_claims: list[str] = []
    try:
        client = _get_client()
        msg = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            system=_ATOMIZE_SYSTEM,
            messages=[{"role": "user", "content": text}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) >= 3 else parts[-1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        atomic_claims = json.loads(raw.strip())
        if not isinstance(atomic_claims, list):
            atomic_claims = []
    except Exception:
        # Fallback: Sätze nach Punkt splitten
        import re
        atomic_claims = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 20][:10]

    if not atomic_claims:
        return {
            "hallucination_risk": "unknown",
            "verified": 0,
            "unverified": 0,
            "contradicted": 0,
            "total_statements": 0,
            "statements": [],
            "original_text": text,
        }

    # Schritt 2: Alle Claims parallel verifizieren
    batch_result = await verify_claims_batch(atomic_claims, domain=domain)
    results = batch_result["results"]
    summary = batch_result["summary"]

    # Schritt 3: Halluzinations-Risiko berechnen
    total = len(results)
    contradicted = summary["contradicted"]
    unknown = summary["unknown"]
    supported = summary["supported"]

    if contradicted > 0:
        risk = "high"
    elif unknown / total > 0.6:
        risk = "medium"
    elif supported / total >= 0.5:
        risk = "low"
    else:
        risk = "medium"

    statements = [
        {
            "statement": r["claim"],
            "verdict": r["verdict"],
            "confidence": r["confidence"],
            "explanation": r.get("explanation", ""),
            "sources": [e["source_references"] for e in r.get("evidence", []) if e.get("source_references")],
        }
        for r in results
    ]

    return {
        "hallucination_risk": risk,
        "verified": supported,
        "unverified": unknown,
        "contradicted": contradicted,
        "total_statements": total,
        "coverage_rate": round(supported / total, 2) if total else 0.0,
        "statements": statements,
        "original_text": text,
    }


async def get_claim_status(claim_id: str) -> dict[str, Any]:
    """
    Prüft den Validierungsstatus eines eingereichten Claims.

    Args:
        claim_id: UUID des Claims

    Returns:
        Status, Konfidenz und nächste Schritte
    """
    async with get_session() as session:
        claim = await queries.get_claim_by_id(session, claim_id, only_live=False)

    if claim is None:
        return {"error": f"Claim '{claim_id}' nicht gefunden"}

    status_messages = {
        "draft": "Entwurf — noch nicht für Peer-Review freigegeben",
        "peer_review": "In Peer-Review — wartet auf Expertenvalidierung",
        "certified": "Zertifiziert — von Experten validiert und freigegeben",
        "needs_renewal": "Abgelaufen — Erneuerung durch Experten erforderlich",
    }

    return {
        "claim_id": claim_id,
        "status": claim["status"],
        "status_description": status_messages.get(claim["status"], "Unbekannt"),
        "confidence_score": claim["confidence_score"],
        "validators": len(claim.get("validated_by", [])),
        "created_at": claim.get("created_at"),
        "last_reviewed": claim.get("last_reviewed"),
    }
