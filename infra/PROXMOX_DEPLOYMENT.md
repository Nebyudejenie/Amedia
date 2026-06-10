# Arada Intelligence OS on Proxmox — Multi-VM Deployment

## Architecture Overview

```
Proxmox Host (32GB RAM, 1TB SSD)
├── VM-100 (20GB RAM, 350GB) — CORE SERVICES
│   ├── PostgreSQL 16 (5432)
│   ├── Redis 7 (6379)
│   ├── FastAPI (8000)
│   └── worker-content (background)
│
├── VM-101 (8GB RAM, 500GB) — MEDIA SERVICES
│   ├── MinIO (9000/9001)
│   ├── Ollama (11434)
│   ├── orchestrator (background)
│   └── publisher (background)
│
├── LXC-200 (2GB RAM, 50GB) — MONITORING
│   ├── Prometheus (9090)
│   ├── Health check aggregator
│   └── Log archiver
│
└── LXC-201 (2GB RAM, 100GB) — BACKUP
    ├── PostgreSQL WAL archiving
    ├── MinIO snapshot backup
    └── Scheduled backup jobs
```

**Internal Network**: vmbr1 (10.10.10.0/24)
- VM-100: 10.10.10.100
- VM-101: 10.10.10.101
- LXC-200: 10.10.10.200
- LXC-201: 10.10.10.201

**Firewall Rules**:
- VM-100 ↔ VM-101: All ports open (internal)
- VM-100 ↔ LXC-200: 9090 (Prometheus scrape)
- VM-100 → LXC-201: 5432 (WAL archive)
- Public: Cloudflare Tunnel on VM-100 (port 8000)

## Deployment Steps

### 1. VM-100 (Core Services)

**Specs**: 20GB RAM (balloon 10GB min), 350GB storage, 8 vCPU

**Startup**:
```bash
# SSH into VM-100
ssh arada@10.10.10.100

# Clone repo
git clone https://github.com/arada-ai/arada-os.git
cd arada-os

# Copy core docker-compose
cp infra/vm100/docker-compose.yml .

# Setup environment
cp .env.example .env
# Edit .env with strong passwords
nano .env

# Start services
docker-compose up -d postgres redis api worker-content

# Wait for health
sleep 30
docker-compose ps
docker-compose exec api curl http://127.0.0.1:8000/system/health
```

**Exposed Ports** (on vmbr1 only):
- PostgreSQL: 10.10.10.100:5432
- Redis: 10.10.10.100:6379
- FastAPI: 10.10.10.100:8000

**Health Check**:
```bash
docker-compose exec postgres pg_isready -U arada
docker-compose exec redis redis-cli ping
curl http://10.10.10.100:8000/system/health
```

### 2. VM-101 (Media Services)

**Specs**: 8GB RAM (balloon 4GB min), 500GB storage, 4 vCPU

**Startup**:
```bash
# SSH into VM-101
ssh arada@10.10.10.101

# Clone repo
git clone https://github.com/arada-ai/arada-os.git
cd arada-os

# Copy media docker-compose
cp infra/vm101/docker-compose.yml .

# Setup environment (connect to VM-100)
cat > .env << EOF
DB_HOST=10.10.10.100
DB_PORT=5432
DB_USER=arada
DB_PASSWORD=$(cat ~/.arada/db_password)
REDIS_HOST=10.10.10.100
REDIS_PORT=6379
MINIO_SECRET_KEY=change-me-strong-key
OLLAMA_HOST=0.0.0.0:11434
EOF

# Start services
docker-compose up -d minio ollama orchestrator publisher

# Wait for health
sleep 60
docker-compose ps
curl http://10.10.10.101:9000/minio/health/live
```

**Exposed Ports** (on vmbr1 only):
- MinIO API: 10.10.10.101:9000
- MinIO Console: 10.10.10.101:9001
- Ollama: 10.10.10.101:11434

**Health Check**:
```bash
curl http://10.10.10.101:9000/minio/health/live
curl http://10.10.10.101:11434/api/tags
```

### 3. LXC-200 (Monitoring)

**Specs**: 2GB RAM, 50GB storage, 2 vCPU

