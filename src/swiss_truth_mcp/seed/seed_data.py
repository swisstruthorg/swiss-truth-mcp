"""
Seed-Script: Lädt initiale KI/ML-Claims in Neo4j.

Ausführen: python -m swiss_truth_mcp.seed.seed_data
"""
import asyncio
import json
import uuid
from pathlib import Path

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session, close_driver
from swiss_truth_mcp.db import queries, schema
from swiss_truth_mcp.embeddings import embed_texts
from swiss_truth_mcp.validation.trust import sign_claim, now_iso, expiry_iso

SEED_FILE = Path(__file__).parent / "ai_ml_claims.json"


async def seed() -> None:
    print("Initialisiere Schema...")
    async with get_session() as session:
        await schema.setup_schema(session)

    raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    print(f"Berechne Embeddings für {len(raw)} Claims...")

    texts = [r["text"] for r in raw]
    embeddings = await embed_texts(texts)

    now = now_iso()
    expires = expiry_iso(settings.default_ttl_days)

    print("Schreibe Claims in Neo4j...")
    async with get_session() as session:
        for raw_claim, embedding in zip(raw, embeddings):
            claim_id = str(uuid.uuid4())
            claim_dict = {
                "id": claim_id,
                "text": raw_claim["text"],
                "domain_id": raw_claim["domain_id"],
                "confidence_score": raw_claim["confidence_score"],
                "status": "certified",
                "language": raw_claim.get("language", "de"),
                "source_urls": raw_claim.get("source_urls", []),
                "created_at": now,
                "last_reviewed": now,
                "expires_at": expires,
                "embedding": embedding,
            }
            claim_dict["hash_sha256"] = sign_claim(claim_dict)

            await queries.create_claim(session, claim_dict)

            # Experten-Nodes erstellen und verknüpfen
            for validator in raw_claim.get("validators", []):
                expert_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, validator["name"]))
                await session.run(
                    """
                    MERGE (e:Expert {id: $id})
                    SET e.name = $name, e.institution = $institution, e.credential_verified = true
                    WITH e
                    MATCH (c:Claim {id: $claim_id})
                    MERGE (e)-[:VALIDATES {timestamp: $ts, verdict: 'approved'}]->(c)
                    """,
                    {
                        "id": expert_id,
                        "name": validator["name"],
                        "institution": validator.get("institution", ""),
                        "claim_id": claim_id,
                        "ts": now,
                    },
                )

    print(f"Seed abgeschlossen: {len(raw)} Claims importiert.")
    await close_driver()


if __name__ == "__main__":
    asyncio.run(seed())
