#!/usr/bin/env bash
# Create the internal-only bridge (vmbr1) for private VM<->VM service traffic.
# Idempotent: safe to re-run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=00-config.sh
source "${HERE}/00-config.sh"
# shellcheck source=lib.sh
source "${HERE}/lib.sh"

require_root
require_pve

if ip link show "${BRIDGE_INT}" >/dev/null 2>&1; then
  msg "Internal bridge ${BRIDGE_INT} already exists — skipping."
  exit 0
fi

IFACES="/etc/network/interfaces"
if grep -qE "iface[[:space:]]+${BRIDGE_INT}[[:space:]]" "${IFACES}" 2>/dev/null; then
  warn "${BRIDGE_INT} is defined in ${IFACES} but not up; reloading."
else
  msg "Adding ${BRIDGE_INT} (${INT_GW_HOST}) to ${IFACES}"
  cp -a "${IFACES}" "${IFACES}.arada.bak.$(date +%s)"
  cat >>"${IFACES}" <<EOF

auto ${BRIDGE_INT}
iface ${BRIDGE_INT} inet static
    address ${INT_GW_HOST}/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
#arada internal network (private VM<->VM traffic, no physical uplink)
EOF
fi

msg "Reloading network configuration (ifreload -a)…"
ifreload -a
msg "Done. ${BRIDGE_INT} is up; Proxmox host reachable at ${INT_GW_HOST} on the internal subnet."