**Startup**:
```bash
# SSH into LXC-200
ssh arada@10.10.10.200

# Install Prometheus
sudo apt-get update
sudo apt-get install -y prometheus

# Configure Prometheus
sudo tee /etc/prometheus/prometheus.yml > /dev/null << EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'arada-api'
    static_configs:
      - targets: ['10.10.10.100:8000']
    metrics_path: '/metrics'

  - job_name: 'arada-postgres'
    static_configs:
      - targets: ['10.10.10.100:9187']

  - job_name: 'arada-redis'
    static_configs:
      - targets: ['10.10.10.100:9121']
EOF

# Start Prometheus
sudo systemctl restart prometheus
sudo systemctl enable prometheus

# Verify
curl http://127.0.0.1:9090/-/healthy
```

**Exposed Ports**:
- Prometheus: 10.10.10.200:9090

### 4. LXC-201 (Backup)

**Specs**: 2GB RAM, 100GB storage, 2 vCPU

**Startup**:
```bash
# SSH into LXC-201
ssh arada@10.10.10.201

# Install backup tools
sudo apt-get update
sudo apt-get install -y postgresql-client-16 s3cmd

# Configure WAL archiving
cat > ~/.pgpass << EOF
10.10.10.100:5432:arada:arada:$(cat ~/.arada/db_password)
EOF
chmod 600 ~/.pgpass

# Configure S3 backup
s3cmd --configure  # Configure MinIO as S3

# Create backup scripts
mkdir -p ~/backup
```

**See**: [BACKUP.md](BACKUP.md) for detailed backup procedures.

## Service Communication

### VM-100 → VM-100 (localhost)
```
api ↔ postgres
api ↔ redis
worker-content ↔ postgres
worker-content ↔ redis
```

### VM-100 → VM-101 (vmbr1, 10.10.10.0/24)
```
api → minio (10.10.10.101:9000)
api → ollama (10.10.10.101:11434)
worker-content → qdrant (10.10.10.101:6333) [if on VM-101]
```

### VM-100 → LXC-200 (vmbr1, metrics push)
```
api (metrics) → prometheus (10.10.10.200:9090)
```

### VM-100 → LXC-201 (vmbr1, backup)
```
postgres → WAL archive to 10.10.10.201
```

## Network Configuration

### VM-100 (Core)
```bash
# /etc/network/interfaces
auto eth0
iface eth0 inet dhcp

auto eth1
iface eth1 inet static
  address 10.10.10.100/24
  gateway 10.10.10.1
```

### VM-101 (Media)
```bash
auto eth0
iface eth0 inet dhcp

auto eth1
iface eth1 inet static
  address 10.10.10.101/24
  gateway 10.10.10.1
```

### UFW Rules (VM-100)
```bash
sudo ufw default deny incoming
sudo ufw allow ssh
sudo ufw allow from 10.10.10.0/24  # Internal network

# Allow specific ports from public (via Cloudflare Tunnel)
sudo ufw allow 8000/tcp
```

### UFW Rules (VM-101)
```bash
sudo ufw default deny incoming
sudo ufw allow ssh
sudo ufw allow from 10.10.10.0/24  # Internal network
```

## Health Checks

### API Health (from any guest)
```bash
curl http://10.10.10.100:8000/system/health
```

Returns:
```json
{
  "status": "ok",
  "checks": {
    "postgresql": "ok",
    "redis": "ok",
    "qdrant": "ok"
  }
}
```

### Database Health (VM-100)
```bash
docker-compose exec postgres psql -U arada -d arada -c "SELECT 1;"
```

### MinIO Health (VM-101)
```bash
curl http://10.10.10.101:9000/minio/health/live
```

### Prometheus Targets (LXC-200)
```bash
curl http://10.10.10.200:9090/api/v1/targets
```

## Monitoring & Alerts

### Prometheus Queries

**API request rate**:
```
rate(http_requests_total[5m])
```

**Database connections**:
```
SELECT count(*) FROM pg_stat_activity;
```

**Redis memory usage**:
```
INFO memory
```

### Alert Rules (LXC-200)
Create `/etc/prometheus/rules.yml`:
```yaml
groups:
  - name: arada
    rules:
      - alert: APIDown
        expr: up{job="arada-api"} == 0
        for: 2m

      - alert: DatabaseDown
        expr: pg_up{job="arada-postgres"} == 0
        for: 2m

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
```

## Backup Strategy

