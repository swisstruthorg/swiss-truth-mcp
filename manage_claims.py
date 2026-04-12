#!/usr/bin/env python3
"""
Swiss Truth MCP — Continuous Claim Orchestrator
================================================
Läuft als Cronjob alle 30 Minuten auf dem Server.
Ziel: alle Domains auf ≥ 100 certified Claims bringen, dann neue Domains befüllen.

Verwendung:
    python3 /opt/swiss-truth/manage_claims.py
    python3 /opt/swiss-truth/manage_claims.py --status   # nur Status anzeigen
    python3 /opt/swiss-truth/manage_claims.py --domain eu-law  # eine Domain erzwingen
"""
from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import sys
import time
from datetime import datetime

import requests

# ─── File lock — prevents concurrent cron runs ───────────────────────────────

LOCK_FILE = "/tmp/swiss-truth-orchestrator.lock"


def acquire_lock() -> "IO | None":
    """Returns lock file handle if acquired, None if another instance is running."""
    try:
        f = open(LOCK_FILE, "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write(str(os.getpid()))
        f.flush()
        return f
    except BlockingIOError:
        return None

# ─── Config ──────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("SWISS_TRUTH_API_BASE", "https://swisstruth.org")
API_KEY  = os.environ.get("SWISS_TRUTH_API_KEY", "dev-key-change-in-prod")

# Minimum certified claims per domain — below this we keep generating
TARGET = int(os.environ.get("SWISS_TRUTH_TARGET", "100"))

# Claims requested per generate call
BATCH_SIZE = int(os.environ.get("SWISS_TRUTH_BATCH", "30"))

# Domains to skip (if broken or intentionally paused)
SKIP_DOMAINS: set[str] = set(os.environ.get("SWISS_TRUTH_SKIP", "").split(",")) - {""}

# Maximum rounds per orchestrator run (safety limit)
MAX_ROUNDS = int(os.environ.get("SWISS_TRUTH_MAX_ROUNDS", "5"))

# Sleep between API calls (seconds)
SLEEP_BETWEEN = int(os.environ.get("SWISS_TRUTH_SLEEP", "5"))

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("manage_claims")


# ─── API Helpers ─────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "X-Swiss-Truth-Key": API_KEY,
        "Content-Type": "application/json",
    }


def get_domain_stats() -> dict[str, int]:
    """Returns {domain_id: certified_count} for all domains."""
    try:
        r = requests.get(f"{API_BASE}/domains", headers=_headers(), timeout=30)
        r.raise_for_status()
        domains = r.json()
        return {d["id"]: d.get("certified_claims", d.get("certified_count", 0)) for d in domains}
    except Exception as e:
        log.error(f"Could not fetch domain stats: {e}")
        return {}


def generate_claims(domain_id: str, count: int = BATCH_SIZE) -> dict:
    """Triggers claim generation for a domain. Returns result dict."""
    try:
        r = requests.post(
            f"{API_BASE}/admin/generate",
            headers=_headers(),
            json={"domain_id": domain_id, "count": count},
            timeout=600,  # generation can take up to 10 min
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"error": "timeout", "certified": 0}
    except Exception as e:
        return {"error": str(e), "certified": 0}


