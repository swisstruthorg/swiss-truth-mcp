"""
Cypher query library — all DB operations go through here.
"""
from __future__ import annotations

from typing import Any, Optional

from neo4j import AsyncSession

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.validation.trust import decay_confidence


def _with_decay(claim: dict) -> dict:
    """Fügt effective_confidence (alterskorrigiert) zum Claim-Dict hinzu."""
    base = claim.get("confidence_score", 0.0)
    reviewed = claim.get("last_reviewed")
    claim["effective_confidence"] = decay_confidence(base, reviewed)
    return claim


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_claims(
    session: AsyncSession,
    query_embedding: list[float],
    query_text: str,
    domain_id: Optional[str],
    min_confidence: float,
    limit: int = 10,
    language: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Hybrid search: vector similarity + fulltext, filtered by status + confidence."""
    domain_filter   = "AND c.domain_id = $domain_id" if domain_id else ""
    language_filter = "AND c.language = $language"   if language  else ""

    # Vector search via Neo4j Vector Index
    cypher = f"""
    CALL db.index.vector.queryNodes('claim_embedding_index', $limit, $embedding)
    YIELD node AS c, score AS vector_score
    WHERE c.status = 'certified'
      AND c.confidence_score >= $min_confidence
      {domain_filter}
      {language_filter}
    OPTIONAL MATCH (e:Expert)-[v:VALIDATES]->(c)
    OPTIONAL MATCH (c)-[:REFERENCES]->(s:Source)
    WITH c, vector_score,
         collect(DISTINCT {{name: e.name, institution: e.institution}}) AS validators,
         collect(DISTINCT s.url) AS sources
    RETURN c {{
        .id, .text, .question, .domain_id, .confidence_score, .status,
        .language, .hash_sha256, .created_at, .last_reviewed, .expires_at
    }} AS claim,
    validators,
    sources,
    vector_score
    ORDER BY vector_score DESC
    LIMIT $limit
    """
    params: dict[str, Any] = {
        "embedding": query_embedding,
        "min_confidence": min_confidence,
        "limit": limit,
    }
    if domain_id:
        params["domain_id"] = domain_id
    if language:
        params["language"] = language

    result = await session.run(cypher, params)
    rows = await result.data()
    return [
        _with_decay({**row["claim"], "validated_by": row["validators"], "source_references": row["sources"], "vector_score": row["vector_score"]})
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Get single claim
# ---------------------------------------------------------------------------

async def get_claim_by_id(session: AsyncSession, claim_id: str) -> Optional[dict[str, Any]]:
    result = await session.run(
        """
        MATCH (c:Claim {id: $id})
        OPTIONAL MATCH (e:Expert)-[:VALIDATES]->(c)
        OPTIONAL MATCH (c)-[:REFERENCES]->(s:Source)
        WITH c,
             collect(DISTINCT {name: e.name, institution: e.institution}) AS validators,
             collect(DISTINCT s.url) AS sources
        RETURN c {
            .id, .text, .question, .domain_id, .confidence_score, .status,
            .language, .hash_sha256, .created_at, .last_reviewed, .expires_at
        } AS claim, validators, sources
        """,
        {"id": claim_id},
    )
    row = await result.single()
    if row is None:
        return None
    return _with_decay({**row["claim"], "validated_by": row["validators"], "source_references": row["sources"]})


# ---------------------------------------------------------------------------
# Create claim
# ---------------------------------------------------------------------------

async def create_claim(session: AsyncSession, claim: dict[str, Any]) -> dict[str, Any]:
    await session.run(
        """
        CREATE (c:Claim {
            id: $id,
            text: $text,
            question: $question,
            domain_id: $domain_id,
            confidence_score: $confidence_score,
            status: $status,
            language: $language,
            hash_sha256: $hash_sha256,
            created_at: $created_at,
            last_reviewed: $last_reviewed,
            expires_at: $expires_at,
            embedding: $embedding
        })
        WITH c
        MATCH (d:Domain {id: $domain_id})
        MERGE (c)-[:BELONGS_TO]->(d)
        """,
        claim,
    )
    for url in claim.get("source_urls", []):
        await session.run(
            """
            MERGE (s:Source {url: $url})
            ON CREATE SET s.id = randomUUID()
            WITH s
            MATCH (c:Claim {id: $claim_id})
            MERGE (c)-[:REFERENCES]->(s)
            """,
            {"url": url, "claim_id": claim["id"]},
        )
    return claim


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------

async def list_domains(session: AsyncSession) -> list[dict[str, Any]]:
    result = await session.run(
        """
        MATCH (d:Domain)
        OPTIONAL MATCH (c:Claim {status: 'certified'})-[:BELONGS_TO]->(d)
        RETURN d {.id, .name, .description, .language} AS domain, count(c) AS certified_count
        ORDER BY domain.name
        """
    )
    rows = await result.data()
    return [{**row["domain"], "certified_claims": row["certified_count"]} for row in rows]


# ---------------------------------------------------------------------------
# Conflict detection helper
# ---------------------------------------------------------------------------

async def find_conflicting_claims(
    session: AsyncSession, query_embedding: list[float], similarity_threshold: float = 0.92
) -> list[dict[str, Any]]:
    """Find certified claims that are semantically very similar (potential conflicts)."""
    result = await session.run(
        """
        CALL db.index.vector.queryNodes('claim_embedding_index', 5, $embedding)
        YIELD node AS c, score
        WHERE score >= $threshold AND c.status = 'certified'
        RETURN c {.id, .text, .confidence_score} AS claim, score
        """,
        {"embedding": query_embedding, "threshold": similarity_threshold},
    )
    rows = await result.data()
    return [{**row["claim"], "similarity": row["score"]} for row in rows]


# ---------------------------------------------------------------------------
# Update claim status (for validation workflow)
# ---------------------------------------------------------------------------

async def update_claim_status(
    session: AsyncSession, claim_id: str, status: str, confidence_score: Optional[float] = None
) -> None:
    params: dict[str, Any] = {"id": claim_id, "status": status}
    confidence_set = ", c.confidence_score = $confidence_score" if confidence_score is not None else ""
    if confidence_score is not None:
        params["confidence_score"] = confidence_score
    await session.run(
        f"MATCH (c:Claim {{id: $id}}) SET c.status = $status{confidence_set}",
        params,
    )


# ---------------------------------------------------------------------------
# Review workflow
# ---------------------------------------------------------------------------

async def count_claims_by_status(session: AsyncSession, status: str) -> int:
    result = await session.run(
        "MATCH (c:Claim {status: $status}) RETURN count(c) AS n",
        {"status": status},
    )
    row = await result.single()
    return row["n"] if row else 0


async def list_claims_by_status(
    session: AsyncSession, status: str, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    result = await session.run(
        """
        MATCH (c:Claim {status: $status})
        OPTIONAL MATCH (c)-[:BELONGS_TO]->(d:Domain)
        OPTIONAL MATCH (c)-[:REFERENCES]->(s:Source)
        OPTIONAL MATCH (e:Expert)-[:VALIDATES]->(c)
        WITH c, d,
             collect(DISTINCT s.url) AS sources,
             collect(DISTINCT {name: e.name, institution: e.institution}) AS validators
        RETURN c {
            .id, .text, .question, .domain_id, .confidence_score, .status,
            .language, .hash_sha256, .created_at, .last_reviewed, .expires_at
        } AS claim,
        d.name AS domain_name,
        sources,
        validators
        ORDER BY c.created_at DESC
        SKIP $offset
        LIMIT $limit
        """,
        {"status": status, "limit": limit, "offset": offset},
    )
    rows = await result.data()
    return [
        _with_decay({
            **row["claim"],
            "domain_name": row["domain_name"],
            "source_references": row["sources"],
            "validated_by": [v for v in row["validators"] if v.get("name")],
        })
        for row in rows
    ]


async def validate_claim(
    session: AsyncSession,
    claim_id: str,
    expert_name: str,
    expert_institution: str,
    verdict: str,
    confidence_score: float,
    reviewed_at: str,
) -> None:
    expert_id = f"expert-{expert_name.lower().replace(' ', '-')}"
    new_status = "certified" if verdict == "approved" else "draft"

    await session.run(
        """
        MERGE (e:Expert {id: $expert_id})
        SET e.name = $name, e.institution = $institution, e.credential_verified = false
        WITH e
        MATCH (c:Claim {id: $claim_id})
        MERGE (e)-[v:VALIDATES]->(c)
        SET v.timestamp = $ts, v.verdict = $verdict
        SET c.status = $status,
            c.confidence_score = $confidence,
            c.last_reviewed = $ts
        """,
        {
            "expert_id": expert_id,
            "name": expert_name,
            "institution": expert_institution,
            "claim_id": claim_id,
            "ts": reviewed_at,
            "verdict": verdict,
            "status": new_status,
            "confidence": confidence_score,
        },
    )


# ---------------------------------------------------------------------------
# Expiry & Renewal
# ---------------------------------------------------------------------------

async def expire_outdated_claims(session: AsyncSession, now: str) -> list[dict[str, Any]]:
    """Setzt alle certified Claims deren expires_at < now auf 'needs_renewal'.
    Gibt die neu abgelaufenen Claims zurück."""
    result = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.expires_at IS NOT NULL AND c.expires_at < $now
        SET c.status = 'needs_renewal'
        RETURN c { .id, .text, .domain_id, .confidence_score, .expires_at } AS claim
        """,
        {"now": now},
    )
    rows = await result.data()
    return [row["claim"] for row in rows]


