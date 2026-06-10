# Arada Intelligence OS — FastAPI Backend (Prompt 2.5)

Single internal contract: HTTP + Pydantic schemas. All modules call FastAPI; all
stores (Postgres, Redis, MinIO, Qdrant, Ollama) are abstracted behind async clients
with retry + timeout.

Auth: user registration → JWT tokens (access + refresh) → role-based access control +
workspace isolation on every route.

Content: ingest from sources (RSS, HTTP JSON APIs) → normalize + deduplicate (SHA256 hash) →
score (relevance, engagement, trend, quality) → feed into orchestration queues.

Orchestration: append-only job state machine (pending → processing → completed/failed) →
task dispatch (brief → script → render → publish) → audit trail (event log).

Media: templates (customizable video layouts) + asset library (audio, video, images) →
render video (script + template → MinIO) → publish to platforms (Twitter, YouTube, TikTok).

## Run it

```bash
cp .env.example .env          # edit passwords/hosts
pip install -r requirements.txt
python main.py                # uvicorn dev server (reload on file change)

# In another terminal:
./verify.sh
```

With Docker:
```bash
docker build -t arada-api:latest .
docker run -d --name arada-api \
  --env-file .env \
  -p 127.0.0.1:8000:8000 \
  arada-api:latest
./verify.sh
```

## Structure
```
api/
├── main.py              # FastAPI app, lifespan, middleware, metrics, exception handler
├── config.py            # Pydantic Settings (all env vars)
├── schemas.py           # Pydantic request/response models (all entities)
├── clients.py           # Async wrappers: PostgreSQLPool, RedisClient, MinIOClient, QdrantClient, OllamaClient
├── auth_service.py      # Auth: JWT, password hashing, user/api-key CRUD
├── dependencies.py      # FastAPI dependency injection: get_current_user, require_role
├── content_service.py   # Content: fetch (RSS/JSON API), normalize, deduplicate, score
├── workflow_service.py  # Workflow: job state machine, event logging (append-only)
├── media_service.py     # Media: templates, render (script+template), publish (platforms)
├── worker.py            # Background worker: fetch/normalize/score jobs
├── orchestrator.py      # Orchestrator: brief→script→render→publish pipeline
├── publisher.py         # Publisher: dispatch publish jobs to platforms
├── routers/
│   ├── __init__.py
│   ├── auth.py          # /auth/* — registration, login, refresh, me, workspace, api-keys
│   ├── content.py       # /content/* — sources, items, scoring
│   ├── workflow.py      # /workflow/* — jobs, events
│   ├── media.py         # /media/* — templates, render, publish
│   └── health.py        # /system/health
├── pyproject.toml
├── requirements.txt
├── .env.example
├── Dockerfile           # multi-stage, non-root user
└── verify.sh
```

## Auth Flow

1. **Register**: `POST /auth/register` with email + password + workspace_name
   - Creates workspace (free plan) + user (owner role)
   - Returns access + refresh tokens

2. **Login**: `POST /auth/login` with email + password
   - Updates last_login_at
   - Returns access + refresh tokens

3. **Refresh**: `POST /auth/refresh` with refresh token
   - Returns new access token + new refresh token

4. **Me**: `GET /auth/me` (requires access token)
   - Returns current user profile

5. **Workspace**: `GET /auth/workspace` (requires access token)
   - Returns workspace metadata

6. **API Keys**: CRUD `/auth/api-keys` (owner/admin only)
   - Create: `POST` with name + scopes → returns prefix + secret
   - List: `GET` → shows all keys for workspace
   - Delete: `DELETE /{api_key_id}` → soft-delete

## Middleware & Observability
- **Request ID**: UUID per request → `X-Request-ID` header
- **Metrics**: Prometheus `/metrics` with request count + duration by method/endpoint
- **Logging**: structured, JSON-compatible
- **CORS**: configurable origins (env var)
- **Exception handler**: global catch-all returns 500 + request ID
- **Auth**: JWT Bearer token validation via `get_current_user` dependency
- **RBAC**: `require_role(*allowed_roles)` decorator enforces permission checks

