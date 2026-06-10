#!/usr/bin/env bash
# Arada Intelligence OS — one-shot Proxmox provisioning.
# Runs on the Proxmox host as root. Idempotent: re-running skips existing pieces.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/00-config.sh"
source "${HERE}/lib.sh"

require_root
require_pve
check_pubkey

msg "=== Arada infra provisioning ==="
bash "${HERE}/01-network-bridge.sh"
bash "${HERE}/02-download-images.sh"
bash "${HERE}/10-create-vm100.sh"
bash "${HERE}/11-create-vm101.sh"
bash "${HERE}/12-create-lxc200.sh"
bash "${HERE}/13-create-lxc201.sh"

cat <<EOF

$(msg "All guests created.")

Internal addresses (private bridge ${BRIDGE_INT}, subnet ${INT_SUBNET}):
  VM-100  arada-core    ${IP_VM100}
  VM-101  arada-media   ${IP_VM101}
  LXC-200 arada-obs     ${IP_LXC200}
  LXC-201 arada-backup  ${IP_LXC201}

VMs also have a DHCP address on ${BRIDGE_WAN}; find it with:  qm guest cmd <vmid> network-get-interfaces

NEXT STEPS
  1. Verify:        bash ${HERE}/verify.sh
  2. Provision each guest (copy ../guest to the guest, then run as the ${GUEST_USER} user):
       VM-100:  sudo ROLE=vm100 ./provision-guest.sh
       VM-101:  sudo ROLE=vm101 ./provision-guest.sh
       LXC-200: sudo ROLE=lxc   ./provision-guest.sh
       LXC-201: sudo ROLE=lxc   ./provision-guest.sh
EOF
