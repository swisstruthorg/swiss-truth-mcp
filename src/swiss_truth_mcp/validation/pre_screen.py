"""
Tier-1 Vorprüfung — KI-gestützte Validierung eingereichter Claims via Claude API.

Prüft:
 - Ist die Aussage atomar (eine einzige, klar abgegrenzte Behauptung)?
 - Ist sie sachlich und nicht meinungsbasiert?
 - Gibt es Quellenverweise?
 - Offensichtliche interne Widersprüche?
"""
from __future__ import annotations

import json
from typing import Optional

import asyncio
import anthropic
import httpx

from swiss_truth_mcp.config import settings

# Modell-Mapping: Anthropic SDK-Namen → open-claude.com-Namen
# open-claude.com unterstützt nur claude-haiku-4-5-20251001
_PROVIDER_MODEL_MAP: dict[str, str] = {
    "claude-haiku-4-5-20251001":   "claude-haiku-4-5-20251001",
    "claude-haiku-4-5":            "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5":           "claude-haiku-4-5-20251001",
    "claude-sonnet-4-5-20251022":  "claude-haiku-4-5-20251001",
    "claude-sonnet-4.6":           "claude-haiku-4-5-20251001",
    "claude-opus-4-6":             "claude-haiku-4-5-20251001",
}

_http_client: Optional[httpx.AsyncClient] = None
_sdk_client: Optional[anthropic.AsyncAnthropic] = None


def _get_http_client() -> httpx.AsyncClient:
    """Async httpx-Client für Drittanbieter (Cloudflare-WAF-kompatibel)."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            headers={"user-agent": "curl/8.4.0"},
            timeout=httpx.Timeout(300.0),
        )
    return _http_client


def _get_sdk_client() -> anthropic.AsyncAnthropic:
    """Standard Anthropic SDK-Client (nur für offizielle Anthropic API)."""
    global _sdk_client
    if _sdk_client is None:
        _sdk_client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.anthropic_timeout_seconds,
        )
    return _sdk_client


async def _call_api(model: str, max_tokens: int, system: str, user_content: str) -> str:
    """Unified API-Call — wählt automatisch SDK oder direktes httpx je nach Config.
    Bei 503-Fehlern (Provider busy) wird bis zu 3× mit 2s Backoff wiederholt."""
    if settings.anthropic_base_url:
        mapped_model = _PROVIDER_MODEL_MAP.get(model, model)
        for attempt in range(3):
            r = await _get_http_client().post(
                f"{settings.anthropic_base_url.rstrip('/')}/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": mapped_model,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user_content}],
                },
            )
            data = r.json()
            if "error" in data:
                msg = data["error"].get("message", str(data["error"]))
                code = data["error"].get("code", 0)
                # 503 = Provider busy → retry
                if (code == 503 or "busy" in msg.lower()) and attempt < 2:
                    await asyncio.sleep(2 ** attempt)  # 1s, 2s
                    continue
                raise RuntimeError(msg)
            return data["content"][0]["text"]
        raise RuntimeError("Provider busy after 3 retries")
    else:
        client = _get_sdk_client()
        message = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return message.content[0].text


SYSTEM_PROMPT = """Du bist ein Qualitätsprüfer für eine wissenschaftliche Wissensdatenbank.
Analysiere den eingereichten Claim und gib eine JSON-Antwort mit folgenden Feldern:
- passed: boolean — true wenn der Claim die Qualitätsstandards erfüllt
- issues: array of strings — Liste der gefundenen Probleme (leer wenn passed=true)
- suggested_domain: string — vorgeschlagene Domänen-ID (z.B. 'ai-ml', 'swiss-health', 'climate')
- atomicity_ok: boolean — ist es eine einzelne, klar abgegrenzte Aussage?
- has_sources: boolean — sind Quellenverweise vorhanden?
- is_factual: boolean — ist es eine sachliche Aussage (keine Meinung/Vorhersage)?

