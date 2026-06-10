# Arada Intelligence OS — Analytics Dashboard & BI

Open-source analytics platform for real-time monitoring of content performance, publishing results, and business metrics.

## Overview

**Three analytics levels:**
1. **Operational** — Job status, queue depth, error rates (Prometheus)
2. **Content** — Item scores, trending topics, engagement (Metabase)
3. **Business** — Revenue, affiliate conversions, user growth (Metabase)

## Stack

**Tools:**
- **Metabase** — Open-source BI dashboard (Docker, localhost:3000)
- **PostgreSQL** — Queryable data (7 schemas, 50+ tables)
- **Prometheus** — Real-time metrics (request rate, latency, errors)
- **Grafana** — System monitoring dashboards (already done in BP4.1)

## Metabase Setup

### 1. Install Metabase

```yaml
# Add to data/docker-compose.yml
metabase:
  image: metabase/metabase:latest
  container_name: arada-metabase
  ports:
    - "127.0.0.1:3000:3000"
  environment:
    MB_DB_TYPE: postgres
    MB_DB_DBNAME: metabase
    MB_DB_HOST: postgres
    MB_DB_PORT: 5432
    MB_DB_USER: metabase
    MB_DB_PASS: ${METABASE_DB_PASSWORD}
    MB_ENCRYPTION_SECRET_KEY: ${METABASE_SECRET_KEY}
  depends_on:
    - postgres
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:3000/api/health"]
    interval: 10s
    timeout: 5s
    retries: 3
  restart: unless-stopped
```

### 2. Initialize Metabase Database

```bash
docker-compose exec postgres psql -U arada -d arada << 'SQL'
CREATE USER metabase WITH PASSWORD 'change-me-strong';
CREATE DATABASE metabase OWNER metabase;
GRANT CONNECT ON DATABASE metabase TO metabase;
SQL
```

### 3. Access Metabase

```
http://127.0.0.1:3000
Email: admin@arada.fun
Password: (set during first login)
```

## Pre-built Dashboards

### 1. Content Performance

**Query: Top Scoring Items**

```sql
SELECT
  ni.id,
  ni.title,
  ni.url,
  cs.final_score,
  cs.relevance_score,
  cs.engagement_score,
  cs.trend_score,
  cs.quality_score,
  COUNT(DISTINCT pr.id) as publish_count,
  ni.created_at
FROM content.normalized_items ni
LEFT JOIN content.content_scores cs ON ni.id = cs.item_id
LEFT JOIN analytics.publish_results pr ON ni.id = pr.video_id
WHERE ni.workspace_id = '{{workspace_id}}'
  AND ni.deleted_at IS NULL
GROUP BY ni.id, cs.id
ORDER BY cs.final_score DESC
LIMIT 100;
```

**Dashboard cards:**
- Avg score by day (line chart)
- Top 10 highest-scoring items (table)
- Score distribution (histogram)
- Scoring by source (bar chart)

### 2. Publishing & Distribution

**Query: Publishing Performance**

```sql
SELECT
  pj.created_at::DATE as date,
  unnest(pj.platforms) as platform,
  COUNT(DISTINCT pj.id) as jobs,
  COUNT(DISTINCT CASE WHEN pj.status = 'completed' THEN pj.id END) as completed,
  COUNT(DISTINCT pr.id) as result_count,
  AVG(CASE WHEN pr.status = 'success' THEN 1 ELSE 0 END) as success_rate
FROM analytics.publish_jobs pj
LEFT JOIN analytics.publish_results pr ON pj.id = pr.publish_job_id
WHERE pj.workspace_id = '{{workspace_id}}'
  AND pj.deleted_at IS NULL
GROUP BY pj.created_at::DATE, platform
ORDER BY date DESC;
```

**Dashboard cards:**
- Publish jobs by platform (stacked bar)
- Success rate trend (line)
- Jobs per day (area chart)
- Platform comparison (table)

### 3. Workflow Execution

**Query: Job Processing Metrics**

