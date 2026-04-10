#!/bin/bash
# ─── Swiss Truth MCP — Seed-Daten auf Server importieren ────────────────────
# Ausführen nachdem deploy.sh erfolgreich war:
#   SERVER_HOST=swisstruth.org ./deploy/seed-remote.sh
set -euo pipefail

SERVER_USER="swisstruth"
SERVER_HOST="${SERVER_HOST:-DEINE_SERVER_IP}"
DEPLOY_DIR="/opt/swiss-truth"

echo "🌱  Swiss Truth — Seed-Daten importieren"
echo "Server: ${SERVER_USER}@${SERVER_HOST}"
echo "==============================="

# Seed-Dateien auf Server übertragen
echo "→ Seed-Dateien übertragen..."
rsync -az src/swiss_truth_mcp/seed/*_claims.json \
    ${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/seed/

# Seed-Import im API-Container ausführen
echo "→ Import starten..."
ssh ${SERVER_USER}@${SERVER_HOST} << REMOTE
cd ${DEPLOY_DIR}

# Seed-Dateien in Container kopieren
docker cp seed/. swiss-truth-api:/app/src/swiss_truth_mcp/seed/

# Seed-CLI im Container ausführen
docker exec swiss-truth-api swiss-truth-seed

echo ""
echo "✅  Import abgeschlossen!"
REMOTE

echo ""
echo "Dashboard prüfen: https://${SERVER_HOST}/dashboard"