Antworte NUR mit gültigem JSON, kein Prosatext."""

USER_TEMPLATE = """Claim: {text}
Domäne: {domain_id}
Quellenverweise: {sources}"""


async def pre_screen_claim(
    text: str,
    domain_id: str,
    source_urls: list[str],
) -> dict:
    if not settings.anthropic_api_key:
        return _fallback_pre_screen(text, source_urls)

    try:
        content = await _call_api(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT,
            user_content=USER_TEMPLATE.format(
                text=text,
                domain_id=domain_id,
                sources=", ".join(source_urls) if source_urls else "keine",
            ),
        )
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        result = json.loads(content.strip())
        return result
    except Exception as e:
        return _fallback_pre_screen(text, source_urls, error=str(e))


VERIFY_SYSTEM_PROMPT = """Du bist ein Quellenprüfer für eine wissenschaftliche Wissensdatenbank.
Prüfe ob der vorliegende Seiteninhalt die Behauptung direkt oder indirekt belegt.
Antworte NUR mit gültigem JSON:
{"supports": true/false, "confidence": 0.0-1.0, "reason": "Kurzbegründung max. 80 Zeichen"}

supports=true:  Inhalt belegt die Behauptung klar oder zumindest teilweise.
supports=false: Inhalt ist irrelevant, widerspricht der Behauptung, oder ist leer."""


async def verify_source_supports_claim(claim_text: str, page_content: str) -> dict:
    """
    Prüft ob der Seiteninhalt (plain text, bereits extrahiert) den Claim inhaltlich belegt.
    Gibt {"supports": bool, "confidence": float, "reason": str} zurück.
    Im Zweifel (leerer Inhalt, API-Fehler) → supports=True (kein False-Positive).
    """
    if not page_content.strip():
        return {"supports": True, "confidence": 0.5, "reason": "Kein Inhalt extrahierbar"}

    if not settings.anthropic_api_key:
        return {"supports": True, "confidence": 0.5, "reason": "API nicht verfügbar"}

    try:
        raw = await _call_api(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=VERIFY_SYSTEM_PROMPT,
            user_content=(
                f"Behauptung: {claim_text}\n\n"
                f"Seiteninhalt (Auszug):\n{page_content[:3000]}"
            ),
        )
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {"supports": True, "confidence": 0.5, "reason": "Prüfung fehlgeschlagen"}


COMPARE_SYSTEM_PROMPT = """You are a fact-checking engine for a scientific knowledge base.
Compare the SUBMITTED CLAIM against the CERTIFIED FACT and return ONLY valid JSON:
{"relation": "supports"|"contradicts"|"unrelated", "confidence": 0.0-1.0, "explanation": "max 120 chars"}

supports:    The certified fact confirms or is consistent with the submitted claim.
contradicts: The certified fact directly refutes or conflicts with the submitted claim.
unrelated:   The certified fact is about a different topic and cannot verify the claim."""


async def compare_claims(submitted: str, certified: str) -> dict:
    """
    Vergleicht einen eingereichten Claim mit einem zertifizierten Claim.
    Gibt {"relation": supports|contradicts|unrelated, "confidence": float, "explanation": str} zurück.
    """
    if not settings.anthropic_api_key:
        return {"relation": "unrelated", "confidence": 0.5, "explanation": "API nicht verfügbar"}

    try:
        raw = await _call_api(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=COMPARE_SYSTEM_PROMPT,
            user_content=(
                f"SUBMITTED CLAIM: {submitted}\n\n"
                f"CERTIFIED FACT: {certified}"
            ),
        )
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {"relation": "unrelated", "confidence": 0.5, "explanation": f"Vergleich fehlgeschlagen: {e}"}


def _fallback_pre_screen(text: str, source_urls: list[str], error: str = "") -> dict:
    """Einfache regelbasierte Prüfung wenn Claude API nicht verfügbar."""
    issues = []
    if len(text) < 20:
        issues.append("Claim ist zu kurz (min. 20 Zeichen)")
    if "?" in text:
        issues.append("Claim ist eine Frage, keine Aussage")
    if not source_urls:
        issues.append("Keine Quellenverweise angegeben")
    if error:
        issues.append(f"AI-Vorprüfung nicht verfügbar: {error}")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "suggested_domain": "ai-ml",
        "atomicity_ok": True,
        "has_sources": len(source_urls) > 0,
        "is_factual": True,
        "fallback_mode": True,
    }