async def list_expiring_soon(
    session: AsyncSession, now: str, cutoff: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Claims die zwischen now und cutoff ablaufen (noch certified)."""
    result = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.expires_at >= $now AND c.expires_at <= $cutoff
        OPTIONAL MATCH (c)-[:BELONGS_TO]->(d:Domain)
        RETURN c {
            .id, .text, .domain_id, .confidence_score,
            .hash_sha256, .expires_at, .last_reviewed
        } AS claim,
        d.name AS domain_name
        ORDER BY c.expires_at ASC
        LIMIT $limit
        """,
        {"now": now, "cutoff": cutoff, "limit": limit},
    )
    rows = await result.data()
    return [{**row["claim"], "domain_name": row["domain_name"]} for row in rows]


async def renew_claim(
    session: AsyncSession,
    claim_id: str,
    expert_name: str,
    expert_institution: str,
    confidence_score: float,
    new_hash: str,
    reviewed_at: str,
    new_expiry: str,
) -> None:
    """Verlängert einen needs_renewal Claim: setzt Status auf certified + neues expires_at."""
    expert_id = f"expert-{expert_name.lower().replace(' ', '-')}"
    await session.run(
        """
        MERGE (e:Expert {id: $expert_id})
        SET e.name = $name, e.institution = $institution
        WITH e
        MATCH (c:Claim {id: $claim_id})
        MERGE (e)-[v:VALIDATES]->(c)
        SET v.timestamp  = $ts,
            v.verdict    = 'renewed'
        SET c.status           = 'certified',
            c.confidence_score = $confidence,
            c.last_reviewed    = $ts,
            c.expires_at       = $new_expiry,
            c.hash_sha256      = $new_hash
        """,
        {
            "expert_id":   expert_id,
            "name":        expert_name,
            "institution": expert_institution,
            "claim_id":    claim_id,
            "ts":          reviewed_at,
            "confidence":  confidence_score,
            "new_expiry":  new_expiry,
            "new_hash":    new_hash,
        },
    )


