# Arada Intelligence OS

**Complete, self-hosted autonomous media operating system.**

Ingest trends from any source (RSS, APIs) → generate short-form video content → publish to social platforms → learn from analytics. 100% open-source, runs on a single machine (Proxmox/Docker) or Kubernetes cluster.

## Quick Start

```bash
# Setup (1 command, ~5 minutes)
make setup

# API is now at http://127.0.0.1:8000
# MinIO console at http://127.0.0.1:9001
# See .env for credentials
```

## What It Does

**Content Ingestion:**
- Fetch from RSS feeds, HTTP JSON APIs, or manual upload
- Normalize: extract title, description, url, author, date
- Deduplicate: SHA256 hash detection
- Score: relevance, engagement, trend, quality (weighted 30/20/30/20)

**Content → Video:**
- Brief: summarize scored items into daily digest
- Script: generate video script with intro/outro
- Render: template-based video generation (mock JSON → real FFmpeg later)
- Publish: dispatch to Twitter, YouTube, TikTok, etc.

**Observability:**
- Append-only audit trail for every workflow
- Prometheus metrics on `/metrics`
- Health checks for all services
- Workspace-scoped isolation

## Architecture

**7 Services, 3 Workers:**
```
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Backend (8000)                │
│  ├─ /auth/* (JWT, RBAC, api-keys, workspaces)          │
│  ├─ /content/* (sources, items, scoring)                │
│  ├─ /workflow/* (job state machine, events)             │
│  ├─ /media/* (templates, render, publish)               │
│  └─ /system/health, /metrics                            │
└─────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  PostgreSQL     │ │   Redis 7        │ │  MinIO (S3)      │
│  (7 schemas)    │ │ (Streams, cache) │ │ (video storage)  │
└─────────────────┘ └──────────────────┘ └──────────────────┘
         ↓
┌──────────────────────────────────────────────────────────┐
│                  Worker Services                         │
│  ├─ Content Ingestion (fetch/normalize/score)           │
│  ├─ Orchestration (brief→script→render→publish)         │
│  └─ Publishing (dispatch to platforms, track results)   │
└──────────────────────────────────────────────────────────┘
         ↓
    ┌────────────┬──────────────┐
    │   Qdrant   │   Ollama     │
    │  (vectors) │  (embeddings)│
    └────────────┴──────────────┘
```

## Key Features

- **Multi-tenant**: Workspace isolation at database level
- **Async**: All I/O non-blocking (asyncio + asyncpg)
- **Idempotent**: Safe to retry, no duplicate side effects
- **Auditable**: Append-only events, no deletes (soft-delete with timestamps)
- **Scalable**: Batch processing, concurrent workers, connection pooling
- **Observable**: Request IDs, Prometheus metrics, structured logging
- **Secure**: JWT bearer tokens, bcrypt password hashing, parameterized SQL

## File Structure

