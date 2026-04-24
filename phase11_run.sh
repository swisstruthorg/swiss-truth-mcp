#!/usr/bin/env bash
# ============================================================
# Phase 11: Agent Acquisition Blitz
# Milestone: "Agenten finden uns überall."
# ============================================================
set -euo pipefail

STEP="${1:-all}"
DRY_RUN="${2:-}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BLUE}[→]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Swiss Truth — Phase 11: Agent Acquisition Blitz       ║"
echo "║   Milestone: Agenten finden uns überall.                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────────────────────
# Step 11-01: Package Metadata Check
# ─────────────────────────────────────────────────────────────
step_11_01() {
    info "Step 11-01: Package Metadata Check"
    echo ""

    # Check PyPI packages
    for pkg in "integrations/crewai-pkg/pyproject.toml" "integrations/autogen-pkg/pyproject.toml" "integrations/langchain-pkg/pyproject.toml"; do
        if grep -q "Topic :: Scientific/Engineering :: Artificial Intelligence" "$pkg" 2>/dev/null; then
            log "$pkg — AI classifier ✓"
        else
            warn "$pkg — AI classifier MISSING"
        fi
        if grep -q "hallucination-prevention" "$pkg" 2>/dev/null; then
            log "$pkg — hallucination-prevention keyword ✓"
        else
            warn "$pkg — hallucination-prevention keyword MISSING"
        fi
    done

    # Check npm
    if grep -q "model-context-protocol" "npm/package.json" 2>/dev/null; then
        log "npm/package.json — model-context-protocol keyword ✓"
    else
        warn "npm/package.json — model-context-protocol keyword MISSING"
    fi
    if grep -q "eu-ai-act" "npm/package.json" 2>/dev/null; then
        log "npm/package.json — eu-ai-act keyword ✓"
    else
        warn "npm/package.json — eu-ai-act keyword MISSING"
    fi

    echo ""
    log "Step 11-01 complete — Package metadata verified"
}

# ─────────────────────────────────────────────────────────────
# Step 11-02: MCP Directory Listings Check
# ─────────────────────────────────────────────────────────────
step_11_02() {
    info "Step 11-02: MCP Directory Listings"
    echo ""

    echo "  Pending MCP Directory Submissions:"
    echo "  ─────────────────────────────────────────────────────"
    echo "  [ ] mcp.run          → data/outreach/pr_mcp_run.md"
    echo "  [ ] PulseMCP         → data/outreach/pr_pulsemcp.md"
    echo "  [ ] mcpservers.org   → data/outreach/pr_mcpservers.md"
    echo ""
    echo "  Already submitted:"
    echo "  [✓] Smithery         → https://smithery.ai/server/swiss-truth-mcp"
    echo "  [🔄] modelcontextprotocol/servers → PR #4007 (awaiting review)"
    echo "  [✓] Glama            → submitted 2026-04-22"
    echo "  [🔄] awesome-mcp-servers → PR #5230 (awaiting review)"
    echo ""

    if [ -f "data/outreach/pr_mcp_run.md" ]; then
        log "PR templates exist in data/outreach/"
    else
        warn "PR templates not found — run phase11_run.sh --step 11-03 first"
    fi

    log "Step 11-02 complete — Directory listing status shown"
}

# ─────────────────────────────────────────────────────────────
# Step 11-03: Awesome List PRs Check
# ─────────────────────────────────────────────────────────────
step_11_03() {
    info "Step 11-03: Awesome List PRs"
    echo ""

    echo "  Pending Awesome List PRs:"
    echo "  ─────────────────────────────────────────────────────"
    echo "  [ ] awesome-langchain    → data/outreach/pr_awesome_langchain.md"
    echo "  [ ] awesome-llm-apps     → data/outreach/pr_awesome_llm_apps.md"
    echo "  [ ] awesome-ai-agents    → data/outreach/pr_awesome_ai_agents.md"
    echo ""

    for f in "data/outreach/pr_awesome_langchain.md" "data/outreach/pr_awesome_llm_apps.md" "data/outreach/pr_awesome_ai_agents.md"; do
        if [ -f "$f" ]; then
            log "$f ✓"
        else
            warn "$f — not found"
        fi
    done

    log "Step 11-03 complete"
}

