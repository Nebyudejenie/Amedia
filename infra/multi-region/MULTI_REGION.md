# Arada Intelligence OS — Multi-Region Deployment

Deploy Arada across multiple geographic regions for high availability, disaster recovery, and compliance.

## Overview

**Three deployment architectures:**

1. **Active-Passive** — Primary region handles all traffic; secondary acts as hot standby
2. **Active-Active** — Both regions serve traffic; automatic failover if either fails
3. **Regional** — Separate instances per region (data sovereignty, GDPR compliance)

This guide covers all three with specific configs, failover strategies, and monitoring.

---

## Architecture: Active-Passive (Recommended for most)

```
┌─────────────────────────────────────────────────────────────┐
│                    Cloudflare / Route53                     │
│        Health checks + Geographic routing + DDoS            │
└────────────────┬────────────────────────────────────────────┘
                 │
        ┌────────┴────────────┐
        │                     │
   ┌────▼──────┐         ┌────▼──────┐
   │ US-EAST   │         │ EU-WEST   │
   │ (Primary) │         │ (Standby) │
   └────┬──────┘         └────┬──────┘
        │                     │
   ┌────▼──────────┐    ┌────▼──────────┐
   │ PostgreSQL:   │    │ PostgreSQL:   │
   │ - Primary     │────│ - Replica     │
   │ - WAL shipping│    │ (streaming)   │
   └────┬──────────┘    └────┬──────────┘
        │                     │
   ┌────▼──────────┐    ┌────▼──────────┐
   │ Redis:        │    │ Redis:        │
   │ - Primary     │────│ - Replica     │
   │ - RDB export  │    │ (AOF sync)    │
   └────┬──────────┘    └────┬──────────┘
        │                     │
   ┌────▼──────────┐    ┌────▼──────────┐
   │ MinIO:        │    │ MinIO:        │
   │ - Primary     │────│ - Replication │
   │ (object sync) │    │ (event-based) │
   └───────────────┘    └───────────────┘

All user traffic → US-EAST
Failover → EU-WEST if US-EAST down (automated, <30s)
```

---

## Part 1: PostgreSQL Replication (Streaming)

### Primary Setup (Region A, e.g., US-EAST)

**1a. Enable WAL archiving (docker-compose.yml):**

```yaml
postgres:
  environment:
    POSTGRES_INITDB_ARGS: |
      -c wal_level=replica
      -c max_wal_senders=10
      -c max_replication_slots=10
      -c hot_standby=on
      -c hot_standby_feedback=on
```

**1b. Create replication role:**

```sql
CREATE ROLE replicator WITH REPLICATION ENCRYPTED PASSWORD 'strong-repl-password';
GRANT CONNECT ON DATABASE arada TO replicator;
```

**1c. Configure pg_hba.conf (allow replica connections):**

```
# Add this line:
host    replication    replicator    <REPLICA_IP>/32    md5
```

### Replica Setup (Region B, e.g., EU-WEST)

**1d. Create replica using pg_basebackup:**

```bash
#!/bin/bash
# On replica server, before starting PostgreSQL:

PG_DATA=/var/lib/postgresql/data
REPLICA_SLOT_NAME=us_east_slot

# Stop existing PostgreSQL if running
systemctl stop postgresql

# Clear old data
rm -rf $PG_DATA/*

# Perform base backup
pg_basebackup \
  -h <PRIMARY_HOST> \
  -U replicator \
  -D $PG_DATA \
  -Xstream \
  -C \
  -S $REPLICA_SLOT_NAME \
  -v \
  -P

# Verify
ls -la $PG_DATA/
# Should contain: base/, global/, pg_wal/, postgresql.auto.conf

# Start replica
systemctl start postgresql

# Verify replication is working
psql -h localhost -U postgres -d postgres << 'SQL'
SELECT slot_name, active FROM pg_replication_slots;
SELECT pid, usename, client_addr, state FROM pg_stat_replication;
SQL
```

**1e. Docker-based replica (alternative):**

```yaml
postgres-replica:
  image: postgres:16-alpine
  container_name: arada-postgres-replica
  environment:
    POSTGRES_INITDB_ARGS: |
      -c wal_level=replica
      -c hot_standby=on
      -c hot_standby_feedback=on
      -c recovery_target_timeline=latest
  command: >
    bash -c "
      if [ ! -f /var/lib/postgresql/data/PG_VERSION ]; then
        pg_basebackup -h postgres-primary -U replicator -D /var/lib/postgresql/data -Xstream;
      fi &&
      docker-entrypoint.sh postgres
    "
  depends_on:
    postgres-primary:
      condition: service_healthy
  environment:
    PGPASSWORD: <REPLICATOR_PASSWORD>
```

