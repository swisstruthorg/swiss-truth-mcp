#!/usr/bin/env python3
"""
Swiss Truth MCP — Continuous Claim Orchestrator
================================================
Läuft als Cronjob alle 30 Minuten auf dem Server.
Ziel: alle Domains auf ≥ 200 certified Claims bringen, dann neue Domains befüllen.

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
    """Returns lock file handle if acquired, None if another instance is running.
    Handles stale lock files (process no longer alive).
    """
    # Check for stale lock file first
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid_str = f.read().strip()
            if pid_str:
                pid = int(pid_str)
                # Check if the process is still alive
                try:
                    os.kill(pid, 0)  # signal 0 = just check existence
                    # Process is alive → another instance is running
                except ProcessLookupError:
                    # Process is dead → stale lock, remove it
                    log.warning(f"Removing stale lock file (PID {pid} no longer running)")
                    os.unlink(LOCK_FILE)
                except PermissionError:
                    # Process exists but we can't signal it → treat as alive
                    pass
        except (ValueError, OSError):
            # Corrupt lock file → remove it
            try:
                os.unlink(LOCK_FILE)
            except OSError:
                pass

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
TARGET = int(os.environ.get("SWISS_TRUTH_TARGET", "200"))

# Claims requested per generate call
BATCH_SIZE = int(os.environ.get("SWISS_TRUTH_BATCH", "30"))

# Domains to skip (if broken or intentionally paused)
SKIP_DOMAINS: set[str] = set(os.environ.get("SWISS_TRUTH_SKIP", "").split(",")) - {""}

# Maximum rounds per orchestrator run (safety limit — high enough to fill all domains)
MAX_ROUNDS = int(os.environ.get("SWISS_TRUTH_MAX_ROUNDS", "50"))

# Sleep between API calls (seconds)
SLEEP_BETWEEN = int(os.environ.get("SWISS_TRUTH_SLEEP", "5"))

# Global wall-clock timeout in seconds (default 4 hours = 14400s)
# Prevents the cron job from running forever and blocking the next scheduled run
MAX_RUNTIME_SECONDS = int(os.environ.get("SWISS_TRUTH_MAX_RUNTIME", "14400"))

# How many consecutive rounds without ANY progress before giving up
# (allows temporary API errors to be tolerated)
MAX_STALE_ROUNDS = int(os.environ.get("SWISS_TRUTH_MAX_STALE", "3"))

# Retry config for API calls
API_RETRY_COUNT = int(os.environ.get("SWISS_TRUTH_RETRY_COUNT", "3"))
API_RETRY_DELAY = int(os.environ.get("SWISS_TRUTH_RETRY_DELAY", "10"))

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


def get_domain_stats(retries: int = API_RETRY_COUNT) -> dict[str, int]:
    """Returns {domain_id: certified_count} for all domains. Retries on failure."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(f"{API_BASE}/domains", headers=_headers(), timeout=30)
            r.raise_for_status()
            domains = r.json()
            return {d["id"]: d.get("certified_claims", d.get("certified_count", 0)) for d in domains}
        except Exception as e:
            log.warning(f"Could not fetch domain stats (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(API_RETRY_DELAY)
    log.error(f"Failed to fetch domain stats after {retries} attempts.")
    return {}


def generate_claims(domain_id: str, count: int = BATCH_SIZE, retries: int = API_RETRY_COUNT) -> dict:
    """Triggers claim generation for a domain. Returns result dict. Retries on transient errors."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(
                f"{API_BASE}/admin/generate",
                headers=_headers(),
                json={"domain_id": domain_id, "count": count},
                timeout=600,  # generation can take up to 10 min
            )
            # Permanent errors (auth, bad request) — don't retry
            if r.status_code in (401, 403, 422):
                log.error(f"Permanent error {r.status_code} for domain '{domain_id}': {r.text[:200]}")
                return {"error": f"http_{r.status_code}", "certified": 0, "permanent": True}
            r.raise_for_status()
            return r.json()
        except requests.exceptions.Timeout:
            log.warning(f"Timeout generating claims for '{domain_id}' (attempt {attempt}/{retries})")
            if attempt < retries:
                time.sleep(API_RETRY_DELAY)
            else:
                return {"error": "timeout", "certified": 0}
        except Exception as e:
            log.warning(f"Error generating claims for '{domain_id}' (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(API_RETRY_DELAY)
            else:
                return {"error": str(e), "certified": 0}
    return {"error": "max_retries_exceeded", "certified": 0}


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
    start_time = time.monotonic()
    log.info("=== Swiss Truth Claim Orchestrator starting ===")
    log.info(f"Config: TARGET={TARGET}, BATCH_SIZE={BATCH_SIZE}, MAX_ROUNDS={MAX_ROUNDS}, "
             f"MAX_RUNTIME={MAX_RUNTIME_SECONDS}s, MAX_STALE_ROUNDS={MAX_STALE_ROUNDS}")

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
    stale_rounds = 0  # consecutive rounds without any certified claims

    while rounds < MAX_ROUNDS:
        # Check global wall-clock timeout
        elapsed = time.monotonic() - start_time
        if elapsed >= MAX_RUNTIME_SECONDS:
            log.warning(f"⏱  Global runtime limit reached ({elapsed:.0f}s / {MAX_RUNTIME_SECONDS}s) — stopping.")
            break

        rounds += 1
        round_certified = 0  # total certified claims this round

        # Refresh stats each round
        if rounds > 1:
            stats = get_domain_stats()
            if not stats:
                log.warning("Could not refresh domain stats — using cached values.")
                # Don't abort, use last known stats
            if force_domain:
                targets = [(force_domain, stats.get(force_domain, 0))]
            else:
                targets = select_domains_to_fill(stats)

        if not targets:
            log.info("🎉 All domains reached target — stopping early.")
            break

        remaining_time = MAX_RUNTIME_SECONDS - (time.monotonic() - start_time)
        log.info(f"--- Round {rounds}/{MAX_ROUNDS} — {len(targets)} domain(s) below {TARGET} "
                 f"— {remaining_time:.0f}s remaining ---")

        for domain_id, current_count in targets:
            # Per-domain time check
            if time.monotonic() - start_time >= MAX_RUNTIME_SECONDS:
                log.warning("⏱  Runtime limit reached mid-round — stopping.")
                break

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
                # Permanent errors (auth/bad request): skip this domain for the rest of the run
                if result.get("permanent"):
                    log.error(f"  ❌ {domain_id}: permanent error, adding to skip list for this run.")
                    SKIP_DOMAINS.add(domain_id)
            else:
                certified = result.get("certified", result.get("certified_count", 0))
                generated = result.get("generated", result.get("total_generated", 0))
                log.info(f"  ✓  {domain_id}: generated={generated}, certified={certified}")
                round_certified += certified

            time.sleep(SLEEP_BETWEEN)

        # Stale round detection — only count rounds where we actually tried to generate
        if round_certified == 0:
            stale_rounds += 1
            log.warning(f"  No certified claims this round ({stale_rounds}/{MAX_STALE_ROUNDS} stale rounds).")
            if stale_rounds >= MAX_STALE_ROUNDS:
                log.warning(f"⛔ {MAX_STALE_ROUNDS} consecutive rounds without progress — stopping to avoid infinite loop.")
                break
        else:
            stale_rounds = 0  # reset on any progress

    # Final status
    final_stats = get_domain_stats()
    if final_stats:
        print_status(final_stats)
        green = sum(1 for c in final_stats.values() if c >= TARGET)
        elapsed = time.monotonic() - start_time
        log.info(f"=== Done: {green}/{len(final_stats)} domains at ≥{TARGET} certified claims "
                 f"(runtime: {elapsed:.0f}s, rounds: {rounds}) ===")
    else:
        log.warning("Could not fetch final stats.")


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Swiss Truth Claim Orchestrator")
    parser.add_argument("--status", action="store_true", help="Show domain status and exit")
    parser.add_argument("--domain", type=str, default=None, help="Only process this domain")
    parser.add_argument("--target", type=int, default=None, help="Override TARGET (default 200)")
    parser.add_argument("--batch", type=int, default=None, help="Override BATCH_SIZE (default 30)")
    parser.add_argument("--rounds", type=int, default=None, help="Override MAX_ROUNDS (default 50)")
    parser.add_argument("--max-runtime", type=int, default=None, help="Override MAX_RUNTIME_SECONDS (default 14400)")
    args = parser.parse_args()

    global TARGET, BATCH_SIZE, MAX_ROUNDS, MAX_RUNTIME_SECONDS
    if args.target:
        TARGET = args.target
    if args.batch:
        BATCH_SIZE = args.batch
    if args.rounds:
        MAX_ROUNDS = args.rounds
    if args.max_runtime:
        MAX_RUNTIME_SECONDS = args.max_runtime

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
