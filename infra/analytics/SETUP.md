# Arada Analytics — Quick Setup Guide

Get your analytics dashboard running in 5 minutes.

## Prerequisites

- Docker Compose running (all services healthy)
- PostgreSQL 16 initialized with migrations
- Access to `docker-compose.yml` directory

## Step 1: Start Metabase Container

Metabase is already defined in `docker-compose.yml`. If you haven't started it yet:

```bash
cd arada-os
docker-compose up -d metabase
```

Wait for health check (30-60 seconds):

```bash
docker-compose logs metabase | grep "Metabase started"
```

Access at: **http://127.0.0.1:3000**

## Step 2: Initialize Analytics Schema

Create materialized views and analytics tables:

```bash
psql -h 127.0.0.1 -U arada -d arada -f infra/analytics/init.sql
```

When prompted for password, use `$DB_PASSWORD` from your `.env`.

Expected output:
```
CREATE SCHEMA
CREATE MATERIALIZED VIEW
...
GRANT
```

## Step 3: Auto-Configure Metabase (Optional)

This creates dashboards and saved questions automatically:

```bash
# Install Python dependencies
pip install requests

# Run setup script
METABASE_URL=http://127.0.0.1:3000 \
METABASE_ADMIN_EMAIL=admin@arada.fun \
METABASE_ADMIN_PASSWORD=changeme \
POSTGRES_HOST=127.0.0.1 \
POSTGRES_DB=arada \
POSTGRES_USER=arada \
POSTGRES_PASSWORD=$DB_PASSWORD \
python3 infra/analytics/metabase_setup.py
```

Expected output:
```
✓ Metabase is healthy
✓ Logged in as admin@arada.fun
✓ Database already exists (ID: 2)
✓ Created collection: Content Analytics
✓ Created question: Top Scoring Items
...
✓ Metabase setup complete!
```

## Step 4: Manual Dashboard Setup (If Automation Fails)

1. Open Metabase: http://127.0.0.1:3000
2. Login: `admin@arada.fun` / `changeme`
3. Click **Settings** → **Admin** → **Databases**
4. Add database "Arada Analytics":
   - Type: PostgreSQL
   - Host: 127.0.0.1
   - Port: 5432
   - Name: arada
   - User: arada
   - Password: (your DB_PASSWORD)
5. Click **Sync database schema**
6. Create dashboards (see ANALYTICS.md for example queries)

## Step 5: Verify Analytics

Test data freshness:

```bash
docker-compose exec postgres psql -U arada -d arada << 'SQL'
SELECT * FROM analytics.item_stats ORDER BY date DESC LIMIT 1;
SELECT * FROM analytics.publish_stats ORDER BY date DESC LIMIT 1;
SELECT * FROM analytics.job_stats ORDER BY date DESC LIMIT 1;
SQL
```

Expected: Recent dates with aggregated metrics.

## Step 6: Setup Daily Refresh (Optional)

Materialized views need periodic refreshing for up-to-date dashboards:

```bash
# Create a cron job on the host
crontab -e

# Add this line (refresh every 4 hours):
0 */4 * * * docker-compose exec -T postgres psql -U arada -d arada -c "SELECT analytics.refresh_stats();"
```

Or use systemd timer:

```bash
# Create timer file
sudo tee /etc/systemd/system/arada-analytics-refresh.timer > /dev/null << 'EOF'
[Unit]
Description=Arada Analytics Refresh
OnBootSec=5min
OnUnitActiveSec=4h

[Install]
WantedBy=timers.target
EOF

# Create service
sudo tee /etc/systemd/system/arada-analytics-refresh.service > /dev/null << 'EOF'
[Unit]
Description=Arada Analytics Refresh Service

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'cd /path/to/arada-os && docker-compose exec -T postgres psql -U arada -d arada -c "SELECT analytics.refresh_stats();"'
User=root
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable arada-analytics-refresh.timer
sudo systemctl start arada-analytics-refresh.timer
```

## Accessing Metabase

**Default credentials:**
- Email: `admin@arada.fun`
- Password: `changeme` (set in METABASE_ADMIN_PASSWORD)

**Dashboard locations:**
- Executive Summary: http://127.0.0.1:3000/collection/root
- Content Analytics: Collection "Content Analytics"
- Publishing Metrics: Collection "Publishing Metrics"
- Workflow Performance: Collection "Workflow Performance"
- Business Metrics: Collection "Business Metrics"

## Common Tasks

### Run a Custom Query

1. Metabase home → **+ New** → **Native query**
2. Select database "Arada Analytics"
3. Paste SQL from [ANALYTICS.md](ANALYTICS.md)
4. Click **Visualize**
5. Save question to a collection

### Create a Custom Dashboard

1. **+ New** → **Dashboard**
2. Name: "My Dashboard"
3. Click **Save**
4. Add cards from existing questions via **+ Add questions**

### Export Data

1. Click question/card → **⋮** → **Download results**
2. Select format: CSV, XLSX, JSON
3. Download

### Setup Email Alerts

1. Admin Settings → **Alerts**
2. Create alert on question threshold (e.g., "Job failures > 5")
3. Set email recipients and frequency
4. Save

### Connect Slack

1. Admin Settings → **Email and notifications**
2. **Slack settings** → **Create a Slack app**
3. Follow OAuth flow
4. Add Slack notifications to alerts/dashboards

## Troubleshooting

### Metabase won't start

```bash
# Check logs
docker-compose logs metabase | tail -50

# Verify PostgreSQL is healthy
docker-compose ps postgres
```

### Database connection fails

```bash
# Test PostgreSQL connection
docker-compose exec postgres psql -U arada -d arada -c "SELECT 1;"

# Verify user exists
docker-compose exec postgres psql -U postgres -c "SELECT * FROM pg_user WHERE usename LIKE '%metabase%';"
```

### No data in dashboards

```bash
# Verify analytics schema exists
docker-compose exec postgres psql -U arada -d arada -c "SELECT * FROM analytics.item_stats LIMIT 1;"

# Refresh materialized views
docker-compose exec postgres psql -U arada -d arada -c "SELECT analytics.refresh_stats();"

# Check for recent data in base tables
docker-compose exec postgres psql -U arada -d arada -c "SELECT COUNT(*) FROM content.normalized_items WHERE created_at > NOW() - INTERVAL '7 days';"
```

### Slow dashboard loading

1. Check Metabase query performance: Admin → **Query performance**
2. Consider adding database indexes (see [ANALYTICS.md](ANALYTICS.md))
3. Refresh materialized views more frequently
4. Use simpler queries with pre-aggregated data

## Performance Tips

- **Materialized views** refresh every 4 hours (change as needed)
- **Query caching** enabled by default in Metabase (1 hour)
- **Database indexes** on `(workspace_id, date)` for common aggregations
- **Partitioning** for large time-series tables (see ANALYTICS.md)

## Next Steps

1. Explore pre-built dashboards
2. Create custom questions for your KPIs
3. Setup alerts for anomalies
4. Integrate with Slack/email
5. Export weekly reports

---

**Questions?** See [ANALYTICS.md](ANALYTICS.md) for complete guide.
