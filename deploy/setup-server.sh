#!/bin/bash
# ─── Swiss Truth MCP — Infomaniak VPS Setup (einmalig) ──────────────────────
# Ausführen als root direkt nach VPS-Erstellung:
#   bash setup-server.sh
set -euo pipefail

echo "🇨🇭  Swiss Truth MCP — Server Setup"
echo "======================================"

# ─── 1. System Update ────────────────────────────────────────────────────────
apt-get update -qq && apt-get upgrade -y -qq

# ─── 2. Docker installieren ──────────────────────────────────────────────────
echo "→ Docker installieren..."
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# ─── 3. Deploy-User anlegen (kein Root für Betrieb) ──────────────────────────
echo "→ Deploy-User 'swisstruth' anlegen..."
useradd -m -s /bin/bash swisstruth || true
usermod -aG docker swisstruth

# ─── 4. Projektverzeichnis anlegen ───────────────────────────────────────────
mkdir -p /opt/swiss-truth
chown swisstruth:swisstruth /opt/swiss-truth

# ─── 5. UFW Firewall ─────────────────────────────────────────────────────────
echo "→ Firewall konfigurieren..."
apt-get install -y -qq ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp    # HTTP  (Caddy → HTTPS redirect)
ufw allow 443/tcp   # HTTPS (Caddy)
ufw --force enable
echo "   Offene Ports: 22 (SSH), 80 (HTTP→redirect), 443 (HTTPS)"
echo "   Neo4j (7687) und API (8000) sind NUR intern erreichbar ✓"

# ─── 6. Fail2ban (Brute-Force Schutz) ────────────────────────────────────────
apt-get install -y -qq fail2ban
systemctl enable fail2ban
systemctl start fail2ban

# ─── 7. SSH Hardening ────────────────────────────────────────────────────────
sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload sshd
echo "   SSH Password-Login deaktiviert (nur SSH-Key) ✓"

echo ""
echo "✅  Server-Setup abgeschlossen!"
echo ""
echo "Nächster Schritt: deploy.sh ausführen"
