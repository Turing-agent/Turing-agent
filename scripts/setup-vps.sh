#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  Auto-Repro: VPS Setup & Firewall Configuration"
echo "=========================================================="

# Check root / sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root or with sudo: sudo ./scripts/setup-vps.sh"
  exit 1
fi

echo "==> Updating system packages..."
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release ufw

echo "==> Installing Docker and Docker Compose plugin..."
if ! command -v docker &> /dev/null; then
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable docker
systemctl start docker

echo "==> Configuring UFW Firewall for Auto-Repro..."
# Allow SSH first so maintainer is not locked out
ufw allow 22/tcp comment 'SSH'

# Allow Provisioner & Dashboard
ufw allow 4000/tcp comment 'Auto-Repro Dashboard & Provisioner'

# Allow n8n Webhook & UI
ufw allow 5678/tcp comment 'n8n Workflow Engine'

# Allow Ephemeral Container Ports (8100 - 8199)
ufw allow 8100:8199/tcp comment 'Auto-Repro Ephemeral Containers'

echo "==> Enabling UFW..."
ufw --force enable
ufw status verbose

echo "=========================================================="
echo "  VPS Setup Complete!"
echo "  - Docker: $(docker --version)"
echo "  - Firewall: Ports 22, 4000, 5678, and 8100-8199 opened."
echo "=========================================================="
