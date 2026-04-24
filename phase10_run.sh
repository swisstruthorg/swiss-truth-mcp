#!/usr/bin/env bash
# ============================================================
# Phase 10: Content Foundation — Master Orchestrator
# ============================================================
# Milestone: "Erst das Regal füllen, dann den Laden öffnen."
#
# Steps:
#   10-01  Coverage-Audit aller 30 Domains
#   10-02  Bulk Claim Generation — Tier 1 (swiss-health, swiss-law, swiss-finance, ai-ml, ai-safety, eu-law)
#   10-03  Bulk Claim Generation — Tier 2 & Tier 3
#   10-04  Multi-Language Expansion (FR + IT für Schweizer Kerndomains)
#   10-05  Quality Assurance (Conflict Detection + Coverage Re-Check)
#   10-06  Agent-Attraktivitäts-Benchmark
#
# Verwendung:
#   ./phase10_run.sh              # alle Steps
#   ./phase10_run.sh --step 10-01 # nur Coverage-Audit
#   ./phase10_run.sh --step 10-02 # nur Tier-1 Generation
#   ./phase10_run.sh --step 10-04 # nur Multilang
#   ./phase10_run.sh --dry-run    # zeigt was gemacht würde, ohne API-Calls
#
# Umgebungsvariablen:
#   SWISS_TRUTH_API_BASE  (default: https://swisstruth.org)
#   SWISS_TRUTH_API_KEY   (default: aus .env)
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ─── Load .env ───────────────────────────────────────────────
if [ -f .env ]; then
    set -a; source .env; set +a
fi

API_BASE="${SWISS_TRUTH_API_BASE:-https://swisstruth.org}"
API_KEY="${SWISS_TRUTH_API_KEY:-dev-key-change-in-prod}"
DRY_RUN=false
ONLY_STEP=""
LOG_FILE="phase10_$(date +%Y%m%d_%H%M%S).log"

# ─── Parse Args ──────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --step)       ONLY_STEP="$2"; shift 2 ;;
        --api-base)   API_BASE="$2"; shift 2 ;;
        --api-key)    API_KEY="$2"; shift 2 ;;
        --log)        LOG_FILE="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | grep -v '#!/' | sed 's/^# //' | sed 's/^#//'
            exit 0
            ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ─── Logging ─────────────────────────────────────────────────
exec > >(tee -a "$LOG_FILE") 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
info()    { log "ℹ️  $*"; }
success() { log "✅ $*"; }
warn()    { log "⚠️  $*"; }
error()   { log "❌ $*"; }
step_header() {
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  $1"
    echo "════════════════════════════════════════════════════════════"
}

# ─── API Helper ──────────────────────────────────────────────
api_get() {
    local path="$1"
    curl -sf -H "X-Swiss-Truth-Key: ${API_KEY}" \
         -H "Content-Type: application/json" \
         "${API_BASE}${path}"
}

api_post() {
    local path="$1"
    local data="$2"
    curl -sf -X POST \
         -H "X-Swiss-Truth-Key: ${API_KEY}" \
         -H "Content-Type: application/json" \
         -d "$data" \
         "${API_BASE}${path}"
}

# ─── Generate Claims via manage_claims.py ────────────────────
generate_domain() {
    local domain="$1"
    local count="$2"
    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY-RUN] Would generate $count claims for '$domain'"
        return 0
    fi
    info "Generating $count claims for domain: $domain"
    python3 manage_claims.py --domain "$domain" --batch "$count" --rounds 1 \
        && success "  ✓ $domain done" \
        || warn "  ⚠ $domain had errors (non-fatal)"
    sleep 3
}

# ─── Multilang via seed/multilang.py ─────────────────────────
multilang_domain() {
    local domain="$1"
    local lang="$2"
    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY-RUN] Would expand $domain → $lang"
        return 0
    fi
    info "Multilang expansion: $domain → $lang"
    python3 -m swiss_truth_mcp.seed.multilang --domain "$domain" --lang "$lang" \
        && success "  ✓ $domain/$lang done" \
        || warn "  ⚠ $domain/$lang had errors (non-fatal)"
    sleep 2
}

should_run() {
    local step="$1"
    [ -z "$ONLY_STEP" ] || [ "$ONLY_STEP" = "$step" ]
}

# ════════════════════════════════════════════════════════════════
# STEP 10-01: Coverage-Audit aller 30 Domains
# ════════════════════════════════════════════════════════════════
run_10_01() {
    step_header "10-01: Coverage-Audit aller 30 Domains"

    info "Fetching domain stats from $API_BASE..."

    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY-RUN] Would call GET ${API_BASE}/domains and GET ${API_BASE}/api/coverage"
        return 0
    fi

    # Domain stats
    python3 manage_claims.py --status

    # Coverage API (if available)
    local coverage_result
    if coverage_result=$(api_get "/api/coverage" 2>/dev/null); then
        echo ""
        echo "Coverage Report:"
        echo "$coverage_result" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, list):
    items = data
elif isinstance(data, dict):
    items = data.get('domains', data.get('coverage', [data]))