### PostgreSQL
- **Method**: WAL archiving to LXC-201
- **Frequency**: Continuous (archiving)
- **Retention**: 7 days of WAL files

**Configure on VM-100**:
```bash
# In docker-compose.yml postgres service:
environment:
  POSTGRES_INITDB_ARGS: "-c archive_mode=on -c archive_command='scp %p arada@10.10.10.201:/backup/wal/%f'"
```

### MinIO
- **Method**: Scheduled snapshots to LXC-201
- **Frequency**: Daily (23:00 UTC)
- **Retention**: 30 days

**On LXC-201**:
```bash
crontab -e
# Add: 0 23 * * * /home/arada/backup/minio-backup.sh
```

### Full Backup (VM-100)
```bash
docker-compose down
tar -czf backup-$(date +%Y%m%d).tar.gz postgres_data redis_data
# Send to LXC-201: scp backup-*.tar.gz arada@10.10.10.201:/backup/
docker-compose up -d
```

## Scaling & Maintenance

### Upgrade PostgreSQL (VM-100)
```bash
# Stop services
docker-compose down

# Backup
pg_dump -U arada -d arada > backup.sql

# Update image in docker-compose.yml
# pg_upgrade or full restore

docker-compose up -d postgres
```

### Scale Workers (VM-100 or VM-101)
Add more worker replicas in docker-compose.yml:
```yaml
worker-content-2:
  extends: worker-content
  container_name: arada-worker-content-2
  environment:
    WORKER_ID: content-2
```

### Rebalance Services
Move MinIO to dedicated storage VM:
1. Create new VM with large SSD
2. Configure MinIO on new VM
3. Sync buckets: `mc mirror minio1/bucket minio2/bucket`
4. Update API env (MINIO_HOST)
5. Drain old MinIO, remove from VM-101

## Disaster Recovery

### Database Failure (VM-100)
```bash
# On LXC-201: restore from WAL archive
pg_basebackup -h 10.10.10.201 -U arada -D /tmp/recovery
# Point recovery.conf to archived WAL
pg_ctl start -D /tmp/recovery
```

### VM-101 (Media) Failure
```bash
# Start new VM-101
docker-compose up -d minio ollama

# Restore MinIO from backup
mc mirror /backup/minio-snapshot minio/
```

### Total Loss
```bash
# 1. Restore Proxmox guests from backup
# 2. Restore PostgreSQL from WAL archive (LXC-201)
# 3. Restore MinIO from daily snapshot (LXC-201)
# 4. Restart all services
docker-compose up -d
```

## Public Access (Cloudflare Tunnel)

### Setup on VM-100
```bash
# Install cloudflared
sudo apt-get install -y cloudflare-warp

# Authenticate
sudo cloudflared tunnel login

# Create tunnel
sudo cloudflared tunnel create arada

# Configure
cat > ~/.cloudflared/arada-config.yml << EOF
tunnel: arada
credentials-file: ~/.cloudflared/arada-creds.json
ingress:
  - hostname: arada.fun
    service: http://localhost:8000
  - service: http_status:404
EOF

# Start
sudo cloudflared tunnel run --config ~/.cloudflared/arada-config.yml
```

Now `arada.fun` points to VM-100 API (8000) without exposing home IP.

## Monitoring Checklist

- [ ] PostgreSQL CPU/memory (Prometheus)
- [ ] Redis memory usage (INFO memory)
- [ ] MinIO disk usage (du -sh /data)
- [ ] Network I/O (iftop, nethogs)
- [ ] API response time (Prometheus query)
- [ ] Worker queue depth (Redis LLEN)
- [ ] Backup success (log file check)

## Troubleshooting

**VM-101 can't reach VM-100 PostgreSQL**:
```bash
# On VM-101:
ping 10.10.10.100  # Check connectivity
psql -h 10.10.10.100 -U arada -d arada -c "SELECT 1;"
```

**API can't reach MinIO**:
```bash
# On VM-100:
docker-compose exec api curl http://10.10.10.101:9000/minio/health/live
```

**Backup job failed**:
```bash
# On LXC-201:
tail -f /var/log/arada-backup.log
```

---

**See also**: [DEPLOYMENT.md](../DEPLOYMENT.md) for Docker Compose, [BACKUP.md](./BACKUP.md) for backup details.
