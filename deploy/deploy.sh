#!/bin/bash
# ─── Swiss Truth MCP — Deploy / Update ──────────────────────────────────────
# Lokal ausführen (von deinem Mac):
#   ./deploy/deploy.sh
#
# Oder direkt auf dem Server als 'swisstruth':
#   cd /opt/swiss-truth && bash deploy.sh
set -euo pipefail

SERVER_USER="swisstruth"
SERVER_HOST="${SERVER_HOST:-DEINE_SERVER_IP}"
DEPLOY_DIR="/opt/swiss-truth"
IMAGE_NAME="swiss-truth-api"

echo "🚀  Swiss Truth MCP — Deploy"
echo "Server: ${SERVER_USER}@${SERVER_HOST}"
echo "==============================="

# ─── 1. Docker Image lokal bauen ─────────────────────────────────────────────
echo ""
echo "→ [1/4] Docker Image bauen..."
docker build -t ${IMAGE_NAME}:latest .
docker save ${IMAGE_NAME}:latest | gzip > /tmp/swiss-truth-api.tar.gz
echo "   Image gebaut und exportiert ✓"

# ─── 2. Dateien auf Server übertragen ────────────────────────────────────────
echo ""
echo "→ [2/4] Dateien übertragen..."
rsync -az --progress \
    docker-compose.prod.yml \
    Caddyfile \
    ${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/

# Image übertragen
scp /tmp/swiss-truth-api.tar.gz ${SERVER_USER}@${SERVER_HOST}:/tmp/
rm /tmp/swiss-truth-api.tar.gz
echo "   Dateien übertragen ✓"

# ─── 3. Auf Server deployen ───────────────────────────────────────────────────
echo ""
echo "→ [3/4] Auf Server deployen..."
ssh ${SERVER_USER}@${SERVER_HOST} << 'REMOTE'
set -euo pipefail
cd /opt/swiss-truth

# Image laden
echo "   Image laden..."
docker load < /tmp/swiss-truth-api.tar.gz
rm /tmp/swiss-truth-api.tar.gz

# Services neu starten
echo "   Services starten..."
docker compose -f docker-compose.prod.yml pull n8n    # n8n immer aktuell
docker compose -f docker-compose.prod.yml up -d --remove-orphans

echo "   Warte auf Healthchecks..."
sleep 15
docker compose -f docker-compose.prod.yml ps
REMOTE

echo "   Deploy abgeschlossen ✓"

# ─── 4. Health Check ─────────────────────────────────────────────────────────
echo ""
echo "→ [4/4] Health Check..."
sleep 5
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://${SERVER_HOST}/health 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" = "200" ]; then
    echo "   ✅  API erreichbar (HTTP 200)"
else
    echo "   ⚠️   API antwortet mit HTTP ${HTTP_STATUS} — Logs prüfen:"
    echo "        ssh ${SERVER_USER}@${SERVER_HOST} 'docker logs swiss-truth-api --tail 50'"
fi

echo ""
echo "==============================="
echo "✅  Deploy abgeschlossen!"
echo "   → https://${SERVER_HOST}"
echo "   → https://n8n.${SERVER_HOST}"