### Monitor Replication Lag

```sql
-- On primary
SELECT
  slot_name,
  restart_lsn,
  confirmed_flush_lsn,
  (restart_lsn - confirmed_flush_lsn) as bytes_behind
FROM pg_replication_slots;

-- On replica
SELECT
  pg_last_wal_receive_lsn() as receive_lsn,
  pg_last_wal_replay_lsn() as replay_lsn,
  (pg_last_wal_receive_lsn() - pg_last_wal_replay_lsn()) as bytes_behind,
  EXTRACT(EPOCH FROM (NOW() - pg_last_xact_replay_timestamp()))::INT as replay_lag_seconds;
```

**Alert thresholds (in Prometheus):**

```promql
# Replication lag > 10MB
pg_replication_lag_bytes > 10485760

# Replay lag > 30 seconds
pg_replay_lag_seconds > 30
```

---

## Part 2: Redis Replication

### Primary Setup (Region A)

**2a. Enable replication in redis.conf:**

```conf
# On primary
repl-diskless-sync yes
repl-diskless-sync-delay 5
```

**2b. docker-compose configuration:**

```yaml
redis-primary:
  image: redis:7-alpine
  container_name: arada-redis-primary
  command: redis-server /usr/local/etc/redis/redis.conf
  ports:
    - "127.0.0.1:6379:6379"
  volumes:
    - ./redis/redis-primary.conf:/usr/local/etc/redis/redis.conf
    - redis-primary-data:/data
```

### Replica Setup (Region B)

**2c. Redis replica configuration:**

```yaml
redis-replica:
  image: redis:7-alpine
  container_name: arada-redis-replica
  command: redis-server --slaveof redis-primary 6379
  depends_on:
    - redis-primary
  ports:
    - "127.0.0.1:6380:6379"
  volumes:
    - redis-replica-data:/data
```

### Monitor Replication

```bash
# On primary
redis-cli INFO replication

# Expected output:
# role:master
# connected_slaves:1
# slave0:ip=<REPLICA_IP>,port=6379,offset=...

# On replica
redis-cli -p 6380 INFO replication
# Expected output:
# role:slave
# master_host:<PRIMARY_HOST>
# master_sync_in_progress:0
```

---

## Part 3: MinIO Cross-Region Replication

### Primary Setup (Region A)

**3a. Enable versioning on source bucket:**

```bash
mc version enable arada/arada-bucket
```

**3b. Configure replication rule:**

```bash
mc ilm import arada/arada-bucket << 'EOF'
{
  "Rules": [
    {
      "ID": "replicate-to-eu-west",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "Destination": {
        "Bucket": "arn:minio:replication::arada:arada-bucket",
        "ReplicationTime": {
          "Status": "Enabled",
          "Time": {"Minutes": 15}
        },
        "Metrics": {
          "Status": "Enabled",
          "EventThreshold": {"Minutes": 15}
        }
      }
    }
  ]
}
EOF
```

### Replica Setup (Region B)

**3c. Add replica tenant (Kubernetes example):**

```yaml
minio-replica:
  image: minio/minio:latest
  environment:
    MINIO_ROOT_USER: arada
    MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    MINIO_REGION_NAME: eu-west-1
  command: >
    server /data
    --console-address ":9001"
  volumes:
    - minio-replica-data:/data
```

**3d. Peer MinIO instances (CLI):**

```bash
# On primary region
mc admin peer add arada-eu http://minio-replica:9000 arada $MINIO_SECRET_KEY --source

# Verify peer
mc admin peer list arada
```

### Monitor MinIO Replication

```bash
# Check replication status
mc stat arada/arada-bucket/some-object

# View replication metrics
mc admin heal arada --recursive --force --dry-run

# Replication lag
mc watch arada/arada-bucket --prefix videos/
```

---

## Part 4: Geographic Routing & Failover

### Option A: Cloudflare (Recommended)

**4a. Setup Cloudflare Load Balancing:**

1. Cloudflare Dashboard → **Load Balancing**
2. Create load balancer: `api.arada.fun`
3. Add origins:
   - **us-east.arada.fun** (Primary) — Priority 1, Health check enabled
   - **eu-west.arada.fun** (Secondary) — Priority 2, Health check enabled
4. Health check settings:
   - Endpoint: `/system/health`
   - Interval: 30s
   - Timeout: 5s
   - Expected code: 200

