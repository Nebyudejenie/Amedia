# Arada Intelligence OS on Kubernetes — Deployment Guide

## Overview

Deploy Arada Intelligence OS on any Kubernetes cluster (GKE, EKS, AKS, self-hosted, etc.) using Helm.

**Architecture:**
```
Kubernetes Cluster
├── Stateful Services (StatefulSets)
│   ├── postgres (1 replica, 100Gi)
│   ├── redis (1 replica, 10Gi)
│   ├── minio (1 replica, 500Gi)
│   └── qdrant (1 replica, 50Gi)
├── Stateless Services (Deployments)
│   ├── api (3 replicas, auto-scale 2-10)
│   ├── worker-content (2 replicas, auto-scale 1-5)
│   ├── orchestrator (2 replicas, auto-scale 1-3)
│   ├── publisher (1 replica, auto-scale 1-5)
│   └── ollama (1 replica, GPU optional)
├── Ingress (nginx/istio)
│   └── arada.fun → api:8000
└── Storage (PersistentVolumes)
    ├── fast-ssd (SSD for stateful data)
    └── bulk-storage (for MinIO backups)
```

## Prerequisites

- Kubernetes 1.24+ cluster
- kubectl configured
- Helm 3.0+
- Storage provisioner (gp3, fast-ssd, premium-rwo, etc.)
- Ingress controller (nginx or istio)

**Install Helm:**
```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

## Quick Start (5 minutes)

```bash
# 1. Clone repo
git clone https://github.com/arada-ai/arada-os.git
cd arada-os

# 2. Create secrets
kubectl create namespace arada
kubectl -n arada create secret generic arada-secrets \
  --from-literal=db-password=change-me-strong \
  --from-literal=minio-secret-key=change-me-strong \
  --from-literal=jwt-secret-key=$(openssl rand -base64 32)

# 3. Deploy
helm install arada infra/k8s/arada-os \
  --namespace arada \
  --set postgres.credentials.password=change-me-strong \
  --set minio.credentials.secretKey=change-me-strong \
  --set global.jwtSecretKey=$(openssl rand -base64 32)

# 4. Wait for rollout
kubectl -n arada rollout status deployment/api

# 5. Access
kubectl -n arada get ingress
# Visit: https://arada.fun (after DNS/TLS setup)
```

## Detailed Setup

### 1. Create Namespace & Secrets

```bash
# Create namespace
kubectl create namespace arada
kubectl label namespace arada istio-injection=enabled  # Optional

# Create secrets
kubectl -n arada create secret generic arada-secrets \
  --from-literal=db-password=$(openssl rand -32 | base64) \
  --from-literal=minio-secret-key=$(openssl rand -32 | base64) \
  --from-literal=jwt-secret-key=$(openssl rand -base64 32)

# Verify
kubectl -n arada get secrets
```

### 2. Configure Storage Classes

**GKE (Google Cloud):**
```bash
kubectl apply -f - << EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: pd.csi.storage.gke.io
parameters:
  type: pd-ssd
  replication-type: regional-pd
EOF
```

**EKS (AWS):**
```bash
kubectl apply -f - << EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: ebs.csi.aws.com
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
EOF
```

**AKS (Azure):**
```bash
kubectl apply -f - << EOF
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/azure-disk
parameters:
  storageaccounttype: Premium_LRS
  kind: Managed
EOF
```

### 3. Install Ingress Controller

**nginx (recommended):**
```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace
```

**Istio (optional):**
```bash
curl -L https://istio.io/downloadIstio | sh -
cd istio-*
./bin/istioctl install --set profile=demo
```

### 4. Create TLS Certificate

**Using cert-manager (recommended):**
```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true

# Create ClusterIssuer
kubectl apply -f - << EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@arada.fun
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

### 5. Deploy Arada OS

**Using custom values:**
```bash
helm install arada infra/k8s/arada-os \
  --namespace arada \
  --values infra/k8s/values-prod.yaml
```

**Or inline:**
```bash
helm install arada infra/k8s/arada-os \
  --namespace arada \
  --set global.domain=arada.fun \
  --set api.replicas=3 \
  --set api.autoscaling.enabled=true \
  --set postgres.storage.class=fast-ssd \
  --set minio.storage.size=500Gi
```

### 6. Monitor Deployment

```bash
# Watch rollout
kubectl -n arada rollout status deployment/api
kubectl -n arada rollout status statefulset/postgres

# Check pods
kubectl -n arada get pods
kubectl -n arada get pvc

# View logs
kubectl -n arada logs deployment/api
kubectl -n arada logs statefulset/postgres
```

## Configuration

### Custom values.yaml

Create `values-prod.yaml`:
```yaml
global:
  domain: arada.fun
  environment: production

postgres:
  replicas: 3
  storage:
    size: 500Gi
  resources:
    limits:
      memory: 4Gi

api:
  replicas: 5
  autoscaling:
    minReplicas: 3
    maxReplicas: 20

ingress:
  hosts:
    - host: arada.fun
      paths:
        - path: /
          pathType: Prefix
```

```bash
helm install arada infra/k8s/arada-os \
  -f values-prod.yaml \
  --namespace arada
```

### Update Deployment

```bash
helm upgrade arada infra/k8s/arada-os \
  --namespace arada \
  --values values-prod.yaml
```

