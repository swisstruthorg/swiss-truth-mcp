"""
swiss-truth-expire — Expiry-Checker CLI

Scannt alle certified Claims, setzt abgelaufene auf 'needs_renewal'
und sendet Webhook-Events an n8n (falls N8N_WEBHOOK_URL konfiguriert).

Ausführung:
  swiss-truth-expire              # scharf
  swiss-truth-expire --dry-run    # nur anzeigen, nichts ändern
  swiss-truth-expire --seed-demo  # 5 Demo-Claims mit vergangenem Ablaufdatum anlegen
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from swiss_truth_mcp.db.neo4j_client import get_driver, close_driver
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.embeddings import embed_text
from swiss_truth_mcp.integrations.webhook import fire_event
from swiss_truth_mcp.validation.trust import sign_claim, now_iso


# ---------------------------------------------------------------------------
# Demo-Claims für Tests (bereits abgelaufen)
# ---------------------------------------------------------------------------

DEMO_EXPIRED = [
    {
        "text": "BERT verwendet bidirektionale Transformer und wurde 2018 von Google veröffentlicht. Es war das erste grosse Vortrainierte Modell das NLP-Benchmarks dominierte.",
        "domain_id": "ai-ml", "language": "de", "confidence_score": 0.96,
        "source_urls": ["https://arxiv.org/abs/1810.04805"],
        "expires_days_ago": 45,
    },
    {
        "text": "Word2Vec ist ein flaches neuronales Netz das Wörter als dichte Vektoren repräsentiert, entwickelt von Mikolov et al. bei Google im Jahr 2013.",
        "domain_id": "ai-ml", "language": "de", "confidence_score": 0.93,
        "source_urls": ["https://arxiv.org/abs/1301.3781"],
        "expires_days_ago": 12,
    },
    {
        "text": "Apache Spark MLlib ist die Machine-Learning-Bibliothek von Apache Spark und unterstützt Algorithmen für Klassifikation, Regression, Clustering und kollaboratives Filtern.",
        "domain_id": "ai-ml", "language": "de", "confidence_score": 0.91,
        "source_urls": ["https://spark.apache.org/mllib/"],
        "expires_days_ago": 90,
    },
    {
        "text": "Der Softmax-Funktion wird in neuronalen Netzen verwendet, um rohe Ausgabewerte (Logits) in eine Wahrscheinlichkeitsverteilung über Klassen umzuwandeln.",
        "domain_id": "ai-ml", "language": "de", "confidence_score": 0.97,
        "source_urls": ["https://en.wikipedia.org/wiki/Softmax_function"],
        "expires_days_ago": 5,
    },
    {
        "text": "Batch-Normalisierung ist eine Technik, die die Eingaben jeder Schicht in einem neuronalen Netz normalisiert, um das Training zu stabilisieren und zu beschleunigen.",
        "domain_id": "ai-ml", "language": "de", "confidence_score": 0.95,
        "source_urls": ["https://arxiv.org/abs/1502.03167"],
        "expires_days_ago": 2,
    },
]


async def _seed_demo(session) -> int:
    """Legt 5 Demo-Claims mit abgelaufenem expires_at an."""
    count = 0
    for raw in DEMO_EXPIRED:
        # Idempotenz
        r = await session.run(
            "MATCH (c:Claim {text: $text}) RETURN count(c) AS n", {"text": raw["text"]}
        )
        row = await r.single()
        if row["n"] > 0:
            print(f"  ⏭  Übersprungen (existiert): {raw['text'][:55]}…")
            continue

        now = datetime.now(timezone.utc)
        created_at = (now - timedelta(days=raw["expires_days_ago"] + 400)).isoformat()
        expires_at = (now - timedelta(days=raw["expires_days_ago"])).isoformat()
        embedding  = await embed_text(raw["text"])

        claim: dict = {
            "id":               str(uuid.uuid4()),
            "text":             raw["text"],
            "domain_id":        raw["domain_id"],
            "confidence_score": raw["confidence_score"],
            "status":           "certified",
            "language":         raw["language"],
            "hash_sha256":      "",
            "created_at":       created_at,
            "last_reviewed":    created_at,
            "expires_at":       expires_at,
            "embedding":        embedding,
            "source_urls":      raw["source_urls"],
        }
        claim["hash_sha256"] = sign_claim(claim)
        await queries.create_claim(session, claim)

        # Expert anlegen
        await queries.validate_claim(
            session,
            claim_id=claim["id"],
            expert_name="Swiss Truth Seed Curator",
            expert_institution="Swiss Truth Foundation",
            verdict="approved",
            confidence_score=raw["confidence_score"],
            reviewed_at=created_at,
        )
        days = raw["expires_days_ago"]
        print(f"  ✅ Demo-Claim (abgelaufen vor {days}d): {raw['text'][:55]}…")
        count += 1
    return count


# ---------------------------------------------------------------------------
# Expiry-Check
# ---------------------------------------------------------------------------

async def _run(dry_run: bool = False, seed_demo: bool = False) -> None:
    print("🕐  Swiss Truth Expiry Checker")
    print("=" * 55)

    driver = get_driver()

    if seed_demo:
        print("🌱  Demo-Claims mit abgelaufenem Datum anlegen…\n")
        async with driver.session() as session:
            n = await _seed_demo(session)
        print(f"\n  {n} Demo-Claim(s) angelegt.\n")
        print("=" * 55)

    now = now_iso()
    print(f"📅  Prüfung zum Zeitpunkt: {now[:19]} UTC\n")

    if dry_run:
        # Nur anzeigen
        async with driver.session() as session:
            r = await session.run(
                """
                MATCH (c:Claim {status: 'certified'})
                WHERE c.expires_at IS NOT NULL AND c.expires_at < $now
                RETURN c.id AS id, c.text AS text,
                       c.expires_at AS exp, c.domain_id AS domain
                ORDER BY c.expires_at ASC
                """,
                {"now": now},
            )
            rows = await r.data()

        if not rows:
            print("✅  Keine abgelaufenen Claims gefunden.")
        else:
            print(f"⚠️   {len(rows)} Claim(s) würden auf 'needs_renewal' gesetzt:\n")
            for c in rows:
                print(f"  [{c['domain']}] abgelaufen: {c['exp'][:10]} — {c['text'][:60]}…")
        print("\n🔍  Dry-run — keine Änderungen.")
    else:
        # Scharf schalten
        async with driver.session() as session:
            expired = await queries.expire_outdated_claims(session, now)

        if not expired:
            print("✅  Keine neuen abgelaufenen Claims.")
        else:
            print(f"🔄  {len(expired)} Claim(s) auf 'needs_renewal' gesetzt:\n")
            for c in expired:
                print(f"  [{c['domain_id']}] {c['text'][:60]}…")

            # Webhook-Events feuern
            for c in expired:
                await fire_event("claim.expired", {
                    "claim_id":        c["id"],
                    "domain_id":       c["domain_id"],
                    "text":            c["text"][:200],
                    "expired_at":      c["expires_at"],
                    "renewal_url":     f"http://127.0.0.1:8001/review/renewal",
                })

        # Zusammenfassung: wie viele brauchen noch Renewal?
        async with driver.session() as session:
            r = await session.run(
                "MATCH (c:Claim {status: 'needs_renewal'}) RETURN count(c) AS n"
            )
            row = await r.single()
            total_renewal = row["n"]

        print()
        print("=" * 55)
        print(f"🔄  Neu abgelaufen:      {len(expired):>3} Claims")
        print(f"⏳  Total needs_renewal: {total_renewal:>3} Claims")
        print()
        print(f"→  Renewal Queue: http://127.0.0.1:8001/review/renewal")

    await close_driver()


def main() -> None:
    dry_run   = "--dry-run"   in sys.argv
    seed_demo = "--seed-demo" in sys.argv
    asyncio.run(_run(dry_run=dry_run, seed_demo=seed_demo))


if __name__ == "__main__":
    main()
