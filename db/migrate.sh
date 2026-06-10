#!/usr/bin/env bash
# Arada Intelligence OS — idempotent SQL migration runner.
# Applies db/migrations/*.sql in filename order, tracking applied files in
# public.schema_migrations. Each file runs in a single transaction.
#
# Connection via standard libpq env vars (override as needed):
#   PGHOST (default 127.0.0.1) PGPORT (5432) PGUSER (arada) PGDATABASE (arada)
#   PGPASSWORD (required)
#
# Examples:
#   PGPASSWORD=secret ./migrate.sh
#   # against the bundled compose container:
#   ./migrate.sh --docker            (runs psql inside the arada-postgres container)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIG_DIR="${HERE}/migrations"

USE_DOCKER=0
[[ "${1:-}" == "--docker" ]] && USE_DOCKER=1

PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-arada}"
PGDATABASE="${PGDATABASE:-arada}"

if [[ "${USE_DOCKER}" -eq 1 ]]; then
  CONTAINER="${PG_CONTAINER:-arada-postgres}"
  psql_run() { docker exec -i -e PGPASSWORD="${PGPASSWORD:-arada}" "${CONTAINER}" \
                 psql -v ON_ERROR_STOP=1 -U "${PGUSER}" -d "${PGDATABASE}" "$@"; }
else
  : "${PGPASSWORD:?set PGPASSWORD (or use --docker)}"
  export PGPASSWORD
  command -v psql >/dev/null 2>&1 || { echo "psql not found; use --docker or install postgresql-client"; exit 1; }
  psql_run() { psql -v ON_ERROR_STOP=1 -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" "$@"; }
fi

echo "[arada] ensuring migration tracking table…"
psql_run -q -c "CREATE TABLE IF NOT EXISTS public.schema_migrations (
  filename   text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now());"

shopt -s nullglob
applied=0 skipped=0
for f in "${MIG_DIR}"/*.sql; do
  base="$(basename "${f}")"
  exists="$(psql_run -tAq -c "SELECT 1 FROM public.schema_migrations WHERE filename='${base}';" || true)"
  if [[ "${exists}" == "1" ]]; then
    echo "[arada] skip   ${base}"; skipped=$((skipped+1)); continue
  fi
  echo "[arada] apply  ${base}"
  if [[ "${USE_DOCKER}" -eq 1 ]]; then
    docker exec -i -e PGPASSWORD="${PGPASSWORD:-arada}" "${CONTAINER}" \
      psql -v ON_ERROR_STOP=1 --single-transaction -U "${PGUSER}" -d "${PGDATABASE}" \
      -c "$(cat "${f}")" \
      -c "INSERT INTO public.schema_migrations(filename) VALUES ('${base}');"
  else
    psql_run --single-transaction -f "${f}" \
      -c "INSERT INTO public.schema_migrations(filename) VALUES ('${base}');"
  fi
  applied=$((applied+1))
done

echo "[arada] migrations complete (applied=${applied}, skipped=${skipped})."
