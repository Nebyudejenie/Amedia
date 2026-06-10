# Arada Intelligence OS — Deployment Guide

## Quick Start (Local Development)

```bash
# Clone and initialize
git clone https://github.com/arada-ai/arada-os.git
cd arada-os

# One-command setup (interactive)
make setup

# Or manually:
cp .env.example .env
# Edit .env with strong passwords
docker-compose up -d
bash api/verify.sh
```

**Access points:**
- API: http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs
- Metrics: http://127.0.0.1:8000/metrics
- MinIO Console: http://127.0.0.1:9001

## Architecture

```
Docker Compose Stack:
├── postgres (5432)      — PostgreSQL 16, 7 schemas, 9 migrations
├── redis (6379)         — Redis 7, Streams + consumer groups
├── minio (9000/9001)    — S3-compatible object storage
├── qdrant (6333)        — Vector database, 5 collections (768-dim)
├── ollama (11434)       — Local LLM inference
├── api (8000)           — FastAPI backend, 80+ endpoints
├── worker-content       — Content ingestion + normalization
├── orchestrator         — Workflow (brief→script→render→publish)
└── publisher            — Platform publishing (Twitter, YouTube, TikTok)

All services communicate over internal bridge (10.10.10.0/24).
Data persistence via named volumes.
```

## Services

### PostgreSQL (postgres)
- **Image**: postgres:16-alpine
- **Port**: 5432 (localhost only)
- **Credentials**: arada / $DB_PASSWORD
- **Volume**: postgres_data
- **Health**: pg_isready check every 10s

**Schemas:**
- auth — users, roles, workspaces, api_keys
- content — sources, raw_items, normalized_items, content_scores
- media — templates, audio_assets, video_assets
- analytics — publish_jobs, publish_results, experiments
- workflow — jobs, events (append-only)
- system — prompt_templates, feature_flags, decisions
- revenue — affiliate_links, leads, revenue_summary

### Redis (redis)
- **Image**: redis:7-alpine
- **Port**: 6379 (localhost only)
- **Volume**: redis_data
- **Health**: PING check every 10s
- **Config**: 2GB maxmemory, LRU eviction, RDB persistence

**Usage:**
- Lists: content:fetch-queue (fetch jobs)
- Key-value: health checks, caching
- Streams: (ready for consumer groups in future)

### MinIO (minio)
- **Image**: minio/latest
- **Ports**: 9000 (API), 9001 (Console)
- **Credentials**: arada / $MINIO_SECRET_KEY
- **Volume**: minio_data
- **Health**: health/live endpoint check every 10s

**Buckets:**
- arada-{workspace_id} (per-tenant video storage)

### Qdrant (qdrant)
- **Image**: qdrant/latest
- **Port**: 6333 (REST API)
- **Volume**: qdrant_data
- **Health**: /health endpoint check every 10s

**Collections** (768-dim, cosine distance):
- content_embeddings — normalized item vectors
- script_memory — script/brief vectors
- knowledge_memory — system knowledge base
- trend_memory — trend tracking
- audience_profiles — user interest profiles

### Ollama (ollama)
- **Image**: ollama/latest
- **Port**: 11434
- **Volume**: ollama_data
- **Health**: /api/tags endpoint check every 30s

**Models:**
- nomic-embed-text (for embeddings)
- llama2 (optional, for text generation)

### FastAPI (api)
- **Image**: Built from ./api/Dockerfile
- **Port**: 8000 (localhost only)
- **Health**: /system/health check every 10s
- **Depends on**: All data stores (conditional startup)

