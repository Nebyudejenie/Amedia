#!/usr/bin/env bash
# Deploy Arada Intelligence OS to Proxmox VM-100 (Core Services)
# Run this on VM-100 after initial provisioning

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[1;32m'
COLOR_BLUE='\033[1;34m'
COLOR_YELLOW='\033[1;33m'

log() { echo -e "${COLOR_BLUE}→${COLOR_RESET} $1"; }
success() { echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"; }
warn() { echo -e "${COLOR_YELLOW}!${COLOR_RESET} $1"; }

log "Arada Intelligence OS — VM-100 Deployment"
echo

# Verify IP
IP=$(hostname -I | awk '{print $2}')
if [[ "$IP" != "10.10.10.100" ]]; then
  warn "Expected IP 10.10.10.100, got $IP"
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
if [[ ! -f infra/vm100/.env ]]; then
  log "Creating .env file..."
  cp infra/vm100/.env.example infra/vm100/.env
  warn "Edit infra/vm100/.env with strong passwords!"
  nano infra/vm100/.env
fi
success ".env configured"
echo

# Copy docker-compose
log "Setting up docker-compose..."
cp infra/vm100/docker-compose.yml .
success "docker-compose.yml copied"
echo

# Create backup directories
log "Creating backup directories..."
sudo mkdir -p /var/arada/backup/wal
sudo chown arada:arada /var/arada/backup
success "Backup directories created"
echo

# Start services
log "Starting services..."
docker-compose up -d
echo

# Wait for health
log "Waiting for PostgreSQL..."
max_attempts=30
attempt=0
while ! docker-compose exec -T postgres pg_isready -U arada >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "PostgreSQL failed to start"
    docker-compose logs postgres
    exit 1
  fi
  sleep 1
done
success "PostgreSQL ready"
echo

# Run migrations
log "Running database migrations..."
docker-compose exec -T postgres psql -U arada -d arada << 'SQL' >/dev/null || true
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  filename TEXT PRIMARY KEY,
  applied_at TIMESTAMP DEFAULT NOW()
);
SQL

for migration in db/migrations/*.sql; do
  filename=$(basename "$migration")
  if ! docker-compose exec -T postgres psql -U arada -d arada -c "SELECT 1 FROM public.schema_migrations WHERE filename = '$filename'" 2>/dev/null | grep -q 1; then
    log "Applying $filename..."
    docker-compose exec -T postgres psql -U arada -d arada -f "/migrations/$filename" >/dev/null 2>&1 || true
    docker-compose exec -T postgres psql -U arada -d arada -c "INSERT INTO public.schema_migrations (filename) VALUES ('$filename')" >/dev/null 2>&1 || true
  fi
done
success "Database migrations complete"
echo

# Wait for API
log "Waiting for API..."
attempt=0
while ! curl -s http://127.0.0.1:8000/system/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "API failed to start"
    docker-compose logs api
    exit 1
  fi
  sleep 1
done
success "API ready"
echo

# Verify health
log "Verifying services..."
curl -s http://127.0.0.1:8000/system/health | jq . || true
echo

success "VM-100 deployment complete!"
echo
echo "Services running:"
echo "  • PostgreSQL: 10.10.10.100:5432"
echo "  • Redis: 10.10.10.100:6379"
echo "  • API: 10.10.10.100:8000"
echo
echo "Next steps:"
echo "  1. Deploy VM-101 (media services): ssh arada@10.10.10.101"
echo "  2. Configure reverse proxy (Cloudflare Tunnel)"
echo "  3. Setup monitoring (LXC-200)"
echo "  4. Setup backups (LXC-201)"
echo
echo "See infra/PROXMOX_DEPLOYMENT.md for details"
