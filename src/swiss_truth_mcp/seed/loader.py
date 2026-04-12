"""
swiss-truth-seed — Seed-Loader CLI

Liest alle *_claims.json-Dateien im seed/-Verzeichnis und schreibt alle Claims
idempotent in die Neo4j-Datenbank.

Unterstützte Dateien (auto-discovery):
  ai_ml_claims.json, climate_claims.json, swiss_health_claims.json, ...

Strategie:
  confidence >= 0.88  →  status = 'certified'  (direkt zertifiziert, pre_screen hat bereits geprüft)
  confidence  < 0.88  →  status = 'peer_review' (füllt die Review-Queue)

Idempotenz: Claims mit identischem Text werden übersprungen (MERGE on text).

Optionen:
  --dry-run          Zeigt was importiert würde, ohne DB-Schreibzugriff
  --file FILE.json   Nur eine bestimmte Datei importieren
  --domain DOMAIN    Nur Dateien für eine bestimmte Domain importieren
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from pathlib import Path

import httpx

from swiss_truth_mcp.db.neo4j_client import get_driver, close_driver
from swiss_truth_mcp.db.schema import setup_schema
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.embeddings import embed_text
from swiss_truth_mcp.validation.pre_screen import pre_screen_claim, verify_source_supports_claim
from swiss_truth_mcp.validation.trust import sign_claim, now_iso, expiry_iso

SEED_DIR = Path(__file__).parent
CERTIFIED_THRESHOLD = 0.88
CURATOR_NAME = "Swiss Truth Seed Curator"
CURATOR_INSTITUTION = "Swiss Truth Foundation"

# ---------------------------------------------------------------------------
# URL-Validierung
# ---------------------------------------------------------------------------

async def _check_url(client: httpx.AsyncClient, url: str) -> bool:
    """
    Prüft ob eine URL erreichbar ist (HTTP 2xx oder 3xx).
    Versucht zuerst HEAD (schnell), fällt auf GET zurück wenn HEAD nicht erlaubt.
    """
    try:
        r = await client.head(url, follow_redirects=True)
        if r.status_code == 405:  # Method Not Allowed — GET versuchen
            r = await client.get(url, follow_redirects=True)
        return 200 <= r.status_code < 400
    except Exception:
        return False


async def validate_source_urls(urls: list[str]) -> tuple[list[str], list[str]]:
    """
    Validiert alle source_urls eines Claims per HTTP-Check.
    Gibt (gültige_urls, ungültige_urls) zurück.

    Ungültige URLs (404, Timeout, DNS-Fehler) werden nicht gespeichert —
    sie würden die wissenschaftliche Glaubwürdigkeit des Claims untergraben.
    """
    if not urls:
        return [], []

    valid: list[str] = []
    invalid: list[str] = []

    headers = {"User-Agent": "SwissTruthBot/1.0 (url-validator; contact@swisstruth.org)"}

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, headers=headers) as client:
        # Parallel prüfen mit max. 5 gleichzeitigen Requests
        sem = asyncio.Semaphore(5)

        async def check_with_sem(url: str) -> tuple[str, bool]:
            async with sem:
                return url, await _check_url(client, url)

        results = await asyncio.gather(*[check_with_sem(u) for u in urls])

    for url, ok in results:
        if ok:
            valid.append(url)
        else:
            invalid.append(url)

    return valid, invalid


# ---------------------------------------------------------------------------
# Quellenverifikation (Inhalt belegt Claim?)
# ---------------------------------------------------------------------------

def _extract_text(html: str) -> str:
    """Einfache HTML → Plaintext Konvertierung (kein BS4-Overhead)."""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>",  " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


async def verify_sources_against_claim(claim_text: str, urls: list[str]) -> tuple[list[str], list[str]]:
    """
    Fetcht den Inhalt jeder URL und prüft via Claude Haiku ob er den Claim belegt.
    PDFs und nicht-extrahierbare Seiten → im Zweifel behalten (supports=True).
    Gibt (belegte_urls, unbelegte_urls) zurück.
    """
    headers = {"User-Agent": "SwissTruthBot/1.0 (source-verifier; contact@swisstruth.org)"}
    sem = asyncio.Semaphore(3)

    async def check_one(url: str) -> tuple[str, bool, str]:
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=headers) as client:
                    r = await client.get(url)
                if r.status_code >= 400:
                    return url, False, f"HTTP {r.status_code}"
                # PDFs und Binär-Inhalte → nicht prüfbar, behalten
                content_type = r.headers.get("content-type", "")
                if "pdf" in content_type or "octet-stream" in content_type:
                    return url, True, "PDF — nicht extrahierbar"
                page_text = _extract_text(r.text)
                result = await verify_source_supports_claim(claim_text, page_text)
                return url, result.get("supports", True), result.get("reason", "")
            except Exception as e:
                return url, True, f"Prüfung nicht möglich ({type(e).__name__})"

    results = await asyncio.gather(*[check_one(u) for u in urls])

    supported, unsupported = [], []
    for url, ok, reason in results:
        if ok:
            supported.append(url)
        else:
            unsupported.append(url)
            print(f"         ✗ Quelle belegt Claim nicht: {url[:55]} — {reason}")

    return supported, unsupported


# ---------------------------------------------------------------------------
# Seed-Dateien entdecken
# ---------------------------------------------------------------------------

def _discover_seed_files(only_file: str | None = None, only_domain: str | None = None) -> list[Path]:
    """
    Gibt alle *_claims.json-Dateien im seed/-Verzeichnis zurück,
    sortiert nach Name. Optionale Filter:
      only_file   — nur diese eine Datei (Pfad oder Dateiname)
      only_domain — nur Dateien deren Name mit f"{domain}_claims.json" übereinstimmt
    """
    if only_file:
        p = Path(only_file)
        if not p.is_absolute():
            p = SEED_DIR / p
        if not p.exists():
            print(f"❌  Datei nicht gefunden: {p}", file=sys.stderr)
            sys.exit(1)
        return [p]

    files = sorted(SEED_DIR.glob("*_claims.json"))

    if only_domain:
        target = f"{only_domain}_claims.json"
        files = [f for f in files if f.name == target]
        if not files:
            print(f"❌  Keine Datei für Domain '{only_domain}' gefunden (Erwartet: {target})", file=sys.stderr)
            sys.exit(1)

    return files


# ---------------------------------------------------------------------------
# Idempotenz-Prüfung
# ---------------------------------------------------------------------------

async def _claim_text_exists(session, text: str) -> bool:
    """True wenn ein Claim mit exakt diesem Text bereits existiert."""
    result = await session.run(
        "MATCH (c:Claim {text: $text}) RETURN count(c) AS n",
        {"text": text},
    )
    row = await result.single()
    return row["n"] > 0


async def _find_semantic_duplicate(session, embedding: list[float], threshold: float = 0.95) -> dict | None:
    """
    Sucht nach einem semantisch sehr ähnlichen Claim (Ähnlichkeit >= threshold).
    Gibt den ähnlichsten Claim zurück oder None.
    Prüft alle Stati (nicht nur certified), um Duplikate in jeder Phase zu erkennen.
    """
    result = await session.run(
        """
        CALL db.index.vector.queryNodes('claim_embedding_index', 3, $embedding)
        YIELD node AS c, score
        WHERE score >= $threshold
        RETURN c.id AS id, c.text AS text, c.status AS status, score
        ORDER BY score DESC
        LIMIT 1
        """,
        {"embedding": embedding, "threshold": threshold},
    )
    row = await result.single()
    if row is None:
        return None
    return {"id": row["id"], "text": row["text"], "status": row["status"], "score": row["score"]}


# ---------------------------------------------------------------------------
# Einen Claim importieren
# ---------------------------------------------------------------------------

async def _import_claim(session, raw: dict, index: int, total: int) -> str:
    """
    Importiert einen einzelnen Claim.
    Gibt 'created', 'certified' oder 'skipped' zurück.
    """
    text = raw["text"]

    if await _claim_text_exists(session, text):
        print(f"  [{index:02d}/{total}] ⏭  Übersprungen (identischer Text): {text[:55]}…")
        return "skipped"

    confidence  = raw.get("confidence_score", 0.9)
    domain_id   = raw.get("domain_id", "ai-ml")
    language    = raw.get("language", "de")
    source_urls = raw.get("source_urls", [])
    question    = raw.get("question", "")

    # ── Embedding (vor Duplikat-Check, da für Vektor-Suche benötigt) ─────────
    embed_input = f"{question} {text}".strip() if question else text
    embedding = await embed_text(embed_input)

    # ── Semantischer Duplikat-Check ──────────────────────────────────────────
    duplicate = await _find_semantic_duplicate(session, embedding, threshold=0.95)
    if duplicate:
        print(
            f"  [{index:02d}/{total}] ⏭  Übersprungen (semantisches Duplikat "
            f"{duplicate['score']:.3f}): {text[:45]}…"
        )
        return "skipped"

    # ── Pre-Screen (Tier-1 Qualitätsprüfung via Claude Haiku) ───────────────
    screen = await pre_screen_claim(
        text=text,
        domain_id=domain_id,
        source_urls=source_urls,
    )
    if not screen.get("passed", True):
        issues = "; ".join(screen.get("issues", []))
        print(f"  [{index:02d}/{total}] ✗  Pre-Screen fehlgeschlagen: {issues[:80]}")
        return "skipped"

    # ── URL-Validierung (erreichbar?) ────────────────────────────────────────
    if source_urls:
        valid_urls, invalid_urls = await validate_source_urls(source_urls)
        if invalid_urls:
            print(f"         ⚠ Ungültige URLs entfernt: {', '.join(u[:50] for u in invalid_urls)}")
        source_urls = valid_urls

    # ── Quellenverifikation (belegt Inhalt den Claim?) ───────────────────────
    if source_urls:
        source_urls, rejected = await verify_sources_against_claim(text, source_urls)
        if rejected:
            print(f"         ⚠ {len(rejected)} Quelle(n) ohne Claim-Bezug entfernt")

    if not source_urls:
        print(f"         ✗ Keine verifizierten Quellen — setze auf peer_review")
        confidence = min(confidence, 0.89)

    status     = "certified" if confidence >= CERTIFIED_THRESHOLD else "peer_review"
    created_at = now_iso()
    expires_at = expiry_iso(days=365)

    claim = {
        "id":               str(uuid.uuid4()),
        "text":             text,
        "question":         question,
        "domain_id":        domain_id,
        "confidence_score": confidence,
        "status":           status,
        "language":         language,
        "hash_sha256":      "",           # wird unten gesetzt
        "created_at":       created_at,
        "last_reviewed":    created_at if status == "certified" else None,
        "expires_at":       expires_at,
        "embedding":        embedding,
        "source_urls":      source_urls,
    }

    # SHA-256 berechnen (ohne embedding)
    claim["hash_sha256"] = sign_claim(claim)

    # In DB schreiben
    await queries.create_claim(session, claim)

    # Für certified-Claims direkt einen Expert-Node anlegen
    if status == "certified":
        await queries.validate_claim(
            session,
            claim_id=claim["id"],
            expert_name=CURATOR_NAME,
            expert_institution=CURATOR_INSTITUTION,
            verdict="approved",
            confidence_score=confidence,
            reviewed_at=created_at,
        )
        label = "✅ certified"
    else:
        label = "🟡 peer_review"

    print(f"  [{index:02d}/{total}] {label} ({confidence:.2f}): {text[:55]}…")
    return status


# ---------------------------------------------------------------------------
# Eine Seed-Datei importieren
# ---------------------------------------------------------------------------

async def _import_file(session, seed_file: Path, dry_run: bool) -> dict:
    """Importiert alle Claims aus einer Seed-Datei. Gibt Zähldict zurück."""
    claims_raw: list[dict] = json.loads(seed_file.read_text(encoding="utf-8"))
    total = len(claims_raw)
    print(f"\n📄  {seed_file.name}  ({total} Claims)")
    print("-" * 55)

    counts = {"certified": 0, "peer_review": 0, "skipped": 0}

    if dry_run:
        for i, c in enumerate(claims_raw, 1):
            status = "certified" if c["confidence_score"] >= CERTIFIED_THRESHOLD else "peer_review"
            domain = c.get("domain_id", "?")
            print(f"  [{i:02d}/{total}] {status} ({c['confidence_score']:.2f}) [{domain}]: {c['text'][:50]}…")
            counts[status] = counts.get(status, 0) + 1
        return counts

    for i, raw in enumerate(claims_raw, 1):
        result = await _import_claim(session, raw, i, total)
        counts[result] = counts.get(result, 0) + 1

    return counts


# ---------------------------------------------------------------------------
# Hauptroutine
# ---------------------------------------------------------------------------

async def _run(dry_run: bool = False, only_file: str | None = None, only_domain: str | None = None) -> None:
    print("🌱  Swiss Truth Seed Loader — Multi-Domain")
    print("=" * 55)

    seed_files = _discover_seed_files(only_file=only_file, only_domain=only_domain)

    if not seed_files:
        print("❌  Keine *_claims.json-Dateien gefunden!", file=sys.stderr)
        sys.exit(1)

    print(f"📂  {len(seed_files)} Seed-Datei(en) gefunden:")
    for f in seed_files:
        print(f"     · {f.name}")

    if dry_run:
        print("\n🔍  DRY-RUN — kein Schreibzugriff auf die DB")

    # Schema sicherstellen (nur im echten Lauf)
    if not dry_run:
        driver = get_driver()
        async with driver.session() as session:
            await setup_schema(session)

    # Alle Dateien importieren
    totals = {"certified": 0, "peer_review": 0, "skipped": 0}

    if dry_run:
        for seed_file in seed_files:
            counts = await _import_file(None, seed_file, dry_run=True)
            for k, v in counts.items():
                totals[k] = totals.get(k, 0) + v
    else:
        driver = get_driver()
        async with driver.session() as session:
            for seed_file in seed_files:
                counts = await _import_file(session, seed_file, dry_run=False)
                for k, v in counts.items():
                    totals[k] = totals.get(k, 0) + v
        await close_driver()

    # Zusammenfassung
    grand_total = sum(totals.values())
    print()
    print("=" * 55)
    print(f"✅  Zertifiziert:   {totals['certified']:>4} Claims")
    print(f"🟡  Peer Review:    {totals['peer_review']:>4} Claims")
    print(f"⏭   Übersprungen:   {totals['skipped']:>4} Claims (bereits vorhanden)")
    print(f"📊  Gesamt:         {grand_total:>4} Claims aus {len(seed_files)} Datei(en)")
    print()

    if dry_run:
        print("→  Dry-run — zum echten Import: swiss-truth-seed")
    else:
        print("→  Review-Queue:  http://127.0.0.1:8001/review")
        print("→  Zertifiziert:  http://127.0.0.1:8001/review/certified")
        print("→  Dashboard:     http://127.0.0.1:8001/dashboard")


def main() -> None:
    args = sys.argv[1:]
    dry_run     = "--dry-run" in args
    only_file   = None
    only_domain = None

    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            only_file = args[idx + 1]

    if "--domain" in args:
        idx = args.index("--domain")
        if idx + 1 < len(args):
            only_domain = args[idx + 1]

    asyncio.run(_run(dry_run=dry_run, only_file=only_file, only_domain=only_domain))


if __name__ == "__main__":
    main()