# ---------------------------------------------------------------------------
# Dashboard-Statistiken
# ---------------------------------------------------------------------------

async def get_dashboard_stats(session: AsyncSession) -> dict[str, Any]:
    """Aggregiert alle KPIs für das Stats-Dashboard in einer DB-Runde."""

    # 1. Globale Zähler pro Status
    r = await session.run(
        "MATCH (c:Claim) RETURN c.status AS status, count(c) AS n"
    )
    status_rows = await r.data()
    counts: dict[str, int] = {row["status"]: row["n"] for row in status_rows}
    total         = sum(counts.values())
    certified     = counts.get("certified", 0)
    peer_review   = counts.get("peer_review", 0)
    draft         = counts.get("draft", 0)
    needs_renewal = counts.get("needs_renewal", 0)
    cert_rate     = round(certified / total * 100, 1) if total else 0.0

    # 2. Domain-Breakdown
    r = await session.run(
        """
        MATCH (d:Domain)
        OPTIONAL MATCH (cert:Claim {status: 'certified'})-[:BELONGS_TO]->(d)
        OPTIONAL MATCH (rev:Claim  {status: 'peer_review'})-[:BELONGS_TO]->(d)
        OPTIONAL MATCH (dra:Claim  {status: 'draft'})-[:BELONGS_TO]->(d)
        RETURN d.id   AS id,
               d.name AS name,
               count(DISTINCT cert) AS certified,
               count(DISTINCT rev)  AS peer_review,
               count(DISTINCT dra)  AS draft
        ORDER BY certified DESC
        """
    )
    domains = await r.data()

    # 3. Confidence-Buckets (nur certified)
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        RETURN
          CASE
            WHEN c.confidence_score >= 0.97 THEN '0.97–1.00'
            WHEN c.confidence_score >= 0.94 THEN '0.94–0.96'
            WHEN c.confidence_score >= 0.90 THEN '0.90–0.93'
            ELSE                                 '< 0.90'
          END AS bucket,
          count(c) AS n
        ORDER BY bucket DESC
        """
    )
    confidence_dist = await r.data()

    # 4. Top-Validatoren
    r = await session.run(
        """
        MATCH (e:Expert)-[v:VALIDATES]->(c:Claim)
        WHERE e.name IS NOT NULL
        RETURN e.name        AS name,
               e.institution AS institution,
               count(c)      AS total,
               sum(CASE WHEN c.status = 'certified' THEN 1 ELSE 0 END) AS certified
        ORDER BY certified DESC, total DESC
        LIMIT 8
        """
    )
    validators = await r.data()

    # 5. Zuletzt zertifizierte Claims
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.last_reviewed IS NOT NULL
        OPTIONAL MATCH (e:Expert)-[:VALIDATES]->(c)
        WITH c, collect(DISTINCT e.name)[0] AS validator
        RETURN c.id              AS id,
               c.text            AS text,
               c.domain_id       AS domain_id,
               c.confidence_score AS confidence_score,
               c.last_reviewed   AS last_reviewed,
               validator
        ORDER BY c.last_reviewed DESC
        LIMIT 6
        """
    )
    recent = await r.data()

    # 6. Durchschnittlicher Trust-Score
    r = await session.run(
        "MATCH (c:Claim {status: 'certified'}) RETURN avg(c.confidence_score) AS avg_conf"
    )
    row = await r.single()
    avg_confidence = round((row["avg_conf"] or 0.0) * 100, 1)

    # 7. Ablauf-Metriken: bald ablaufend (30 Tage) + needs_renewal
    from swiss_truth_mcp.validation.trust import now_iso, expiry_iso
    _now = now_iso()
    _in30 = expiry_iso(days=30)
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.expires_at IS NOT NULL AND c.expires_at <= $cutoff
        RETURN count(c) AS n
        """,
        {"cutoff": _in30},
    )
    row30 = await r.single()
    expiring_soon = row30["n"] if row30 else 0

    return {
        "total":            total,
        "certified":        certified,
        "peer_review":      peer_review,
        "draft":            draft,
        "needs_renewal":    needs_renewal,
        "expiring_soon":    expiring_soon,
        "cert_rate":        cert_rate,
        "avg_confidence":   avg_confidence,
        "domains":          domains,
        "confidence_dist":  confidence_dist,
        "validators":       validators,
        "recent":           recent,
    }


# ---------------------------------------------------------------------------
# Query-Analytics
# ---------------------------------------------------------------------------

async def record_claim_queries(session: AsyncSession, claim_ids: list[str]) -> None:
    """Inkrementiert query_count + last_queried_at für alle zurückgegebenen Claims (fire-and-forget)."""
    if not claim_ids:
        return
    from swiss_truth_mcp.validation.trust import now_iso as _now
    await session.run(
        """
        UNWIND $ids AS id
        MATCH (c:Claim {id: id})
        SET c.query_count     = coalesce(c.query_count, 0) + 1,
            c.last_queried_at = $now
        """,
        {"ids": claim_ids, "now": _now()},
    )


async def get_query_analytics(session: AsyncSession) -> dict[str, Any]:
    """Aggregiert Query-Nutzungsdaten für das Analytics-Dashboard."""

    # Top-10 meistgefragte Claims
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.query_count IS NOT NULL AND c.query_count > 0
        RETURN c.id AS id, c.text AS text, c.domain_id AS domain_id,
               c.confidence_score AS confidence_score,
               c.query_count AS query_count,
               c.last_queried_at AS last_queried_at
        ORDER BY c.query_count DESC
        LIMIT 10
        """
    )
    top_claims = await r.data()

    # Domain-Nutzung (Summe query_count pro Domain)
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.query_count IS NOT NULL
        RETURN c.domain_id AS domain_id,
               sum(c.query_count) AS total_queries,
               count(c) AS claim_count
        ORDER BY total_queries DESC
        """
    )
    domain_usage = await r.data()

    # Claims nie abgefragt
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.query_count IS NULL OR c.query_count = 0
        RETURN count(c) AS n
        """
    )
    row = await r.single()
    never_queried = row["n"] if row else 0

    # Gesamt-Queries
    r = await session.run(
        "MATCH (c:Claim) WHERE c.query_count IS NOT NULL RETURN sum(c.query_count) AS total"
    )
    row = await r.single()
    total_queries = int(row["total"] or 0) if row else 0

    return {
        "top_claims":    top_claims,
        "domain_usage":  domain_usage,
        "never_queried": never_queried,
        "total_queries": total_queries,
    }


