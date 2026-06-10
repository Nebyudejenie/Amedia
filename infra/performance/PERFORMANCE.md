# Arada Intelligence OS — Performance Optimization

Production performance tuning across database, cache, API, and infrastructure layers.

## Overview

**Target metrics:**
- API response: < 100ms p95, < 500ms p99
- Database: < 10ms queries (cached), < 50ms worst-case
- Throughput: 1000+ req/s on single API instance
- Concurrency: 100+ concurrent connections

**Three layers:**
1. **Database** — indexing, query optimization, connection pooling
2. **Cache** — Redis strategy, TTL, invalidation
3. **API** — pagination, compression, response optimization

## Layer 1: Database Optimization

### Connection Pooling

**Current setup** (api/config.py):
```python
db_pool_min: int = 5
db_pool_max: int = 20
```

**For production**, adjust based on load:
```python
# Light load (100 req/s)
db_pool_min = 5
db_pool_max = 10

# Medium load (500 req/s)
db_pool_min = 10
db_pool_max = 30

# High load (1000+ req/s)
db_pool_min = 20
db_pool_max = 50
```

Monitor pool usage:
```sql
SELECT sum(numbackends) as total_connections FROM pg_stat_database;
SELECT datname, usename, count(*) FROM pg_stat_activity GROUP BY datname, usename;
```

### Indexing Strategy

**Current indexes** (from migrations):
```sql
CREATE INDEX idx_users_workspace_id ON auth.users(workspace_id);
CREATE INDEX idx_raw_items_source_id ON content.raw_items(source_id);
CREATE INDEX idx_normalized_items_content_hash ON content.normalized_items(content_hash);
```

**Add for common queries:**

```sql
-- Content scoring queries (BP2.1)
CREATE INDEX idx_content_scores_item_id ON content.content_scores(item_id);
CREATE INDEX idx_content_scores_final_score ON content.content_scores(final_score DESC);

-- Workflow queries (BP2.4)
CREATE INDEX idx_jobs_workspace_status ON workflow.jobs(workspace_id, status);
CREATE INDEX idx_jobs_status_created ON workflow.jobs(status, created_at DESC);
CREATE INDEX idx_events_job_id ON workflow.events(job_id);

-- Analytics queries (BP2.5)
CREATE INDEX idx_publish_jobs_status ON analytics.publish_jobs(status);
CREATE INDEX idx_publish_results_job_id ON analytics.publish_results(publish_job_id);

-- Soft delete pattern
CREATE INDEX idx_users_deleted_at ON auth.users(deleted_at) WHERE deleted_at IS NOT NULL;
```

**Index usage monitoring:**

```sql
-- Unused indexes (candidates for removal)
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;

-- Expensive queries
SELECT query, calls, mean_exec_time, max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Query Optimization

**Bad patterns (avoid):**

```python
# ❌ SELECT * (loads unused columns)
async with db.acquire() as conn:
    rows = await conn.fetch("SELECT * FROM users WHERE workspace_id = $1", ws_id)

# ✅ SELECT specific columns
async with db.acquire() as conn:
    rows = await conn.fetch(
        "SELECT id, email, role FROM users WHERE workspace_id = $1",
        ws_id
    )
```

```python
# ❌ N+1 queries (fetch users, then loop and fetch each user's workspace)
users = await conn.fetch("SELECT * FROM users WHERE workspace_id = $1", ws_id)
for user in users:
    workspace = await conn.fetchrow("SELECT * FROM workspaces WHERE id = $1", user['workspace_id'])

# ✅ JOIN (single query)
users = await conn.fetch(
    """SELECT u.id, u.email, u.role, w.name as workspace_name
       FROM users u
       JOIN workspaces w ON u.workspace_id = w.id
       WHERE u.workspace_id = $1""",
    ws_id
)
```

```python
# ❌ LIMIT without ORDER BY (inconsistent results)
items = await conn.fetch("SELECT * FROM items LIMIT 10")