**Routes:**
- /auth/* — user registration, login, JWT, api-keys
- /content/* — sources, items, scoring
- /workflow/* — job creation, status polling, events
- /media/* — templates, rendering, publishing
- /system/health — service health status
- /metrics — Prometheus metrics

### Worker Services
All run in same Docker Compose, pull from shared PostgreSQL/Redis.

**worker-content** (Content Ingestion):
- Polls content:fetch-queue from Redis
- Fetches from RSS/JSON APIs
- Normalizes + deduplicates
- Scores items
- Updates source.last_fetched_at

**orchestrator** (Task Orchestration):
- Polls workflow.jobs by status (pending→processing)
- Processes: brief→script→render→publish
- Uses FOR UPDATE SKIP LOCKED for concurrency
- Logs append-only events

**publisher** (Platform Publishing):
- Polls analytics.publish_jobs (status=queued)
- Dispatches to Twitter, YouTube, TikTok (mock)
- Tracks results per platform
- Auto-completes when all platforms done

## Environment Variables

Required (no defaults):
- `DB_PASSWORD` — Strong PostgreSQL password
- `MINIO_SECRET_KEY` — Strong S3 secret
- `JWT_SECRET_KEY` — Min 32 chars, random string

Optional (sensible defaults):
- `DEBUG=false` — Enable debug mode
- `CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]` — CORS allowlist
- `RATE_LIMIT_CALLS=100` — Per-window rate limit
- `RATE_LIMIT_PERIOD_SECONDS=60` — Rate limit window

See `.env.example` for all options.

## Networking

Internal bridge `arada-internal` (10.10.10.0/24):
- Services communicate via service names (DNS)
- All ports bound to 127.0.0.1 (no external exposure)
- Reverse proxy (nginx/Cloudflare Tunnel) handles public traffic in production

Example connection strings:
```
postgres://arada:$DB_PASSWORD@postgres:5432/arada
redis://redis:6379/0
http://minio:9000
http://qdrant:6333
http://ollama:11434
```

## Storage

Named volumes (persist across container restarts):
- `postgres_data` — PostgreSQL WAL, tables
- `redis_data` — Redis RDB snapshots
- `minio_data` — All S3 objects
- `qdrant_data` — Vector index + metadata
- `ollama_data` — Model cache

**Backup strategy:**
- PostgreSQL: `docker-compose exec postgres pg_dump -U arada arada > backup.sql`
- MinIO: `docker-compose exec minio mc mirror minio/arada /backup`
- Full: `docker-compose down -v && docker volume rm arada-os_* && docker-compose up -d`

## Monitoring

### Health Checks
Each service has liveness checks:
```bash
make status    # docker-compose ps
make verify    # Run full health suite (api/verify.sh)
```

### Logs
```bash
make logs           # All services (streaming)
make logs-api       # API only
make logs-db        # PostgreSQL only
docker-compose logs -f [service]  # Any service
```

### Metrics
Prometheus format on `http://127.0.0.1:8000/metrics`:
```
http_requests_total[method, endpoint, status]
http_request_duration_seconds[method, endpoint]
```

## Scaling & Operations

### Add replicas (orchestrator, publisher, content worker)
```yaml
services:
  orchestrator-2:
    extends: orchestrator
    container_name: arada-orchestrator-2
    environment:
      WORKER_ID: orchestrator-2
```

### Update .env
```bash
# Edit .env
docker-compose up -d
# No migrations needed; idempotent schema
```

### Upgrade PostgreSQL
```bash
docker-compose down
docker volume create postgres_data_backup
docker run --rm -v postgres_data:/from -v postgres_data_backup:/to alpine cp -r /from /to
# Change postgres image version in docker-compose.yml
docker-compose up -d
```

### Reset everything
```bash
make clean      # Stops + removes all volumes
make setup      # Re-initializes
```

## Production Checklist

- [ ] Use strong passwords ($DB_PASSWORD, $MINIO_SECRET_KEY, $JWT_SECRET_KEY)
- [ ] Set `DEBUG=false`
- [ ] Update CORS_ORIGINS to your domain(s)
- [ ] Use persistent volumes (not ephemeral)
- [ ] Set up backup jobs (database, MinIO)
- [ ] Reverse proxy in front (nginx or Cloudflare Tunnel)
- [ ] Monitor logs and metrics (Prometheus scrape on :8000/metrics)
- [ ] Schedule database maintenance (VACUUM, ANALYZE)
- [ ] Test disaster recovery (restore from backup)

## Troubleshooting

**API won't start:**
```bash
docker-compose logs api      # Check error
docker-compose down && docker-compose up -d api postgres redis qdrant minio
```

**Database migrations failed:**
```bash
docker-compose exec postgres psql -U arada -d arada
arada=# SELECT * FROM public.schema_migrations;
```

**MinIO bucket issues:**
```bash
docker-compose exec minio mc ls minio
docker-compose exec minio mc mb minio/arada
```

**Worker not processing:**
```bash
docker-compose logs worker-content
docker-compose exec redis redis-cli LLEN content:fetch-queue
```

**Permissions error on volumes:**
```bash
docker-compose down
sudo chown -R 1000:1000 postgres_data redis_data  # Adjust UID/GID
docker-compose up -d
```

## Next Steps

- **BP3.2** — Proxmox multi-VM deployment (VM-100: core, VM-101: media)
- **BP3.3** — Kubernetes deployment (GKE, EKS, self-hosted)
- **BP4** — Reverse proxy + SSL (nginx, Cloudflare)
- **BP5** — Analytics dashboard (Grafana)
- **BP6** — Multi-tenant isolation (network policies, quotas)
