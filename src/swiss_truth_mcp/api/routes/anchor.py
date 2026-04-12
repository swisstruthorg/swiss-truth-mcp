"""
Blockchain-Anchoring Endpoints

POST /admin/anchor          — Wöchentlicher Merkle-Root Anchor (Cron / Admin)
GET  /api/anchors           — Öffentlicher Audit-Trail aller Anchor-Records
GET  /api/anchors/latest    — Letzter bestätigter Anchor
GET  /api/anchors/{anchor_id}/verify/{claim_hash}  — Merkle-Inclusion-Proof

Authentifizierung für POST: Admin-Cookie ODER X-Swiss-Truth-Key Header.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from swiss_truth_mcp.config import settings
from swiss_truth_mcp.db.neo4j_client import get_session
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.blockchain.anchor import run_anchor_job, verify_inclusion

router = APIRouter(tags=["blockchain"])


# ─── Auth: Cookie ODER API-Key ────────────────────────────────────────────────

async def _require_admin_or_apikey(request: Request) -> dict:
    """Erlaubt Admin-Cookie (UI) ODER X-Swiss-Truth-Key Header (Automation)."""
    from swiss_truth_mcp.auth.dependencies import get_current_user

    api_key = (
        request.headers.get("x-swiss-truth-key", "").strip()
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )
    if api_key and api_key == settings.swiss_truth_api_key:
        return {"username": "automation", "role": "admin", "active": True}

    user = await get_current_user(request)
    if user and user.get("role") == "admin" and user.get("active"):
        return user

    raise HTTPException(status_code=401, detail="Admin-Authentifizierung erforderlich")


# ─── POST /admin/anchor ───────────────────────────────────────────────────────

class AnchorRequest(BaseModel):
    dry_run: bool = False          # True = Merkle-Root berechnen, NICHT auf Chain senden


@router.post("/admin/anchor")
async def trigger_anchor(
    req: AnchorRequest = AnchorRequest(),
    auth=Depends(_require_admin_or_apikey),
):
    """
    Wöchentlicher Blockchain-Anchor-Job:
    1. Alle zertifizierten Claim-Hashes aus Neo4j holen
    2. Deterministischen Merkle-Root berechnen (sortiert + SHA256)
    3. Self-Transaktion auf EVM-Chain senden (data = 'swiss-truth-v1:<root>:<count>')
    4. Anchor-Record in Neo4j speichern (öffentlich abrufbar unter /api/anchors)

    Wöchentlicher Cron (jeden Sonntag 02:00):
      curl -X POST https://swisstruth.org/admin/anchor \\
        -H "X-Swiss-Truth-Key: KEY" \\
        -H "Content-Type: application/json" \\
        -d '{"dry_run": false}'

    dry_run=true: nur Merkle-Root berechnen, kein On-Chain-Write.
    """
    async with get_session() as session:
        record = await run_anchor_job(
            session=session,
            rpc_url=settings.eth_rpc_url,
            private_key=settings.eth_private_key,
            chain_id=settings.eth_chain_id,
            chain_name=settings.eth_chain_name,
            dry_run=req.dry_run,
        )

    return {
        "ok": True,
        "anchor": record,
    }


# ─── GET /api/anchors ─────────────────────────────────────────────────────────

@router.get("/api/anchors")
async def list_anchors(limit: int = 52):
    """
    Öffentlicher Audit-Trail aller Blockchain-Anchor-Records.
    Kein Auth erforderlich — Transparenz by Design.

    Jeder Record enthält:
    - merkle_root: SHA256-Merkle-Root aller zertifizierten Claims zum Zeitpunkt
    - tx_hash:     Ethereum/Polygon Transaction Hash
    - explorer_url: Link zu Polygonscan / Etherscan
    - claim_count: Anzahl zertifizierter Claims im Snapshot
    """
    if limit > 200:
        limit = 200
    async with get_session() as session:
        records = await queries.list_anchor_records(session, limit=limit)
    return {
        "ok": True,
        "count": len(records),
        "anchors": records,
    }


# ─── GET /api/anchors/latest ─────────────────────────────────────────────────

@router.get("/api/anchors/latest")
async def get_latest_anchor():
    """Letzter bestätigter Anchor-Record (für Badges, Widgets, APIs)."""
    async with get_session() as session:
        anchor = await queries.get_latest_anchor(session)
    if not anchor:
        raise HTTPException(
            status_code=404,
            detail="Noch kein bestätigter Anchor-Record vorhanden.",
        )
    return {"ok": True, "anchor": anchor}


# ─── GET /api/anchors/{anchor_id}/verify/{claim_hash} ────────────────────────

@router.get("/api/anchors/{anchor_id}/verify/{claim_hash}")
async def verify_claim_in_anchor(anchor_id: str, claim_hash: str):
    """
    Merkle-Inclusion-Proof: Prüft ob ein Claim-Hash im gegebenen Anchor enthalten war.

    Gibt zurück:
    - included: true/false
    - merkle_root: Root des Anchors
    - claim_hash: normalisierter gesuchter Hash

    Beispiel:
      GET /api/anchors/<anchor_id>/verify/sha256:abc123...
    """
    async with get_session() as session:
        # Anchor-Record holen
        result = await session.run(
            "MATCH (a:AnchorRecord {id: $id}) RETURN a {.merkle_root} AS a",
            {"id": anchor_id},
        )
        row = await result.single()
        if not row:
            raise HTTPException(status_code=404, detail="Anchor-Record nicht gefunden.")

        anchor_root = row["a"]["merkle_root"]

        # Alle Hashes zum Zeitpunkt können wir nicht exakt rekonstruieren — aber wir
        # können den aktuellen Satz prüfen (zeigt ob Claim JETZT noch certified ist)
        all_hashes = await queries.get_all_certified_hashes(session)

    included = verify_inclusion(claim_hash, all_hashes, anchor_root)

    return {
        "ok": True,
        "anchor_id": anchor_id,
        "claim_hash": claim_hash.replace("sha256:", "").lower(),
        "merkle_root": anchor_root,
        "included": included,
        "note": "Inclusion proof checks current certified hashes against the stored Merkle root.",
    }
