#!/usr/bin/env bash
# LXC-200 — Monitoring stack (Prometheus, Grafana, Loki, Uptime Kuma).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/00-config.sh"
source "${HERE}/lib.sh"
require_root; require_pve; check_pubkey
create_ct "${LXC200_ID}" "${LXC200_NAME}" "${LXC200_CORES}" "${LXC200_MEM}" "${LXC200_SWAP}" "${LXC200_DISK}" "${IP_LXC200}"
msg "LXC-200 created. Provision it with role=lxc (see ../guest/README.md)."
