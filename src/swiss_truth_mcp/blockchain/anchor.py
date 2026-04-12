"""
Swiss Truth — Blockchain Anchoring

Wöchentliche Verankerung des Merkle-Roots aller zertifizierten Claims
auf einer EVM-kompatiblen Blockchain (Standard: Polygon, konfigurierbar).

Architektur:
  1. Alle certified Claims SHA256-Hashes aus Neo4j holen
  2. Deterministischen Merkle-Root berechnen (pure Python)
  3. Als Transaktion auf Chain schreiben (data field = 'swiss-truth-v1:<root>')
  4. Anchor-Record in Neo4j speichern (öffentlich abfragbar)

Config (.env):
  ETH_RPC_URL=https://polygon-rpc.com          # kostenloser Public RPC
  ETH_PRIVATE_KEY=0x...                         # Wallet-Private-Key
  ETH_CHAIN_ID=137                              # 137=Polygon, 1=Mainnet, 8453=Base
  ETH_CHAIN_NAME=polygon
"""
from __future__ import annotations

import hashlib
import uuid
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── Merkle-Tree (pure Python, stdlib only) ───────────────────────────────────

def compute_merkle_root(hashes: list[str]) -> str:
    """
    Berechnet deterministischen Merkle-Root aus einer Liste von SHA256-Hashes.

    Eigenschaften:
    - Deterministisch: Sortierung vor Berechnung → gleiche Claims = gleicher Root
    - Tamper-evident: Jede Änderung an einem Hash ändert den Root
    - Padding: Ungerade Anzahl → letzter Hash wird dupliziert (Bitcoin-Standard)

    Args:
        hashes: Liste von SHA256-Hashes (mit oder ohne 'sha256:'-Prefix)

    Returns:
        Merkle-Root als 64-stelliger Hex-String
    """
    if not hashes:
        return hashlib.sha256(b"swiss-truth-empty-v1").hexdigest()

    # Normalisieren: Prefix entfernen, lowercase, deduplication, sortieren
    nodes: list[str] = sorted(set(
        h.replace("sha256:", "").lower()
        for h in hashes
        if h and len(h.replace("sha256:", "")) == 64
    ))

    if not nodes:
        return hashlib.sha256(b"swiss-truth-empty-v1").hexdigest()

    # Merkle-Tree bottom-up aufbauen
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])  # Letzten Knoten duplizieren (Padding)
        nodes = [
            hashlib.sha256((nodes[i] + nodes[i + 1]).encode("ascii")).hexdigest()
            for i in range(0, len(nodes), 2)
        ]

    return nodes[0]


def verify_inclusion(claim_hash: str, all_hashes: list[str], merkle_root: str) -> bool:
    """Prüft ob ein Claim-Hash im Merkle-Tree enthalten ist."""
    computed = compute_merkle_root(all_hashes)
    normalized = claim_hash.replace("sha256:", "").lower()
    normalized_hashes = [h.replace("sha256:", "").lower() for h in all_hashes]
    return computed == merkle_root and normalized in normalized_hashes


# ─── Ethereum-Anchoring ───────────────────────────────────────────────────────

