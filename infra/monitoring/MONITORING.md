# Arada Intelligence OS — Monitoring & Observability

Complete monitoring stack for production deployments (Prometheus, Grafana, Alertmanager, Loki).

## Overview

**Three pillars:**
1. **Metrics** (Prometheus) — request counts, latency, errors, resource usage
2. **Logs** (Loki) — structured logs from all services
3. **Dashboards** (Grafana) — visualize metrics + logs
4. **Alerts** (Alertmanager) — fire on threshold breaches

## Quick Start (Docker Compose)

```bash
# Start monitoring stack
docker-compose -f infra/monitoring/docker-compose.yml up -d

# Access
echo "Prometheus:  http://localhost:9090"
echo "Grafana:     http://localhost:3000  (admin/admin)"
echo "Alertmanager: http://localhost:9093"
```

## Architecture

```
┌─────────────────────────────────────────┐
│         Arada Services                  │
│  (api, postgres, redis, minio, etc.)    │
│  Expose /metrics (Prometheus format)    │
└────────────┬────────────────────────────┘
             │ scrape every 15s
             ▼
┌──────────────────────────┐
│     Prometheus 9090      │
│  Time-series database    │
│  15-day retention        │
└────────────┬─────────────┘
             │
    ┌────────┼────────┐
    │        │        │
    ▼        ▼        ▼
┌────────┐┌──────┐┌──────────────┐
│ Grafana││ Loki ││Alertmanager  │
│ 3000   ││ 3100 ││ 9093         │
└────────┘└──────┘└──────────────┘
    │        │          │
    └────────┴──────────┘
         Email/Slack
```

## Setup

### 1. Prometheus Configuration

File: `infra/monitoring/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  retention: 15d

scrape_configs:
  # Arada API
  - job_name: 'arada-api'
    static_configs:
      - targets: ['api:8000']
    metrics_path: '/metrics'

  # PostgreSQL (via postgres_exporter)
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  # Redis (via redis_exporter)
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  # Node metrics
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

rule_files:
  - 'alert-rules.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

### 2. Alert Rules

File: `infra/monitoring/alert-rules.yml`

```yaml
groups:
  - name: arada-alerts
    rules:
      # API alerts
      - alert: APIDown
        expr: up{job="arada-api"} == 0
        for: 2m
        annotations:
          summary: "API is down"
          description: "Arada API has been unreachable for 2+ minutes"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate"
          description: "Error rate > 5% ({{ $value }})"

      # Database alerts
      - alert: DatabaseDown
        expr: up{job="postgres"} == 0
        for: 1m
        annotations:
          summary: "PostgreSQL is down"

      - alert: DatabaseConnections
        expr: pg_stat_activity_count > 80
        for: 5m
        annotations:
          summary: "High database connections"
          description: "{{ $value }} active connections (limit: 100)"

      # Redis alerts
      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m

      - alert: RedisMemory
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        annotations:
          summary: "Redis memory usage > 90%"

      # Resource alerts
      - alert: HighCPUUsage
        expr: node_cpu_usage > 0.8
        for: 5m

      - alert: HighMemoryUsage
        expr: node_memory_usage > 0.85
        for: 5m

      - alert: DiskSpaceLow
        expr: node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.1
        for: 5m
```

### 3. Alertmanager Configuration

File: `infra/monitoring/alertmanager.yml`

```yaml
global:
  resolve_timeout: 5m
  slack_api_url: ${SLACK_WEBHOOK_URL}

route:
  receiver: 'slack'
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

receivers:
  - name: 'slack'
    slack_configs:
      - channel: '#alerts'
        title: 'Arada Alert'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'email'
    email_configs:
      - to: 'ops@arada.fun'
        from: 'alerts@arada.fun'
        smarthost: 'smtp.gmail.com:587'
        auth_username: '${SMTP_USER}'
        auth_password: '${SMTP_PASSWORD}'
```

### 4. Grafana Dashboards

Pre-built dashboards available:
- **API Performance**: request rate, latency (p50/p95/p99), error rate
- **Database Health**: connections, queries/sec, cache hit ratio, replication lag
- **Redis**: memory usage, keys, command rate, evictions
- **System**: CPU, memory, disk usage, network I/O
- **Workflow**: job queue depth, processing rate, error rate

**Import dashboards:**
```bash
# Via Grafana UI: Data Sources > Prometheus > Dashboards (import)
# Or via API:
curl -X POST http://localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @infra/monitoring/grafana-dashboards/api-performance.json
```

## Metrics Reference

### API Metrics (Prometheus format)

**Request metrics:**
```
http_requests_total{method="GET",endpoint="/auth/me",status="200"} 1234
http_request_duration_seconds_bucket{le="0.1",endpoint="/auth/me"} 1000
http_request_duration_seconds_bucket{le="0.5",endpoint="/auth/me"} 1200
```

**Example queries:**
```promql
# Request rate (requests/sec)
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status=~"5.."}[5m])

