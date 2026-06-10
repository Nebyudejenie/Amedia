#!/usr/bin/env bash
# Arada Intelligence OS — Proxmox provisioning configuration
# ----------------------------------------------------------------------------
# Edit these values to match your environment, then run ./create-all.sh on the
# Proxmox host (as root). Every value can also be overridden via the environment
# (e.g. STORAGE=local-zfs ./create-all.sh).
# ----------------------------------------------------------------------------
set -euo pipefail

# --- Proxmox storage --------------------------------------------------------
# STORAGE must support content type 'images' (VMs) and 'rootdir' (LXC).
STORAGE="${STORAGE:-local-lvm}"
# TEMPLATE_STORAGE must support 'vztmpl' (CT templates) and 'iso'.
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"

# --- Networking -------------------------------------------------------------
BRIDGE_WAN="${BRIDGE_WAN:-vmbr0}"        # existing bridge with LAN/Internet (DHCP)
BRIDGE_INT="${BRIDGE_INT:-vmbr1}"        # internal-only bridge (created by 01-network-bridge.sh)
INT_SUBNET="${INT_SUBNET:-10.10.10.0/24}"
INT_GW_HOST="${INT_GW_HOST:-10.10.10.1}" # Proxmox host address on the internal bridge

# Internal static IPs (private VM<->VM service mesh; never exposed publicly)
IP_VM100="${IP_VM100:-10.10.10.100}"
IP_VM101="${IP_VM101:-10.10.10.101}"
IP_LXC200="${IP_LXC200:-10.10.10.200}"
IP_LXC201="${IP_LXC201:-10.10.10.201}"

# --- Guest access -----------------------------------------------------------
GUEST_USER="${GUEST_USER:-arada}"
SSH_PUBKEY_FILE="${SSH_PUBKEY_FILE:-/root/.ssh/arada_ed25519.pub}"
SSH_PORT="${SSH_PORT:-2222}"
GUEST_TZ="${GUEST_TZ:-Africa/Addis_Ababa}"

# --- Images -----------------------------------------------------------------
CLOUDIMG_URL="${CLOUDIMG_URL:-https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img}"
CLOUDIMG_PATH="${CLOUDIMG_PATH:-/var/lib/vz/template/iso/noble-server-cloudimg-amd64.img}"
LXC_TEMPLATE_FILTER="${LXC_TEMPLATE_FILTER:-ubuntu-24.04-standard}"

# --- Guest specifications ---------------------------------------------------
# Note on RAM: VM max + VM max = 28GB on a 32GB host. Balloon minimums let the
# Proxmox host reclaim RAM under pressure so the host is never starved. LXCs use
# only what they need. Watch host memory after deploy and lower balloons if tight.
# Note on disk: 350+500+50+100 = 1000GB of *virtual* (max) size. This REQUIRES a
# thin-provisioned storage (lvm-thin / zfs); actual usage grows on demand.
VM100_ID=100;  VM100_NAME="arada-core";   VM100_CORES=8; VM100_MEM=20480; VM100_BALLOON=10240; VM100_DISK=350
VM101_ID=101;  VM101_NAME="arada-media";  VM101_CORES=4; VM101_MEM=8192;  VM101_BALLOON=4096;  VM101_DISK=500
LXC200_ID=200; LXC200_NAME="arada-obs";    LXC200_CORES=2; LXC200_MEM=2048; LXC200_SWAP=512; LXC200_DISK=50
LXC201_ID=201; LXC201_NAME="arada-backup"; LXC201_CORES=1; LXC201_MEM=2048; LXC201_SWAP=512; LXC201_DISK=100
