#!/bin/bash

################################################################################
# Proxmox Docker Setup - Simplified for Debian/Proxmox
#
# This installs Docker on Proxmox without hitting enterprise repo issues
#
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Proxmox Docker Setup (Debian/Proxmox Compatible)         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
   echo -e "${RED}❌ This script must run as root${NC}"
   exit 1
fi

echo -e "${BLUE}📋 System Information:${NC}"
cat /etc/os-release | grep "PRETTY_NAME"
uname -a
echo

# Disable enterprise repositories (they require a license)
echo -e "${YELLOW}🔧 Disabling Proxmox enterprise repositories...${NC}"
if [ -f /etc/apt/sources.list.d/pve-enterprise.list ]; then
    mv /etc/apt/sources.list.d/pve-enterprise.list /etc/apt/sources.list.d/pve-enterprise.list.bak
    echo -e "${GREEN}✅ Enterprise repos disabled${NC}"
fi

if [ -f /etc/apt/sources.list.d/ceph.list ]; then
    mv /etc/apt/sources.list.d/ceph.list /etc/apt/sources.list.d/ceph.list.bak
    echo -e "${GREEN}✅ Ceph repos disabled${NC}"
fi

# Update package list
echo -e "${YELLOW}🔄 Updating package list...${NC}"
apt-get update

# Install basic dependencies
echo -e "${YELLOW}📦 Installing dependencies...${NC}"
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    apt-transport-https \
    software-properties-common \
    git \
    wget \
    net-tools \
    htop

# Add Docker official GPG key
echo -e "${YELLOW}🔑 Adding Docker GPG key...${NC}"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

# Add Docker repository
echo -e "${YELLOW}📚 Adding Docker repository...${NC}"
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update again with Docker repo
apt-get update

# Install Docker
echo -e "${YELLOW}🐳 Installing Docker...${NC}"
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker
echo -e "${YELLOW}🚀 Starting Docker service...${NC}"
systemctl enable docker
systemctl start docker

# Verify Docker
echo -e "${BLUE}✅ Verifying Docker installation...${NC}"
echo "Docker version:"
docker --version
echo "Docker Compose version:"
docker-compose --version

# Test Docker works
echo -e "${YELLOW}🧪 Testing Docker...${NC}"
if docker run --rm hello-world > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Docker is working correctly${NC}"
else
    echo -e "${RED}❌ Docker test failed${NC}"
    exit 1
fi

# Create deployment directory
echo -e "${YELLOW}📁 Creating deployment directory...${NC}"
mkdir -p /opt/arada
chmod 755 /opt/arada

# Summary
echo
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo
echo -e "${BLUE}System Status:${NC}"
docker --version
docker-compose --version
echo "Disk space available: $(df -h /opt | tail -1 | awk '{print $4}')"
echo
echo -e "${BLUE}📝 Next steps:${NC}"
echo "1. Create docker-compose.prod.yml in /opt/arada"
echo "2. From your local machine, run: ./scripts/deploy-manual.sh"
echo
