#!/bin/bash

################################################################################
# Manual Deployment Script for Arada Intelligence OS
#
# Usage:
#   ./scripts/deploy-manual.sh                    # Deploy to Proxmox
#   ./scripts/deploy-manual.sh 192.168.1.150      # Deploy to specific IP
#   SKIP_MIGRATIONS=1 ./scripts/deploy-manual.sh  # Skip database migrations
#
################################################################################

set -e

# Configuration
PROXMOX_IP="${1:-192.168.1.200}"
PROXMOX_USER="root"
PROXMOX_KEY="${HOME}/.ssh/proxmox_deploy"
REGISTRY="ghcr.io"
IMAGE_NAME="Nebyudejenie/Amedia"
IMAGE_TAG="latest"
DOMAIN="arada.fun"
DEPLOYMENT_PATH="/opt/arada"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-0}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Arada Intelligence OS - Manual Deployment Script          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo

# Validate SSH key exists
if [ ! -f "$PROXMOX_KEY" ]; then
    echo -e "${RED}❌ SSH key not found: $PROXMOX_KEY${NC}"
    echo "   Run: ssh-keygen -t ed25519 -f ~/.ssh/proxmox_deploy"
    exit 1
fi

echo -e "${BLUE}📋 Deployment Configuration:${NC}"
echo "   Proxmox IP:      $PROXMOX_IP"
echo "   Proxmox User:    $PROXMOX_USER"
echo "   Docker Image:    $REGISTRY/$IMAGE_NAME:$IMAGE_TAG"
echo "   Domain:          $DOMAIN"
echo "   Deployment Path: $DEPLOYMENT_PATH"
echo "   Skip Migrations: $SKIP_MIGRATIONS"
echo

# Test SSH connectivity
echo -e "${YELLOW}🔍 Testing SSH connectivity...${NC}"
if ! ssh -i "$PROXMOX_KEY" -o ConnectTimeout=5 "$PROXMOX_USER@$PROXMOX_IP" "echo '✅ Connected'" > /dev/null 2>&1; then
    echo -e "${RED}❌ Cannot connect to $PROXMOX_IP${NC}"
    echo "   Check:"
    echo "   1. Proxmox VM is running"
    echo "   2. SSH key is authorized: ssh-copy-id -i $PROXMOX_KEY root@$PROXMOX_IP"
    echo "   3. Network connectivity: ping $PROXMOX_IP"
    exit 1
fi

# Test Docker connectivity on Proxmox
echo -e "${YELLOW}🐳 Testing Docker on Proxmox...${NC}"
if ! ssh -i "$PROXMOX_KEY" "$PROXMOX_USER@$PROXMOX_IP" "docker ps > /dev/null 2>&1" > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker not available on Proxmox${NC}"
    echo "   Install Docker: apt-get update && apt-get install -y docker.io"
    exit 1
fi

echo -e "${GREEN}✅ All checks passed${NC}"
echo

# Start deployment
echo -e "${BLUE}🚀 Starting deployment...${NC}"
echo

ssh -i "$PROXMOX_KEY" "$PROXMOX_USER@$PROXMOX_IP" << DEPLOY_SCRIPT
set -e

echo -e "\033[0;34m📥 Pulling latest Docker image...\033[0m"
docker pull $REGISTRY/$IMAGE_NAME:$IMAGE_TAG

echo -e "\033[0;34m📁 Navigating to deployment directory...\033[0m"
cd $DEPLOYMENT_PATH

echo -e "\033[0;34m🛑 Stopping running containers...\033[0m"
docker-compose -f docker-compose.prod.yml down || true

if [ "$SKIP_MIGRATIONS" != "1" ]; then
    echo -e "\033[0;34m📊 Running database migrations...\033[0m"
    docker-compose -f docker-compose.prod.yml run --rm api python -m alembic upgrade head
fi

echo -e "\033[0;34m🚀 Starting containers...\033[0m"
docker-compose -f docker-compose.prod.yml up -d

echo -e "\033[0;34m⏳ Waiting for API to become healthy (max 60 seconds)...\033[0m"
for i in {1..12}; do
    if curl -sf https://api.$DOMAIN/system/health > /dev/null 2>&1; then
        echo -e "\033[0;32m✅ API is healthy!\033[0m"
        break
    fi
    echo "   Attempt $i/12: Waiting..."
    sleep 5
done

echo
echo -e "\033[0;34m📊 Container Status:\033[0m"
docker-compose -f docker-compose.prod.yml ps

echo
echo -e "\033[0;32m✅ Deployment Complete!\033[0m"
echo
echo "Services:"
echo "   API:     https://api.$DOMAIN"
echo "   Metrics: https://metrics.$DOMAIN"
echo "   Grafana: https://grafana.$DOMAIN"
echo

DEPLOY_SCRIPT

# Check exit status
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Deployment successful!${NC}"
    echo
    echo -e "${BLUE}📊 Next Steps:${NC}"
    echo "   1. Check logs: ssh -i $PROXMOX_KEY $PROXMOX_USER@$PROXMOX_IP docker-compose -f $DEPLOYMENT_PATH/docker-compose.prod.yml logs -f api"
    echo "   2. Monitor dashboards: https://grafana.$DOMAIN"
    echo "   3. Run health check: curl https://api.$DOMAIN/system/health"
    exit 0
else
    echo -e "${RED}❌ Deployment failed!${NC}"
    exit 1
fi