# ✅ LIMIT with ORDER BY (deterministic)
items = await conn.fetch(
    "SELECT * FROM items ORDER BY created_at DESC LIMIT 10"
)
```

### Maintenance

**Weekly maintenance:**

```bash
#!/bin/bash
# Run in docker-compose exec postgres psql -U arada -d arada << 'SQL'

-- Vacuum and analyze (clean up dead rows, update statistics)
VACUUM ANALYZE;

-- Reindex (rebuild fragmented indexes)
REINDEX DATABASE arada;

-- Check bloat
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
# SQL
```

**Automated via pg_maintenance extension:**
```sql
CREATE EXTENSION pg_maintenance;
SELECT * FROM pg_maintenance.maintenance_state();
```

### Slow Query Logging

Enable in docker-compose.yml:
```yaml
postgres:
  environment:
    POSTGRES_INITDB_ARGS: "-c log_min_duration_statement=100"  # Log queries > 100ms
```

View slow queries:
```bash
docker-compose exec postgres tail -f /var/log/postgresql/postgresql.log | grep "duration:"
```

## Layer 2: Redis Caching

### Caching Strategy

**Never cache:**
- Authentication (always query DB)
- Real-time job status
- User preferences/settings

**Always cache** (long TTL):
- Workspaces (1 hour)
- Roles + permissions (1 hour)
- Templated responses (30 min)

**Smart cache** (invalidate on write):
- User profiles (invalidate on update)
- Content scores (invalidate on recalculate)
- Workflow status (invalidate on state change)

### Implementation

```python
# Cache helper
async def get_or_cache(key: str, fetch_fn, ttl=3600):
    # Try Redis
    cached = await RedisClient.get(key)
    if cached:
        return json.loads(cached)
    
    # Fetch from DB
    value = await fetch_fn()
    
    # Store in Redis
    await RedisClient.set(key, json.dumps(value), ex=ttl)
    
    return value

# Usage
workspace = await get_or_cache(
    f"workspace:{workspace_id}",
    lambda: db.fetchrow("SELECT * FROM workspaces WHERE id = $1", workspace_id),
    ttl=3600
)
```

### Cache Invalidation

```python
# On write, invalidate cache
async def update_workspace(workspace_id: str, name: str):
    # Update DB
    await db.execute("UPDATE workspaces SET name = $1 WHERE id = $2", name, workspace_id)
    
    # Invalidate cache
    await RedisClient.delete(f"workspace:{workspace_id}")
```

### Monitoring Redis

```bash
# Memory usage
docker-compose exec redis redis-cli INFO memory

# Key count
docker-compose exec redis redis-cli DBSIZE

# Hot keys (most accessed)
docker-compose exec redis redis-cli --hotkeys

# Check evictions
docker-compose exec redis redis-cli INFO stats | grep evicted
```

## Layer 3: API Optimization

### Pagination

**Always paginate large datasets:**

```python
@app.get("/content/items")
async def list_items(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    # Fetch count + items
    total = await db.fetchval(
        "SELECT COUNT(*) FROM content.normalized_items WHERE workspace_id = $1",
        workspace_id
    )
    items = await db.fetch(
        """SELECT id, title, url FROM content.normalized_items
           WHERE workspace_id = $1
           ORDER BY created_at DESC
           LIMIT $2 OFFSET $3""",
        workspace_id, limit, offset
    )
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items
    }
```

### Compression

Already enabled in FastAPI + nginx:

```python
# FastAPI
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript;
```

Monitor compression:
```bash
curl -I https://arada.fun/system/health | grep -i content-encoding
# Should see: Content-Encoding: gzip
```

### Response Time Optimization

**Async all I/O:**

```python
# ❌ Blocking
import time
time.sleep(1)  # Blocks entire worker