```sql
SELECT
  j.job_type,
  j.status,
  COUNT(DISTINCT j.id) as count,
  AVG(EXTRACT(EPOCH FROM (j.completed_at - j.created_at))) as avg_duration_seconds,
  MIN(j.created_at) as oldest,
  MAX(j.created_at) as newest
FROM workflow.jobs j
WHERE j.workspace_id = '{{workspace_id}}'
  AND j.created_at > NOW() - INTERVAL '7 days'
GROUP BY j.job_type, j.status
ORDER BY j.job_type, count DESC;
```

**Dashboard cards:**
- Jobs by type + status (funnel chart)
- Avg processing time (gauge)
- Job distribution (donut)
- Recent jobs (table, filterable)

### 4. Revenue & Affiliate

**Query: Affiliate Performance**

```sql
SELECT
  DATE_TRUNC('day', ac.created_at)::DATE as date,
  al.url,
  COUNT(DISTINCT ac.id) as clicks,
  COUNT(DISTINCT conv.id) as conversions,
  ROUND(100.0 * COUNT(DISTINCT conv.id) / COUNT(DISTINCT ac.id), 2) as conversion_rate,
  SUM(COALESCE(conv.amount, 0))::NUMERIC(10, 2) as revenue
FROM revenue.affiliate_clicks ac
JOIN revenue.affiliate_links al ON ac.link_id = al.id
LEFT JOIN revenue.affiliate_conversions conv ON ac.id = conv.click_id
WHERE al.workspace_id = '{{workspace_id}}'
GROUP BY DATE_TRUNC('day', ac.created_at), al.url
ORDER BY date DESC;
```

**Dashboard cards:**
- Revenue trend (line chart)
- Conversion funnel (sankey)
- Top links (table)
- Revenue by day (bar chart)

### 5. User & Workspace

**Query: Workspace Activity**

```sql
SELECT
  DATE_TRUNC('day', u.created_at)::DATE as date,
  COUNT(DISTINCT u.id) as new_users,
  COUNT(DISTINCT CASE WHEN u.last_login_at > NOW() - INTERVAL '7 days' THEN u.id END) as active_7d,
  COUNT(DISTINCT CASE WHEN u.last_login_at > NOW() - INTERVAL '1 day' THEN u.id END) as active_1d
FROM auth.users u
WHERE u.workspace_id = '{{workspace_id}}'
GROUP BY DATE_TRUNC('day', u.created_at)
ORDER BY date DESC;
```

**Dashboard cards:**
- User growth (line)
- Active users (gauge)
- User roles (pie)
- User timeline (table)

## Advanced Analytics

### Cohort Analysis

**Retention: Users by signup week**

```sql
WITH user_cohorts AS (
  SELECT
    DATE_TRUNC('week', created_at)::DATE as cohort_date,
    id,
    created_at
  FROM auth.users
  WHERE workspace_id = '{{workspace_id}}'
)
SELECT
  cohort_date,
  DATE_TRUNC('week', last_login_at)::DATE as activity_week,
  COUNT(DISTINCT id) as user_count
FROM user_cohorts
JOIN auth.users u ON user_cohorts.id = u.id
WHERE u.last_login_at IS NOT NULL
GROUP BY cohort_date, DATE_TRUNC('week', u.last_login_at)
ORDER BY cohort_date DESC;
```

### Trend Analysis

**Content trends over time**

```sql
SELECT
  DATE_TRUNC('week', ni.created_at)::DATE as week,
  COUNT(DISTINCT ni.id) as items_created,
  AVG(cs.final_score) as avg_score,
  MAX(cs.final_score) as max_score,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY cs.final_score) as median_score
FROM content.normalized_items ni
LEFT JOIN content.content_scores cs ON ni.id = cs.item_id
WHERE ni.workspace_id = '{{workspace_id}}'
  AND ni.deleted_at IS NULL
GROUP BY DATE_TRUNC('week', ni.created_at)
ORDER BY week DESC;
```

### Anomaly Detection

**Flag unusual scoring patterns**