## Clients
All use async/await + timeouts (5–60s per operation):
- **PostgreSQLPool**: asyncpg, 5–20 connections
- **RedisClient**: aioredis, standard ops + list push/pop
- **MinIOClient**: S3-compatible, bucket + object ops
- **QdrantClient**: async, search + upsert
- **OllamaClient**: HTTP wrapper, generate + embed

## Content Ingestion Flow

**Sources**: Create RSS or HTTP JSON API sources (with custom field mapping).

**Fetch**: `POST /content/sources/{id}/fetch` queues a fetch job in Redis.

**Worker**: Background worker (async loop) processes jobs:
1. Fetch items from RSS/API using feedparser/httpx
2. Insert raw items (ON CONFLICT for idempotency)
3. Normalize: extract title, description, url, author, published_at
4. Deduplicate: SHA256(title + description) → soft-delete duplicates
5. Score: relevance (keywords + length), engagement (domain trust), trend, quality

**Items**: GET `/content/items` returns normalized, scored items (workspace-scoped).

## Workflow State Machine

**States**: pending → processing → completed/failed/cancelled

**Operations**:
- Create: start a new job (brief, script, render, publish)
- Claim: worker polls and locks N pending jobs (SKIP LOCKED for concurrency)
- Complete: transition to completed + store output data
- Fail: transition to failed + store error message

**Events** (append-only audit trail):
- Job created, claimed, completed, failed, cancelled
- Task dispatched, started, completed, failed
- Metadata: worker_id, error_message, output_data, etc.

## Orchestration Pipeline

**Content Ingestion Worker**: Fetches from sources → normalizes → scores → updates source.last_fetched_at

**Task Orchestrator**: Polls workflow jobs in parallel:
- **Brief**: SELECT normalized_items → summarize → store in content_briefs
- **Script**: SELECT content_briefs → generate script → store in scripts
- **Render**: SELECT scripts + templates → render → mock video (placeholder)
- **Publish**: SELECT videos → create analytics.publish_jobs → queue to platforms

## Media & Publishing Flow

**Templates**: Customizable video layouts (short-form, long-form, story, reel).

**Rendering**: Script + template → JSON mockup → stored in MinIO as `videos/{workspace_id}/{video_id}.json`

**Publishing**: Create publish job (queued) → publisher worker polls → dispatches to platforms
- Per-platform results tracked in analytics.publish_results
- Polling status updates when all platforms published

## Acceptance criteria (Prompt 2.5)

- [x] Create video template (template_type: short-form, long-form, story, reel)
- [x] List templates (with pagination, workspace-scoped)
- [x] Get template details (with config parsing)
- [x] Render video (script + template → MinIO storage)
- [x] Create publish job (video_id, platforms list, metadata)
- [x] List publish jobs (with optional status filter, pagination)
- [x] Get publish job details
- [x] Publish to platform (mock Twitter, YouTube, TikTok)
- [x] Track publish results (per-platform post_id + url)
- [x] Asset library (audio, video, images — store/list/track in media.audio/video_assets)
- [x] MinIO integration (store rendered videos, retrieve URLs)
- [x] Publisher worker (async, polls queued jobs, dispatches to platforms)
- [x] Workspace isolation (all templates/jobs/assets scoped to workspace_id)

**Complete BP2 (API + Auth + Content + Orchestration + Media):**
- ✅ Auth: registration, login, JWT, RBAC, api-keys
- ✅ Content: ingestion (RSS, JSON APIs), normalization, deduplication, scoring
- ✅ Orchestration: job state machine, event audit trail, task dispatch
- ✅ Media: templates, rendering, publishing

Next: **BP3 — Infrastructure & Deployment** (Docker Compose for all services, health checks, monitoring).