**4b. Failover behavior:**

```yaml
# Cloudflare Load Balancer config
{
  "name": "api.arada.fun",
  "origins": [
    {
      "name": "us-east",
      "address": "us-east.arada.fun",
      "enabled": true,
      "weight": 1,
      "monitor": "health-check-1"
    },
    {
      "name": "eu-west",
      "address": "eu-west.arada.fun",
      "enabled": true,
      "weight": 1,
      "monitor": "health-check-1"
    }
  ],
  "default_pool": "us-east",
  "fallback_pool": "eu-west",
  "ttl": 30  # DNS TTL (failover in ~30s)
}
```

### Option B: AWS Route53 (Enterprise)

**4c. Setup Route53 health checks:**

```hcl
# Terraform example
resource "aws_route53_health_check" "primary" {
  ip_address        = "us-east.arada.fun"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/system/health"
  failure_threshold = 3
  request_interval  = 30
  tags = {
    Name = "arada-primary"
  }
}

resource "aws_route53_health_check" "secondary" {
  ip_address        = "eu-west.arada.fun"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/system/health"
  failure_threshold = 3
  request_interval  = 30
}

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.arada.zone_id
  name    = "api.arada.fun"
  type    = "A"

  set_identifier = "Primary"
  failover_routing_policy {
    type = "PRIMARY"
  }

  alias {
    name                   = "us-east.arada.fun"
    zone_id                = aws_route53_zone.us_east.zone_id
    evaluate_target_health = true
  }
  health_check_id = aws_route53_health_check.primary.id
}

resource "aws_route53_record" "api_secondary" {
  zone_id = aws_route53_zone.arada.zone_id
  name    = "api.arada.fun"
  type    = "A"

  set_identifier = "Secondary"
  failover_routing_policy {
    type = "SECONDARY"
  }

  alias {
    name                   = "eu-west.arada.fun"
    zone_id                = aws_route53_zone.eu_west.zone_id
    evaluate_target_health = true
  }
  health_check_id = aws_route53_health_check.secondary.id
}
```

### Option C: Manual Failover (DNS)

**4d. Update DNS manually when failover needed:**

```bash
#!/bin/bash
# failover.sh - Manual DNS failover script

CURRENT_REGION=${1:-us-east}
TARGET_REGION=${2:-eu-west}

if [ "$CURRENT_REGION" = "us-east" ]; then
  echo "Failing over from US-EAST to EU-WEST..."
  
  # Update CloudFlare DNS (if using CF API)
  curl -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records/${RECORD_ID}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"content":"eu-west.arada.fun"}'
    
  echo "Failover complete. api.arada.fun now points to eu-west.arada.fun"
else
  echo "Failing back to US-EAST..."
  # Reverse process
fi
```

---

## Part 5: Promoting Replica to Primary (Disaster Recovery)

### PostgreSQL Failover

**5a. Promote replica to primary:**

```bash
#!/bin/bash
# On replica server

# Stop all replicas (if any)
psql -h localhost -U postgres -d postgres << 'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_replication;
SQL

# Promote replica to primary
pg_ctl promote -D /var/lib/postgresql/data

# Verify
psql -h localhost -U postgres -d postgres << 'SQL'
SELECT pg_is_in_recovery();  -- Should return false
SELECT NOW() as promotion_time;
SQL
```

**5b. Update streaming replication:**

```sql
-- On old primary (if still running), create standby.signal to demote
touch /var/lib/postgresql/data/standby.signal

-- Stop and restart PostgreSQL
systemctl restart postgresql

-- Verify it's now a standby
SELECT pg_is_in_recovery();  -- Should return true
```

### Redis Failover

**5c. Promote Redis replica:**

```bash
# On replica
redis-cli -p 6380 SLAVEOF NO ONE

# Verify
redis-cli -p 6380 INFO replication
# Should show: role:master

# Update primary to be replica of new primary (if needed)
redis-cli SLAVEOF <NEW_PRIMARY_IP> 6380
```

### Verify Data Consistency After Failover

```bash
# Check row counts (should match)
psql -h us-east.arada.fun -U arada -d arada -c "SELECT COUNT(*) FROM content.normalized_items;"
psql -h eu-west.arada.fun -U arada -d arada -c "SELECT COUNT(*) FROM content.normalized_items;"

# Check Redis keys (should match)
redis-cli -h us-east.arada.fun INFO keyspace
redis-cli -h eu-west.arada.fun INFO keyspace

# Check MinIO objects (should match)
mc ls arada/arada-bucket --recursive | wc -l
```