# ---------------------------------------------------------------------------
# Coverage-Analyse
# ---------------------------------------------------------------------------

async def get_claim_texts_by_domain(
    session: AsyncSession, domain_id: str, status: str = "certified"
) -> list[str]:
    """Gibt alle Claim-Texte + Fragen einer Domain zurück (für Topic-Matching)."""
    result = await session.run(
        """
        MATCH (c:Claim {status: $status, domain_id: $domain_id})
        RETURN coalesce(c.question, '') + ' ' + c.text AS combined
        """,
        {"status": status, "domain_id": domain_id},
    )
    rows = await result.data()
    return [row["combined"].lower() for row in rows]


# ---------------------------------------------------------------------------
# Trust-Page Statistiken
# ---------------------------------------------------------------------------

async def get_trust_stats(session: AsyncSession) -> dict[str, Any]:
    """Aggregiert alle öffentlichen Trust-Metriken in einer DB-Runde."""

    # 1. Globale Zähler
    r = await session.run(
        "MATCH (c:Claim) RETURN c.status AS status, count(c) AS n"
    )
    status_rows = await r.data()
    counts: dict[str, int] = {row["status"]: row["n"] for row in status_rows}
    total     = sum(counts.values())
    certified = counts.get("certified", 0)
    cert_rate = round(certified / total * 100, 1) if total else 0.0

    # 2. Durchschnittliche Konfidenz (certified)
    r = await session.run(
        "MATCH (c:Claim {status: 'certified'}) RETURN avg(c.confidence_score) AS avg_conf"
    )
    row = await r.single()
    avg_confidence = round((row["avg_conf"] or 0.0), 3)

    # 3. Unique Sources
    r = await session.run("MATCH (s:Source) RETURN count(s) AS n")
    row = await r.single()
    unique_sources = row["n"] if row else 0

    # 4. Sprach-Verteilung (certified)
    r = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        RETURN c.language AS lang, count(c) AS n
        ORDER BY n DESC
        """
    )
    language_rows = await r.data()
    lang_labels = {"de": "Deutsch", "en": "English", "fr": "Français", "it": "Italiano",
                   "es": "Español", "zh": "中文"}
    languages = [{"code": r["lang"], "label": lang_labels.get(r["lang"], r["lang"]), "count": r["n"]}
                 for r in language_rows]

    # 5. Domain-Breakdown (certified, absteigend)
    r = await session.run(
        """
        MATCH (d:Domain)
        OPTIONAL MATCH (c:Claim {status: 'certified'})-[:BELONGS_TO]->(d)
        RETURN d.id AS id, d.name AS name, count(c) AS n
        ORDER BY n DESC
        """
    )
    domains = [{"id": r["id"], "name": r["name"], "count": r["n"]}
               for r in await r.data() if r["n"] > 0]

    # 6. Quellen-Typen kategorisieren
    r = await session.run("MATCH (s:Source) RETURN s.url AS url")
    source_urls = [row["url"] for row in await r.data() if row["url"]]
    gov, academic, other = 0, 0, 0
    for url in source_urls:
        if any(x in url for x in [".admin.ch", ".ch/", "admin.ch", "parlament.ch", "fedlex"]):
            gov += 1
        elif any(x in url for x in ["arxiv.org", ".edu", "nih.gov", "nature.com",
                                     "science.org", "pubmed", "research", "uni-"]):
            academic += 1
        else:
            other += 1

    return {
        "total":          total,
        "certified":      certified,
        "cert_rate":      cert_rate,
        "avg_confidence": avg_confidence,
        "unique_sources": unique_sources,
        "languages":      languages,
        "domains":        domains,
        "sources_gov":    gov,
        "sources_academic": academic,
        "sources_other":  other,
    }


# ---------------------------------------------------------------------------
# RSS Feed
# ---------------------------------------------------------------------------

async def get_feed_claims(session: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    """Neueste zertifizierte Claims für den RSS-Feed, absteigend nach last_reviewed."""
    result = await session.run(
        """
        MATCH (c:Claim {status: 'certified'})
        WHERE c.last_reviewed IS NOT NULL
        OPTIONAL MATCH (c)-[:REFERENCES]->(s:Source)
        OPTIONAL MATCH (c)-[:BELONGS_TO]->(d:Domain)
        WITH c, d, collect(s.url) AS sources
        RETURN c {
            .id, .text, .domain_id, .confidence_score,
            .hash_sha256, .language, .last_reviewed
        } AS claim, d.name AS domain_name, sources
        ORDER BY c.last_reviewed DESC
        LIMIT $limit
        """,
        {"limit": limit},
    )
    rows = await result.data()
    return [
        {**row["claim"], "domain_name": row["domain_name"], "source_references": row["sources"]}
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Webhook-Subscriptions
# ---------------------------------------------------------------------------

async def create_webhook_subscription(session: AsyncSession, sub: dict[str, Any]) -> dict[str, Any]:
    await session.run(
        """
        CREATE (w:WebhookSubscription {
            id:            $id,
            url:           $url,
            label:         $label,
            domain_filter: $domain_filter,
            token:         $token,
            created_at:    $created_at
        })
        """,
        sub,
    )
    return sub


async def list_webhook_subscriptions(
    session: AsyncSession,
    domain_filter: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Alle Subscriptions — bei domain_filter nur passende + ungefilterte."""
    if domain_filter:
        result = await session.run(
            """
            MATCH (w:WebhookSubscription)
            WHERE w.domain_filter IS NULL OR w.domain_filter = $domain
            RETURN w {.id, .url, .label, .domain_filter, .created_at} AS sub
            """,
            {"domain": domain_filter},
        )
    else:
        result = await session.run(
            "MATCH (w:WebhookSubscription) RETURN w {.id, .url, .label, .domain_filter, .created_at} AS sub"
        )
    rows = await result.data()
    return [row["sub"] for row in rows]


