# Arada Intelligence OS — Backup & Disaster Recovery

## Overview

**Backup Strategy**:
- PostgreSQL: Continuous WAL archiving (VM-100 → LXC-201)
- MinIO: Daily snapshots (VM-101 → LXC-201)
- Redis: RDB snapshots (VM-100, local recovery)
- Full system: Weekly tarball (all services → external storage)

**Recovery RTO/RPO**:
- Database: RPO = 0 (WAL streaming), RTO = 5-10 min
- MinIO: RPO = 1 day, RTO = 10-15 min
- Full: RPO = 7 days, RTO = 30+ min

## PostgreSQL WAL Archiving

### Setup (VM-100)

**Create archiving directory**:
```bash
sudo mkdir -p /var/arada/backup/wal
sudo chown postgres:postgres /var/arada/backup/wal
```

**Configure PostgreSQL** (in docker-compose.yml):
```yaml
postgres:
  environment:
    POSTGRES_INITDB_ARGS: "-c archive_mode=on -c archive_command='cp %p /var/arada/backup/wal/%f'"
  volumes:
    - /var/arada/backup/wal:/mnt/wal_archive
```

**Verify archiving**:
```bash
docker-compose exec postgres psql -U arada -d arada -c "SELECT * FROM pg_stat_archiver;"
```

### WAL Sync to LXC-201

**On LXC-201, setup SSH access**:
```bash
# Generate key pair
ssh-keygen -t ed25519 -f ~/.ssh/backup_key -N ""

# Add VM-100 authorized_keys
scp ~/.ssh/backup_key.pub arada@10.10.10.100:~/.ssh/authorized_keys_backup
# On VM-100: cat ~/.ssh/authorized_keys_backup >> ~/.ssh/authorized_keys
```

**Create sync script** (/home/arada/backup/sync-wal.sh):
```bash
#!/bin/bash
set -euo pipefail

LOG=/var/log/arada-backup.log
WAL_DIR=/mnt/backup/wal

mkdir -p $WAL_DIR

echo "[$(date)] Syncing WAL files..." >> $LOG

rsync -avz --delete \
  -e "ssh -i ~/.ssh/backup_key" \
  arada@10.10.10.100:/var/arada/backup/wal/ \
  $WAL_DIR/

echo "[$(date)] WAL sync complete" >> $LOG
```

**Schedule sync** (crontab):
```bash
*/5 * * * * /home/arada/backup/sync-wal.sh  # Every 5 minutes
```

### Restore from WAL

**Full recovery** (point-in-time):
```bash
# On fresh PostgreSQL:
pg_basebackup -h 10.10.10.101 -U arada -D /var/lib/postgresql/data

# Create recovery.conf
cat > /var/lib/postgresql/data/recovery.conf << EOF
restore_command = 'cp /mnt/backup/wal/%f %p'
recovery_target_timeline = 'latest'
EOF

# Start recovery
pg_ctl start -D /var/lib/postgresql/data
# Monitor: tail -f /var/log/postgresql/postgresql.log
```

## MinIO Snapshots

### Daily Backup Script (LXC-201)

**Install s3cmd**:
```bash
sudo apt-get install -y s3cmd
s3cmd --configure  # Configure for MinIO (10.10.10.101:9000)
```

**Backup script** (/home/arada/backup/minio-backup.sh):
```bash
#!/bin/bash
set -euo pipefail

LOG=/var/log/arada-backup.log
BACKUP_DIR=/mnt/backup/minio
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

echo "[$(date)] Starting MinIO backup..." >> $LOG

# Create backup directory
mkdir -p $BACKUP_DIR/$TIMESTAMP

# Sync all buckets
s3cmd sync s3://arada s3://arada-backup/snapshot-$TIMESTAMP --recursive

# Compress backup
tar -czf $BACKUP_DIR/minio-$TIMESTAMP.tar.gz \
  --exclude='*.tmp' \
  /mnt/backup/minio/$TIMESTAMP

rm -rf $BACKUP_DIR/$TIMESTAMP

# Keep only last 30 days
find $BACKUP_DIR -name "minio-*.tar.gz" -mtime +30 -delete

echo "[$(date)] MinIO backup complete: $BACKUP_DIR/minio-$TIMESTAMP.tar.gz" >> $LOG
```

**Schedule backup** (crontab):
```bash
0 23 * * * /home/arada/backup/minio-backup.sh  # Daily at 23:00 UTC
```

### Restore MinIO

**From backup**:
```bash
# Extract backup
tar -xzf /mnt/backup/minio/minio-20240601-000000.tar.gz -C /tmp

# Use mc to restore
docker-compose exec minio mc mirror /tmp/snapshot-20240601-000000 minio/arada/
```

## Redis Snapshots

Redis RDB is enabled by default (in docker-compose.yml volumes).

**Manual backup**:
```bash
# On VM-100:
docker-compose exec redis redis-cli BGSAVE
docker-compose exec redis redis-cli LASTSAVE

# Copy dump.rdb
docker cp arada-redis:/data/dump.rdb ~/backup/redis-$(date +%s).rdb
```

**Restore**:
```bash
docker cp redis-backup.rdb arada-redis:/data/dump.rdb
docker-compose restart redis
```

## Full System Backup

### Weekly Tarball

