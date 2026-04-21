"""
Multi-Language Claim Translation (Plan 03-03)

Translates existing certified claims into FR, IT, ES, ZH using Claude.
Preserves source URLs and adjusts confidence slightly.

Usage:
    python -m swiss_truth_mcp.seed.multilang --domain swiss-health --lang fr --count 20
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from swiss_truth_mcp.config import settings

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).parent

SUPPORTED_LANGS = {"fr": "French", "it": "Italian", "es": "Spanish", "zh": "Chinese"}

_TRANSLATE_SYSTEM = """You are a precise multilingual translator for a certified knowledge base.
Translate the given factual claims from {source_lang} to {target_lang}.

RULES:
- Preserve the factual accuracy — do NOT change any numbers, dates, or proper nouns
- Keep the same atomic structure (one fact per claim)
- Translate both "question" and "text" fields
- Keep source_urls unchanged (they are primary sources in the original language)
- Adjust confidence by -0.01 (translation introduces minimal uncertainty)
- Return ONLY valid JSON array

Example input:
[{{"question": "How does Swiss health insurance work?", "text": "Health insurance is mandatory in Switzerland under the KVG.", "source_urls": ["https://bag.admin.ch/..."], "confidence": 0.97}}]

Example output (for French):
[{{"question": "Comment fonctionne l'assurance maladie suisse?", "text": "L'assurance maladie est obligatoire en Suisse en vertu de la LAMal.", "source_urls": ["https://bag.admin.ch/..."], "confidence": 0.96}}]"""


async def translate_claims(
    claims: list[dict],
    target_lang: str,
    source_lang: str = "de",
    batch_size: int = 5,
) -> list[dict]:
    """Translate a batch of claims to the target language using Claude."""
    from swiss_truth_mcp.validation.pre_screen import _get_sdk_client

    if target_lang not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported language: {target_lang}. Supported: {list(SUPPORTED_LANGS.keys())}")

    client = _get_sdk_client()
    translated = []
    lang_names = {"de": "German", "en": "English", "fr": "French", "it": "Italian"}
    source_name = lang_names.get(source_lang, source_lang)
    target_name = SUPPORTED_LANGS[target_lang]

    system = _TRANSLATE_SYSTEM.format(source_lang=source_name, target_lang=target_name)

    for i in range(0, len(claims), batch_size):
        batch = claims[i:i + batch_size]
        batch_input = [
            {
                "question": c.get("question", ""),
                "text": c.get("text", ""),
                "source_urls": c.get("source_urls", [])[:2],
                "confidence": c.get("confidence_score", c.get("confidence", 0.95)),
            }
            for c in batch
        ]

        try:
            msg = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": json.dumps(batch_input, ensure_ascii=False)}],
            )

            raw = msg.content[0].text.strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) >= 3 else parts[-1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            result = json.loads(raw)
            if isinstance(result, list):
                for item in result:
                    item["language"] = target_lang
                translated.extend(result)
                print(f"  ✓ Translated batch {i//batch_size + 1}: {len(result)} claims → {target_lang}")
        except Exception as e:
            logger.error("Translation batch %d failed: %s", i // batch_size + 1, e)
            print(f"  ✗ Batch {i//batch_size + 1} failed: {e}")

    return translated


async def translate_domain(
    domain_id: str,
    target_lang: str,
    count: int = 20,
    save: bool = True,
) -> list[dict]:
    """
    Translate certified claims from a domain into a target language.

    Args:
        domain_id: Source domain ID
        target_lang: Target language code (fr, it, es, zh)
        count: Max claims to translate
        save: If True, save to JSON file

    Returns:
        List of translated claims
    """
    from swiss_truth_mcp.db.neo4j_client import get_session
    from swiss_truth_mcp.db import queries

    # Fetch certified claims
    async with get_session() as session:
        claims = await queries.get_certified_claims_by_domain(session, domain_id)

    if not claims:
        print(f"No certified claims found for domain '{domain_id}'")
        return []

    # Take up to `count` claims
    source_claims = claims[:count]
    source_lang = source_claims[0].get("language", "de") if source_claims else "de"

    print(f"Translating {len(source_claims)} claims from {domain_id} ({source_lang} → {target_lang})...")

    translated = await translate_claims(source_claims, target_lang, source_lang)

    if save and translated:
        filename = f"{domain_id.replace('-', '_')}_claims_{target_lang}.json"
        filepath = SEED_DIR / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(translated, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(translated)} translated claims to {filepath}")

    return translated


def main():
    """CLI entry point for multi-language generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Translate Swiss Truth claims to other languages")
    parser.add_argument("--domain", required=True, help="Domain ID (e.g. swiss-health)")
    parser.add_argument("--lang", required=True, choices=list(SUPPORTED_LANGS.keys()), help="Target language")
    parser.add_argument("--count", type=int, default=20, help="Max claims to translate")
    parser.add_argument("--no-save", action="store_true", help="Don't save to file")
    args = parser.parse_args()

    result = asyncio.run(translate_domain(args.domain, args.lang, args.count, save=not args.no_save))
    print(f"\nDone: {len(result)} claims translated to {SUPPORTED_LANGS[args.lang]}")


if __name__ == "__main__":
    main()
