"""
Sets up Neo4j constraints, indexes, and seed domains.
Run once on first start via: python -m swiss_truth_mcp.db.schema
"""
import asyncio

from neo4j import AsyncSession

from swiss_truth_mcp.db.neo4j_client import get_session, close_driver

CONSTRAINTS = [
    "CREATE CONSTRAINT claim_id    IF NOT EXISTS FOR (c:Claim)               REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT expert_id   IF NOT EXISTS FOR (e:Expert)              REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT domain_id   IF NOT EXISTS FOR (d:Domain)              REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT source_id   IF NOT EXISTS FOR (s:Source)              REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT webhook_id  IF NOT EXISTS FOR (w:WebhookSubscription) REQUIRE w.id IS UNIQUE",
]

FULLTEXT_INDEX = """
CREATE FULLTEXT INDEX claim_text_index IF NOT EXISTS
FOR (c:Claim) ON EACH [c.text]
OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words'}}
"""

FULLTEXT_INDEX_QUESTION = """
CREATE FULLTEXT INDEX claim_question_index IF NOT EXISTS
FOR (c:Claim) ON EACH [c.question]
OPTIONS {indexConfig: {`fulltext.analyzer`: 'standard-no-stop-words'}}
"""

VECTOR_INDEX = """
CREATE VECTOR INDEX claim_embedding_index IF NOT EXISTS
FOR (c:Claim) ON (c.embedding)
OPTIONS {indexConfig: {
  `vector.dimensions`: 384,
  `vector.similarity_function`: 'cosine'
}}
"""

SEED_DOMAINS = [
    {"id": "ai-ml",        "name": "AI/ML",                       "description": "Definitionen, Konzepte und Fakten zu Künstlicher Intelligenz und Machine Learning", "language": "de"},
    {"id": "swiss-health", "name": "Schweizer Gesundheitswesen",   "description": "Medizinische Leitlinien und Fakten mit Schweizer Bezug", "language": "de"},
    {"id": "climate",      "name": "Klimawissenschaft",            "description": "Wissenschaftlicher Konsens zu Klima und Umwelt", "language": "de"},
    {"id": "swiss-law",        "name": "Schweizer Recht",          "description": "Gesetze, Rechtsgrundsätze und Institutionen des Schweizer Rechtssystems", "language": "de"},
    {"id": "swiss-finance",    "name": "Schweizer Finanzmarkt",    "description": "Finanzplatz Schweiz, SNB, Banken, Börse und Regulierung", "language": "de"},
    {"id": "swiss-education",  "name": "Schweizer Bildung",        "description": "Bildungsstruktur, Hochschulen und Berufsbildung der Schweiz", "language": "de"},
    {"id": "swiss-energy",     "name": "Schweizer Energie",        "description": "Energieproduktion, Kernkraft, Wasserkraft und Energiestrategie der Schweiz", "language": "de"},
    {"id": "swiss-transport",  "name": "Schweizer Verkehr",        "description": "Bahn, Strasse, Luftfahrt und öffentlicher Verkehr in der Schweiz", "language": "de"},
    {"id": "swiss-politics",   "name": "Schweizer Politik",        "description": "Politisches System, Bundesrat, Parlament und direkte Demokratie", "language": "de"},
    {"id": "swiss-agriculture","name": "Schweizer Landwirtschaft", "description": "Landwirtschaft, Lebensmittelproduktion und Agrarpolitik der Schweiz", "language": "de"},
    {"id": "world-science",    "name": "Naturwissenschaften",      "description": "Grundlagen der Physik, Chemie, Biologie und Mathematik", "language": "de"},
    {"id": "world-history",    "name": "Weltgeschichte",           "description": "Wichtige historische Ereignisse und Entwicklungen der Weltgeschichte", "language": "de"},
    {"id": "eu-law",           "name": "EU Law & Regulation",      "description": "European Union legislation, GDPR, AI Act, Digital Markets Act, and EU court rulings", "language": "en"},
    {"id": "eu-health",        "name": "EU & Global Health",        "description": "European Medicines Agency, WHO guidelines, EU health policy, and global epidemiology", "language": "en"},
    {"id": "global-science",   "name": "Global Science",            "description": "Peer-reviewed scientific findings across medicine, biology, physics, and interdisciplinary research", "language": "en"},
]


async def setup_schema(session: AsyncSession) -> None:
    for constraint in CONSTRAINTS:
        await session.run(constraint)

    await session.run(FULLTEXT_INDEX)
    await session.run(FULLTEXT_INDEX_QUESTION)
    await session.run(VECTOR_INDEX)

    for domain in SEED_DOMAINS:
        await session.run(
            """
            MERGE (d:Domain {id: $id})
            SET d.name = $name, d.description = $description, d.language = $language
            """,
            domain,
        )

    print("Schema setup complete.")


async def main() -> None:
    async with get_session() as session:
        await setup_schema(session)
    await close_driver()


if __name__ == "__main__":
    asyncio.run(main())
