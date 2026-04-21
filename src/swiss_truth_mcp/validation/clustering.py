"""
Claim Clustering — Phase 5 (Plan 05-04)

Groups semantically similar claims using embedding cosine similarity.
Creates ClusterOf relationships in Neo4j.

Usage:
    from swiss_truth_mcp.validation.clustering import cluster_domain
    clusters = await cluster_domain("ai-ml", threshold=0.85)
"""
from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncSession

logger = logging.getLogger(__name__)


async def get_domain_embeddings(
    session: AsyncSession, domain_id: str
) -> list[dict[str, Any]]:
    """Get all certified claim IDs + embeddings for a domain."""
    result = await session.run(
        """
        MATCH (c:Claim {status: 'certified', domain_id: $domain_id})
        WHERE c.embedding IS NOT NULL
        RETURN c.id AS id, c.text AS text, c.embedding AS embedding,
               c.confidence_score AS confidence
        """,
        {"domain_id": domain_id},
    )
    return await result.data()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_clusters(
    claims: list[dict], threshold: float = 0.85
) -> list[list[dict]]:
    """
    Simple agglomerative clustering based on cosine similarity.
    Returns list of clusters, each cluster is a list of claims.
    """
    if not claims:
        return []

    n = len(claims)
    assigned = [False] * n
    clusters: list[list[dict]] = []

    for i in range(n):
        if assigned[i]:
            continue
        cluster = [claims[i]]
        assigned[i] = True

        for j in range(i + 1, n):
            if assigned[j]:
                continue
            sim = cosine_similarity(
                claims[i]["embedding"], claims[j]["embedding"]
            )
            if sim >= threshold:
                cluster.append(claims[j])
                assigned[j] = True

        clusters.append(cluster)

    # Sort by cluster size (largest first)
    clusters.sort(key=len, reverse=True)
    return clusters


async def store_cluster_relationships(
    session: AsyncSession,
    clusters: list[list[dict]],
) -> int:
    """Store ClusterOf relationships in Neo4j. Returns count created."""
    count = 0
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        # Use first claim as cluster center
        center_id = cluster[0]["id"]
        for member in cluster[1:]:
            await session.run(
                """
                MATCH (center:Claim {id: $center_id})
                MATCH (member:Claim {id: $member_id})
                MERGE (member)-[r:CLUSTER_OF]->(center)
                SET r.similarity = $similarity
                """,
                {
                    "center_id": center_id,
                    "member_id": member["id"],
                    "similarity": cosine_similarity(
                        cluster[0]["embedding"], member["embedding"]
                    ),
                },
            )
            count += 1
    return count


async def cluster_domain(
    session: AsyncSession,
    domain_id: str,
    threshold: float = 0.85,
) -> dict[str, Any]:
    """
    Cluster all certified claims in a domain.
    Returns summary with cluster count and sizes.
    """
    claims = await get_domain_embeddings(session, domain_id)
    if not claims:
        return {
            "domain_id": domain_id,
            "total_claims": 0,
            "clusters": [],
            "relationships_created": 0,
        }

    clusters = build_clusters(claims, threshold)
    rel_count = await store_cluster_relationships(session, clusters)

    cluster_summaries = []
    for i, cluster in enumerate(clusters):
        cluster_summaries.append({
            "cluster_id": i,
            "size": len(cluster),
            "center_claim_id": cluster[0]["id"],
            "center_text": cluster[0]["text"][:120],
            "member_ids": [c["id"] for c in cluster],
        })

    logger.info(
        "Clustered %d claims in %s → %d clusters, %d relationships",
        len(claims), domain_id, len(clusters), rel_count,
    )

    return {
        "domain_id": domain_id,
        "total_claims": len(claims),
        "cluster_count": len(clusters),
        "multi_claim_clusters": len([c for c in clusters if len(c) > 1]),
        "clusters": cluster_summaries,
        "relationships_created": rel_count,
    }


async def get_clusters_for_domain(
    session: AsyncSession, domain_id: str
) -> list[dict[str, Any]]:
    """Get existing clusters from Neo4j for a domain."""
    result = await session.run(
        """
        MATCH (member:Claim {domain_id: $domain_id})-[r:CLUSTER_OF]->(center:Claim)
        RETURN center.id AS center_id, center.text AS center_text,
               collect({
                   id: member.id,
                   text: member.text,
                   similarity: r.similarity,
                   confidence: member.confidence_score
               }) AS members
        ORDER BY size(collect(member)) DESC
        """,
        {"domain_id": domain_id},
    )
    return await result.data()
