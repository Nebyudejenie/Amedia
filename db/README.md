# Arada Intelligence OS — Data Core (Prompt 1.1)

The PostgreSQL system of record: 7 schemas, full table set, indexes (incl. GIN
on JSONB), append-only event/audit tables, seed data, an idempotent migration
runner, and tuning config.

## Schemas & tables
| Schema | Tables |
|--------|--------|
| `auth` | workspaces, roles, users, api_keys |
| `content` | sources, raw_items, normalized_items, content_scores, content_briefs, scripts |
| `media` | templates, audio_assets, video_assets, asset_library |
| `analytics` | experiments, experiment_results, publish_jobs, publish_results, analytics_daily |
| `workflow` | jobs, events*, audit_logs* |
| `system` | prompt_templates, feature_flags, runbooks, knowledge_base, decisions, system_config |
| `revenue` | affiliate_links, affiliate_clicks, affiliate_conversions, leads, revenue_summary |

`*` append-only: no `updated_at`/`deleted_at`, no FK to workspaces, so the
historical record survives tenant deletion.

Conventions: UUID PKs (`gen_random_uuid()`), `created_at`/`updated_at`/`deleted_at`
on mutable tables, a shared `set_updated_at()` trigger, `citext` for emails/slugs,
GIN indexes on queried JSONB, partial indexes filtering soft-deleted rows.

## Run it
```bash
cp .env.example .env          # set a strong POSTGRES_PASSWORD
docker compose up -d          # (host with the compose plugin)
./migrate.sh --docker         # apply migrations into the container
./verify.sh  --docker         # assert acceptance criteria
```
Against an external Postgres instead of the bundled container:
```bash
PGHOST=10.10.10.100 PGUSER=arada PGDATABASE=arada PGPASSWORD=*** ./migrate.sh
PGHOST=10.10.10.100 PGUSER=arada PGDATABASE=arada PGPASSWORD=*** ./verify.sh
```

`migrate.sh` tracks applied files in `public.schema_migrations` and is safe to
re-run (already-applied files are skipped). Each file runs in one transaction.

## Tuning
`postgresql.tuning.conf` is sized for VM-100 where Postgres shares ~20GB with
Redis/Qdrant/Ollama/MinIO/n8n/API. `init/10-include-tuning.sh` appends an
`include` to the generated `postgresql.conf` at first init, preserving the
image's defaults. Raise `shared_buffers`/`effective_cache_size` if Postgres ever
gets a dedicated VM.

## Acceptance criteria (Prompt 1.1) — verified
- [x] 7 schemas, all tables created with PKs, FKs (ON DELETE rules), indexes + GIN.
- [x] `created_at`/`updated_at`/`deleted_at` + working `updated_at` trigger.
- [x] Append-only `events` and `audit_logs`.
- [x] Seed: 6 roles, 6 feature flags, 5 config keys, default workspace.
- [x] Idempotent runner; re-run applies nothing.
- [x] Tuning include active (`shared_buffers=512MB`, `random_page_cost=1.1`).
- [x] FK cascade, soft-delete, and prompt-registry uniqueness behave correctly.

## Production notes
- In the consolidated stack (BP1.2) Postgres joins the `internal` Docker network
  and the **host port mapping is removed** — the DB is never exposed (Phase 3 §3.5).
- Per-service least-privilege DB roles + PgBouncer arrive in later phases.
- Backups (pg_dump/restic) are built in BP13.

Next prompt: **1.2 — Redis, MinIO, Qdrant bring-up.**