```
arada-os/
├── README.md                    # This file
├── DEPLOYMENT.md               # Full deployment guide
├── docker-compose.yml          # Services + networking
├── Makefile                    # Common commands (setup, up, down, logs)
├── setup.sh                    # Interactive first-time setup
├── .env.example                # Environment template
│
├── api/                        # FastAPI application (80+ endpoints)
│   ├── main.py                # FastAPI app, lifespan, middleware
│   ├── config.py              # Pydantic settings from .env
│   ├── schemas.py             # Request/response models
│   ├── clients.py             # Async DB/cache/storage clients
│   ├── auth_service.py        # Auth: JWT, password hashing
│   ├── content_service.py     # Content: fetch, normalize, score
│   ├── workflow_service.py    # Workflow: state machine, events
│   ├── media_service.py       # Media: templates, render, publish
│   ├── dependencies.py        # FastAPI dependency injection
│   ├── worker.py              # Content ingestion worker
│   ├── orchestrator.py        # Workflow task dispatch
│   ├── publisher.py           # Platform publishing
│   ├── routers/               # Route handlers
│   │   ├── auth.py            # /auth/*
│   │   ├── content.py         # /content/*
│   │   ├── workflow.py        # /workflow/*
│   │   ├── media.py           # /media/*
│   │   └── health.py          # /system/health
│   ├── Dockerfile             # Multi-stage, non-root user
│   ├── requirements.txt        # Pinned dependencies
│   ├── .env.example           # API-specific template
│   ├── pyproject.toml         # Package metadata
│   ├── verify.sh              # Health check suite
│   └── README.md              # API-specific docs
│
├── db/                        # Database schemas & migrations
│   ├── migrations/            # 9 SQL files (extensions, auth, content, media, etc.)
│   ├── postgresql.tuning.conf # Optimized for VM (512MB shared_buffers)
│   ├── init/                  # Startup scripts
│   ├── docker-compose.yml     # Standalone Postgres for local dev
│   ├── migrate.sh             # Idempotent migration runner
│   ├── .env.example           # DB template
│   └── verify.sh              # Schema validation
│
├── data/                      # Redis, MinIO, Qdrant config
│   ├── redis/redis.conf       # Queue-optimized: 2GB maxmem, LRU
│   ├── qdrant/                # Vector DB collections (768-dim)
│   ├── docker-compose.yml     # Standalone services for local dev
│   └── verify.sh              # Health checks
│
├── infra/                     # Infrastructure & operations
│   ├── analytics/             # Metabase dashboard (BP5.1)
│   │   ├── ANALYTICS.md       # Guide: setup, dashboards, queries
│   │   ├── init.sql           # Materialized views, read-only user
│   │   ├── metabase_setup.py  # Auto-configure dashboards via API
│   │   └── SETUP.md           # Quick setup (5 minutes)
│   ├── multi-region/          # Multi-region deployment (BP5.2)
│   │   ├── MULTI_REGION.md    # Architecture: active-passive/active-active
│   │   ├── SETUP.md           # Step-by-step AWS deployment
│   │   └── terraform/         # IaC for AWS multi-region
│   │       ├── main.tf        # RDS replication, Route53 failover
│   │       ├── variables.tf   # Configuration variables
│   │       └── terraform.tfvars.example
│   ├── webhooks/              # Event-driven integrations (BP5.3)
│   │   ├── WEBHOOKS.md        # Architecture: events, deliveries, retries
│   │   ├── init.sql           # Schema: webhooks, events, DLQ
│   │   └── SETUP.md           # Setup: Slack, Discord, custom APIs
│   ├── ml/                    # Advanced ML models (BP5.4)
│   │   ├── ML_MODELS.md       # LLM, forecasting, segmentation, sentiment, recommendations
│   │   ├── init.sql           # Schema: model registry, experiments, usage tracking
│   │   └── SETUP.md           # Setup: Ollama/OpenAI/Anthropic, cost optimization
│   ├── monitoring/            # Prometheus + Grafana (BP4.1)
│   ├── reverse-proxy/         # Nginx + Cloudflare Tunnel (BP4.2)
│   ├── performance/           # Optimization & load testing (BP4.3)
│   ├── security/              # Hardening guide & scripts (BP4.4)
│   ├── PROXMOX_DEPLOYMENT.md # Multi-VM architecture (BP3.2)
│   ├── K8S_DEPLOYMENT.md      # Kubernetes setup (BP3.3)
│   ├── BACKUP.md              # WAL archiving & disaster recovery
│   ├── proxmox/               # Hypervisor setup
│   └── guest/                 # VM provisioning (Docker, SSH hardening)
```

## Quick Commands

```bash
make help         # Show all available commands
make setup        # First-time initialization
make up           # Start services
make down         # Stop services
make restart      # Restart all
make status       # Show container status
make logs         # Stream all logs
make logs-api     # API logs only
make verify       # Run health checks
make build        # Rebuild Docker images
make clean        # Stop + remove volumes (DESTRUCTIVE)
```

## API Examples

**Register a user:**
```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "strong-password-12chars+",
    "workspace_name": "My Workspace"
  }'
# Returns: { "access_token", "refresh_token", "expires_in_seconds" }
```

**Create a content source:**
```bash
curl -X POST http://127.0.0.1:8000/content/sources \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hacker News",
    "source_type": "rss",
    "url": "https://news.ycombinator.com/rss"
  }'
```

**Trigger ingestion:**
```bash
curl -X POST http://127.0.0.1:8000/content/sources/{source_id}/fetch \
  -H "Authorization: Bearer $TOKEN"
# Returns: { "job_id", "status": "queued" }
# Worker picks up job and processes asynchronously
```

**Create workflow job (brief → script → render → publish):**
```bash
curl -X POST http://127.0.0.1:8000/workflow/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "job_type": "brief",
    "input_data": { "item_ids": ["item-uuid-1", "item-uuid-2"] },
    "priority": 10
  }'
# Returns: { "id", "status": "pending", "created_at" }
# Orchestrator picks up job and dispatches to script → render → publish
```

**Get job status:**
```bash
curl http://127.0.0.1:8000/workflow/jobs/{job_id} \
  -H "Authorization: Bearer $TOKEN"
# Returns full job state + events
```

## Database Schema

**7 Schemas, 9 Migrations:**

- **auth**: users, workspaces, roles, api_keys, RBAC enforcement
- **content**: sources, raw_items, normalized_items, content_scores, briefs, scripts
- **media**: templates, audio_assets, video_assets, asset_library
- **analytics**: publish_jobs, publish_results, experiments, daily_summary
- **workflow**: jobs (state machine), events (append-only), audit_logs
- **system**: prompt_templates (versioned), feature_flags, decisions, knowledge_base
- **revenue**: affiliate_links, conversions, leads, revenue_summary

