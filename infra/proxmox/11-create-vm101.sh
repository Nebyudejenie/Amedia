#!/usr/bin/env bash
# VM-101 — Media Factory (Piper TTS, subtitle worker, FFmpeg render worker, render-api).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/00-config.sh"
source "${HERE}/lib.sh"
require_root; require_pve; check_pubkey
create_vm "${VM101_ID}" "${VM101_NAME}" "${VM101_CORES}" "${VM101_MEM}" "${VM101_BALLOON}" "${VM101_DISK}" "${IP_VM101}"
msg "VM-101 created. Provision it with role=vm101 (see ../guest/README.md)."