```sql
WITH score_stats AS (
  SELECT
    AVG(final_score) as avg_score,
    STDDEV_POP(final_score) as stddev_score
  FROM content.content_scores
  WHERE workspace_id = '{{workspace_id}}'
)
SELECT
  ni.id,
  ni.title,
  cs.final_score,
  (cs.final_score - ss.avg_score) / ss.stddev_score as z_score,
  CASE
    WHEN (cs.final_score - ss.avg_score) / ss.stddev_score > 2 THEN 'HIGH'
    WHEN (cs.final_score - ss.avg_score) / ss.stddev_score < -2 THEN 'LOW'
    ELSE 'NORMAL'
  END as anomaly
FROM content.normalized_items ni
JOIN content.content_scores cs ON ni.id = cs.item_id
CROSS JOIN score_stats ss
WHERE ABS((cs.final_score - ss.avg_score) / ss.stddev_score) > 2
ORDER BY z_score DESC;
```

## Saved Dashboards (Auto-create)

Create these via Metabase UI or API:

1. **Executive Summary** (single page)
   - New items this week
   - Total publishes
   - Avg engagement score
   - Revenue (if applicable)

2. **Content Ops** (daily standup)
   - Processing queue depth (from Prometheus)
   - Job success rate (24h)
   - Top 10 items by score
   - Publishing backlog

3. **Publishing Performance** (weekly)
   - Jobs by platform
   - Success rate by platform
   - Average time to publish
   - Platform trends

4. **Business Metrics** (weekly)
   - User growth
   - Revenue trend
   - Affiliate conversions
   - Content quality

5. **Anomalies** (ad-hoc)
   - Scoring outliers
   - Publishing failures
   - Processing slowdowns

## Exporting & Alerts

### Scheduled Exports

**Email reports (weekly):**

```sql
-- Save as Metabase question, set schedule: Every Monday 9am
SELECT
  COUNT(DISTINCT id) as items_published,
  COUNT(DISTINCT job_type) as job_types,
  AVG(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completion_rate
FROM workflow.jobs
WHERE workspace_id = '{{workspace_id}}'
  AND created_at > NOW() - INTERVAL '7 days';
```

### Slack Alerts (via Metabase)

Connect Slack channel to Metabase for:
- Daily summary (9am)
- Publishing failures (real-time)
- Anomalies (when detected)
- Weekly recap (Monday)

## Integration with Prometheus

**Bridge data:**

```python
# In api/main.py, add custom metric exports
from prometheus_client import Gauge

content_score_gauge = Gauge(
    'content_score_avg',
    'Average content score',
    ['workspace_id']
)

@app.get("/metrics/content")
async def content_metrics():
    """Export content metrics for Prometheus scraping."""
    async with PostgreSQLPool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT workspace_id, AVG(final_score) as avg_score FROM content.content_scores GROUP BY workspace_id"
        )
        if result:
            content_score_gauge.labels(workspace_id=result['workspace_id']).set(result['avg_score'])
    return generate_latest()
```

## Access Control

**Metabase permissions:**
- Admin: Full access (DB credentials, saved dashboards)
- Analyst: Read-only (saved dashboards + saved questions)
- Viewer: Public dashboards only

**Data isolation:**
- Use `workspace_id` parameter in all queries
- Create per-workspace folders in Metabase
- Restrict data access via Metabase permission model

## Performance Tips

1. **Materialized Views** for common aggregations:
   ```sql
   CREATE MATERIALIZED VIEW analytics.item_stats AS
   SELECT
     workspace_id,
     DATE_TRUNC('day', created_at)::DATE as date,
     COUNT(*) as count,
     AVG(final_score) as avg_score
   FROM content.normalized_items
   WHERE deleted_at IS NULL
   GROUP BY workspace_id, DATE_TRUNC('day', created_at);
   
   CREATE INDEX ON analytics.item_stats(workspace_id, date);
   
   -- Refresh daily
   REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.item_stats;
   ```

2. **Partitioning** for large time-series tables:
   ```sql
   ALTER TABLE workflow.jobs PARTITION BY RANGE (DATE_TRUNC('month', created_at));
   ```

3. **Column compression** for archival:
   ```sql
   ALTER TABLE analytics.publish_results SET (compression = pglz);
   ```

## References

- Metabase: https://www.metabase.com/
- PostgreSQL Analytics: https://www.postgresql.org/docs/16/functions-math.html
- Advanced Queries: https://www.postgresql.org/docs/16/queries-with.html

---

**See also**: [MONITORING.md](../monitoring/MONITORING.md), [PERFORMANCE.md](../performance/PERFORMANCE.md)
