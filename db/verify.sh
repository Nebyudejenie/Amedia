#!/usr/bin/env bash
# Verify Prompt 1.1 acceptance: schemas present, expected tables exist,
# triggers attached, seed rows loaded, migrations recorded.
# Usage: ./verify.sh [--docker]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--docker" ]]; then
  CONTAINER="${PG_CONTAINER:-arada-postgres}"
  q() { docker exec -i -e PGPASSWORD="${PGPASSWORD:-arada}" "${CONTAINER}" \
          psql -tAq -U "${PGUSER:-arada}" -d "${PGDATABASE:-arada}" -c "$1"; }
else
  export PGPASSWORD="${PGPASSWORD:?set PGPASSWORD or use --docker}"
  q() { psql -tAq -h "${PGHOST:-127.0.0.1}" -p "${PGPORT:-5432}" -U "${PGUSER:-arada}" -d "${PGDATABASE:-arada}" -c "$1"; }
fi

fail=0
check() { # <label> <actual> <expected>
  if [[ "$2" == "$3" ]]; then echo -e "  \033[1;32mPASS\033[0m $1 ($2)";
  else echo -e "  \033[1;31mFAIL\033[0m $1 (got '$2', want '$3')"; fail=1; fi
}

echo "== Schemas =="
check "7 app schemas" \
  "$(q "SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('auth','content','media','analytics','workflow','system','revenue');")" \
  "7"

echo "== Tables per schema =="
check "auth tables"      "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='auth';")"      "4"
check "content tables"   "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='content';")"   "6"
check "media tables"     "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='media';")"     "4"
check "analytics tables" "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='analytics';")" "5"
check "workflow tables"  "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='workflow';")"  "3"
check "system tables"    "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='system';")"    "6"
check "revenue tables"   "$(q "SELECT count(*) FROM information_schema.tables WHERE table_schema='revenue';")"   "5"

echo "== Integrity =="
check "foreign keys >= 25" \
  "$([[ "$(q "SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY' AND constraint_schema IN ('auth','content','media','analytics','workflow','system','revenue');")" -ge 25 ]] && echo ok || echo no)" \
  "ok"
check "GIN indexes >= 7" \
  "$([[ "$(q "SELECT count(*) FROM pg_indexes WHERE indexdef ILIKE '%USING gin%';")" -ge 7 ]] && echo ok || echo no)" \
  "ok"
check "updated_at triggers >= 18" \
  "$([[ "$(q "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'trg_%_updated';")" -ge 18 ]] && echo ok || echo no)" \
  "ok"

echo "== Seed data =="
check "roles seeded"        "$(q "SELECT count(*) FROM auth.roles;")"          "6"
check "feature flags"       "$(q "SELECT count(*) FROM system.feature_flags;")" "6"
check "config keys"         "$(q "SELECT count(*) FROM system.system_config;")" "5"
check "default workspace"   "$(q "SELECT count(*) FROM auth.workspaces WHERE slug='arada';")" "1"

echo "== Migrations recorded =="
check "9 migrations applied" "$(q "SELECT count(*) FROM public.schema_migrations;")" "9"

echo
if [[ ${fail} -eq 0 ]]; then echo -e "\033[1;32mPrompt 1.1 verification PASSED\033[0m"
else echo -e "\033[1;31mPrompt 1.1 verification FAILED\033[0m"; exit 1; fi