# ─────────────────────────────────────────────────────────────
# Step 11-04: Community Posts Check
# ─────────────────────────────────────────────────────────────
step_11_04() {
    info "Step 11-04: Community Posts"
    echo ""

    echo "  Community Post Drafts:"
    echo "  ─────────────────────────────────────────────────────"
    echo "  [ ] Hacker News (Show HN)     → data/outreach/post_hackernews.md"
    echo "  [ ] r/LangChain               → data/outreach/post_reddit_langchain.md"
    echo "  [ ] r/MachineLearning         → data/outreach/post_reddit_ml.md"
    echo "  [ ] LangChain GitHub Disc.    → data/outreach/post_github_discussions_langchain.md"
    echo "  [ ] CrewAI Community          → data/outreach/post_github_discussions_crewai.md"
    echo ""
    echo "  Note: LangChain Discord → blocked (no #tools-and-integrations channel found)"
    echo "        Alternative: https://github.com/langchain-ai/langchain/discussions"
    echo "  Note: CrewAI Discord → blocked"
    echo "        Alternative: https://community.crewai.com"
    echo ""

    for f in "data/outreach/post_hackernews.md" "data/outreach/post_reddit_langchain.md" "data/outreach/post_reddit_ml.md"; do
        if [ -f "$f" ]; then
            log "$f ✓"
        else
            warn "$f — not found"
        fi
    done

    log "Step 11-04 complete"
}

# ─────────────────────────────────────────────────────────────
# Step 11-05: Outreach Tracker Update
# ─────────────────────────────────────────────────────────────
step_11_05() {
    info "Step 11-05: Outreach Tracker Status"
    echo ""

    if command -v python3 &>/dev/null; then
        python3 - <<'PYEOF'
import json, sys
try:
    with open("data/outreach_tracker.json") as f:
        data = json.load(f)

    done = sum(1 for x in data.get("mcp_directory_listings", []) if x["status"] == "done")
    in_progress = sum(1 for x in data.get("mcp_directory_listings", []) if x["status"] == "in_progress")
    todo = sum(1 for x in data.get("mcp_directory_listings", []) if x["status"] == "todo")

    print(f"  MCP Directories: {done} done, {in_progress} in_progress, {todo} todo")

    done_pr = sum(1 for x in data.get("awesome_list_prs", []) if x["status"] == "done")
    ip_pr = sum(1 for x in data.get("awesome_list_prs", []) if x["status"] == "in_progress")
    todo_pr = sum(1 for x in data.get("awesome_list_prs", []) if x["status"] == "todo")
    print(f"  Awesome List PRs: {done_pr} done, {ip_pr} in_progress, {todo_pr} todo")

    done_cp = sum(1 for x in data.get("community_posts", []) if x["status"] == "done")
    todo_cp = sum(1 for x in data.get("community_posts", []) if x["status"] == "todo")
    blocked_cp = sum(1 for x in data.get("community_posts", []) if x["status"] == "blocked")
    print(f"  Community Posts: {done_cp} done, {todo_cp} todo, {blocked_cp} blocked")
except Exception as e:
    print(f"  Error reading tracker: {e}", file=sys.stderr)
PYEOF
    fi

    echo ""
    log "Step 11-05 complete"
}

# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
cd "$(dirname "$0")"

case "$STEP" in
    all)
        step_11_01
        echo ""
        step_11_02
        echo ""
        step_11_03
        echo ""
        step_11_04
        echo ""
        step_11_05
        ;;
    --step)
        case "${2:-}" in
            11-01) step_11_01 ;;
            11-02) step_11_02 ;;
            11-03) step_11_03 ;;
            11-04) step_11_04 ;;
            11-05) step_11_05 ;;
            *) err "Unknown step: ${2:-}. Use 11-01 through 11-05"; exit 1 ;;
        esac
        ;;
    *)
        echo "Usage: $0 [all | --step 11-01..11-05]"
        exit 1
        ;;
esac

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Phase 11 Status Summary                               ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║   Outreach materials: data/outreach/                    ║"
echo "║   Next: Submit PRs + community posts manually           ║"
echo "║   Track progress: data/outreach_tracker.json            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
