#!/usr/bin/env bash
# Setup script for Arada Intelligence OS
# Initializes environment, database, and starts services

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[1;32m'
COLOR_BLUE='\033[1;34m'
COLOR_YELLOW='\033[1;33m'

log() {
  echo -e "${COLOR_BLUE}→${COLOR_RESET} $1"
}

success() {
  echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"
}

warn() {
  echo -e "${COLOR_YELLOW}!${COLOR_RESET} $1"
}

log "Arada Intelligence OS Setup"
echo

# Check prerequisites
log "Checking prerequisites..."
command -v docker >/dev/null 2>&1 || { warn "Docker not found"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { warn "Docker Compose not found"; exit 1; }
success "Docker and Docker Compose found"
echo

# Environment setup
if [[ ! -f .env ]]; then
  log "Creating .env from template..."
  cp .env.example .env
  warn "Update .env with strong passwords before proceeding!"
  echo "Edit .env and run: $0 again"
  exit 0
fi
success ".env file exists"
echo

# Load environment
set -a
source .env
set +a

# Start services
log "Starting services..."
docker-compose up -d
success "Services started"
echo

# Wait for PostgreSQL
log "Waiting for PostgreSQL to be ready..."
max_attempts=30
attempt=0
while ! docker-compose exec -T postgres pg_isready -U arada >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "PostgreSQL failed to start"
    exit 1
  fi
  sleep 1
done
success "PostgreSQL is ready"
echo

# Run migrations
log "Running database migrations..."
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/001_extensions_and_schemas.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/002_auth.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/003_content.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/004_media.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/005_analytics.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/006_workflow.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/007_system.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/008_revenue.sql >/dev/null 2>&1 || true
docker-compose exec -T postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/009_seed.sql >/dev/null 2>&1 || true
success "Database migrations applied"
echo

# Initialize MinIO buckets
log "Initializing MinIO buckets..."
sleep 2
docker-compose exec -T minio mc mb minio/arada --ignore-existing >/dev/null 2>&1 || true
success "MinIO buckets initialized"
echo

# Initialize Qdrant collections
log "Initializing Qdrant collections..."
sleep 2
bash data/qdrant/init-collections.sh 2>&1 || warn "Qdrant collections may already exist"
success "Qdrant collections initialized"
echo

# Wait for API
log "Waiting for API to be ready..."
max_attempts=30
attempt=0
while ! curl -s http://127.0.0.1:8000/system/health >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [[ $attempt -ge $max_attempts ]]; then
    warn "API failed to start"
    exit 1
  fi
  sleep 1
done
success "API is ready"
echo

# Health check
log "Running health checks..."
bash api/verify.sh
echo

success "Setup complete! Arada Intelligence OS is running."
echo
echo "Access points:"
echo "  • API:      http://127.0.0.1:8000"
echo "  • Docs:     http://127.0.0.1:8000/docs"
echo "  • Metrics:  http://127.0.0.1:8000/metrics"
echo "  • MinIO:    http://127.0.0.1:9001 (arada / password in .env)"
echo
echo "To stop services: docker-compose down"
echo "To view logs:     docker-compose logs -f [service]"
