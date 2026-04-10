"""
Konflikterkennung — findet bestehende Certified Claims die semantisch sehr ähnlich
sind und möglicherweise widersprechen.
"""
from neo4j import AsyncSession

from swiss_truth_mcp.db.queries import find_conflicting_claims

# Threshold ab dem wir von potenziellem Konflikt/Duplikat ausgehen
CONFLICT_THRESHOLD = 0.93


async def detect_conflicts(
    session: AsyncSession,
    embedding: list[float],
    claim_text: str,
) -> list[dict]:
    """
    Gibt eine Liste potenziell konfliktierender Claims zurück.
    Similarity >= CONFLICT_THRESHOLD bedeutet: sehr ähnliche Aussage bereits vorhanden.
    """
    candidates = await find_conflicting_claims(session, embedding, CONFLICT_THRESHOLD)
    return candidates