async def delete_webhook_subscription(
    session: AsyncSession, sub_id: str, token: str
) -> bool:
    result = await session.run(
        """
        MATCH (w:WebhookSubscription {id: $id, token: $token})
        WITH w, count(w) AS n
        DELETE w
        RETURN n
        """,
        {"id": sub_id, "token": token},
    )
    row = await result.single()
    return bool(row and row["n"] > 0)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

async def create_user(session: AsyncSession, user: dict) -> dict:
    await session.run(
        """
        CREATE (u:User {
            id:            $id,
            username:      $username,
            email:         $email,
            password_hash: $password_hash,
            role:          $role,
            active:        $active,
            created_at:    $created_at
        })
        """,
        user,
    )
    return user


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[dict]:
    result = await session.run(
        "MATCH (u:User {username: $username}) RETURN u {.id,.username,.email,.role,.active,.created_at} AS u",
        {"username": username},
    )
    row = await result.single()
    return row["u"] if row else None


async def get_user_by_username_with_hash(session: AsyncSession, username: str) -> Optional[dict]:
    """Wie get_user_by_username, gibt zusätzlich password_hash zurück (nur für Login)."""
    result = await session.run(
        "MATCH (u:User {username: $username}) RETURN u {.id,.username,.email,.role,.active,.created_at,.password_hash} AS u",
        {"username": username},
    )
    row = await result.single()
    return row["u"] if row else None