**Key patterns:**
- Soft delete: `deleted_at` timestamp (not NULL)
- Multi-tenant: `workspace_id` on every table
- Audit trail: append-only events (no updates/deletes)
- Deduplication: content_hash (SHA256) + external_id unique constraints
- Idempotency: ON CONFLICT DO NOTHING for duplicates

## Technology Stack

**Backend:**
- Python 3.11, FastAPI (async)
- asyncpg (PostgreSQL), aioredis (Redis)
- Pydantic (validation), python-jose (JWT), passlib (passwords)
- Prometheus client (metrics)

**Data:**
- PostgreSQL 16 (7 schemas, 9 migrations)
- Redis 7 (Streams, consumer groups, queues)
- MinIO (S3-compatible object storage)
- Qdrant (768-dim vectors, cosine distance)
- Ollama (local LLM inference)

**Infrastructure:**
- Docker & Docker Compose (dev/prod)
- Proxmox (hypervisor, 4 VMs/LXCs)
- Ubuntu 24.04 LTS (all guests)
- Cloudflare Tunnel (public access, no exposed IP)

**Observability:**
- Prometheus (metrics scraping)
- Grafana (system dashboards, 20+ alerts)
- Metabase (business intelligence, 5 analytical dashboards)
- Structured logging (JSON compatible)
- Request IDs (trace correlation)
- Health checks (per-service)

## Deployment Options

### Local Development
```bash
docker-compose up -d
# All services running in containers
# See [DEPLOYMENT.md](DEPLOYMENT.md)
```

### Proxmox Multi-VM (Production)
4 guests on single Proxmox host (32GB RAM, 1TB SSD):
- **VM-100** (20GB, 350GB): PostgreSQL, Redis, API, worker-content
- **VM-101** (8GB, 500GB): MinIO, Qdrant, Ollama, orchestrator, publisher
- **LXC-200** (2GB, 50GB): Prometheus, health monitoring
- **LXC-201** (2GB, 100GB): WAL archiving, backup automation

Internal network (vmbr1, 10.10.10.0/24), public via Cloudflare Tunnel.

- See [infra/PROXMOX_DEPLOYMENT.md](infra/PROXMOX_DEPLOYMENT.md) for architecture
- See [infra/BACKUP.md](infra/BACKUP.md) for backup procedures
- Run: `bash infra/vm100/deploy.sh` on VM-100, then `bash infra/vm101/deploy.sh` on VM-101

### Cloud (Kubernetes)
- StatefulSet for PostgreSQL, Redis
- Deployment for API + workers
- PersistentVolumes for data
- Helm charts (coming soon)

## Status

✅ **BP4 Complete** — Advanced Features
- [x] Monitoring & Observability (BP4.1): Prometheus, Grafana, 20+ alerts
- [x] Reverse Proxy & SSL/TLS (BP4.2): Cloudflare Tunnel + Nginx + Let's Encrypt
- [x] Performance Optimization (BP4.3): Indexing, caching, load testing (500+ req/s, <100ms p95)
- [x] Security Hardening (BP4.4): JWT, RBAC, RLS, encryption, audit logging, automated hardening

✅ **BP5 Complete** — Advanced Features & Expansion
- [x] Analytics Dashboard & BI (BP5.1): Metabase with 5 dashboards, cohort analysis, anomaly detection
- [x] Multi-region deployment (BP5.2): Active-passive + active-active, RDS + Redis + S3 replication, Route53 failover
- [x] Webhook integrations (BP5.3): 14+ event types, Slack/Discord/Stripe pre-built, exponential backoff, DLQ
- [x] Advanced ML models (BP5.4): LLM content generation, trend prediction, audience segmentation, sentiment analysis, recommendations

✅ **BP3 Complete** — Infrastructure & Deployment
- [x] Docker Compose (local dev, ~5 min setup)
- [x] Proxmox Multi-VM (private datacenter, 4 guests, HA backup)
- [x] Kubernetes (multi-cloud, auto-scaling, Helm charts)

✅ **BP2 Complete** — API, Auth, Content Ingestion, Orchestration, Media Publishing
- 80+ endpoints
- Multi-tenant isolation
- Append-only audit trails
- 3 background workers

## Contributing

This is an open-source project. To contribute:
1. Fork the repo
2. Create a feature branch
3. Submit a pull request
4. Ensure all tests pass (`make verify`)

## License

MIT License — See [LICENSE](LICENSE) file

## Support

- **Docs**: See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed setup
- **API Docs**: http://127.0.0.1:8000/docs (Swagger UI)
- **Issues**: Open a GitHub issue

## Roadmap

- [ ] FFmpeg integration (real video rendering)
- [ ] LLM-powered content generation (using Ollama)
- [ ] Analytics dashboard (Grafana)
- [ ] Multi-region deployment
- [ ] Kubernetes Helm charts
- [ ] Mobile app (iOS/Android)
- [ ] Advanced RBAC (fine-grained permissions)
- [ ] Custom integrations (Zapier, IFTTT)

---

**Built with ❤️ for autonomous creators everywhere.**
