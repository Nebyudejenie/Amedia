# Arada Intelligence OS — DevOps & CI/CD Guide

Complete DevOps setup for production deployment to Proxmox with automated CI/CD via GitHub Actions.

## Overview

**Deployment Flow:**
```
Push to GitHub main branch
    ↓
GitHub Actions triggers
    ↓
1. Test & Lint (pytest, flake8, bandit)
    ↓
2. Build Docker image (ghcr.io registry)
    ↓
3. Security scan (Trivy vulnerability scan)
    ↓
4. Push to GitHub registry
    ↓
5. Deploy to Proxmox VM (SSH)
    ↓
6. Database migrations (Alembic)
    ↓
7. Start containers (docker-compose)
    ↓
8. Health checks (curl /system/health)
    ↓
9. Slack notification
```

---

## Part 1: GitHub Setup

### 1.1 Repository Secrets Configuration

You need to add these secrets to GitHub for CI/CD to work:

**Go to:** GitHub → Settings → Secrets and variables → Actions

Add these secrets:

| Secret Name | Value | Example |
|-------------|-------|---------|
| `PROXMOX_SSH_KEY` | Private SSH key for Proxmox | (see Step 1.2) |
| `DB_PASSWORD` | PostgreSQL password | `SecureP@ss123!` |
| `MINIO_SECRET_KEY` | MinIO secret | `MinioSecure123!` |
| `JWT_SECRET_KEY` | JWT secret (64 chars) | `random_64_char_string` |
| `GRAFANA_PASSWORD` | Grafana admin password | `GrafanaP@ss123!` |
| `METABASE_DB_PASSWORD` | Metabase DB password | `MetabaseDB123!` |
| `METABASE_SECRET_KEY` | Metabase secret (64 chars) | `random_64_char_string` |
| `SLACK_WEBHOOK_URL` | Slack webhook (optional) | `https://hooks.slack.com/...` |
| `GITHUB_USER` | Your GitHub username | `Nebyudejenie` |
| `GITHUB_TOKEN` | GitHub personal access token | (see Step 1.3) |

### 1.2 Generate SSH Key for Proxmox

On your local machine:

```bash
# Generate SSH key pair
ssh-keygen -t ed25519 -f ~/.ssh/proxmox_deploy -C "arada-deploy"
# Press Enter twice (no passphrase for CI/CD)

# Copy public key to Proxmox
ssh-copy-id -i ~/.ssh/proxmox_deploy.pub root@192.168.1.200

# Verify connection
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200 "echo 'SSH key works!'"

# Get the private key for GitHub (copy the contents of ~/.ssh/proxmox_deploy)
cat ~/.ssh/proxmox_deploy
```

Then in GitHub:
1. Go to Secrets → New repository secret
2. Name: `PROXMOX_SSH_KEY`
3. Paste the **entire private key** (including `-----BEGIN OPENSSH PRIVATE KEY-----` header)
4. Click "Add secret"

### 1.3 GitHub Personal Access Token

Create a token for pushing/pulling Docker images:

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Generate new token → Scopes:
   - `repo` (full control of private repositories)
   - `write:packages` (push Docker images)
   - `read:packages` (pull Docker images)
   - `workflow` (access Actions)
3. Copy the token → Add as `GITHUB_TOKEN` secret

---

## Part 2: Proxmox Setup

### 2.1 Install Docker & Docker Compose

SSH into Proxmox VM (192.168.1.200):

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sudo bash

# Add current user to docker group
sudo usermod -aG docker $(whoami)
newgrp docker

# Install Docker Compose
sudo curl -L https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify
docker --version
docker-compose --version
```

### 2.2 Prepare Deployment Directory

```bash
# Create deployment directory
sudo mkdir -p /opt/arada
sudo chown $(whoami):$(whoami) /opt/arada
cd /opt/arada

# Create .env file with secrets
cat > .env << 'ENVEOF'
# Database
DB_USER=arada
DB_PASSWORD=<STRONG_PASSWORD>
DB_NAME=arada

# MinIO
MINIO_ROOT_USER=arada
MINIO_SECRET_KEY=<STRONG_SECRET>

# Security
JWT_SECRET_KEY=<64_CHAR_RANDOM_STRING>
QDRANT_API_KEY=qdrant

# Monitoring
GRAFANA_PASSWORD=<GRAFANA_PASSWORD>
METABASE_DB_PASSWORD=<METABASE_PASSWORD>
METABASE_SECRET_KEY=<64_CHAR_SECRET>

# Registry
REGISTRY=ghcr.io/Nebyudejenie/Amedia
ENVEOF

# Verify .env was created
cat .env
```

### 2.3 Authenticate to GitHub Container Registry

```bash
# Login to GitHub registry (use your GitHub token)
echo $GITHUB_TOKEN | docker login ghcr.io -u <USERNAME> --password-stdin