## Scaling

### Horizontal Pod Autoscaling (HPA)

**Enabled by default** for:
- API (2-10 replicas, 70% CPU / 80% memory)
- worker-content (1-5 replicas)
- orchestrator (1-3 replicas)
- publisher (1-5 replicas)

**Monitor HPA:**
```bash
kubectl -n arada get hpa
kubectl -n arada describe hpa api-hpa
```

### Vertical Pod Autoscaling (VPA)

Optional (install separately):
```bash
helm repo add fairwinds-stable https://charts.fairwinds.com/stable
helm install vpa fairwinds-stable/vpa --namespace kube-system
```

### Database Replication

**PostgreSQL read replicas:**
```yaml
postgres:
  replicas: 3
  # Requires manual streaming replication setup
```

**Redis Sentinel (optional):**
```yaml
redis:
  replicas: 3
  sentinel:
    enabled: true
```

## Backup & Recovery

### Automated Backups

**Using Velero:**
```bash
helm repo add velero https://vmware-tanzu.github.io/helm-charts
helm install velero velero/velero \
  --namespace velero \
  --create-namespace \
  --set configuration.backupStorageLocation.bucket=arada-backups \
  --set configuration.backupStorageLocation.provider=aws
```

### Manual Backup

```bash
# PostgreSQL
kubectl -n arada exec postgres-0 -- pg_dump -U arada arada > backup.sql

# Full cluster
kubectl -n arada get all --export -o yaml > backup.yaml
```

### Restore

```bash
# PostgreSQL restore
kubectl -n arada exec -i postgres-0 -- psql -U arada arada < backup.sql

# Full restore
kubectl apply -f backup.yaml
```

## Monitoring & Logging

### Prometheus (optional)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

### ELK Stack (optional)

```bash
helm repo add elastic https://helm.elastic.co
helm install elasticsearch elastic/elasticsearch \
  --namespace logging \
  --create-namespace
```

### View Logs

```bash
kubectl -n arada logs deployment/api --all-containers=true -f
kubectl -n arada logs -l app=api --all-containers=true -f
```

## Networking

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: arada-network-policy
  namespace: arada
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
  egress:
  - to:
    - namespaceSelector: {}
```

### Service Discovery

**Internal DNS (automatic):**
```
postgres.arada.svc.cluster.local:5432
redis.arada.svc.cluster.local:6379
minio.arada.svc.cluster.local:9000
api.arada.svc.cluster.local:8000
```

## Cost Optimization

### Recommended Node Pool Sizes

**Development** (single-node):
- Machine type: n1-standard-4 (4 vCPU, 15GB RAM)
- Storage: 100GB SSD

**Production** (multi-node):
- Master: 3x n1-standard-2 (Kubernetes managed, auto-scale 3-5)
- Worker: 3x n1-highmem-4 (4 vCPU, 26GB RAM)
- Storage: 500GB+ SSD (gp3, premium-rwo, or pd-ssd)

**Cost per month** (GCP, us-central1):
- Compute: ~$200-400/month
- Storage: ~$50-100/month
- Network: ~$20-50/month
- **Total: ~$300-600/month**

### Resource Limits

```yaml
# Prevent resource explosion
resources:
  limits:
    cpu: 1000m
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

# Pod disruption budgets
podDisruptionBudget:
  minAvailable: 1
```

## Troubleshooting

### Pod Won't Start

```bash
kubectl -n arada describe pod [pod-name]
kubectl -n arada logs [pod-name]
kubectl -n arada logs [pod-name] --previous
```

### Database Connection Failed

```bash
# Test connectivity
kubectl -n arada exec api-0 -- psql -h postgres -U arada -d arada -c "SELECT 1;"

# Check service
kubectl -n arada get svc postgres
kubectl -n arada get endpoints postgres
```

### MinIO Not Accessible

```bash
# Check service
kubectl -n arada get svc minio

# Port-forward for testing
kubectl -n arada port-forward svc/minio 9000:9000
# Visit http://localhost:9000
```

### PVC Stuck in Pending

```bash
# Check storage class
kubectl get storageclass
kubectl -n arada get pvc

# Check node resources
kubectl top nodes
kubectl describe node [node-name]
```

## Cleanup

```bash
# Delete Helm release
helm uninstall arada --namespace arada

# Delete namespace
kubectl delete namespace arada

# Delete persistent volumes (WARNING: data loss)
kubectl delete pvc -n arada --all
```

## Advanced Topics

### Multi-Region Deployment

Replicate across regions with:
1. Multi-cloud Kubernetes (GKE, EKS, AKS)
2. Cross-region database replication
3. Global load balancer (Cloud CDN, CloudFront)

### GitOps (ArgoCD)

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd --namespace argocd --create-namespace
```

### Service Mesh (Istio)

```bash
# Enable traffic shaping, canary deployments, mutual TLS
istioctl install --set profile=production
```

## References

- Kubernetes Docs: https://kubernetes.io/docs/
- Helm Docs: https://helm.sh/docs/
- Cert-Manager: https://cert-manager.io/
- Velero: https://velero.io/

---

**See also**: [DEPLOYMENT.md](../DEPLOYMENT.md) for Docker Compose, [PROXMOX_DEPLOYMENT.md](./PROXMOX_DEPLOYMENT.md) for Proxmox setup.
