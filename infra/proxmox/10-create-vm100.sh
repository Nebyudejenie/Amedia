#!/usr/bin/env bash
# VM-100 — Core Platform (Caddy, cloudflared, FastAPI, n8n, Postgres, Redis,
# Qdrant, MinIO, Ollama, Open WebUI, MCP, light workers).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/00-config.sh"
source "${HERE}/lib.sh"
require_root; require_pve; check_pubkey
create_vm "${VM100_ID}" "${VM100_NAME}" "${VM100_CORES}" "${VM100_MEM}" "${VM100_BALLOON}" "${VM100_DISK}" "${IP_VM100}"
msg "VM-100 created. Provision it with role=vm100 (see ../guest/README.md)."