# P95 latency
histogram_quantile(0.95, http_request_duration_seconds)

# Endpoints by traffic
topk(10, rate(http_requests_total[5m]))
```

### Database Metrics (pg_exporter)

```promql
# Database size
pg_database_size_bytes

# Active connections
pg_stat_activity_count

# Queries/sec
rate(pg_stat_statements_calls[5m])

# Cache hit ratio
(pg_stat_database_blks_hit / (pg_stat_database_blks_hit + pg_stat_database_blks_read)) > 0.99
```

### Redis Metrics (redis_exporter)

```promql
# Memory usage
redis_memory_used_bytes

# Keys
redis_db_keys

# Operations/sec
rate(redis_commands_processed_total[5m])

# Evictions/sec
rate(redis_evicted_keys_total[5m])
```

## Logging with Loki

### Setup

```bash
# Start Loki + Promtail
docker-compose -f infra/monitoring/docker-compose.yml \
  -f infra/monitoring/loki-compose.yml up -d
```

### Configure Log Shipping

**Promtail scrapes logs from:**
- Docker containers (via `/var/lib/docker/containers`)
- Kubernetes pods (via kubelet API)
- Files (syslog, application logs)

**Example Promtail config:**
```yaml
scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: 'service'
```

### Query Logs

**LogQL examples:**
```logql
# All Arada logs
{job="arada"}

# Error logs
{job="arada"} | "ERROR"

# Slow queries (latency > 100ms)
{job="postgres"} | "duration" | duration > 100ms

# API errors by endpoint
{job="arada-api"} | json | status >= 500 | label_format endpoint=uri
```

## Kubernetes Monitoring

### Install Prometheus Stack

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```

### ServiceMonitor (K8s)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: arada
  namespace: arada
spec:
  selector:
    matchLabels:
      app: api
  endpoints:
  - port: http
    path: /metrics
    interval: 15s
```

## Best Practices

### Cardinality (avoid explosion)

❌ **Bad** (high cardinality):
```
http_requests_total{user_id="123",ip="1.2.3.4",path="/api/v1/..."}
```

✅ **Good** (low cardinality):
```
http_requests_total{method="GET",endpoint="/api/users",status="200"}
```

### Retention

- **Prometheus**: 15 days (local SSD)
- **Loki**: 30 days (object storage)
- **Grafana**: Keep important dashboards as snapshots

### Alert Fatigue

- Avoid alerting on every metric
- Set meaningful thresholds
- Use `for:` to avoid noise (e.g., `for: 5m`)
- Route different severities differently (page vs email)

## Troubleshooting

### Prometheus not scraping

```bash
# Check targets
curl http://prometheus:9090/api/v1/targets

# Check rules
curl http://prometheus:9090/api/v1/rules
```

### Grafana not showing data

```bash
# Test Prometheus connection
curl http://prometheus:9090/api/v1/query?query=up
```

### Alerts not firing

```bash
# Check alert status
curl http://prometheus:9090/api/v1/alerts

# Check Alertmanager
curl http://alertmanager:9093/api/v1/status
```

## Cost Optimization

**Storage costs** (example: DigitalOcean):
- 1GB Prometheus retention/day = ~$0.01/month
- 15-day retention = $0.15/month
- Loki 30-day = $0.30/month
- **Total: ~$0.50/month** (negligible)

**Memory usage:**
- Prometheus: ~500MB baseline + 50KB per unique metric
- Grafana: ~100MB
- **Total: ~1GB** (negligible)

## References

- Prometheus: https://prometheus.io/docs/
- Grafana: https://grafana.com/docs/
- Loki: https://grafana.com/docs/loki/
- AlertManager: https://prometheus.io/docs/alerting/latest/alertmanager/

---

**See also**: [K8S_DEPLOYMENT.md](../K8S_DEPLOYMENT.md), [DEPLOYMENT.md](../DEPLOYMENT.md)