async def anchor_to_chain(
    merkle_root: str,
    claim_count: int,
    rpc_url: str,
    private_key: str,
    chain_id: int,
    chain_name: str,
) -> dict[str, Any]:
    """
    Verankert den Merkle-Root auf einer EVM-Blockchain.

    Methode: Self-Transaction mit data = b'swiss-truth-v1:<merkle_root>'
    Die Transaktion ist permanent on-chain gespeichert und öffentlich verifizierbar.

    Returns:
        dict mit tx_hash, block_number, gas_used, explorer_url
    """
    try:
        from web3 import Web3
        from web3.exceptions import TransactionNotFound
    except ImportError:
        raise RuntimeError(
            "web3 nicht installiert. Container mit --rebuild neu bauen: "
            "bash deploy/update.sh --rebuild"
        )

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))

    if not w3.is_connected():
        raise RuntimeError(f"Keine Verbindung zu RPC: {rpc_url}")

    account = w3.eth.account.from_key(private_key)
    address = account.address

    # Data field: 'swiss-truth-v1:<merkle_root>:<claim_count>'
    data_str = f"swiss-truth-v1:{merkle_root}:{claim_count}"
    data_bytes = data_str.encode("utf-8")

    # Gas schätzen: 21000 Basis + 68 Gas/Byte für Non-Zero-Data
    estimated_gas = 21000 + 68 * len(data_bytes) + 2000  # 2000 Puffer

    nonce = w3.eth.get_transaction_count(address, "latest")
    gas_price = w3.eth.gas_price

    tx = {
        "nonce":    nonce,
        "to":       address,   # Self-Transaction (kein Token-Burn, kein Wertverlust)
        "value":    0,
        "data":     data_bytes,
        "gas":      estimated_gas,
        "gasPrice": gas_price,
        "chainId":  chain_id,
    }

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    # Auf Bestätigung warten (max. 3 Minuten)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=2)

    # Block-Explorer URLs je nach Chain
    explorers = {
        1:     f"https://etherscan.io/tx/{tx_hash.hex()}",
        137:   f"https://polygonscan.com/tx/{tx_hash.hex()}",
        8453:  f"https://basescan.org/tx/{tx_hash.hex()}",
        42161: f"https://arbiscan.io/tx/{tx_hash.hex()}",
    }

    return {
        "tx_hash":      tx_hash.hex(),
        "block_number": receipt["blockNumber"],
        "gas_used":     receipt["gasUsed"],
        "status":       "confirmed" if receipt["status"] == 1 else "failed",
        "from_address": address,
        "explorer_url": explorers.get(chain_id, f"tx:{tx_hash.hex()}"),
        "data_inscribed": data_str,
    }


# ─── Vollständiger Anchor-Job ─────────────────────────────────────────────────

async def run_anchor_job(
    session,            # Neo4j AsyncSession
    rpc_url: str = "",
    private_key: str = "",
    chain_id: int = 137,
    chain_name: str = "polygon",
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Kompletter wöchentlicher Anchor-Job:
    1. Alle certified Claim-Hashes aus Neo4j laden
    2. Merkle-Root berechnen
    3. Optional: auf Chain verankern
    4. Anchor-Record in Neo4j speichern

    Args:
        dry_run: True = Merkle-Root berechnen aber NICHT senden (für Tests)

    Returns:
        Vollständiger Anchor-Record
    """
    from swiss_truth_mcp.db import queries
    from swiss_truth_mcp.validation.trust import now_iso

    # 1. Alle Hashes holen
    hashes = await queries.get_all_certified_hashes(session)
    merkle_root = compute_merkle_root(hashes)

    anchor_id = str(uuid.uuid4())
    anchored_at = now_iso()

    record: dict[str, Any] = {
        "id":           anchor_id,
        "merkle_root":  merkle_root,
        "claim_count":  len(hashes),
        "anchored_at":  anchored_at,
        "chain":        chain_name if not dry_run else "dry-run",
        "chain_id":     chain_id if not dry_run else 0,
        "tx_hash":      None,
        "block_number": None,
        "explorer_url": None,
        "status":       "dry-run" if dry_run else "pending",
        "data_inscribed": f"swiss-truth-v1:{merkle_root}:{len(hashes)}",
    }

    # 2. Optional auf Chain verankern
    if not dry_run and rpc_url and private_key:
        try:
            tx_result = await anchor_to_chain(
                merkle_root=merkle_root,
                claim_count=len(hashes),
                rpc_url=rpc_url,
                private_key=private_key,
                chain_id=chain_id,
                chain_name=chain_name,
            )
            record.update({
                "tx_hash":      tx_result["tx_hash"],
                "block_number": tx_result["block_number"],
                "explorer_url": tx_result["explorer_url"],
                "status":       tx_result["status"],
            })
            logger.info(
                "Anchor confirmed on %s — tx: %s block: %s claims: %d",
                chain_name, tx_result["tx_hash"], tx_result["block_number"], len(hashes),
            )
        except Exception as e:
            record["status"] = f"error: {e}"
            logger.error("Anchor failed: %s", e)
    elif not dry_run:
        record["status"] = "computed-only"
        logger.warning(
            "ETH_RPC_URL / ETH_PRIVATE_KEY not configured — Merkle-Root computed but not anchored."
        )

    # 3. In Neo4j speichern
    await queries.create_anchor_record(session, record)

    return record
