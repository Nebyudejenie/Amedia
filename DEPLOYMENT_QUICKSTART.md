# Arada Intelligence OS — Deployment Quick Start (15 Minutes)

**Complete guide to deploy Arada to your Proxmox infrastructure.**

---

## ⚡ 5-Minute Setup Checklist

### Step 1: Generate SSH Key (2 min)

On your local machine:

```bash
# Generate SSH key for Proxmox
ssh-keygen -t ed25519 -f ~/.ssh/proxmox_deploy -C "arada-deploy"
# Press Enter twice (no passphrase)

# Copy to Proxmox
ssh-copy-id -i ~/.ssh/proxmox_deploy.pub root@192.168.1.200

# Test it works
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200 "echo 'Connected!'"
```

### Step 2: Create GitHub Secrets (3 min)

Go to: **GitHub → Your Repo → Settings → Secrets and variables → Actions**

Add 8 secrets:

```bash
# 1. SSH Private Key
PROXMOX_SSH_KEY = (paste contents of ~/.ssh/proxmox_deploy)

# 2. Database password
DB_PASSWORD = Your_Strong_DB_Password_123!

# 3. MinIO secret
MINIO_SECRET_KEY = Your_Strong_MinIO_Secret_123!

# 4. JWT secret (copy one of these random strings)
JWT_SECRET_KEY = abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ12

# 5. Monitoring passwords
GRAFANA_PASSWORD = Your_Grafana_Password_123!
METABASE_DB_PASSWORD = Your_Metabase_DB_Password_123!
METABASE_SECRET_KEY = another_random_64_char_string_here_1234567890

# 6. GitHub credentials (for Docker registry)
GITHUB_USER = Your_GitHub_Username
GITHUB_TOKEN = ghp_your_personal_access_token_here
```

**How to add secrets:**
1. Click "New repository secret"
2. Name: (e.g., `DB_PASSWORD`)
3. Value: (e.g., your actual password)
4. Click "Add secret"
5. Repeat for all 8 secrets

### Step 3: Prepare Proxmox (5 min)

SSH into Proxmox VM:

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

# Install Docker & Docker Compose
curl -fsSL https://get.docker.com | sudo bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Create deployment directory
sudo mkdir -p /opt/arada
sudo chown $(whoami):$(whoami) /opt/arada
cd /opt/arada

# Create .env file (EDIT WITH ACTUAL VALUES)
cat > .env << 'EOF'
DB_PASSWORD=Your_Strong_DB_Password_123!
MINIO_SECRET_KEY=Your_Strong_MinIO_Secret_123!
JWT_SECRET_KEY=abcdefghijklmnopqrstuvwxyz1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ12
GRAFANA_PASSWORD=Your_Grafana_Password_123!
METABASE_DB_PASSWORD=Your_Metabase_DB_Password_123!
METABASE_SECRET_KEY=another_random_64_char_string_here_1234567890
REGISTRY=ghcr.io/Nebyudejenie/Amedia
EOF

# Verify .env
cat .env

# Login to Docker Registry
echo "Enter your GitHub token:"
read GITHUB_TOKEN
echo $GITHUB_TOKEN | docker login ghcr.io -u <your_github_username> --password-stdin
```

---

## 🚀 Deploy!

### Option A: Automatic Deployment (via GitHub Actions)

Simply push code to main branch:

```bash
# On your local machine
git push origin main

# Watch deployment in GitHub:
# Go to: GitHub → Actions → CI/CD Pipeline
# See real-time logs and status
```

**What happens automatically:**
1. Tests run (pytest, flake8)
2. Docker image builds
3. Security scan runs
4. Pushed to ghcr.io
5. Deployed to Proxmox (192.168.1.200)
6. Database migrations run
7. Containers start
8. Health checks verify

### Option B: Manual Deployment (for testing)

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200
cd /opt/arada

# Copy files from GitHub (or you can git clone)
# Assuming you have docker-compose.prod.yml locally

# Pull latest image
docker pull ghcr.io/Nebyudejenie/Amedia:latest

# Start everything
docker-compose -f docker-compose.prod.yml up -d

# Wait 30 seconds, then test
sleep 30
curl http://localhost:8000/system/health

# Should see: {"status": "healthy"}
```

---

## ✅ Verify Deployment

```bash
# SSH into Proxmox
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200
cd /opt/arada

# Check containers are running
docker-compose -f docker-compose.prod.yml ps

# Expected output (all should be "Up"):
# NAME                    STATUS
# arada-postgres-prod     Up (healthy)
# arada-redis-prod        Up (healthy)
# arada-minio-prod        Up (healthy)
# arada-qdrant-prod       Up (healthy)
# arada-ollama-prod       Up (healthy)
# arada-api-prod          Up (healthy)
# arada-prometheus-prod   Up
# arada-grafana-prod      Up
# arada-metabase-prod     Up

# Test API
curl http://localhost:8000/system/health

# Should return: {"status":"healthy","timestamp":"2026-06-10T..."}

# View logs
docker-compose -f docker-compose.prod.yml logs -f api
```