else:
    items = []

tier1 = ['swiss-health','swiss-law','swiss-finance','ai-ml','ai-safety','eu-law']
tier2 = ['climate','cybersecurity','economics','biotech','us-law','world-science','eu-health','global-science']

total_domains = len(items)
zero_domains = [d for d in items if (d.get('certified_claims',0) if isinstance(d,dict) else 0) == 0]
print(f'  Total domains: {total_domains}')
print(f'  Domains with 0 claims: {len(zero_domains)}')

if isinstance(items, list) and items and isinstance(items[0], dict):
    for d in sorted(items, key=lambda x: x.get('id','') if isinstance(x,dict) else ''):
        did = d.get('id', d.get('domain_id','?'))
        cnt = d.get('certified_claims', d.get('claim_count', 0))
        tier = 'T1' if did in tier1 else ('T2' if did in tier2 else 'T3')
        target = 50 if tier == 'T1' else (30 if tier == 'T2' else 15)
        status = '✅' if cnt >= target else '🔴'
        bar = '█' * min(cnt * 20 // max(target,1), 20) + '░' * max(0, 20 - min(cnt * 20 // max(target,1), 20))
        print(f'  {status} [{tier}] {did:<26} {bar} {cnt:>4}/{target}')
" 2>/dev/null || echo "$coverage_result" | python3 -m json.tool 2>/dev/null || echo "$coverage_result"
    else
        warn "Coverage endpoint not available — using domain stats only"
    fi

    success "10-01 Coverage-Audit complete. Log: $LOG_FILE"
}

# ════════════════════════════════════════════════════════════════
# STEP 10-02: Bulk Claim Generation — Tier 1 Domains
# Target: ≥50 certified claims each, ≥90% coverage
# ════════════════════════════════════════════════════════════════
run_10_02() {
    step_header "10-02: Bulk Generation — Tier 1 Domains (50+ each)"

    # Tier 1: Kern-Domains — müssen exzellent sein
    local TIER1_DOMAINS=(
        "swiss-health"
        "swiss-law"
        "swiss-finance"
        "ai-ml"
        "ai-safety"
        "eu-law"
    )
    local TIER1_COUNT=50

    info "Tier-1 Domains (${#TIER1_DOMAINS[@]} domains × ${TIER1_COUNT} claims each)"
    info "Estimated new claims: $((${#TIER1_DOMAINS[@]} * TIER1_COUNT))"
    echo ""

    for domain in "${TIER1_DOMAINS[@]}"; do
        generate_domain "$domain" "$TIER1_COUNT"
    done

    success "10-02 Tier-1 generation complete."
    info "Expected: 300+ new certified claims in Tier-1 domains"
}

# ════════════════════════════════════════════════════════════════
# STEP 10-03: Bulk Claim Generation — Tier 2 & Tier 3
# ════════════════════════════════════════════════════════════════
run_10_03() {
    step_header "10-03: Bulk Generation — Tier 2 & Tier 3 Domains"

    # Tier 2: Wichtige Domains — 30+ claims each
    local TIER2_DOMAINS=(
        "climate"
        "cybersecurity"
        "economics"
        "biotech"
        "us-law"
        "world-science"
        "eu-health"
        "global-science"
    )
    local TIER2_COUNT=30

    # Tier 3: Basis-Domains — 15+ claims each
    local TIER3_DOMAINS=(
        "swiss-education"
        "swiss-energy"
        "swiss-transport"
        "swiss-politics"
        "swiss-agriculture"
        "swiss-digital"
        "swiss-environment"
        "mental-health"
        "blockchain-crypto"
        "nutrition-food"
        "labor-employment"
        "quantum-computing"
        "space-science"
        "renewable-energy"
        "world-history"
        "international-law"
    )
    local TIER3_COUNT=15

    info "Tier-2 Domains (${#TIER2_DOMAINS[@]} domains × ${TIER2_COUNT} claims)"
    for domain in "${TIER2_DOMAINS[@]}"; do
        generate_domain "$domain" "$TIER2_COUNT"
    done

    echo ""
    info "Tier-3 Domains (${#TIER3_DOMAINS[@]} domains × ${TIER3_COUNT} claims)"
    for domain in "${TIER3_DOMAINS[@]}"; do
        generate_domain "$domain" "$TIER3_COUNT"
    done

    success "10-03 Tier-2/3 generation complete."
    info "Expected: 240 Tier-2 + 240 Tier-3 = ~480 new claims"
}

# ════════════════════════════════════════════════════════════════
# STEP 10-04: Multi-Language Expansion
# Schweizer Landessprachen: FR + IT für Kern-Domains
# ════════════════════════════════════════════════════════════════
run_10_04() {
    step_header "10-04: Multi-Language Expansion (FR + IT)"

    # Swiss core domains — FR first (Romandie)
    local FR_DOMAINS=("swiss-health" "swiss-law" "swiss-finance" "ai-ml")
    # IT (Ticino)
    local IT_DOMAINS=("swiss-health" "swiss-law" "swiss-finance")

    info "FR expansion (${#FR_DOMAINS[@]} domains)"
    for domain in "${FR_DOMAINS[@]}"; do
        multilang_domain "$domain" "fr"
    done

    echo ""
    info "IT expansion (${#IT_DOMAINS[@]} domains)"
    for domain in "${IT_DOMAINS[@]}"; do
        multilang_domain "$domain" "it"
    done

    success "10-04 Multi-language expansion complete."
    info "Expected: 200+ multilingual claims (FR + IT)"
}

