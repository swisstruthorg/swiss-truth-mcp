#!/bin/bash
# ─── Swiss Truth MCP — Täglicher Renewal-Check ───────────────────────────────
# Markiert abgelaufene certified Claims als 'needs_renewal'.
#
# Crontab (täglich um 02:00 Uhr Serverzeit):
#   0 2 * * * /opt/swiss-truth/deploy/cron-renewal.sh >> /opt/swiss-truth/logs/renewal.log 2>&1
#
# Einrichten:
#   chmod +x /opt/swiss-truth/deploy/cron-renewal.sh
#   (crontab -l 2>/dev/null; echo "0 2 * * * /opt/swiss-truth/deploy/cron-renewal.sh >> /opt/swiss-truth/logs/renewal.log 2>&1") | crontab -

set -euo pipefail

API_URL="https://swisstruth.org/admin/run-renewal-check"
API_KEY="${SWISS_TRUTH_API_KEY:-}"

# API-Key aus .env laden falls nicht gesetzt
if [ -z "$API_KEY" ]; then
  ENV_FILE="/opt/swiss-truth/.env"
  if [ -f "$ENV_FILE" ]; then
    API_KEY=$(grep -E '^SWISS_TRUTH_API_KEY=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '"'"'" )
  fi
fi

if [ -z "$API_KEY" ]; then
  echo "[$(date -Iseconds)] ERROR: SWISS_TRUTH_API_KEY nicht gefunden" >&2
  exit 1
fi

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL" \
  -H "X-Swiss-Truth-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  --max-time 30)

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "200" ]; then
  EXPIRED=$(echo "$BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('expired_count',0))" 2>/dev/null || echo "?")
  echo "[$(date -Iseconds)] OK — $EXPIRED Claims auf needs_renewal gesetzt"
else
  echo "[$(date -Iseconds)] ERROR — HTTP $HTTP_CODE: $BODY" >&2
  exit 1
fi
