#!/usr/bin/env bash
# Arada Intelligence OS — shared Proxmox helper functions.
# Sourced by the numbered scripts; not meant to be run directly.
set -euo pipefail

msg()  { echo -e "\033[1;32m[arada]\033[0m $*"; }
warn() { echo -e "\033[1;33m[arada:warn]\033[0m $*" >&2; }
die()  { echo -e "\033[1;31m[arada:err]\033[0m $*" >&2; exit 1; }

require_root() { [[ ${EUID} -eq 0 ]] || die "Run as root on the Proxmox host."; }
require_pve()  { command -v qm >/dev/null 2>&1 && command -v pct >/dev/null 2>&1 \
                   || die "qm/pct not found — these scripts must run on a Proxmox VE host."; }
check_pubkey() { [[ -f "${SSH_PUBKEY_FILE}" ]] \
                   || die "SSH public key not found at ${SSH_PUBKEY_FILE} (see ../README.md to generate one)."; }

vm_exists() { qm status "$1"  >/dev/null 2>&1; }
ct_exists() { pct status "$1" >/dev/null 2>&1; }

# create_vm <vmid> <name> <cores> <mem_mb> <balloon_mb> <disk_gb> <internal_ip>
# Uses cloud-init + the Ubuntu cloud image. Requires Proxmox VE >= 7.2 for
# the 'import-from' disk syntax (storage-agnostic, no manual importdisk).
create_vm() {
  local vmid=$1 name=$2 cores=$3 mem=$4 balloon=$5 disk=$6 ip_int=$7
  if vm_exists "${vmid}"; then warn "VM ${vmid} (${name}) already exists — skipping create."; return 0; fi
  [[ -f "${CLOUDIMG_PATH}" ]] || die "Cloud image missing at ${CLOUDIMG_PATH} — run 02-download-images.sh first."

  msg "Creating VM ${vmid} (${name}): ${cores} vCPU / ${mem}MB (balloon ${balloon}) / ${disk}G"
  qm create "${vmid}" \
      --name "${name}" --cores "${cores}" --cpu host --numa 0 \
      --memory "${mem}" --balloon "${balloon}" --ostype l26 --agent enabled=1 \
      --scsihw virtio-scsi-single \
      --net0 "virtio,bridge=${BRIDGE_WAN}" \
      --net1 "virtio,bridge=${BRIDGE_INT}"

  # Import the cloud image directly as scsi0 (creates the disk on STORAGE).
  qm set "${vmid}" --scsi0 "${STORAGE}:0,import-from=${CLOUDIMG_PATH}"
  qm disk resize "${vmid}" scsi0 "${disk}G"

  qm set "${vmid}" --ide2 "${STORAGE}:cloudinit"
  qm set "${vmid}" --boot order=scsi0
  qm set "${vmid}" --serial0 socket --vga serial0
  qm set "${vmid}" --ciuser "${GUEST_USER}" --sshkeys "${SSH_PUBKEY_FILE}"
  qm set "${vmid}" --ipconfig0 ip=dhcp --ipconfig1 "ip=${ip_int}/24"
  qm set "${vmid}" --onboot 1

  msg "Starting VM ${vmid}…"
  qm start "${vmid}"
}

# create_ct <vmid> <name> <cores> <mem_mb> <swap_mb> <disk_gb> <internal_ip>
# Unprivileged LXC with nesting+keyctl so Docker can run inside it.
create_ct() {
  local vmid=$1 name=$2 cores=$3 mem=$4 swap=$5 disk=$6 ip_int=$7
  if ct_exists "${vmid}"; then warn "CT ${vmid} (${name}) already exists — skipping create."; return 0; fi

  local tmpl
  tmpl=$(pveam list "${TEMPLATE_STORAGE}" 2>/dev/null | awk '{print $1}' \
           | grep "${LXC_TEMPLATE_FILTER}" | sort | tail -1) || true
  [[ -n "${tmpl:-}" ]] || die "LXC template matching '${LXC_TEMPLATE_FILTER}' not found — run 02-download-images.sh first."

  msg "Creating CT ${vmid} (${name}): ${cores} core / ${mem}MB / ${disk}G  from ${tmpl}"
  pct create "${vmid}" "${tmpl}" \
      --hostname "${name}" --cores "${cores}" --memory "${mem}" --swap "${swap}" \
      --rootfs "${STORAGE}:${disk}" \
      --net0 "name=eth0,bridge=${BRIDGE_WAN},ip=dhcp" \
      --net1 "name=eth1,bridge=${BRIDGE_INT},ip=${ip_int}/24" \
      --features "nesting=1,keyctl=1" --unprivileged 1 \
      --ssh-public-keys "${SSH_PUBKEY_FILE}" \
      --onboot 1

  msg "Starting CT ${vmid}…"
  pct start "${vmid}"
}
