#!/bin/bash

################################################################################
# Proxmox VM Setup Script
#
# Installs Docker, Docker Compose, and other dependencies on Proxmox VM
# Run this once on your Proxmox VM before deploying Arada
#
# Usage:
#   ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200 << 'EOF'
#   curl -fsSL https://raw.githubusercontent.com/Nebyudejenie/Amedia/main/scripts/setup-proxmox.sh | bash
#   EOF
#
# Or copy this file to Proxmox and run:
#   bash setup-proxmox.sh
#
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Proxmox VM Setup - Docker & Dependencies                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
   echo -e "${RED}❌ This script must run as root${NC}"
   exit 1
fi

echo -e "${BLUE}📋 System Information:${NC}"
uname -a
echo

# Update system
echo -e "${YELLOW}🔄 Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

# Install dependencies
echo -e "${YELLOW}📦 Installing dependencies...${NC}"
apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    git \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    python3-pip \
    wget \
    net-tools \
    htop

# Add Docker GPG key
echo -e "${YELLOW}🔑 Adding Docker GPG key...${NC}"
curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo -e "${YELLOW}📚 Adding Docker repository...${NC}"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update apt cache
apt-get update

# Install Docker
echo -e "${YELLOW}🐳 Installing Docker...${NC}"
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start Docker
echo -e "${YELLOW}🚀 Starting Docker service...${NC}"
systemctl start docker
systemctl enable docker

# Verify Docker
echo -e "${BLUE}✅ Verifying Docker installation...${NC}"
docker --version
docker run hello-world

echo
echo -e "${BLUE}✅ Docker setup complete!${NC}"
echo

# Create deployment directory
echo -e "${YELLOW}📁 Creating deployment directory...${NC}"
mkdir -p /opt/arada
cd /opt/arada

# Create non-root user for deployment
echo -e "${YELLOW}👤 Creating deployment user...${NC}"
if ! id "arada" &>/dev/null; then
    useradd -m -s /bin/bash arada
    usermod -aG docker arada
    echo -e "${GREEN}✅ User 'arada' created${NC}"
else
    echo -e "${YELLOW}ℹ️  User 'arada' already exists${NC}"
fi

# Create docker-compose symlink for compatibility
if [ ! -f /usr/local/bin/docker-compose ]; then
    ln -s /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
    echo -e "${GREEN}✅ docker-compose symlink created${NC}"
fi

# Final verification
echo
echo -e "${BLUE}📊 Final System Check:${NC}"
echo "Docker:"
docker --version
echo "Docker Compose:"
docker-compose --version || docker compose version
echo "Available disk space:"
df -h /opt
echo

echo -e "${GREEN}✅ System setup complete!${NC}"
echo
echo -e "${BLUE}📝 Next steps:${NC}"
echo "1. Clone Arada repository:"
echo "   git clone https://github.com/Nebyudejenie/Amedia.git /opt/arada"
echo "   cd /opt/arada/arada-os"
echo
echo "2. Copy docker-compose.prod.yml:"
echo "   cp docker-compose.prod.yml /opt/arada/"
echo
echo "3. From your local machine, deploy:"
echo "   ./scripts/deploy-manual.sh 192.168.1.200"
echo