**Backup script** (/home/arada/backup/full-backup.sh):
```bash
#!/bin/bash
set -euo pipefail

LOG=/var/log/arada-backup.log
BACKUP_DIR=/mnt/backup/full
TIMESTAMP=$(date +%Y%m%d)

echo "[$(date)] Starting full system backup..." >> $LOG

# Backup docker volumes
mkdir -p $BACKUP_DIR/$TIMESTAMP

docker-compose down  # Stop services safely

# Backup volumes
tar -czf $BACKUP_DIR/postgres-$TIMESTAMP.tar.gz postgres_data/
tar -czf $BACKUP_DIR/redis-$TIMESTAMP.tar.gz redis_data/
tar -czf $BACKUP_DIR/minio-$TIMESTAMP.tar.gz minio_data/
tar -czf $BACKUP_DIR/qdrant-$TIMESTAMP.tar.gz qdrant_data/

docker-compose up -d  # Restart services

# Keep only last 4 weeks
find $BACKUP_DIR -name "*.tar.gz" -mtime +28 -delete

echo "[$(date)] Full backup complete" >> $LOG
```

**Schedule** (weekly Sunday):
```bash
0 2 * * 0 /home/arada/backup/full-backup.sh  # Weekly at 02:00 UTC
```

## External Backup (Cloud)

### Upload to S3 (AWS/Backblaze B2/DigitalOcean Spaces)

**Script** (/home/arada/backup/upload-external.sh):
```bash
#!/bin/bash
set -euo pipefail

LOG=/var/log/arada-backup.log

# AWS S3
aws s3 sync /mnt/backup/wal s3://your-bucket/arada/wal --delete
aws s3 sync /mnt/backup/minio s3://your-bucket/arada/minio --delete
aws s3 sync /mnt/backup/full s3://your-bucket/arada/full --delete

echo "[$(date)] External backup upload complete" >> $LOG
```

**Install AWS CLI**:
```bash
sudo apt-get install -y awscli
aws configure  # Set credentials
```

**Schedule**:
```bash
0 3 * * * /home/arada/backup/upload-external.sh  # Daily at 03:00 UTC
```

## Monitoring & Validation

### Backup Health Check

**Script** (/home/arada/backup/check-backups.sh):
```bash
#!/bin/bash

check_wal() {
  count=$(ls /mnt/backup/wal | wc -l)
  if [[ $count -gt 0 ]]; then
    echo "✓ WAL backup: $count files"
  else
    echo "✗ WAL backup: FAILED"
  fi
}

check_minio() {
  latest=$(ls -lt /mnt/backup/minio/minio-*.tar.gz | head -1 | awk '{print $NF}')
  age=$(($(date +%s) - $(stat -c %Y $latest)))
  if [[ $age -lt 86400 ]]; then  # Less than 1 day
    echo "✓ MinIO backup: $(basename $latest)"
  else
    echo "✗ MinIO backup: STALE ($(($age / 3600)) hours old)"
  fi
}

check_full() {
  latest=$(ls -lt /mnt/backup/full/*.tar.gz 2>/dev/null | head -1 | awk '{print $NF}')
  if [[ -n "$latest" ]]; then
    echo "✓ Full backup: $(basename $latest)"
  else
    echo "✗ Full backup: NONE"
  fi
}

echo "Backup Status:"
check_wal
check_minio
check_full
```

**Monitor logs**:
```bash
tail -f /var/log/arada-backup.log
```

## Disaster Recovery Procedures

### Scenario 1: Database Corruption (VM-100)

```bash
# Stop API
docker-compose stop api worker-content

# Perform point-in-time recovery
pg_basebackup -h localhost -U arada -D /tmp/recovery
# ... restore from WAL as per instructions above

# Restart API
docker-compose start api worker-content
```

### Scenario 2: MinIO Data Loss (VM-101)

```bash
# Stop services that depend on MinIO
docker-compose stop orchestrator publisher

# Restore from backup
tar -xzf /mnt/backup/minio/minio-latest.tar.gz -C /tmp
docker-compose exec minio mc mirror /tmp/snapshot minio/arada/

# Restart services
docker-compose start orchestrator publisher
```

### Scenario 3: VM-100 Total Failure

```bash
# On fresh VM:
1. Provision VM-100 with Ubuntu 24.04
2. Install Docker/Docker Compose
3. Clone arada-os repo
4. Restore database from LXC-201 WAL archive
5. Restore PostgreSQL from backup
6. Start services
```

### Scenario 4: All Services Down

```bash
# On LXC-201:
1. Verify backups exist
   - /mnt/backup/wal/* (WAL files)
   - /mnt/backup/minio/* (MinIO snapshots)
   - /mnt/backup/full/* (Full backups)

# Restore order:
1. Create fresh VMs (VM-100, VM-101)
2. Restore PostgreSQL from latest full backup + WAL
3. Restore MinIO from latest snapshot
4. Start all services
5. Verify health checks pass
```

## Testing Backups

**Monthly restore test** (do NOT skip):
```bash
# 1. Spin up a test VM
# 2. Restore from latest full backup
# 3. Verify all data integrity
# 4. Run api/verify.sh
# 5. Document any issues
# 6. Destroy test VM

# Add to calendar: "Test backup restore - 1st of month"
```

## Backup Storage Capacity

**Typical daily growth**:
- WAL files: 50MB-500MB/day
- MinIO snapshots: 100MB-1GB/day
- Full backups (weekly): 5-10GB

**LXC-201 (100GB)**:
- WAL archive (7 days): ~3-5GB
- MinIO snapshots (30 days): ~5-10GB
- Full backups (4 weeks): ~20-40GB
- Free space: ~40GB

**External storage recommendation**: Unlimited (cloud S3)

## References

- PostgreSQL WAL: https://www.postgresql.org/docs/16/continuous-archiving.html
- MinIO: https://docs.min.io/docs/minio-client-quickstart-guide.html
- RTO/RPO: https://en.wikipedia.org/wiki/Recovery_time_objective

---

**Last Updated**: 2024-06-09