# Verify login
docker run hello-world
```

### 2.4 Create Backup Directory

```bash
# Create backup location
sudo mkdir -p /opt/arada/backups
sudo chown $(whoami):$(whoami) /opt/arada/backups
```

---

## Part 3: Manual Deployment (for testing)

Before relying on GitHub Actions, test the deployment manually:

```bash
# Go to deployment directory
cd /opt/arada

# Copy docker-compose.prod.yml from repo
# (Or GitHub Actions will do this automatically)

# Pull latest image
docker pull ghcr.io/Nebyudejenie/Amedia:latest

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Check logs
docker-compose -f docker-compose.prod.yml logs -f api

# Test API health
curl http://localhost:8000/system/health

# Stop all services
docker-compose -f docker-compose.prod.yml down
```

---

## Part 4: GitHub Actions CI/CD

### 4.1 How CI/CD Works

When you push to `main` branch:

1. **Tests run** (flake8, pytest) — if fail, stops here
2. **Docker image builds** — multi-stage, optimized
3. **Security scan** (Trivy) — checks for vulnerabilities
4. **Push to registry** — ghcr.io/Nebyudejenie/Amedia
5. **Deploy to Proxmox** (only on main branch)
   - SSH into 192.168.1.200
   - Pull new image
   - Stop old containers
   - Run migrations
   - Start new containers
   - Health checks
6. **Slack notification** (if configured)

### 4.2 Workflow File Structure

Location: `.github/workflows/ci-cd.yml`

**Jobs:**
- `test` — Lint & unit tests
- `build` — Docker build & push
- `deploy` — Proxmox deployment (main branch only)
- `notify` — Slack notification

### 4.3 Triggering Deployments

**Automatic (on push to main):**
```bash
git checkout main
git pull origin main
echo "changes" >> file.txt
git add file.txt
git commit -m "Update something"
git push origin main
# → GitHub Actions automatically runs!
```

**Manual (via GitHub UI):**
1. Go to GitHub → Actions → CI/CD Pipeline
2. Click "Run workflow"
3. Select branch
4. Click "Run workflow"

### 4.4 Viewing Deployment Status

1. Go to GitHub → Actions
2. Click the workflow run
3. Expand the job you want to see
4. Watch real-time logs

---

## Part 5: Monitoring Deployments

### 5.1 Check Deployment Logs

```bash
# SSH into Proxmox
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

# View API logs
cd /opt/arada
docker-compose -f docker-compose.prod.yml logs -f api

# View all service logs
docker-compose -f docker-compose.prod.yml logs -f

# Check container status
docker-compose -f docker-compose.prod.yml ps
```

### 5.2 Health Checks

```bash
# API health
curl http://192.168.1.200:8000/system/health

# Database
docker-compose -f docker-compose.prod.yml exec postgres pg_isready -U arada

# Redis
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping

# MinIO
docker-compose -f docker-compose.prod.yml exec minio mc admin info minio
```

### 5.3 Prometheus Metrics

```bash
# View Prometheus targets
curl http://192.168.1.200:9090/api/v1/targets

# Query metrics
curl 'http://192.168.1.200:9090/api/v1/query?query=up'
```

---

## Part 6: Rollback Procedures

### 6.1 Automatic Rollback

If deployment fails health checks, CI/CD automatically rolls back to previous image.

Check CI/CD logs in GitHub Actions for rollback status.

### 6.2 Manual Rollback

If automatic rollback doesn't work:

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

cd /opt/arada

# Stop current containers
docker-compose -f docker-compose.prod.yml down

# Pull previous image (or specific tag)
docker pull ghcr.io/Nebyudejenie/Amedia:main-sha-<previous_commit_sha>

# Start with previous version
docker-compose -f docker-compose.prod.yml up -d

# Verify
curl http://localhost:8000/system/health
```

---

## Part 7: Troubleshooting

### Problem: "SSH key authentication failed"

```bash
# Verify SSH key is configured correctly
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200 "echo test"

# If fails, re-add public key to Proxmox
ssh-copy-id -i ~/.ssh/proxmox_deploy.pub root@192.168.1.200

# Update GitHub secret with new private key
cat ~/.ssh/proxmox_deploy  # Copy to PROXMOX_SSH_KEY secret
```

### Problem: "Docker registry authentication failed"

```bash
# Verify token is valid
docker logout ghcr.io
echo $GITHUB_TOKEN | docker login ghcr.io -u <USERNAME> --password-stdin

# Re-add token to GitHub secret
# Create new token if expired: github.com/settings/tokens
```

### Problem: "Database migration failed"

```bash
# SSH into Proxmox
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200
cd /opt/arada

# Check database logs
docker-compose -f docker-compose.prod.yml logs postgres | tail -100

# Run migrations manually
docker-compose -f docker-compose.prod.yml exec postgres psql -U arada -d arada -f /docker-entrypoint-initdb.d/001_init.sql
```

### Problem: "Health check timeout"

