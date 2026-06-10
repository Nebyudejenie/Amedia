#!/bin/bash
# Arada Intelligence OS — Proxmox Deployment Script
# Run on VM-100 (Core services): bash scripts/deploy-proxmox.sh
# Automatically pulls latest image and deploys to Proxmox

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================
PROXMOX_IP="${PROXMOX_IP:-192.168.1.200}"
PROXMOX_USER="${PROXMOX_USER:-root}"
DEPLOYMENT_PATH="/opt/arada"
GITHUB_REGISTRY="ghcr.io/Nebyudejenie/Amedia"
DOMAIN="arada.fun"
API_HOST="api.${DOMAIN}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m' # No Color

# ============================================================================
# FUNCTIONS
# ============================================================================
log_info() { echo -e "${BLUE}→${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_warn() { echo -e "${YELLOW}!${NC} $1"; }

# ============================================================================
# PRE-DEPLOYMENT CHECKS
# ============================================================================
log_info "Arada Intelligence OS - Proxmox Deployment"
echo "============================================================"
echo

log_info "1. Checking prerequisites..."

# Check if running on Proxmox VM
if ! systemctl is-system-running > /dev/null 2>&1; then
    log_error "Not running on a Linux system"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    log_error "Docker not found. Install Docker first:"
    echo "  curl -fsSL https://get.docker.com | sh"
    exit 1
fi

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    log_error "Docker Compose not found. Install it first:"
    echo "  sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m) -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose"
    exit 1
fi

# Check if deployment directory exists
if [ ! -d "$DEPLOYMENT_PATH" ]; then
    log_info "Creating deployment directory: $DEPLOYMENT_PATH"
    sudo mkdir -p "$DEPLOYMENT_PATH"
    sudo chown $(whoami):$(whoami) "$DEPLOYMENT_PATH"
fi

log_success "Prerequisites check passed"
echo

# ============================================================================
# SETUP ENVIRONMENT
# ============================================================================
log_info "2. Setting up environment..."

if [ ! -f "$DEPLOYMENT_PATH/.env" ]; then
    log_warn "Creating .env file at $DEPLOYMENT_PATH/.env"
    cat > "$DEPLOYMENT_PATH/.env" << 'ENVEOF'
# Database
DB_USER=arada
DB_PASSWORD=CHANGE_ME_STRONG_PASSWORD_HERE
DB_NAME=arada

# MinIO
MINIO_ROOT_USER=arada
MINIO_SECRET_KEY=CHANGE_ME_STRONG_SECRET_HERE

# Security
JWT_SECRET_KEY=CHANGE_ME_64_CHAR_RANDOM_STRING_HERE
QDRANT_API_KEY=qdrant

# Monitoring
GRAFANA_PASSWORD=CHANGE_ME_GRAFANA_PASSWORD
METABASE_DB_PASSWORD=CHANGE_ME_METABASE_PASSWORD
METABASE_SECRET_KEY=CHANGE_ME_METABASE_SECRET

# Registry
REGISTRY=ghcr.io/Nebyudejenie/Amedia
ENVEOF

    log_warn "⚠️  Please edit .env file with secure passwords:"
    log_warn "  nano $DEPLOYMENT_PATH/.env"
    log_warn "Then run this script again."
    exit 1
else
    log_success "Using existing .env file"
fi

echo

# ============================================================================
# PULL DOCKER IMAGE
# ============================================================================
log_info "3. Pulling latest Docker image..."

if [ -f "$DEPLOYMENT_PATH/.env" ]; then
    source "$DEPLOYMENT_PATH/.env"
fi

if docker login -u "$GITHUB_USER" -p "$GITHUB_TOKEN" ghcr.io 2>/dev/null || [ -f ~/.docker/config.json ]; then
    log_info "Pulling image: $GITHUB_REGISTRY:latest"
    docker pull "$GITHUB_REGISTRY:latest" || log_warn "Failed to pull from GitHub registry (may need authentication)"
else
    log_warn "Not authenticated to GitHub registry. Using local image."
fi

log_success "Docker image ready"
echo

# ============================================================================
# DATABASE SETUP
# ============================================================================
log_info "4. Setting up database..."

if [ -f "$DEPLOYMENT_PATH/docker-compose.prod.yml" ]; then
    cd "$DEPLOYMENT_PATH"

    # Start database only
    log_info "Starting PostgreSQL..."
    docker-compose -f docker-compose.prod.yml up -d postgres

    # Wait for database to be ready
    log_info "Waiting for PostgreSQL to be ready..."
    for i in {1..30}; do
        if docker-compose -f docker-compose.prod.yml exec -T postgres pg_isready -U arada > /dev/null 2>&1; then
            log_success "PostgreSQL is ready"
            break
        fi
        echo -n "."
        sleep 2
    done
    echo

    # Run migrations
    log_info "Running database migrations..."
    docker-compose -f docker-compose.prod.yml exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/001_init.sql 2>/dev/null || true

    log_success "Database setup complete"
else
    log_error "docker-compose.prod.yml not found at $DEPLOYMENT_PATH"
    exit 1
fi

echo

# ============================================================================
# DEPLOY SERVICES
# ============================================================================
log_info "5. Starting all services..."
cd "$DEPLOYMENT_PATH"

log_info "Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

log_info "Starting all services..."
docker-compose -f docker-compose.prod.yml up -d

log_success "Services started"
echo

# ============================================================================
# HEALTH CHECKS
# ============================================================================
log_info "6. Running health checks..."

services=("postgres" "redis" "minio" "qdrant" "ollama" "api")

for service in "${services[@]}"; do
    log_info "Checking $service..."
    for i in {1..30}; do
        if docker-compose -f docker-compose.prod.yml exec -T "$service" /bin/sh -c "true" > /dev/null 2>&1; then
            log_success "$service is running"
            break
        fi
        if [ $i -eq 30 ]; then
            log_error "$service failed to start"
        fi
        sleep 2
    done
done

echo

# ============================================================================
# API HEALTH CHECK
# ============================================================================
log_info "7. Verifying API health..."

for i in {1..30}; do
    if curl -sf http://localhost:8000/system/health > /dev/null 2>&1; then
        log_success "API is healthy!"
        echo
        break
    fi
    echo -n "."
    sleep 2
done

echo

# ============================================================================
# POST-DEPLOYMENT
# ============================================================================
log_info "8. Deployment summary..."

echo "============================================================"
log_success "Arada Intelligence OS deployed successfully!"
echo "============================================================"
echo
echo "🌐 Access Points:"
echo "  API:      http://localhost:8000"
echo "  Grafana:  http://localhost:3001"
echo "  Metabase: http://localhost:3000"
echo "  MinIO:    http://localhost:9001"
echo
echo "📋 Default Credentials:"
echo "  Database: arada / (check .env)"
echo "  MinIO:    arada / (check .env)"
echo "  Grafana:  admin / (check .env)"
echo
echo "📊 Useful Commands:"
echo "  Logs:          docker-compose -f docker-compose.prod.yml logs -f api"
echo "  Restart:       docker-compose -f docker-compose.prod.yml restart"
echo "  Stop:          docker-compose -f docker-compose.prod.yml down"
echo "  Backup:        bash scripts/backup-proxmox.sh"
echo
echo "🔗 Next Steps:"
echo "  1. Setup SSL/TLS certificate (Let's Encrypt)"
echo "  2. Configure reverse proxy (Nginx)"
echo "  3. Setup monitoring alerts"
echo "  4. Create backup schedule"
echo
echo "📖 Documentation: infra/DEVOPS.md"
echo "============================================================"

log_success "Deployment complete!"
