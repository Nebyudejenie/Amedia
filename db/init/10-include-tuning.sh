#!/usr/bin/env bash
# Runs once at first DB init (official postgres image entrypoint hook).
# Appends an include for the mounted Arada tuning file so we keep all the
# image's sane defaults and only override what we tune.
set -euo pipefail
TUNING="/etc/postgresql/arada-tuning.conf"
if [[ -f "${TUNING}" ]] && ! grep -q "arada-tuning.conf" "${PGDATA}/postgresql.conf"; then
  {
    echo ""
    echo "# Arada tuning (mounted, see db/postgresql.tuning.conf)"
    echo "include = '${TUNING}'"
  } >> "${PGDATA}/postgresql.conf"
  echo "[arada] appended tuning include to postgresql.conf"
fi