---

## Part 6: Data Sovereignty & Regional Compliance

### GDPR Compliance (EU region)

**6a. Restrict data residency:**

```sql
-- On EU-WEST replica only
CREATE POLICY eu_only ON auth.users
  USING (
    region = 'eu-west' OR
    country IN ('AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE')
  );

ALTER TABLE auth.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth.users ADD POLICY eu_only;
```

### Data Isolation (Regional Deployment)

**6b. Separate instances per region (independent databases):**

```yaml
# Region A (US-EAST)
services:
  postgres-us-east:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: arada_us_east
    volumes:
      - postgres-us-east-data:/var/lib/postgresql/data

  api-us-east:
    depends_on:
      postgres-us-east:
        condition: service_healthy
    environment:
      DB_NAME: arada_us_east
      REGION: us-east

---

# Region B (EU-WEST) — Independent stack
services:
  postgres-eu-west:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: arada_eu_west
    volumes:
      - postgres-eu-west-data:/var/lib/postgresql/data

  api-eu-west:
    depends_on:
      postgres-eu-west:
        condition: service_healthy
    environment:
      DB_NAME: arada_eu_west
      REGION: eu-west
```

---

## Part 7: Monitoring & Observability

### Cross-Region Prometheus Setup

**7a. Federate metrics across regions:**

```yaml
# Global Prometheus instance (or in primary region)
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'us-east'
    static_configs:
      - targets: ['us-east.arada.fun:9090']

  - job_name: 'eu-west'
    static_configs:
      - targets: ['eu-west.arada.fun:9090']

  - job_name: 'federate'
    scrape_interval: 15s
    honor_labels: true
    metrics_path: '/federate'
    params:
      'match[]':
        - '{job=~"prometheus"}'
        - '{__name__=~"job:.*"}'
    static_configs:
      - targets:
          - 'localhost:9090'
          - 'us-east.arada.fun:9090'
          - 'eu-west.arada.fun:9090'
```

### Replication-Specific Alerts

**7b. AlertManager rules:**

```yaml
groups:
  - name: replication
    rules:
      - alert: PostgreSQLReplicationLag
        expr: pg_replication_lag_bytes > 10485760
        for: 5m
        annotations:
          summary: "PostgreSQL replication lag > 10MB ({{ $labels.instance }})"

      - alert: PostgreSQLReplicaDown
        expr: up{job="postgres-replica"} == 0
        for: 2m
        annotations:
          summary: "PostgreSQL replica is down"

      - alert: RedisReplicationBroken
        expr: redis_connected_slaves == 0
        for: 2m
        annotations:
          summary: "Redis replication not working"

      - alert: MinIOReplicationLag
        expr: minio_replication_lag_seconds > 300
        for: 5m
        annotations:
          summary: "MinIO replication lag > 5min"
```

---

## Part 8: Active-Active Setup (Advanced)

For true active-active (both regions serve traffic simultaneously):

**8a. PostgreSQL with Bidirectional Replication (Logical)**

```sql
-- Create publication on both sides
CREATE PUBLICATION arada_pub FOR ALL TABLES;

-- Create subscription on each side pointing to the other
CREATE SUBSCRIPTION arada_sub CONNECTION 'host=eu-west.arada.fun user=replicator password=...' 
  PUBLICATION arada_pub;
```

⚠️ **Warning**: Bidirectional replication requires conflict resolution. Use only for read-heavy workloads or implement application-level conflict handling.

**8b. Global Write Conflict Resolution:**

```sql
-- Add conflict detection
ALTER TABLE content.normalized_items ADD COLUMN version_vector JSONB;

-- Before INSERT, check for conflicts
CREATE FUNCTION resolve_conflicts() RETURNS TRIGGER AS $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM content.normalized_items 
    WHERE id = NEW.id AND version_vector > NEW.version_vector
  ) THEN
    RETURN NULL;  -- Skip insert, remote version wins
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER conflict_resolver BEFORE INSERT ON content.normalized_items
  FOR EACH ROW EXECUTE FUNCTION resolve_conflicts();
```

**8c. Client-side region selection:**

