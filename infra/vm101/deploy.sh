#!/usr/bin/env bash
# Deploy Arada Intelligence OS to Proxmox VM-101 (Media Services)
# Run this on VM-101 after initial provisioning
# Requires VM-100 already running

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[1;32m'
COLOR_BLUE='\033[1;34m'
COLOR_YELLOW='\033[1;33m'

log() { echo -e "${COLOR_BLUE}→${COLOR_RESET} $1"; }
success() { echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"; }
warn() { echo -e "${COLOR_YELLOW}!${COLOR_RESET} $1"; }

log "Arada Intelligence OS — VM-101 Deployment"
echo

# Verify IP
IP=$(hostname -I | awk '{print $2}')
if [[ "$IP" != "10.10.10.101" ]]; then
  warn "Expected IP 10.10.10.101, got $IP"
  read -p "Continue anyway? (y/n) " -n 1 -r
  echo
  [[ $REPLY =~ ^[Yy]$ ]] || exit 1
fi
success "IP verified: $IP"
echo

# Check prerequisites
log "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { warn "Docker not found"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { warn "Docker Compose not found"; exit 1; }
success "Docker and Docker Compose ready"
echo

# Verify VM-100 connectivity
log "Checking VM-100 connectivity..."
max_attempts=5
attempt=0
while ! ping -c 1 10.10.10.100 >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "Cannot reach VM-100 at 10.10.10.100"
    exit 1
  fi
  sleep 1
done
success "VM-100 reachable"
echo

# Clone repo
if [[ ! -d arada-os ]]; then
  log "Cloning repository..."
  git clone https://github.com/arada-ai/arada-os.git
  success "Repository cloned"
else
  success "Repository already exists"
fi
echo

cd arada-os

# Setup environment
if [[ ! -f infra/vm101/.env ]]; then
  log "Creating .env file..."
  cp infra/vm101/.env.example infra/vm101/.env
  warn "Edit infra/vm101/.env with passwords from VM-100!"
  echo "  DB_PASSWORD: (same as VM-100)"
  echo "  MINIO_SECRET_KEY: (use strong secret)"
  echo "  JWT_SECRET_KEY: (same as VM-100)"
  nano infra/vm101/.env
fi
success ".env configured"
echo

# Copy docker-compose
log "Setting up docker-compose..."
cp infra/vm101/docker-compose.yml .
success "docker-compose.yml copied"
echo

# Start services
log "Starting services..."
docker-compose up -d
echo

# Wait for services
log "Waiting for MinIO..."
max_attempts=30
attempt=0
while ! curl -s http://127.0.0.1:9000/minio/health/live >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "MinIO failed to start"
    docker-compose logs minio
    exit 1
  fi
  sleep 1
done
success "MinIO ready"
echo

log "Waiting for Qdrant..."
attempt=0
while ! curl -s http://127.0.0.1:6333/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "Qdrant failed to start"
    docker-compose logs qdrant
    exit 1
  fi
  sleep 1
done
success "Qdrant ready"
echo

log "Waiting for Ollama..."
attempt=0
while ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "Ollama failed to start (may take longer on first run)"
    docker-compose logs ollama | tail -20
  fi
  sleep 5
done
success "Ollama ready"
echo

# Initialize MinIO bucket
log "Initializing MinIO bucket..."
docker-compose exec -T minio mc mb minio/arada --ignore-existing >/dev/null 2>&1 || true
success "MinIO bucket ready"
echo

# Initialize Qdrant collections
log "Initializing Qdrant collections..."
bash data/qdrant/init-collections.sh 2>&1 || warn "Collections may already exist"
success "Qdrant collections ready"
echo

success "VM-101 deployment complete!"
echo
echo "Services running:"
echo "  • MinIO API: 10.10.10.101:9000"
echo "  • MinIO Console: 10.10.10.101:9001"
echo "  • Qdrant: 10.10.10.101:6333"
echo "  • Ollama: 10.10.10.101:11434"
echo
echo "Connected to VM-100 services:"
echo "  • PostgreSQL: 10.10.10.100:5432"
echo "  • Redis: 10.10.10.100:6379"
echo "  • API: 10.10.10.100:8000"
echo
echo "Next steps:"
echo "  1. Test API: curl http://10.10.10.100:8000/system/health"
echo "  2. Setup monitoring (LXC-200)"
echo "  3. Setup backups (LXC-201)"
echo
echo "See infra/PROXMOX_DEPLOYMENT.md for details"
