#!/bin/bash
# ─── Swiss Truth Kanban — Deploy auf Hostinger ────────────────────────────────
#
# Erster Deploy:
#   SERVER_HOST=<hostinger-ip>  bash kanban_service/deploy.sh
#
# Update (nur Code, kein Rebuild):
#   SERVER_HOST=<hostinger-ip>  bash kanban_service/deploy.sh --update
#
# Rebuild (neue Dependencies):
#   SERVER_HOST=<hostinger-ip>  bash kanban_service/deploy.sh --rebuild
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SERVER_HOST="${SERVER_HOST:-}"
SERVER_USER="${SERVER_USER:-root}"
DEPLOY_DIR="/opt/kanban"
IMAGE_NAME="kanban-api"
MODE="${1:-full}"  # full | --update | --rebuild

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}→${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$SERVER_HOST" ]; then
  echo -e "${RED}FEHLER:${NC} SERVER_HOST nicht gesetzt."
  echo "  Beispiel: SERVER_HOST=147.x.x.x bash kanban_service/deploy.sh"
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Swiss Truth Kanban — Deploy auf Hostinger  ║"
echo "╚══════════════════════════════════════════════╝"
echo "  Server: ${SERVER_USER}@${SERVER_HOST}"
echo "  Modus:  ${MODE}"
echo ""

# ─── Update-Modus: nur Quellcode + Restart ────────────────────────────────────
if [ "$MODE" = "--update" ]; then
  info "Quellcode synchronisieren..."
  rsync -az --delete \
    --exclude="__pycache__" --exclude="*.pyc" \
    "${SCRIPT_DIR}/main.py" \
    "${SCRIPT_DIR}/db.py" \
    "${SCRIPT_DIR}/agents.py" \
    "${SCRIPT_DIR}/templates/" \
    "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/app/"

  info "Container neu starten..."
  ssh "${SERVER_USER}@${SERVER_HOST}" \
    "cd ${DEPLOY_DIR} && docker restart kanban-api"
  sleep 8

  HTTP=$(curl -s -o /dev/null -w "%{http_code}" "http://${SERVER_HOST}:9000/health" 2>/dev/null || echo "000")
  [ "$HTTP" = "200" ] && echo -e "   ${GREEN}✓${NC} API OK (HTTP 200)" || warn "HTTP ${HTTP}"
  exit 0
fi

# ─── Vollständiger Deploy ─────────────────────────────────────────────────────

# Schritt 1: Verzeichnis + .env auf Server
info "[1/5] Server vorbereiten..."
ssh "${SERVER_USER}@${SERVER_HOST}" bash << REMOTE
set -euo pipefail
mkdir -p ${DEPLOY_DIR}/app/templates
echo "Verzeichnis: ${DEPLOY_DIR} ✓"

# .env prüfen
if [ ! -f "${DEPLOY_DIR}/.env" ]; then
  echo ""
  echo "⚠  .env fehlt — bitte anlegen:"
  echo "   nano ${DEPLOY_DIR}/.env"
  echo ""
  echo "Inhalt:"
  echo "   ANTHROPIC_API_KEY=sk-ant-..."
  echo ""
fi
REMOTE

# Schritt 2: Dateien übertragen
info "[2/5] Dateien übertragen..."

# docker-compose.yml + Caddyfile nach /opt/kanban/
rsync -az \
  "${SCRIPT_DIR}/docker-compose.yml" \
  "${SCRIPT_DIR}/Caddyfile" \
  "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/"

# App-Quellcode nach /opt/kanban/app/
rsync -az \
  --exclude="__pycache__" --exclude="*.pyc" \
  "${SCRIPT_DIR}/main.py" \
  "${SCRIPT_DIR}/db.py" \
  "${SCRIPT_DIR}/agents.py" \
  "${SCRIPT_DIR}/requirements.txt" \
  "${SCRIPT_DIR}/Dockerfile" \
  "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/app/"

# Templates als eigenes Verzeichnis nach /opt/kanban/app/templates/
rsync -az --delete \
  "${SCRIPT_DIR}/templates/" \
  "${SERVER_USER}@${SERVER_HOST}:${DEPLOY_DIR}/app/templates/"

echo "   Fertig ✓"

# Schritt 3: Docker Image bauen (lokal oder remote)
if [ "$MODE" = "--rebuild" ] || [ "$MODE" = "full" ]; then
  info "[3/5] Docker Image bauen..."

  # Option: lokal bauen + übertragen (langsamere Leitung → auf Server bauen)
  BUILD_REMOTE="${BUILD_REMOTE:-true}"

  if [ "$BUILD_REMOTE" = "true" ]; then
    info "   Baue Image direkt auf dem Server (empfohlen)..."
    ssh "${SERVER_USER}@${SERVER_HOST}" bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}/app
echo "Build-Kontext:"
ls -la
docker build -t ${IMAGE_NAME}:latest .
echo "Image gebaut ✓"
REMOTE
  else
    info "   Baue Image lokal und übertrage..."
    cd "${SCRIPT_DIR}"
    docker build -t ${IMAGE_NAME}:latest .
    docker save ${IMAGE_NAME}:latest | gzip | \
      ssh "${SERVER_USER}@${SERVER_HOST}" "cat > /tmp/kanban-api.tar.gz"
    ssh "${SERVER_USER}@${SERVER_HOST}" \
      "docker load < /tmp/kanban-api.tar.gz && rm /tmp/kanban-api.tar.gz"
  fi
else
  info "[3/5] Image-Build übersprungen (--update Modus)"
fi

# Schritt 4: Services starten
info "[4/5] Services starten..."
ssh "${SERVER_USER}@${SERVER_HOST}" bash << REMOTE
set -euo pipefail
cd ${DEPLOY_DIR}

if [ ! -f ".env" ]; then
  echo "FEHLER: .env Datei fehlt in ${DEPLOY_DIR}/.env"
  echo "Anlegen: echo 'ANTHROPIC_API_KEY=sk-ant-...' > ${DEPLOY_DIR}/.env"
  exit 1
fi

docker compose up -d --remove-orphans
echo "Warte auf Healthcheck..."
sleep 15
docker compose ps
REMOTE
echo "   Fertig ✓"

# Schritt 5: Health Check
info "[5/5] Health Check..."
sleep 5
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "http://${SERVER_HOST}:9000/health" 2>/dev/null || echo "000")

echo ""
echo "╔══════════════════════════════════════════════╗"
if [ "$HTTP" = "200" ]; then
  echo "║   ✅  Kanban Board ist live!                 ║"
  echo "╠══════════════════════════════════════════════╣"
  echo "║                                              ║"
  echo "║   Board:  http://${SERVER_HOST}:9000/kanban       ║"
  echo "║   Health: http://${SERVER_HOST}:9000/health       ║"
  echo "║   API:    http://${SERVER_HOST}:9000/docs         ║"
  echo "║                                              ║"
else
  echo "║   ⚠️   HTTP ${HTTP} — Logs prüfen:            ║"
  echo "╠══════════════════════════════════════════════╣"
  echo "║                                              ║"
  echo "║   ssh ${SERVER_USER}@${SERVER_HOST}          ║"
  echo "║   docker logs kanban-api --tail 30           ║"
  echo "║                                              ║"
fi
echo "╚══════════════════════════════════════════════╝"
echo ""