```python
# FastAPI middleware to route to nearest region
from geolite2 import geolite2

@app.middleware("http")
async def route_by_region(request: Request, call_next):
    # Get client IP
    client_ip = request.client.host
    
    # Lookup geolocation
    match = geolite2.reader().get(client_ip)
    continent = match.get('continent', {}).get('code', 'NA')
    
    # Route to nearest region
    if continent == 'EU':
        request.state.region = 'eu-west'
    else:
        request.state.region = 'us-east'
    
    response = await call_next(request)
    return response
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] Secondary region provisioned (same specs as primary)
- [ ] Network connectivity verified (ping, telnet to ports)
- [ ] Certificates installed (TLS) on both regions
- [ ] Backup verified on primary before starting replication
- [ ] Replication user created with correct permissions
- [ ] Firewall rules allow replication traffic

### During Deployment
- [ ] PostgreSQL replication slot created
- [ ] Base backup from primary completed
- [ ] Replica streaming replication verified
- [ ] Redis replication working (INFO replication)
- [ ] MinIO replication syncing
- [ ] DNS configured (Cloudflare/Route53)
- [ ] Health checks responding on both regions
- [ ] Load balancer failover tested

### Post-Deployment
- [ ] Replication lag < 100ms (production threshold)
- [ ] Automated failover tested (kill primary, verify failover)
- [ ] Failback working (promote primary, demote replica)
- [ ] Cross-region monitoring dashboard live
- [ ] Alerts configured for replication lag/failures
- [ ] Runbook documented for emergency procedures
- [ ] Team trained on failover procedures

---

## Runbook: Emergency Failover

**Scenario**: Primary region (US-EAST) is down.

```bash
#!/bin/bash
# runbook-failover.sh

set -e

echo "🔴 EMERGENCY FAILOVER PROCEDURE"
echo "Primary region (US-EAST) is unavailable"
echo

# Step 1: Confirm primary is down
echo "Step 1: Confirming primary is down..."
if curl -f https://us-east.arada.fun/system/health 2>/dev/null; then
  echo "❌ Primary is still responding. Abort."
  exit 1
fi
echo "✓ Primary confirmed down"
echo

# Step 2: Promote secondary to primary
echo "Step 2: Promoting EU-WEST to primary..."
ssh eu-west.arada.fun << 'EOF'
  # PostgreSQL
  pg_ctl promote -D /var/lib/postgresql/data
  
  # Redis
  redis-cli SLAVEOF NO ONE
  
  # MinIO (already independent)
  echo "MinIO is already independent"
EOF
echo "✓ EU-WEST promoted to primary"
echo

# Step 3: Update DNS
echo "Step 3: Updating DNS to EU-WEST..."
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${CF_RECORD_ID}" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"content":"eu-west.arada.fun"}'
echo "✓ DNS updated"
echo

# Step 4: Verify
echo "Step 4: Verifying failover..."
sleep 5
if curl -f https://eu-west.arada.fun/system/health; then
  echo "✓ EU-WEST is responding"
else
  echo "❌ EU-WEST is not responding. CRITICAL!"
  exit 1
fi
echo

echo "✅ FAILOVER COMPLETE"
echo "All traffic now routed to EU-WEST"
echo
echo "Next steps:"
echo "  1. Investigate primary region (US-EAST) failure"
echo "  2. Repair primary region"
echo "  3. Run: bash runbook-failback.sh"
```

---

## Cost Estimates

| Component | Single Region | Multi-Region | Notes |
|-----------|---------------|--------------|-------|
| **Compute** | $200/mo | $400/mo | Doubled for 2 regions |
| **Database** | $50/mo | $100/mo | Replication overhead minimal |
| **Storage** | $100/mo | $200/mo | Cross-region data transfer costs |
| **Networking** | $50/mo | $150/mo | Cross-region egress (most expensive) |
| **DNS/LB** | $20/mo | $50/mo | Load balancer + health checks |
| **Monitoring** | $100/mo | $150/mo | Extra region's metrics |
| **Total** | **$520/mo** | **$1050/mo** | +100% cost for HA |

**Ways to reduce cost:**
- Active-Passive (secondary is smaller instance) — 60% cost of active-active
- Regional isolation (separate stacks, no replication) — same as single-region per region
- Scheduled replica (spin up on-demand for backups) — 10-20% of replication cost

---

## References

- PostgreSQL Replication: https://www.postgresql.org/docs/16/warm-standby.html
- Redis Replication: https://redis.io/docs/management/replication/
- MinIO Replication: https://min.io/docs/minio/linux/operations/install-deploy-manage/minio-replication.html
- Cloudflare Load Balancing: https://developers.cloudflare.com/load-balancing/
- AWS Route53: https://docs.aws.amazon.com/route53/latest/developerguide/

---

**See also**: [BACKUP.md](../BACKUP.md), [SECURITY.md](../security/SECURITY.md), [MONITORING.md](../monitoring/MONITORING.md)