# ════════════════════════════════════════════════════════════════
# STEP 10-05: Quality Assurance & Conflict Resolution
# ════════════════════════════════════════════════════════════════
run_10_05() {
    step_header "10-05: Quality Assurance & Conflict Resolution"

    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY-RUN] Would run: conflict detection, clustering, renewal, coverage re-check"
        return 0
    fi

    # 1. Conflict Detection
    info "Running conflict detection..."
    if conflicts=$(api_get "/api/conflicts" 2>/dev/null); then
        conflict_count=$(echo "$conflicts" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('total',d.get('count',len(d) if isinstance(d,list) else '?')))" 2>/dev/null || echo "?")
        info "Conflicts detected: $conflict_count"
        if [ "$conflict_count" != "0" ] && [ "$conflict_count" != "?" ]; then
            warn "  → Review conflicts at ${API_BASE}/api/conflicts"
        else
            success "  → No conflicts detected"
        fi
    else
        warn "Conflict endpoint not available — skipping"
    fi

    sleep 2

    # 2. Trigger Renewal for expired claims
    info "Triggering renewal pipeline..."
    if renewal=$(api_post "/admin/renewal" '{"dry_run": false}' 2>/dev/null); then
        renewed=$(echo "$renewal" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('renewed',d.get('count','?')))" 2>/dev/null || echo "?")
        info "Claims renewed: $renewed"
    else
        warn "Renewal endpoint not available — skipping"
    fi

    sleep 2

    # 3. Coverage re-check
    info "Re-checking coverage after generation..."
    python3 manage_claims.py --status

    # 4. Summary
    info "Checking for domains still at 0 claims..."
    if domain_list=$(api_get "/domains" 2>/dev/null); then
        zero_count=$(echo "$domain_list" | python3 -c "
import json,sys
domains = json.load(sys.stdin)
zeros = [d.get('id','?') for d in domains if d.get('certified_claims',d.get('certified_count',0)) == 0]
print(len(zeros))
if zeros: print('  Zero-claim domains:', ', '.join(zeros))
" 2>/dev/null || echo "?")
        if [ "$zero_count" = "0" ]; then
            success "All domains have ≥1 certified claim! ✨"
        else
            warn "$zero_count domain(s) still at 0 claims"
        fi
    fi

    success "10-05 Quality Assurance complete."
}

# ════════════════════════════════════════════════════════════════
# STEP 10-06: Agent-Attraktivitäts-Benchmark
# ════════════════════════════════════════════════════════════════
run_10_06() {
    step_header "10-06: Agent-Attraktivitäts-Benchmark"

    if [ "$DRY_RUN" = "true" ]; then
        info "[DRY-RUN] Would run: python3 phase10_benchmark.py"
        return 0
    fi

    if [ -f "phase10_benchmark.py" ]; then
        python3 phase10_benchmark.py
    else
        warn "phase10_benchmark.py not found — run it separately"
    fi

    success "10-06 Benchmark complete."
}

# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════
main() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║       Swiss Truth MCP — Phase 10: Content Foundation        ║"
    echo "║       Milestone: Erst das Regal füllen, dann öffnen         ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    info "API Base:  $API_BASE"
    info "Dry Run:   $DRY_RUN"
    info "Only Step: ${ONLY_STEP:-all}"
    info "Log File:  $LOG_FILE"
    echo ""

    # Connectivity check
    if [ "$DRY_RUN" = "false" ]; then
        info "Checking API connectivity..."
        if ! curl -sf "${API_BASE}/health" -o /dev/null 2>/dev/null && \
           ! curl -sf "${API_BASE}/api/health" -o /dev/null 2>/dev/null && \
           ! curl -sf "${API_BASE}/domains" -H "X-Swiss-Truth-Key: ${API_KEY}" -o /dev/null 2>/dev/null; then
            warn "API not reachable at $API_BASE — some steps may fail"
            warn "Make sure Docker services are running: docker-compose up -d"
        else
            success "API reachable ✓"
        fi
    fi
    echo ""

    START_TIME=$(date +%s)

    should_run "10-01" && run_10_01
    should_run "10-02" && run_10_02
    should_run "10-03" && run_10_03
    should_run "10-04" && run_10_04
    should_run "10-05" && run_10_05
    should_run "10-06" && run_10_06

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))

    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Phase 10 Complete!  Elapsed: ${ELAPSED}s"
    echo "║  Target: 3000+ certified claims across 30 domains"
    echo "║  Next: Phase 11 — Agent Acquisition Blitz"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    success "Phase 10 done. Log: $LOG_FILE"
}

main