# ✅ Async
import asyncio
await asyncio.sleep(1)  # Doesn't block other requests
```

**Timeout management:**

```python
# Set timeouts on external calls
async with httpx.AsyncClient(timeout=5) as client:
    response = await client.get(url)
```

### Selective field loading

```python
# Query only needed fields
@app.get("/users/{user_id}")
async def get_user(user_id: str, fields: str = Query("id,email,name")):
    allowed_fields = {"id", "email", "name", "role"}
    requested = set(fields.split(",")) & allowed_fields
    
    if not requested:
        requested = {"id", "email", "name"}
    
    query = f"SELECT {','.join(requested)} FROM users WHERE id = $1"
    return await db.fetchrow(query, user_id)
```

## Load Testing

### Locust (Python-based load testing)

**Setup:**

```bash
pip install locust
```

**Test script** (`infra/performance/locustfile.py`):

```python
from locust import HttpUser, task, between

class AradaUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)  # 3x weight
    def get_health(self):
        self.client.get("/system/health")
    
    @task(2)
    def list_items(self):
        self.client.get("/content/items?limit=20&offset=0")
    
    @task(1)
    def get_metrics(self):
        self.client.get("/metrics")
```

**Run:**

```bash
locust -f infra/performance/locustfile.py --host=https://arada.fun

# Or headless (automated)
locust -f locustfile.py --host=https://arada.fun \
  --users 100 --spawn-rate 10 --run-time 60s --headless
```

**Results:** Access http://localhost:8089 to view metrics

### Apache Bench (simple HTTP)

```bash
# 1000 requests, 10 concurrent
ab -n 1000 -c 10 https://arada.fun/system/health

# Output:
# Requests per second:    250 [#/sec]
# Time per request:       40 [ms]
# Failed requests:        0
```

### Wrk (high-performance)

```bash
# Install
sudo apt-get install wrk

# 4 threads, 100 connections, 30s duration
wrk -t4 -c100 -d30s https://arada.fun/system/health

# Output:
# 12000 requests in 30.00s, 3.2MB read
# Requests/sec:   400.00
# Latency: 250ms avg, 500ms p95
```

## Monitoring Performance

### Prometheus Queries

```promql
# Request rate (req/s)
rate(http_requests_total[5m])

# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# Database query time
rate(pg_stat_database_blk_time_user[5m])
```

### Grafana Dashboard

Key panels:
- API latency (p50, p95, p99)
- Request rate (by endpoint)
- Error rate
- Database connections
- Redis memory usage
- Cache hit ratio

## Optimization Checklist

- [ ] Database indexes on all FK + frequently filtered columns
- [ ] Connection pool sized for peak load
- [ ] Slow query logging enabled
- [ ] Cache strategy defined (TTL, invalidation)
- [ ] Redis memory < 80% under load
- [ ] API pagination on all list endpoints
- [ ] Gzip compression enabled
- [ ] Timeouts set on external calls
- [ ] Load test shows > 500 req/s
- [ ] P95 latency < 100ms
- [ ] No N+1 queries in hot paths
- [ ] Database maintenance scheduled (weekly VACUUM)

## Performance Targets

| Metric | Current | Target | Action |
|--------|---------|--------|--------|
| API p95 latency | 150ms | < 100ms | Cache + index |
| DB query | 20ms avg | < 10ms | Index hot queries |
| Throughput | 500 req/s | 1000+ req/s | Add replicas |
| Redis memory | 500MB | < 1GB | Eviction policy |
| Cache hit ratio | 70% | > 85% | Adjust TTL |

## References

- PostgreSQL: https://www.postgresql.org/docs/16/performance.html
- asyncpg: https://magicstack.github.io/asyncpg/current/
- Redis: https://redis.io/topics/optimization
- Locust: https://locust.io/

---

**See also**: [MONITORING.md](../monitoring/MONITORING.md), [REVERSE_PROXY.md](../reverse-proxy/REVERSE_PROXY.md)
