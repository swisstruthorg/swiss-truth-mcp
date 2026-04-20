#!/bin/bash
# ─── Swiss Truth MCP — Migration: Infomaniak → Hostinger KVM 4 ───────────────
#
# Ausführen von deinem Mac:
#   SERVER_OLD=<infomaniak-ip>  SERVER_NEW=<hostinger-ip>  bash deploy/migrate-to-hostinger.sh
#
# Voraussetzungen:
#   - SSH-Key auf beiden Servern hinterlegt (kein Passwort-Prompt)
#   - Docker läuft bereits auf Hostinger KVM 4
#   - .env Datei auf Hostinger unter /opt/swiss-truth/.env vorhanden (s. Schritt 0)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ─── Konfiguration — HIER ANPASSEN ───────────────────────────────────────────
SERVER_OLD="${SERVER_OLD:-}"       # Infomaniak-IP, z.B. 185.x.x.x
SERVER_NEW="${SERVER_NEW:-}"       # Hostinger-IP,  z.B. 147.x.x.x
USER_OLD="${USER_OLD:-swisstruth}" # SSH-User Infomaniak
USER_NEW="${USER_NEW:-root}"       # SSH-User Hostinger (meistens root)
DEPLOY_DIR="/opt/swiss-truth"
IMAGE_NAME="swiss-truth-api"
DOMAIN="${DOMAIN:-swisstruth.org}"
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}→${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $*"; }
error() { echo -e "${RED}✗${NC}  $*" >&2; }

# ─── Pflichtfelder prüfen ─────────────────────────────────────────────────────
if [ -z "$SERVER_OLD" ] || [ -z "$SERVER_NEW" ]; then
  error "SERVER_OLD und SERVER_NEW müssen gesetzt sein."
  echo "  Beispiel: SERVER_OLD=185.x.x.x SERVER_NEW=147.x.x.x bash deploy/migrate-to-hostinger.sh"
  exit 1
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Swiss Truth MCP — Infomaniak → Hostinger Migration       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo "  Quelle  (Infomaniak): ${USER_OLD}@${SERVER_OLD}"
echo "  Ziel    (Hostinger):  ${USER_NEW}@${SERVER_NEW}"
echo "  Domain:               ${DOMAIN}"
echo ""
warn "Stelle sicher dass die .env auf Hostinger unter ${DEPLOY_DIR}/.env liegt!"
echo ""
read -p "Weiter? (Enter/Ctrl+C) "

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 1 — Hostinger: Verzeichnisse + User anlegen
# ═══════════════════════════════════════════════════════════════════════════════
info "[1/7] Hostinger: Verzeichnisse anlegen..."
ssh "${USER_NEW}@${SERVER_NEW}" bash << 'REMOTE'
set -euo pipefail
# Deploy-User anlegen (falls noch nicht vorhanden)
id swisstruth &>/dev/null || {
  useradd -m -s /bin/bash swisstruth
  usermod -aG docker swisstruth
  echo "User 'swisstruth' angelegt und docker-Gruppe hinzugefügt."
}
# Projektverzeichnis
mkdir -p /opt/swiss-truth/logs
chown -R swisstruth:swisstruth /opt/swiss-truth
# Firewall (ufw falls verfügbar)
if command -v ufw &>/dev/null; then
  ufw allow 22/tcp  2>/dev/null || true
  ufw allow 80/tcp  2>/dev/null || true
  ufw allow 443/tcp 2>/dev/null || true
  ufw --force enable 2>/dev/null || true
  echo "Firewall: Port 22/80/443 geöffnet."
fi
echo "Hostinger-Vorbereitung OK"
REMOTE
echo "   Fertig ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 2 — Konfigurationsdateien übertragen
# ═══════════════════════════════════════════════════════════════════════════════
info "[2/7] Konfigurationsdateien zu Hostinger übertragen..."
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
rsync -az --progress \
  "${REPO_ROOT}/docker-compose.prod.yml" \
  "${REPO_ROOT}/Caddyfile" \
  "${REPO_ROOT}/deploy/" \
  "${USER_NEW}@${SERVER_NEW}:${DEPLOY_DIR}/"
echo "   Fertig ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 3 — Docker Image bauen und zu Hostinger übertragen
# ═══════════════════════════════════════════════════════════════════════════════
info "[3/7] Docker Image bauen (lokal)..."
cd "${REPO_ROOT}"
docker build -t ${IMAGE_NAME}:latest .
echo "   Image gebaut ✓"

info "   Image exportieren und übertragen (~500MB, dauert 2-5 Min.)..."
docker save ${IMAGE_NAME}:latest | gzip | ssh "${USER_NEW}@${SERVER_NEW}" \
  "cat > /tmp/swiss-truth-api.tar.gz"
echo "   Image übertragen ✓"

ssh "${USER_NEW}@${SERVER_NEW}" bash << 'REMOTE'
echo "Image laden..."
docker load < /tmp/swiss-truth-api.tar.gz
rm /tmp/swiss-truth-api.tar.gz
echo "Image geladen ✓"
REMOTE

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 4 — Neo4j Backup auf Infomaniak erstellen
# ═══════════════════════════════════════════════════════════════════════════════
info "[4/7] Neo4j Backup auf Infomaniak erstellen..."
ssh "${USER_OLD}@${SERVER_OLD}" bash << 'REMOTE'
set -euo pipefail
BACKUP_PATH="/tmp/neo4j-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${BACKUP_PATH}"

# Neo4j Container stoppen für konsistentes Backup
echo "Neo4j Container kurz stoppen..."
docker stop swiss-truth-neo4j 2>/dev/null || true
sleep 3

# Volume direkt sichern (zuverlässiger als neo4j-admin dump)
VOLUME_PATH=$(docker volume inspect swiss-truth-mcp_neo4j_data \
  --format '{{.Mountpoint}}' 2>/dev/null || \
  docker volume inspect swiss_truth_mcp_neo4j_data \
  --format '{{.Mountpoint}}' 2>/dev/null || echo "")

if [ -n "${VOLUME_PATH}" ] && [ -d "${VOLUME_PATH}" ]; then
  echo "Volume-Pfad: ${VOLUME_PATH}"
  tar -czf "${BACKUP_PATH}/neo4j-data.tar.gz" -C "${VOLUME_PATH}" .
  echo "Volume-Backup erstellt ✓"
else
  echo "Fallback: neo4j-admin dump..."
  docker run --rm \
    -v swiss-truth-mcp_neo4j_data:/data:ro \
    -v "${BACKUP_PATH}":/backup \
    neo4j:5.26-community \
    neo4j-admin database dump neo4j --to-path=/backup --overwrite-destination=true
fi

# Neo4j wieder starten
docker start swiss-truth-neo4j 2>/dev/null || true
echo "Neo4j wieder gestartet ✓"

ls -lh "${BACKUP_PATH}/"
echo "BACKUP_PATH=${BACKUP_PATH}" > /tmp/backup_path.txt
REMOTE

BACKUP_PATH=$(ssh "${USER_OLD}@${SERVER_OLD}" "cat /tmp/backup_path.txt | cut -d= -f2")
echo "   Backup-Pfad: ${BACKUP_PATH} ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 5 — Neo4j Backup zu Hostinger übertragen
# ═══════════════════════════════════════════════════════════════════════════════
info "[5/7] Neo4j Backup zu Hostinger übertragen..."
# Direkt von Server zu Server (kein Umweg über Mac)
ssh "${USER_OLD}@${SERVER_OLD}" \
  "tar -czf - ${BACKUP_PATH}" | \
  ssh "${USER_NEW}@${SERVER_NEW}" \
  "tar -xzf - -C /tmp && echo 'Backup empfangen'"
echo "   Übertragen ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 6 — Hostinger: Services starten + Neo4j Restore
# ═══════════════════════════════════════════════════════════════════════════════
info "[6/7] Hostinger: Services starten und Daten wiederherstellen..."
BACKUP_BASENAME=$(basename "${BACKUP_PATH}")
ssh "${USER_NEW}@${SERVER_NEW}" bash << REMOTE
set -euo pipefail
cd /opt/swiss-truth

# .env prüfen
if [ ! -f ".env" ]; then
  echo "FEHLER: .env Datei fehlt in /opt/swiss-truth/.env"
  echo "Erstelle sie mit: nano /opt/swiss-truth/.env"
  exit 1
fi

# Neo4j zuerst starten (ohne API)
echo "Neo4j starten..."
docker compose -f docker-compose.prod.yml up -d neo4j
echo "Warte 40s auf Neo4j-Start..."
sleep 40

# Restore
BACKUP_DIR="/tmp/${BACKUP_BASENAME}"
if [ -f "\${BACKUP_DIR}/neo4j-data.tar.gz" ]; then
  echo "Volume-Restore..."
  # Neo4j stoppen für Restore
  docker compose -f docker-compose.prod.yml stop neo4j
  VOLUME_PATH=\$(docker volume inspect swiss-truth-mcp_neo4j_data \
    --format '{{.Mountpoint}}' 2>/dev/null || \
    docker volume inspect swiss_truth_mcp_neo4j_data \
    --format '{{.Mountpoint}}' 2>/dev/null || echo "")
  if [ -z "\${VOLUME_PATH}" ]; then
    # Volume noch nicht existiert — anlegen via compose
    docker compose -f docker-compose.prod.yml up --no-start neo4j
    VOLUME_PATH=\$(docker volume inspect swiss-truth-mcp_neo4j_data --format '{{.Mountpoint}}')
  fi
  tar -xzf "\${BACKUP_DIR}/neo4j-data.tar.gz" -C "\${VOLUME_PATH}"
  docker compose -f docker-compose.prod.yml start neo4j
  sleep 30
  echo "Volume-Restore abgeschlossen ✓"
else
  echo "Dump-Restore..."
  NEO4J_PASS=\$(grep NEO4J_PASSWORD .env | cut -d= -f2 | tr -d '"')
  docker run --rm \
    -v swiss-truth-mcp_neo4j_data:/data \
    -v "\${BACKUP_DIR}":/backup:ro \
    neo4j:5.26-community \
    neo4j-admin database load neo4j --from-path=/backup --overwrite-destination=true
  echo "Dump-Restore abgeschlossen ✓"
fi

# Alle Services starten
echo "Alle Services starten..."
docker compose -f docker-compose.prod.yml up -d
sleep 20

# Status
docker compose -f docker-compose.prod.yml ps
echo ""
echo "Services gestartet ✓"

# Cron für Renewal-Check einrichten
chmod +x /opt/swiss-truth/deploy/cron-renewal.sh 2>/dev/null || true
(crontab -u swisstruth -l 2>/dev/null | grep -v cron-renewal; \
  echo "0 2 * * * /opt/swiss-truth/deploy/cron-renewal.sh >> /opt/swiss-truth/logs/renewal.log 2>&1") \
  | crontab -u swisstruth - 2>/dev/null || true
echo "Cron-Job eingerichtet ✓"

# Cleanup
rm -rf "\${BACKUP_DIR}" 2>/dev/null || true
REMOTE
echo "   Fertig ✓"

# ═══════════════════════════════════════════════════════════════════════════════
# SCHRITT 7 — Health Checks
# ═══════════════════════════════════════════════════════════════════════════════
info "[7/7] Health Checks..."
echo ""

# API über IP prüfen (vor DNS-Umschaltung)
API_STATUS=$(curl -sk -o /dev/null -w "%{http_code}" \
  "http://${SERVER_NEW}/health" 2>/dev/null || echo "000")

if [ "$API_STATUS" = "200" ]; then
  echo -e "   ${GREEN}✓${NC} API erreichbar auf Hostinger (HTTP 200)"
else
  warn "API antwortet mit HTTP ${API_STATUS} — Logs prüfen:"
  echo "   ssh ${USER_NEW}@${SERVER_NEW} 'docker logs swiss-truth-api --tail 30'"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Migration abgeschlossen!                                 ║"
echo "╠════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║   DNS-Umschaltung (letzter Schritt):                       ║"
echo "║                                                            ║"
echo "║   Infomaniak DNS → A-Record ändern:                        ║"
echo "║     ${DOMAIN}       →  ${SERVER_NEW}       ║"
echo "║     n8n.${DOMAIN}  →  ${SERVER_NEW}       ║"
echo "║                                                            ║"
echo "║   TTL auf 300 (5 Min) setzen vor der Umschaltung.          ║"
echo "║   Caddy holt HTTPS-Zertifikat automatisch (~30 Sek).       ║"
echo "║                                                            ║"
echo "║   Verifikation nach DNS-Propagierung:                      ║"
echo "║     curl https://${DOMAIN}/health                   ║"
echo "║     curl https://${DOMAIN}/kanban                   ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