```bash
# Check API logs
docker-compose -f docker-compose.prod.yml logs api | tail -100

# Check port is listening
curl -v http://localhost:8000/system/health

# Check if API service crashed
docker-compose -f docker-compose.prod.yml ps api
```

### Problem: "Out of disk space"

```bash
# Check disk usage
df -h

# Clean up old Docker images
docker image prune -a --force

# Clean up old Docker volumes
docker volume prune --force

# Remove old logs
docker system prune --all --force --volumes
```

---

## Part 8: Scheduled Backups

### 8.1 Setup Daily Backup

Create cron job for automated backups:

```bash
# SSH into Proxmox
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

# Edit crontab
crontab -e

# Add this line (backup daily at 2 AM)
0 2 * * * cd /opt/arada && docker-compose -f docker-compose.prod.yml exec -T postgres pg_dump -U arada arada > /opt/arada/backups/backup-$(date +\%Y\%m\%d-\%H\%M\%S).sql

# Verify
crontab -l
```

### 8.2 Manual Backup

```bash
cd /opt/arada

# Backup database
docker-compose -f docker-compose.prod.yml exec -T postgres pg_dump -U arada arada > ./backups/backup-$(date +%Y%m%d-%H%M%S).sql

# Backup MinIO data
docker-compose -f docker-compose.prod.yml exec -T minio mc tar czf - minio/arada > ./backups/minio-$(date +%Y%m%d-%H%M%S).tar.gz

# Backup Redis
docker-compose -f docker-compose.prod.yml exec -T redis redis-cli BGSAVE
docker cp arada-redis-prod:/data/dump.rdb ./backups/redis-$(date +%Y%m%d-%H%M%S).rdb
```

---

## Part 9: SSL/TLS Setup (Let's Encrypt)

### 9.1 Install Certbot

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Get certificate for arada.fun and *.arada.fun
sudo certbot certonly --manual \
  -d arada.fun \
  -d '*.arada.fun' \
  --preferred-challenges dns \
  --agree-tos \
  -n

# Certificates will be at:
# /etc/letsencrypt/live/arada.fun/
```

### 9.2 Setup Nginx Reverse Proxy

See `infra/reverse-proxy/nginx.conf` for complete config.

```bash
# Install Nginx
sudo apt-get install -y nginx

# Copy config
sudo cp infra/reverse-proxy/nginx.conf /etc/nginx/sites-available/arada.fun

# Enable site
sudo ln -s /etc/nginx/sites-available/arada.fun /etc/nginx/sites-enabled/

# Test config
sudo nginx -t

# Start Nginx
sudo systemctl start nginx
sudo systemctl enable nginx
```

### 9.3 Auto-Renewal

```bash
# Enable Let's Encrypt auto-renewal
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

# Verify
sudo systemctl status certbot.timer
```

---

## Part 10: Production Checklist

Before going live, verify:

- [ ] GitHub secrets configured (all 8 secrets)
- [ ] SSH key working (test manual SSH)
- [ ] Docker Compose installed on Proxmox
- [ ] .env file created with strong passwords
- [ ] Proxmox firewall allows ports (8000, 6379, 5432, 9000, 9090, 3000, 3001)
- [ ] DNS points to Proxmox IP (192.168.1.200)
- [ ] SSL certificate configured (arada.fun)
- [ ] Backups configured
- [ ] Monitoring dashboards working
- [ ] Slack notifications configured (optional)
- [ ] Health checks passing
- [ ] Database migrations completed
- [ ] All services healthy (docker ps)
- [ ] API responding (curl http://localhost:8000/system/health)

---

## Part 11: Useful Commands

```bash
# SSH into Proxmox
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

# Go to deployment directory
cd /opt/arada

# View service status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f api

# Restart services
docker-compose -f docker-compose.prod.yml restart

# Stop services
docker-compose -f docker-compose.prod.yml down

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Pull latest image
docker pull ghcr.io/Nebyudejenie/Amedia:latest

# Access PostgreSQL
docker-compose -f docker-compose.prod.yml exec postgres psql -U arada -d arada

# Access Redis CLI
docker-compose -f docker-compose.prod.yml exec redis redis-cli

# View Prometheus metrics
curl http://localhost:9090/api/v1/targets

# Backup database
docker-compose -f docker-compose.prod.yml exec -T postgres pg_dump -U arada arada > backup.sql

# Restore database
docker-compose -f docker-compose.prod.yml exec -T postgres psql -U arada arada < backup.sql
```

---

## References

- Docker: https://docs.docker.com/
- Docker Compose: https://docs.docker.com/compose/
- GitHub Actions: https://docs.github.com/en/actions
- Let's Encrypt: https://letsencrypt.org/
- Prometheus: https://prometheus.io/docs/
- PostgreSQL Backup: https://www.postgresql.org/docs/16/backup-dump.html

---

**Need help?** Check GitHub Actions logs or contact DevOps team.
