# Arada Intelligence OS — Distributed Data Core (Prompt 1.2)

Redis, MinIO, Qdrant: queue, object storage, and vector search.

## Services

| Service | Role | Port | Volume |
|---------|------|------|--------|
| **Redis 7** | Streams + queues + cache + locks | 6379 | redis-data |
| **MinIO** | S3-compatible object storage | 9000 / 9001 (console) | minio-data |
| **Qdrant** | Vector search (768-dim, cosine) | 6333 + 6334 (gRPC) | qdrant-data |

## Run it

```bash
cp .env.example .env          # customize passwords/ports
docker compose up -d
./qdrant/init-collections.sh  # create 5 collections (after Qdrant is healthy)
./verify.sh                   # acceptance checks
```

All three are bound to **127.0.0.1** for development; when integrated into the
main stack (BP1.2 onward), they move to the `internal` Docker network and
loopback bindings are removed.

## Architecture

### Redis
```
Queue taxonomy (Phase 5 §5.1):
  queue:news:ingest
  queue:news:normalize
  queue:news:dedupe
  queue:content:score
  queue:content:brief
  queue:script:generate
  queue:voice:generate
  queue:subtitle:generate
  queue:video:render
  queue:publish:youtube|instagram|tiktok
  queue:analytics:fetch
  queue:cleanup:*
  queue:dead:letter      ← failed jobs
```
Configured for **LRU eviction** at 2GB max. Streams + consumer groups for
durable queue semantics (P2: PgBouncer + per-worker connection pooling).

### MinIO
Default workspace bucket layout: `workspace/{id}/audio/`, `workspace/{id}/videos/`, etc.
Initial buckets created on first run (P2). Root credentials in `.env`; internal
service access via minio-network address.

### Qdrant
5 collections initialized:
- `content_embeddings` — dedup (≥0.92 cosine = duplicate)
- `script_memory` — RAG for hook generation
- `knowledge_memory` — company brain Q&A
- `trend_memory` — topic clustering over time
- `audience_profiles` — audience-fit scoring

Each collection: 768-dim (nomic-embed-text), cosine distance. Point payloads
carry `workspace_id` for multi-tenant isolation.

## Acceptance criteria (Prompt 1.2) — verified

- [x] Redis: responds to PING, streams + consumer-group support.
- [x] MinIO: health check OK, console accessible.
- [x] Qdrant: health check OK, 5 collections created with correct dimensions.
- [x] Idempotent init (re-run collections, verify, no errors).
- [x] All bound to loopback (127.0.0.1) for dev; removed in production network.

## Development access

```bash
redis-cli -h 127.0.0.1 -p 6379 PING
# MinIO console: http://127.0.0.1:9001 (credentials in .env)
curl -s http://127.0.0.1:6333/health | jq .
```

Next phase: **BP2 — API + Auth** (FastAPI skeleton + JWT/RBAC on VM-100).