---

## 🌐 Access Your Deployment

Once deployed, access:

| Service | URL | Credentials |
|---------|-----|-------------|
| **API** | http://192.168.1.200:8000 | (public) |
| **API Docs** | http://192.168.1.200:8000/docs | (public) |
| **Grafana** | http://192.168.1.200:3001 | admin / (check .env) |
| **Metabase** | http://192.168.1.200:3000 | (first run setup) |
| **MinIO** | http://192.168.1.200:9001 | arada / (check .env) |
| **Prometheus** | http://192.168.1.200:9090 | (public) |

---

## 🔒 SSL/TLS Setup (Optional but Recommended)

To use your domain (arada.fun) with HTTPS:

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200

# Install Certbot
sudo apt-get install -y certbot

# Get SSL certificate
sudo certbot certonly --standalone \
  -d arada.fun \
  -d '*.arada.fun'

# Certificate will be at: /etc/letsencrypt/live/arada.fun/

# See infra/reverse-proxy/nginx.conf for Nginx setup
```

---

## 🐛 Troubleshooting

### "SSH key doesn't work"
```bash
# Re-copy SSH key to Proxmox
ssh-copy-id -i ~/.ssh/proxmox_deploy.pub root@192.168.1.200

# Or manually add to Proxmox:
ssh root@192.168.1.200
cat ~/.ssh/proxmox_deploy.pub >> ~/.ssh/authorized_keys
```

### "Docker image fails to pull"
```bash
# Login to GitHub registry
echo $GITHUB_TOKEN | docker login ghcr.io -u <username> --password-stdin

# Create new GitHub token if expired:
# github.com/settings/tokens → Generate new token
# Scopes: repo, write:packages, read:packages, workflow
```

### "API not responding"
```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs api | tail -100

# Check containers are running
docker-compose -f docker-compose.prod.yml ps

# Restart API
docker-compose -f docker-compose.prod.yml restart api
```

### "Database connection failed"
```bash
# Check PostgreSQL
docker-compose -f docker-compose.prod.yml logs postgres | tail -50

# Test connection
docker-compose -f docker-compose.prod.yml exec postgres psql -U arada -d arada -c "SELECT 1;"
```

---

## 📊 Monitoring Deployment

### View GitHub Actions Status

1. Go to **GitHub → Actions → CI/CD Pipeline**
2. Click the latest workflow run
3. Expand jobs to see logs

### View Proxmox Logs

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200
cd /opt/arada

# Real-time API logs
docker-compose -f docker-compose.prod.yml logs -f api

# All service logs
docker-compose -f docker-compose.prod.yml logs -f

# Export logs to file
docker-compose -f docker-compose.prod.yml logs > deployment.log
```

---

## 🔄 Update & Rollback

### Update (Push New Code)

```bash
# On your local machine
git commit -am "Update API endpoints"
git push origin main

# GitHub Actions automatically:
# 1. Tests code
# 2. Builds new image
# 3. Deploys to Proxmox
# 4. Verifies health

# Watch at: GitHub → Actions
```

### Rollback (If Something Breaks)

```bash
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200
cd /opt/arada

# Stop current version
docker-compose -f docker-compose.prod.yml down

# Pull previous version
docker pull ghcr.io/Nebyudejenie/Amedia:main-sha-<previous_sha>

# Start previous version
docker-compose -f docker-compose.prod.yml up -d

# Verify
curl http://localhost:8000/system/health
```

---

## 📚 Complete Documentation

For more details, see:
- **CI/CD Details:** `infra/DEVOPS.md`
- **Docker Setup:** `Dockerfile.prod`, `docker-compose.prod.yml`
- **Infrastructure:** `infra/PROXMOX_DEPLOYMENT.md`
- **Monitoring:** `infra/monitoring/MONITORING.md`
- **Security:** `infra/security/SECURITY.md`

---

## 🎉 Success!

You now have:

✅ Automated CI/CD pipeline via GitHub Actions
✅ Docker builds on every push
✅ Security scanning (Trivy)
✅ Automatic deployment to Proxmox
✅ Database migrations
✅ Health checks & monitoring
✅ Prometheus + Grafana dashboards
✅ Metabase analytics
✅ Slack notifications (optional)

**Your Arada Intelligence OS is now production-ready!**

---

**Questions?** Check `infra/DEVOPS.md` or GitHub Actions logs.
