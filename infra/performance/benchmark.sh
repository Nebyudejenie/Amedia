#!/usr/bin/env bash
# Arada Intelligence OS — Performance Benchmarking Suite

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[1;32m'
COLOR_BLUE='\033[1;34m'
COLOR_YELLOW='\033[1;33m'

log() { echo -e "${COLOR_BLUE}→${COLOR_RESET} $1"; }
success() { echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"; }
warn() { echo -e "${COLOR_YELLOW}!${COLOR_RESET} $1"; }

API_URL="${1:-http://127.0.0.1:8000}"

echo "============================================================"
echo "Arada Intelligence OS — Performance Benchmark Suite"
echo "============================================================"
echo "Target: $API_URL"
echo

# ============================================================================
# 1. HEALTH CHECK
# ============================================================================

log "1. Health Check"
response=$(curl -s -w "\n%{http_code}" "$API_URL/system/health")
status=$(echo "$response" | tail -n1)
if [[ $status == "200" ]]; then
  success "API responding (HTTP $status)"
else
  warn "API returned HTTP $status"
  exit 1
fi
echo

# ============================================================================
# 2. BASIC LATENCY TEST (Apache Bench)
# ============================================================================

if ! command -v ab >/dev/null 2>&1; then
  warn "Apache Bench not installed. Skipping latency test."
  echo "  Install: sudo apt-get install apache2-utils"
else
  log "2. Latency Test (100 sequential requests)"
  ab -n 100 -c 1 -q "$API_URL/system/health" 2>&1 | grep -E "Requests per second|Time per request|Failed"
  echo
fi

# ============================================================================
# 3. CONCURRENT LOAD TEST (Wrk)
# ============================================================================

if ! command -v wrk >/dev/null 2>&1; then
  warn "Wrk not installed. Skipping concurrent test."
  echo "  Install: sudo apt-get install wrk"
else
  log "3. Concurrent Load Test (4 threads, 100 connections, 10s)"
  wrk -t4 -c100 -d10s "$API_URL/system/health" 2>&1 | grep -E "Requests/sec|Avg|Max" || true
  echo
fi

# ============================================================================
# 4. DATABASE PERFORMANCE
# ============================================================================

if docker-compose ps 2>/dev/null | grep -q postgres; then
  log "4. Database Performance Metrics"

  # Cache hit ratio
  docker-compose exec -T postgres psql -U arada -d arada -c "
    SELECT
      ROUND(100 * heap_blks_hit / (heap_blks_hit + heap_blks_read), 2) as cache_hit_ratio
    FROM (
      SELECT sum(heap_blks_hit) as heap_blks_hit, sum(heap_blks_read) as heap_blks_read
      FROM pg_statio_user_tables
    ) t;
  " 2>/dev/null || warn "Could not connect to database"

  # Active connections
  docker-compose exec -T postgres psql -U arada -d arada -c "
    SELECT datname, count(*) as connections FROM pg_stat_activity GROUP BY datname;
  " 2>/dev/null || true

  echo
else
  warn "PostgreSQL not running. Skipping database metrics."
fi

# ============================================================================
# 5. REDIS PERFORMANCE
# ============================================================================

if docker-compose ps 2>/dev/null | grep -q redis; then
  log "5. Redis Performance Metrics"

  docker-compose exec -T redis redis-cli INFO stats 2>/dev/null | grep -E "total_commands_processed|instantaneous_ops_per_sec" || true
  docker-compose exec -T redis redis-cli INFO memory 2>/dev/null | grep -E "used_memory_human|maxmemory_human" || true

  echo
else
  warn "Redis not running. Skipping Redis metrics."
fi

# ============================================================================
# 6. PROMETHEUS METRICS
# ============================================================================

log "6. API Metrics (Prometheus)"
metrics=$(curl -s "$API_URL/metrics" 2>/dev/null || echo "")

if [[ -n "$metrics" ]]; then
  # Extract key metrics
  request_count=$(echo "$metrics" | grep "http_requests_total" | wc -l)
  request_latency=$(echo "$metrics" | grep "http_request_duration_seconds_bucket" | wc -l)

  success "Prometheus metrics available"
  echo "  Request counts: $(echo "$metrics" | grep 'http_requests_total{' | head -1)"
  echo "  Latency buckets: $request_latency entries"
else
  warn "Prometheus metrics not available"
fi
echo

# ============================================================================
# 7. SUMMARY & RECOMMENDATIONS
# ============================================================================

log "Summary"
echo "
✓ Benchmark complete!

Key metrics to monitor:
  - Requests/sec: aim for > 500 req/s
  - P95 latency: target < 100ms
  - Database cache hit ratio: target > 99%
  - Redis evictions: should be 0
  - Error rate: should be < 0.1%

Optimization checklist:
  □ Run database optimization: psql -f infra/performance/optimize.sql
  □ Check slow queries: docker-compose logs postgres | grep 'duration:'
  □ Monitor Redis: docker-compose exec redis redis-cli --hotkeys
  □ Run extended load test: locust -f infra/performance/locustfile.py

For more details, see: infra/performance/PERFORMANCE.md
"
