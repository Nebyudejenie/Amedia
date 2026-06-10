#!/usr/bin/env bash
# Verify Prompt 2.2 acceptance: Auth routes (register, login, refresh, me, api-keys) + JWT + RBAC.
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
TIMEOUT=30
RETRIES=10

fail=0
pass() { echo -e "  \033[1;32mPASS\033[0m $1"; }
bad()  { echo -e "  \033[1;31mFAIL\033[0m $1"; fail=1; }

echo "== API startup =="
for i in $(seq 1 ${RETRIES}); do
  if curl -s "${API_URL}/system/health" | grep -q "ok" 2>/dev/null; then
    pass "API responding"
    break
  fi
  if [[ $i -eq ${RETRIES} ]]; then bad "API did not start"; fi
  sleep 1
done

echo "== Health check =="
response=$(curl -s "${API_URL}/system/health")
if echo "$response" | jq -e '.status' >/dev/null 2>&1; then
  pass "Health endpoint returns JSON"
  if echo "$response" | jq -e '.checks.postgresql=="ok"' >/dev/null 2>&1; then
    pass "PostgreSQL healthy"
  else bad "PostgreSQL check failed"; fi
  if echo "$response" | jq -e '.checks.redis=="ok"' >/dev/null 2>&1; then
    pass "Redis healthy"
  else bad "Redis check failed"; fi
  if echo "$response" | jq -e '.checks.qdrant=="ok"' >/dev/null 2>&1; then
    pass "Qdrant healthy"
  else bad "Qdrant check failed"; fi
else bad "Health endpoint failed"; fi

echo "== Auth: Register =="
REGISTER=$(curl -s -X POST "${API_URL}/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@arada.fun","password":"testpassword123!","workspace_name":"Test Workspace"}')

if echo "$REGISTER" | jq -e '.access_token' >/dev/null 2>&1; then
  pass "User registration"
  ACCESS_TOKEN=$(echo "$REGISTER" | jq -r '.access_token')
  REFRESH_TOKEN=$(echo "$REGISTER" | jq -r '.refresh_token')
else
  bad "User registration";
  echo "Response: $REGISTER"
  ACCESS_TOKEN=""
  REFRESH_TOKEN=""
fi

echo "== Auth: Login =="
LOGIN=$(curl -s -X POST "${API_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@arada.fun","password":"testpassword123!"}')

if echo "$LOGIN" | jq -e '.access_token' >/dev/null 2>&1; then
  pass "User login"
  ACCESS_TOKEN=$(echo "$LOGIN" | jq -r '.access_token')
else
  bad "User login";
  echo "Response: $LOGIN"
fi

echo "== Auth: Get Current User =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  ME=$(curl -s -X GET "${API_URL}/auth/me" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$ME" | jq -e '.id' >/dev/null 2>&1; then
    pass "Get current user"
  else
    bad "Get current user";
    echo "Response: $ME"
  fi
else
  bad "Get current user (no token)"
fi

echo "== Auth: Get Workspace =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  WORKSPACE=$(curl -s -X GET "${API_URL}/auth/workspace" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$WORKSPACE" | jq -e '.id' >/dev/null 2>&1; then
    pass "Get workspace"
  else
    bad "Get workspace";
    echo "Response: $WORKSPACE"
  fi
else
  bad "Get workspace (no token)"
fi

echo "== Auth: Create API Key =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  APIKEY=$(curl -s -X POST "${API_URL}/auth/api-keys" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"test-key","scopes":["read:content"]}')

  if echo "$APIKEY" | jq -e '.secret' >/dev/null 2>&1; then
    pass "Create API key"
  else
    bad "Create API key";
    echo "Response: $APIKEY"
  fi
else
  bad "Create API key (no token)"
fi

echo "== Auth: Refresh Token =="
if [[ -n "$REFRESH_TOKEN" ]]; then
  NEWTOKEN=$(curl -s -X POST "${API_URL}/auth/refresh" \
    -H "Authorization: Bearer $REFRESH_TOKEN" \
    -H "Content-Type: application/json")

  if echo "$NEWTOKEN" | jq -e '.access_token' >/dev/null 2>&1; then
    pass "Refresh token"
  else
    bad "Refresh token";
    echo "Response: $NEWTOKEN"
  fi
else
  bad "Refresh token (no token)"
fi

echo "== Content: Create Source =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  SOURCE=$(curl -s -X POST "${API_URL}/content/sources" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"TechNews RSS","source_type":"rss","url":"https://news.ycombinator.com/rss"}')

  if echo "$SOURCE" | jq -e '.id' >/dev/null 2>&1; then
    pass "Create content source"
    SOURCE_ID=$(echo "$SOURCE" | jq -r '.id')
  else
    bad "Create content source"
    echo "Response: $SOURCE"
    SOURCE_ID=""
  fi
else
  bad "Create content source (no token)"
  SOURCE_ID=""
fi

echo "== Content: List Sources =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  SOURCES=$(curl -s -X GET "${API_URL}/content/sources" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$SOURCES" | jq -e '.total' >/dev/null 2>&1; then
    pass "List content sources"
  else
    bad "List content sources"
  fi
else
  bad "List content sources (no token)"
fi