def run_schema_setup() -> bool:
    """Ensures new domains are registered in Neo4j via docker exec."""
    try:
        import subprocess
        result = subprocess.run(
            ["sudo", "docker", "exec", "swiss-truth-api",
             "python", "-m", "swiss_truth_mcp.db.schema"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            log.info("Schema setup OK")
            return True
        else:
            log.warning(f"Schema setup stderr: {result.stderr[:200]}")
            return False
    except Exception as e:
        log.warning(f"Schema setup failed (non-fatal): {e}")
        return False


# ─── Display ─────────────────────────────────────────────────────────────────

def print_status(stats: dict[str, int]) -> None:
    """Pretty-print domain status."""
    total = sum(stats.values())
    print(f"\n{'─'*65}")
    print(f"  Swiss Truth — Domain Status  [{datetime.now().strftime('%Y-%m-%d %H:%M')}]")
    print(f"{'─'*65}")
    for domain_id, count in sorted(stats.items(), key=lambda x: x[1]):
        filled = min(count * 20 // max(TARGET, 1), 20)
        bar = "█" * filled + "░" * (20 - filled)
        status = "✅" if count >= TARGET else "🔴"
        print(f"  {status} {domain_id:<24} {bar} {count:>4}/{TARGET}")
    green = sum(1 for c in stats.values() if c >= TARGET)
    print(f"{'─'*65}")
    print(f"  Total certified claims: {total}  |  Green domains: {green}/{len(stats)}")
    print(f"{'─'*65}\n")


def select_domains_to_fill(stats: dict[str, int]) -> list[tuple[str, int]]:
    """Returns domains below TARGET, sorted ascending (most urgent first)."""
    below = [(did, cnt) for did, cnt in stats.items()
             if cnt < TARGET and did not in SKIP_DOMAINS]
    below.sort(key=lambda x: x[1])
    return below


# ─── Core Logic ──────────────────────────────────────────────────────────────

def orchestrate(force_domain: str | None = None) -> None:
    log.info("=== Swiss Truth Claim Orchestrator starting ===")

    # Ensure new domains exist in DB
    run_schema_setup()

    stats = get_domain_stats()
    if not stats:
        log.error("No domain stats available — aborting.")
        return

    print_status(stats)

    if force_domain:
        targets = [(force_domain, stats.get(force_domain, 0))]
        log.info(f"Forced mode: only processing domain '{force_domain}'")
    else:
        targets = select_domains_to_fill(stats)
        if not targets:
            log.info("🎉 All domains are at or above target! Nothing to do.")
            return

    log.info(f"Domains to fill: {[d for d, _ in targets]}")

    rounds = 0
    while rounds < MAX_ROUNDS:
        rounds += 1
        made_progress = False

        # Refresh stats each round
        if rounds > 1:
            stats = get_domain_stats()
            if force_domain:
                targets = [(force_domain, stats.get(force_domain, 0))]
            else:
                targets = select_domains_to_fill(stats)

        if not targets:
            log.info("🎉 All domains reached target — stopping early.")
            break

        log.info(f"--- Round {rounds}/{MAX_ROUNDS} — {len(targets)} domain(s) below {TARGET} ---")

        for domain_id, current_count in targets:
            current = stats.get(domain_id, current_count)
            needed = TARGET - current
            if needed <= 0:
                log.info(f"  {domain_id}: already at target, skipping.")
                continue

            batch = min(BATCH_SIZE, needed + 10)
            log.info(f"  Generating {batch} claims for '{domain_id}' (currently {current}/{TARGET})")

            result = generate_claims(domain_id, batch)

            if "error" in result:
                log.warning(f"  ⚠️  {domain_id}: generation error — {result['error']}")
            else:
                certified = result.get("certified", result.get("certified_count", 0))
                generated = result.get("generated", result.get("total_generated", 0))
                log.info(f"  ✓  {domain_id}: generated={generated}, certified={certified}")
                if certified > 0:
                    made_progress = True

            time.sleep(SLEEP_BETWEEN)

        if not made_progress and rounds > 1:
            log.warning("No progress this round — stopping to avoid infinite loop.")
            break

    # Final status
    final_stats = get_domain_stats()
    print_status(final_stats)
    green = sum(1 for c in final_stats.values() if c >= TARGET)
    log.info(f"=== Done: {green}/{len(final_stats)} domains at ≥{TARGET} certified claims ===")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Swiss Truth Claim Orchestrator")
    parser.add_argument("--status", action="store_true", help="Show domain status and exit")
    parser.add_argument("--domain", type=str, default=None, help="Only process this domain")
    parser.add_argument("--target", type=int, default=None, help="Override TARGET (default 100)")
    parser.add_argument("--batch", type=int, default=None, help="Override BATCH_SIZE (default 30)")
    parser.add_argument("--rounds", type=int, default=None, help="Override MAX_ROUNDS (default 5)")
    args = parser.parse_args()

    global TARGET, BATCH_SIZE, MAX_ROUNDS
    if args.target:
        TARGET = args.target
    if args.batch:
        BATCH_SIZE = args.batch
    if args.rounds:
        MAX_ROUNDS = args.rounds

    if args.status:
        stats = get_domain_stats()
        print_status(stats)
        return

    # Prevent concurrent runs (cron may fire while previous run is still going)
    lock = acquire_lock()
    if lock is None:
        log.info("Another orchestrator instance is running — exiting.")
        sys.exit(0)

    try:
        orchestrate(force_domain=args.domain)
    finally:
        lock.close()
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass


if __name__ == "__main__":
    main()
