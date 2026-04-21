"""
Knowledge Graph API Routes — Phase 5 (Plan 05-04)

Clustering endpoints and graph data for visualization.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries

router = APIRouter(tags=["graph"])


@router.get("/api/clusters/{domain_id}")
async def get_clusters(domain_id: str, threshold: float = 0.85):
    """Get or compute claim clusters for a domain."""
    from swiss_truth_mcp.validation.clustering import (
        cluster_domain,
        get_clusters_for_domain,
    )

    async with get_session() as session:
        # Check if clusters already exist
        existing = await get_clusters_for_domain(session, domain_id)
        if existing:
            return {
                "domain_id": domain_id,
                "source": "cached",
                "clusters": existing,
            }

        # Compute fresh clusters
        result = await cluster_domain(session, domain_id, threshold)
        return result


@router.post("/api/clusters/{domain_id}/recompute")
async def recompute_clusters(domain_id: str, threshold: float = 0.85):
    """Force recompute clusters for a domain (clears existing)."""
    from swiss_truth_mcp.validation.clustering import cluster_domain

    async with get_session() as session:
        # Clear existing cluster relationships
        await session.run(
            """
            MATCH (c:Claim {domain_id: $domain_id})-[r:CLUSTER_OF]->()
            DELETE r
            """,
            {"domain_id": domain_id},
        )
        result = await cluster_domain(session, domain_id, threshold)
        return result


@router.get("/api/graph/{domain_id}")
async def get_graph_data(
    domain_id: str,
    min_confidence: float = 0.0,
    status: str = "certified",
    limit: int = 200,
):
    """
    Get graph data for visualization (nodes + edges).
    Returns claims, sources, experts, and their relationships.
    """
    async with get_session() as session:
        # Get claims with relationships
        result = await session.run(
            """
            MATCH (c:Claim {domain_id: $domain_id, status: $status})
            WHERE c.confidence_score >= $min_conf
            OPTIONAL MATCH (c)-[:REFERENCES]->(s:Source)
            OPTIONAL MATCH (e:Expert)-[:VALIDATES]->(c)
            OPTIONAL MATCH (c)-[cl:CLUSTER_OF]->(center:Claim)
            OPTIONAL MATCH (c)-[cf:CONFLICTS_WITH]->(conflict:Claim)
            WITH c,
                 collect(DISTINCT {id: s.id, url: s.url, type: 'source'}) AS sources,
                 collect(DISTINCT {id: e.id, name: e.name, type: 'expert'}) AS experts,
                 collect(DISTINCT {id: center.id, similarity: cl.similarity}) AS cluster_links,
                 collect(DISTINCT {id: conflict.id}) AS conflict_links
            RETURN c.id AS id, c.text AS text, c.confidence_score AS confidence,
                   c.domain_id AS domain_id,
                   sources, experts, cluster_links, conflict_links
            ORDER BY c.confidence_score DESC
            LIMIT $limit
            """,
            {
                "domain_id": domain_id,
                "status": status,
                "min_conf": min_confidence,
                "limit": limit,
            },
        )
        rows = await result.data()

    # Build nodes and edges for D3/Cytoscape
    nodes = []
    edges = []
    seen_nodes = set()

    for row in rows:
        claim_id = row["id"]
        if claim_id not in seen_nodes:
            nodes.append({
                "id": claim_id,
                "label": row["text"][:80],
                "type": "claim",
                "confidence": row["confidence"],
            })
            seen_nodes.add(claim_id)

        for src in row["sources"]:
            if src["id"] and src["id"] not in seen_nodes:
                nodes.append({
                    "id": src["id"],
                    "label": src["url"][:60] if src["url"] else "source",
                    "type": "source",
                })
                seen_nodes.add(src["id"])
            if src["id"]:
                edges.append({
                    "source": claim_id,
                    "target": src["id"],
                    "type": "references",
                })

        for exp in row["experts"]:
            if exp["id"] and exp["id"] not in seen_nodes:
                nodes.append({
                    "id": exp["id"],
                    "label": exp["name"] or "expert",
                    "type": "expert",
                })
                seen_nodes.add(exp["id"])
            if exp["id"]:
                edges.append({
                    "source": exp["id"],
                    "target": claim_id,
                    "type": "validates",
                })

        for cl in row["cluster_links"]:
            if cl["id"]:
                edges.append({
                    "source": claim_id,
                    "target": cl["id"],
                    "type": "cluster_of",
                    "similarity": cl.get("similarity"),
                })

        for cf in row["conflict_links"]:
            if cf["id"]:
                edges.append({
                    "source": claim_id,
                    "target": cf["id"],
                    "type": "conflicts_with",
                })

    return {
        "domain_id": domain_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
    }
