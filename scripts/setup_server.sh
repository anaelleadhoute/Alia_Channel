#!/bin/bash
# AL.IA Channel — Server Setup Script
# Run once on a fresh Ubuntu 24.04 Hetzner VPS
# Usage: bash setup_server.sh

set -e
echo "=== AL.IA Channel — Server Setup ==="

# ─── 1. System update ─────────────────────────────────────────────────
echo "[1/7] Updating system..."
apt-get update -qq && apt-get upgrade -y -qq

# ─── 2. Install dependencies ──────────────────────────────────────────
echo "[2/7] Installing dependencies..."
apt-get install -y -qq \
  curl git ufw fail2ban \
  ca-certificates gnupg lsb-release

# ─── 3. Install Docker ────────────────────────────────────────────────
echo "[3/7] Installing Docker..."
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin

# ─── 4. Firewall (UFW) ────────────────────────────────────────────────
echo "[4/7] Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ─── 5. Fail2ban (brute-force protection) ────────────────────────────
echo "[5/7] Enabling fail2ban..."
systemctl enable fail2ban
systemctl start fail2ban

# ─── 6. Clone project ─────────────────────────────────────────────────
echo "[6/7] Cloning project from GitHub..."
git clone https://github.com/anaelleadhoute/Alia_Channel.git /opt/alia-channel
cd /opt/alia-channel
cp .env.template .env
echo "→ Fill in /opt/alia-channel/.env with your credentials before continuing"

# ─── 7. Docker auto-start ─────────────────────────────────────────────
echo "[7/7] Enabling Docker on boot..."
systemctl enable docker
systemctl start docker

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy project files to /opt/alia-channel"
echo "  2. cp .env.template .env && fill in your credentials"
echo "  3. Run: bash scripts/init_https.sh (after setting your domain DNS)"
echo "  4. Run: docker compose up -d"
