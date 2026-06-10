#!/usr/bin/env bash
# Verify Prompt 1.2 acceptance: Redis, MinIO, Qdrant all healthy and initialized.
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
MINIO_HOST="${MINIO_HOST:-127.0.0.1}"
MINIO_PORT="${MINIO_PORT:-9000}"
QDRANT_HOST="${QDRANT_HOST:-127.0.0.1}"
QDRANT_PORT="${QDRANT_PORT:-6333}"

fail=0
pass() { echo -e "  \033[1;32mPASS\033[0m $1"; }
bad()  { echo -e "  \033[1;31mFAIL\033[0m $1"; fail=1; }

echo "== Redis =="
if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" ping 2>/dev/null | grep -q PONG; then
    pass "Redis responding to PING"
    v=$(redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
    pass "Redis version: $v"
  else bad "Redis not responding"; fi
else
  # Fallback: use nc to check port
  if echo "PING" | nc -w1 "${REDIS_HOST}" "${REDIS_PORT}" 2>/dev/null | grep -q PONG; then
    pass "Redis port responding to PING"
  else bad "Redis not responding on ${REDIS_HOST}:${REDIS_PORT}"; fi
fi

echo "== MinIO =="
if curl -s "http://${MINIO_HOST}:${MINIO_PORT}/minio/health/live" >/dev/null 2>&1; then
  pass "MinIO health check OK"
  # Try to access console endpoint (no auth needed for health)
  curl -s -I "http://${MINIO_HOST}:$((MINIO_PORT+1))/minio" >/dev/null 2>&1 && pass "MinIO console responding" || bad "MinIO console not responding"
else
  bad "MinIO health check failed"
fi

echo "== Qdrant =="
if curl -s "http://${QDRANT_HOST}:${QDRANT_PORT}/health" | jq -e '.title=="qdrant"' >/dev/null 2>&1; then
  pass "Qdrant health check OK"
  # Check collections exist (after init)
  colls=$(curl -s "http://${QDRANT_HOST}:${QDRANT_PORT}/collections" | jq -r '.result.collections[].name // empty' | sort)
  want_colls="audience_profiles content_embeddings knowledge_memory script_memory trend_memory"
  got_colls=$(echo "$colls" | tr '\n' ' ' | xargs)
  if [[ "$(echo $want_colls | tr ' ' '\n' | sort | tr '\n' ' ')" == "$(echo $got_colls | tr ' ' '\n' | sort | tr '\n' ' ')" ]]; then
    pass "All 5 collections initialized"
  else
    bad "Collections mismatch (want: $want_colls, got: $got_colls)"
  fi
else
  bad "Qdrant health check failed"
fi

echo
if [[ ${fail} -eq 0 ]]; then echo -e "\033[1;32mPrompt 1.2 verification PASSED\033[0m"
else echo -e "\033[1;31mPrompt 1.2 verification FAILED\033[0m"; exit 1; fi