async def list_users(session: AsyncSession) -> list[dict]:
    result = await session.run(
        "MATCH (u:User) RETURN u {.id,.username,.email,.role,.active,.created_at} AS u ORDER BY u.created_at"
    )
    rows = await result.data()
    return [r["u"] for r in rows]


async def update_user_active(session: AsyncSession, user_id: str, active: bool) -> None:
    await session.run(
        "MATCH (u:User {id: $id}) SET u.active = $active",
        {"id": user_id, "active": active},
    )


async def update_user_role(session: AsyncSession, user_id: str, role: str) -> None:
    await session.run(
        "MATCH (u:User {id: $id}) SET u.role = $role",
        {"id": user_id, "role": role},
    )


async def update_user_password(session: AsyncSession, user_id: str, password_hash: str) -> None:
    await session.run(
        "MATCH (u:User {id: $id}) SET u.password_hash = $password_hash",
        {"id": user_id, "password_hash": password_hash},
    )


async def delete_user(session: AsyncSession, user_id: str) -> None:
    await session.run(
        "MATCH (u:User {id: $id}) DETACH DELETE u",
        {"id": user_id},
    )


async def count_users(session: AsyncSession) -> int:
    result = await session.run("MATCH (u:User) RETURN count(u) AS n")
    row = await result.single()
    return row["n"] if row else 0