echo "== Content: Trigger Source Fetch =="
if [[ -n "$SOURCE_ID" && -n "$ACCESS_TOKEN" ]]; then
  FETCH=$(curl -s -X POST "${API_URL}/content/sources/${SOURCE_ID}/fetch" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$FETCH" | jq -e '.job_id' >/dev/null 2>&1; then
    pass "Trigger source fetch"
  else
    bad "Trigger source fetch"
  fi
else
  bad "Trigger source fetch (no source_id or token)"
fi

echo "== Content: List Items =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  ITEMS=$(curl -s -X GET "${API_URL}/content/items" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$ITEMS" | jq -e '.total' >/dev/null 2>&1; then
    pass "List content items"
  else
    bad "List content items"
  fi
else
  bad "List content items (no token)"
fi

echo "== Workflow: Create Job =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  JOB=$(curl -s -X POST "${API_URL}/workflow/jobs" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"job_type":"brief","input_data":{"item_ids":["item1","item2"],"brief_type":"daily_digest"},"priority":10}')

  if echo "$JOB" | jq -e '.id' >/dev/null 2>&1; then
    pass "Create workflow job"
    JOB_ID=$(echo "$JOB" | jq -r '.id')
  else
    bad "Create workflow job"
    echo "Response: $JOB"
    JOB_ID=""
  fi
else
  bad "Create workflow job (no token)"
  JOB_ID=""
fi

echo "== Workflow: List Jobs =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  JOBS=$(curl -s -X GET "${API_URL}/workflow/jobs" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$JOBS" | jq -e '.total' >/dev/null 2>&1; then
    pass "List workflow jobs"
  else
    bad "List workflow jobs"
  fi
else
  bad "List workflow jobs (no token)"
fi

echo "== Workflow: Get Job =="
if [[ -n "$JOB_ID" && -n "$ACCESS_TOKEN" ]]; then
  JOBDET=$(curl -s -X GET "${API_URL}/workflow/jobs/${JOB_ID}" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$JOBDET" | jq -e '.status' >/dev/null 2>&1; then
    pass "Get workflow job"
  else
    bad "Get workflow job"
  fi
else
  bad "Get workflow job (no job_id or token)"
fi

echo "== Workflow: Get Job Events =="
if [[ -n "$JOB_ID" && -n "$ACCESS_TOKEN" ]]; then
  EVENTS=$(curl -s -X GET "${API_URL}/workflow/jobs/${JOB_ID}/events" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$EVENTS" | jq -e 'length' >/dev/null 2>&1; then
    pass "Get job events"
  else
    bad "Get job events"
  fi
else
  bad "Get job events (no job_id or token)"
fi

echo "== Media: Create Template =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  TEMPLATE=$(curl -s -X POST "${API_URL}/media/templates" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"Short-Form Template","template_type":"short-form","config":{"duration":60,"resolution":"1080p"}}')

  if echo "$TEMPLATE" | jq -e '.id' >/dev/null 2>&1; then
    pass "Create video template"
    TEMPLATE_ID=$(echo "$TEMPLATE" | jq -r '.id')
  else
    bad "Create video template"
    echo "Response: $TEMPLATE"
    TEMPLATE_ID=""
  fi
else
  bad "Create video template (no token)"
  TEMPLATE_ID=""
fi

echo "== Media: List Templates =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  TEMPLATES=$(curl -s -X GET "${API_URL}/media/templates" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$TEMPLATES" | jq -e '.total' >/dev/null 2>&1; then
    pass "List templates"
  else
    bad "List templates"
  fi
else
  bad "List templates (no token)"
fi

echo "== Media: Create Publish Job =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  PUBJOB=$(curl -s -X POST "${API_URL}/media/publish" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"video_id":"video-123","platforms":["twitter","youtube"],"metadata":{"title":"Test Video"}}')

  if echo "$PUBJOB" | jq -e '.id' >/dev/null 2>&1; then
    pass "Create publish job"
    PUB_JOB_ID=$(echo "$PUBJOB" | jq -r '.id')
  else
    bad "Create publish job"
    echo "Response: $PUBJOB"
    PUB_JOB_ID=""
  fi
else
  bad "Create publish job (no token)"
  PUB_JOB_ID=""
fi

echo "== Media: List Publish Jobs =="
if [[ -n "$ACCESS_TOKEN" ]]; then
  PUBJOBS=$(curl -s -X GET "${API_URL}/media/publish" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$PUBJOBS" | jq -e '.total' >/dev/null 2>&1; then
    pass "List publish jobs"
  else
    bad "List publish jobs"
  fi
else
  bad "List publish jobs (no token)"
fi

echo "== Media: Publish to Platform =="
if [[ -n "$PUB_JOB_ID" && -n "$ACCESS_TOKEN" ]]; then
  PUBRESULT=$(curl -s -X POST "${API_URL}/media/publish/${PUB_JOB_ID}/twitter" \
    -H "Authorization: Bearer $ACCESS_TOKEN")

  if echo "$PUBRESULT" | jq -e '.post_id' >/dev/null 2>&1; then
    pass "Publish to platform"
  else
    bad "Publish to platform"
  fi
else
  bad "Publish to platform (no job_id or token)"
fi

echo "== Metrics =="
if curl -s "${API_URL}/metrics" | grep -q "http_requests_total" 2>/dev/null; then
  pass "Prometheus metrics endpoint"
else
  bad "Metrics endpoint"
fi

echo
if [[ ${fail} -eq 0 ]]; then echo -e "\033[1;32mPrompt 2.5 verification PASSED\033[0m"
else echo -e "\033[1;31mPrompt 2.5 verification FAILED\033[0m"; exit 1; fi
