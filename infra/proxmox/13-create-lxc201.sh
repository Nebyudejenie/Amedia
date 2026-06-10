#!/usr/bin/env bash
# LXC-201 — Backup services (restic, rclone, pg_dump cron, snapshot jobs).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/00-config.sh"
source "${HERE}/lib.sh"
require_root; require_pve; check_pubkey
create_ct "${LXC201_ID}" "${LXC201_NAME}" "${LXC201_CORES}" "${LXC201_MEM}" "${LXC201_SWAP}" "${LXC201_DISK}" "${IP_LXC201}"
msg "LXC-201 created. Provision it with role=lxc (see ../guest/README.md)."
