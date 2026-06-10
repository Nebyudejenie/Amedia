# Arada Intelligence OS on Kubernetes

Deploy Arada Intelligence OS on any Kubernetes cluster using Helm charts.

## Quick Start

```bash
# 1. Install Helm (if needed)
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# 2. Create namespace and secrets
kubectl create namespace arada
kubectl -n arada create secret generic arada-secrets \
  --from-literal=db-password=$(openssl rand -base64 32) \
  --from-literal=minio-secret-key=$(openssl rand -base64 32) \
  --from-literal=jwt-secret-key=$(openssl rand -base64 32)

# 3. Deploy
helm install arada arada-os \
  --namespace arada \
  --values values-production.yaml

# 4. Monitor
kubectl -n arada rollout status deployment/api
kubectl -n arada get pods
```

## Structure

```
infra/k8s/
├── arada-os/                     # Helm chart
│   ├── Chart.yaml               # Chart metadata
│   ├── values.yaml              # Default values
│   ├── values-production.yaml    # Production overrides
│   ├── values-development.yaml   # Development overrides
│   └── templates/               # Kubernetes templates
│       ├── namespace.yaml       # Namespace
│       ├── secrets.yaml         # Secret storage
│       ├── postgres-statefulset.yaml
│       ├── redis-statefulset.yaml
│       ├── minio-statefulset.yaml
│       ├── qdrant-statefulset.yaml
│       ├── api-deployment.yaml
│       ├── workers.yaml         # content, orchestrator, publisher
│       ├── ingress.yaml         # Ingress rules
│       ├── rbac.yaml            # Service accounts + roles
│       ├── network-policy.yaml   # Network isolation
│       └── pod-disruption-budget.yaml
└── README.md                    # This file
```

## Deployment

### Development (Minikube / Local)

```bash
minikube start --cpus=4 --memory=8192

helm install arada arada-os \
  --namespace arada \
  --create-namespace \
  --values values-development.yaml
```

### Production (GKE)

```bash
# Create cluster
gcloud container clusters create arada \
  --zone us-central1-a \
  --num-nodes 3 \
  --machine-type n1-highmem-4

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Create secrets
kubectl create namespace arada
kubectl -n arada create secret generic arada-secrets \
  --from-literal=db-password=$(openssl rand -base64 32) \
  --from-literal=minio-secret-key=$(openssl rand -base64 32) \
  --from-literal=jwt-secret-key=$(openssl rand -base64 32)

# Deploy
helm install arada arada-os \
  --namespace arada \
  --values values-production.yaml
```

### Production (EKS)

```bash
# Create cluster
eksctl create cluster \
  --name arada \
  --region us-east-1 \
  --nodegroup-name workers \
  --nodes 3 \
  --node-type t3.2xlarge

# Deploy (same as GKE)
helm install arada arada-os --values values-production.yaml
```

## Configuration

### Override Values

```bash
helm install arada arada-os \
  --set api.replicas=5 \
  --set postgres.storage.size=500Gi \
  --set global.domain=my-domain.com
```

### Use Custom Values File

```bash
helm install arada arada-os -f my-values.yaml
```

### Update Deployment

```bash
helm upgrade arada arada-os --values values-production.yaml
```

## Monitoring

### View Pods

```bash
kubectl -n arada get pods
kubectl -n arada get statefulsets
kubectl -n arada get deployments
```

### View Logs

```bash
# Follow API logs
kubectl -n arada logs -f deployment/api

# Follow PostgreSQL logs
kubectl -n arada logs -f statefulset/postgres

# View all logs
kubectl -n arada logs -f -l app=api
```

### Check Health

```bash
# Port-forward to test health endpoint
kubectl -n arada port-forward svc/api 8000:8000
curl http://localhost:8000/system/health
```

### View Resources

```bash
kubectl -n arada get pvc
kubectl -n arada get pv
kubectl -n arada describe pvc postgres-data-postgres-0
```

## Scaling

### Manual Scaling

```bash
# Scale API deployment
kubectl -n arada scale deployment api --replicas=5

# Scale stateful set
kubectl -n arada patch statefulset postgres -p '{"spec":{"replicas":3}}'
```

### Auto Scaling

HPA is enabled by default for:
- api (2-10 replicas)
- worker-content (1-5 replicas)
- orchestrator (1-3 replicas)
- publisher (1-5 replicas)

View HPA status:
```bash
kubectl -n arada get hpa
kubectl -n arada describe hpa api-hpa
```

## Backup & Recovery

### Backup PostgreSQL

```bash
kubectl -n arada exec postgres-0 -- pg_dump -U arada arada > backup.sql
```

### Restore PostgreSQL

```bash
kubectl -n arada exec -i postgres-0 -- psql -U arada arada < backup.sql
```

### Backup Full Cluster

```bash
helm get values arada > values-backup.yaml
kubectl -n arada get all -o yaml > cluster-backup.yaml
```

## Troubleshooting

### Pod Fails to Start

```bash
kubectl -n arada describe pod [pod-name]
kubectl -n arada logs [pod-name]
kubectl -n arada logs [pod-name] --previous
```

### PVC Stuck in Pending

```bash
# Check storage class
kubectl get storageclass

# Check events
kubectl -n arada describe pvc postgres-data-postgres-0
```

### Connection Issues

```bash
# Test database connectivity
kubectl -n arada exec api-0 -- \
  psql -h postgres -U arada -d arada -c "SELECT 1;"

# Port-forward for manual testing
kubectl -n arada port-forward svc/postgres 5432:5432
psql -h localhost -U arada -d arada
```

## Cleanup

```bash
# Delete release
helm uninstall arada --namespace arada

# Delete namespace
kubectl delete namespace arada

# Delete PVCs (WARNING: data loss!)
kubectl -n arada delete pvc --all
```

## Advanced

### Multi-Region Deployment

Deploy to multiple clouds with separate Helm releases:

```bash
# GCP
helm install arada-gke arada-os \
  --kubeconfig=$KUBECONFIG_GCP \
  -f values-production.yaml

# AWS
helm install arada-eks arada-os \
  --kubeconfig=$KUBECONFIG_AWS \
  -f values-production.yaml
```

### GitOps (ArgoCD)

```bash
# Install ArgoCD
helm repo add argo https://argoproj.github.io/argo-helm
helm install argocd argo/argo-cd --namespace argocd --create-namespace

# Create Application
kubectl apply -f - << EOF
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: arada
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/arada-ai/arada-os
    targetRevision: main
    path: infra/k8s/arada-os
  destination:
    server: https://kubernetes.default.svc
    namespace: arada
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
EOF
```

## References

- Full deployment guide: [K8S_DEPLOYMENT.md](../K8S_DEPLOYMENT.md)
- Helm documentation: https://helm.sh/docs/
- Kubernetes documentation: https://kubernetes.io/docs/

---

**See also**: [DEPLOYMENT.md](../DEPLOYMENT.md), [PROXMOX_DEPLOYMENT.md](../PROXMOX_DEPLOYMENT.md)
