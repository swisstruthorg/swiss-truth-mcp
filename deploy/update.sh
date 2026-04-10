#!/bin/bash
# ─── Swiss Truth MCP — Quick Update ─────────────────────────────────────────
# Überträgt geänderte Python/Template-Dateien und startet API neu.
# Kein docker cp, kein Image-Build nötig.
#
# Verwendung (vom Mac):
#   ./deploy/update.sh                    # Alles deployen
#   ./deploy/update.sh --no-restart       # Nur Dateien übertragen
set -euo pipefail

SERVER_USER="ubuntu"
SERVER_HOST="83.228.245.153"
DEPLOY_DIR="/opt/swiss-truth"
LOCAL_SRC="$(dirname "$0")/../src/swiss_truth_mcp"

NO_RESTART=false
[[ "${1:-}" == "--no-restart" ]] && NO_RESTART=true

echo "🚀  Swiss Truth — Quick Update"
echo "Server: ${SERVER_USER}@${SERVER_HOST}"
echo "─────────────────────────────────────"

# ── 1. Quellcode synchronisieren ─────────────────────────────────────────────
echo ""
echo "→ Sync src/swiss_truth_mcp/ ..."
rsync -az --delete \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude="*.pyo" \
  "${LOCAL_SRC}/" \
  "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/src/swiss_truth_mcp/"
echo "   ✓ Sync abgeschlossen"

# ── 2. docker-compose.prod.yml synchronisieren ───────────────────────────────
echo ""
echo "→ Sync docker-compose.prod.yml ..."
rsync -az \
  "$(dirname "$0")/../docker-compose.prod.yml" \
  "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/docker-compose.prod.yml"

# ── 3. deploy/-Scripts synchronisieren ───────────────────────────────────────
echo ""
echo "→ Sync deploy/ ..."
rsync -az \
  "$(dirname "$0")/" \
  "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/deploy/"
echo "   ✓ Deploy-Scripts synchronisiert"

# ── 4. Pycache löschen + API neu starten ─────────────────────────────────────
if [ "$NO_RESTART" = false ]; then
  echo ""
  echo "→ Pycache löschen ..."
  ssh "${SERVER_USER}@${SERVER_HOST}" \
    "sudo docker exec swiss-truth-api sh -c \"find /app/src -name '*.pyc' -delete && find /app/src -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null; echo done\" 2>/dev/null || true"

  echo "→ API neu starten ..."
  ssh "${SERVER_USER}@${SERVER_HOST}" \
    "sudo docker restart swiss-truth-api"
  sleep 8

  # Health-Check
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" https://swisstruth.org/health 2>/dev/null || echo "000")
  if [ "$HTTP" = "200" ]; then
    echo "   ✅  API erreichbar (HTTP 200)"
  else
    echo "   ⚠   API antwortet mit HTTP ${HTTP} — Logs prüfen:"
    echo "       ssh ${SERVER_USER}@${SERVER_HOST} 'sudo docker logs swiss-truth-api --tail 20'"
  fi
fi

echo ""
echo "─────────────────────────────────────"
echo "✅  Update abgeschlossen"
echo "   → https://swisstruth.org/dashboard"
