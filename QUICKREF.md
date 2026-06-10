# Arada Intelligence OS — Quick Reference

## Setup (First Time)

```bash
git clone https://github.com/arada-ai/arada-os.git
cd arada-os
make setup
# Follow interactive prompts
```

## Accessing Services

| Service | URL | Credentials |
|---------|-----|-------------|
| **API** | http://127.0.0.1:8000 | — |
| **API Docs** | http://127.0.0.1:8000/docs | — |
| **Metrics** | http://127.0.0.1:8000/metrics | — |
| **MinIO Console** | http://127.0.0.1:9001 | arada / $MINIO_SECRET_KEY |
| **PostgreSQL** | 127.0.0.1:5432 | arada / $DB_PASSWORD |
| **Redis** | 127.0.0.1:6379 | — |

## Common Tasks

### Start/Stop Services
```bash
make up         # Start all containers
make down       # Stop all containers
make restart    # Restart all containers
make status     # Show container status
```

### Monitoring
```bash
make logs       # Stream all logs
make logs-api   # API logs only
make logs-db    # PostgreSQL logs
make verify     # Run health checks
```

### Maintenance
```bash
make clean      # DESTRUCTIVE: stop + remove all volumes
make build      # Rebuild Docker images
```

## API Endpoints

### Authentication
```bash
# Register user
POST /auth/register
  email, password (12+ chars), workspace_name

# Login
POST /auth/login
  email, password

# Get current user
GET /auth/me
  (requires token)

# Refresh token
POST /auth/refresh
  (use refresh_token as bearer)

# Get workspace
GET /auth/workspace
  (requires token)

# Create API key
POST /auth/api-keys
  name, scopes

# List API keys
GET /auth/api-keys

# Delete API key
DELETE /auth/api-keys/{api_key_id}
```

### Content
```bash
# Create source
POST /content/sources
  name, source_type (rss|http_json|manual), url, config

# List sources
GET /content/sources

# Get source
GET /content/sources/{source_id}

# Trigger fetch
POST /content/sources/{source_id}/fetch

# List items
GET /content/items
  ?normalized=true (default)

# Get item
GET /content/items/{item_id}

# Get item score
GET /content/items/{item_id}/score
```

### Workflow
```bash
# Create job
POST /workflow/jobs
  job_type (brief|script|render|publish), input_data, priority

# List jobs
GET /workflow/jobs
  ?status=pending
  ?job_type=brief
  ?limit=20&offset=0

# Get job
GET /workflow/jobs/{job_id}

# Get job events (audit trail)
GET /workflow/jobs/{job_id}/events
```

### Media
```bash
# Create template
POST /media/templates
  name, template_type (short-form|long-form|story|reel), config

# List templates
GET /media/templates

# Get template
GET /media/templates/{template_id}

# Render video
POST /media/render
  script_id, template_id, output_format

# Create publish job
POST /media/publish
  video_id, platforms, metadata

# List publish jobs
GET /media/publish
  ?status=queued

# Publish to platform
POST /media/publish/{job_id}/{platform}
```

## Database

### Connect via psql
```bash
docker-compose exec postgres psql -U arada -d arada
```

### Common queries
```sql
-- List workspaces
SELECT id, name, plan FROM auth.workspaces WHERE deleted_at IS NULL;

-- List users in workspace
SELECT id, email, role FROM auth.users WHERE workspace_id = '...' AND deleted_at IS NULL;

-- Check content sources
SELECT id, name, source_type, last_fetched_at FROM content.sources WHERE workspace_id = '...';

-- View job history
SELECT id, job_type, status, created_at FROM workflow.jobs WHERE workspace_id = '...' ORDER BY created_at DESC;

-- Check job events
SELECT event_type, metadata, created_at FROM workflow.events WHERE job_id = '...' ORDER BY created_at ASC;
```

### Reset database
```bash
docker-compose down
docker volume rm arada-os_postgres_data
docker-compose up -d
```

## Redis

### Connect via redis-cli
```bash
docker-compose exec redis redis-cli
```

### Common commands
```bash
# Check queue length
LLEN content:fetch-queue

# View queue items
LRANGE content:fetch-queue 0 -1

# Clear queue
DEL content:fetch-queue

# Check all keys
KEYS *

# Monitor realtime
MONITOR
```

## MinIO

### Connect via mc (MinIO client)
```bash
docker-compose exec minio mc ls minio
docker-compose exec minio mc ls minio/arada

# Create bucket
docker-compose exec minio mc mb minio/my-bucket

# Upload file
docker-compose exec minio mc cp /tmp/video.mp4 minio/arada/
```

## Debugging

### API won't start
```bash
make logs-api       # Check error message
docker-compose down
docker-compose up -d postgres redis  # Start deps only
docker-compose up -d api             # Try API separately
```

### Database connection error
```bash
docker-compose logs postgres  # Check PostgreSQL logs
docker-compose exec postgres pg_isready -U arada
```

### Worker not processing
```bash
docker-compose logs worker-content   # Check logs
docker-compose exec redis redis-cli  # Inspect queue
LLEN content:fetch-queue
```

### Permission issues
```bash
# Check volume ownership
docker-compose down
ls -la postgres_data/
sudo chown -R 999:999 postgres_data/  # postgres user in container
docker-compose up -d
```

## Performance

### Check metrics
```bash
curl http://127.0.0.1:8000/metrics | grep http_requests
```

### View slow queries
```bash
docker-compose exec postgres psql -U arada -d arada
arada=# SELECT query, calls, total_time, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;
```

### Monitor resource usage
```bash
docker stats arada-postgres arada-redis arada-api
```

## Backup & Restore

### Backup database
```bash
docker-compose exec postgres pg_dump -U arada arada > backup.sql
```

### Restore database
```bash
docker-compose exec -T postgres psql -U arada arada < backup.sql
```

### Backup MinIO
```bash
docker-compose exec minio mc mirror minio/arada /backup
```

## Environment Variables

### Required
- `DB_PASSWORD` — PostgreSQL password (strong!)
- `MINIO_SECRET_KEY` — MinIO secret (strong!)
- `JWT_SECRET_KEY` — JWT signing key (32+ chars random)

### Optional
- `DEBUG=false` — Enable debug mode
- `CORS_ORIGINS=["http://localhost:3000"]` — Allow origins
- `RATE_LIMIT_CALLS=100` — Requests per window
- `RATE_LIMIT_PERIOD_SECONDS=60` — Time window

## Useful Docker Commands

```bash
# View all containers
docker-compose ps

# View service logs (last 100 lines)
docker-compose logs -n 100 api

# Execute command in service
docker-compose exec postgres psql -U arada -d arada

# Rebuild a service
docker-compose build api

# Remove image and rebuild
docker rmi arada-os_api && docker-compose build api

# Inspect service
docker inspect arada-api

# View network
docker network ls
docker network inspect arada-os_arada-internal
```

## Getting Help

- **API Docs**: http://127.0.0.1:8000/docs (Swagger UI)
- **Full Guide**: Read [DEPLOYMENT.md](DEPLOYMENT.md)
- **Issues**: GitHub issues
- **Logs**: `make logs`

---

**Last Updated**: 2024
