# Arada Intelligence OS — Deployment Guide

**Version:** 1.0.0  
**Date:** 2026-06-11  
**Status:** Production Ready  

---

## 🚀 Quick Start (Development)

```bash
# Clone repo
git clone https://github.com/Nebyudejenie/Amedia.git
cd Amedia/arada-os

# Configure environment
cp .env.example .env

# Start services
docker-compose up -d

# Initialize database
docker-compose exec api alembic upgrade head

# Access application
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
# Grafana: http://localhost:3001
# Metabase: http://localhost:3000
```

---

## 🔧 Production Deployment (Kubernetes)

```bash
# Create namespace
kubectl create namespace arada

# Create secrets
kubectl create secret generic arada-secrets \
  --from-literal=db-password=$(openssl rand -base64 32) \
  --from-literal=jwt-secret=$(openssl rand -base64 32) \
  -n arada

# Install PostgreSQL
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgres bitnami/postgresql -n arada

# Install Redis
helm install redis bitnami/redis -n arada

# Deploy application
kubectl apply -f k8s/
kubectl get pods -n arada

# Configure ingress (SSL/TLS)
kubectl apply -f k8s/ingress.yaml
```

---

## 📊 Monitoring

```bash
# Prometheus metrics
curl http://localhost:8000/metrics

# Health check
curl http://localhost:8000/system/health

# View logs
kubectl logs -f -n arada deployment/arada-api
```

---

## 📈 Scaling

```bash
# Auto-scaling
kubectl autoscale deployment arada-api -n arada --min=3 --max=10

# Manual scaling
kubectl scale deployment arada-api -n arada --replicas=5
```

---

## 💾 Backups

```bash
# Database backup
kubectl exec -n arada postgres-0 -- pg_dump -U arada arada | gzip > backup.sql.gz

# Upload to S3
aws s3 cp backup.sql.gz s3://arada-backups/

# Restore
gunzip backup.sql.gz
kubectl exec -n arada postgres-0 -- psql -U arada arada < backup.sql
```

---

## ✅ Production Checklist

- [ ] SSL/TLS configured (HTTPS)
- [ ] Secrets in vault/K8s
- [ ] Database backups automated (daily)
- [ ] Monitoring enabled (Prometheus/Grafana)
- [ ] Alerts configured
- [ ] Auto-scaling enabled
- [ ] Load balancer configured
- [ ] Health checks passing
- [ ] Disaster recovery tested

---

**Status:** ✅ Production Ready
