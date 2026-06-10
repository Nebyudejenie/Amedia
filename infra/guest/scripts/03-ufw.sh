#!/usr/bin/env bash
# Configure UFW: default-deny inbound, allow SSH + the internal service mesh.
# Run as root. Usage: ./03-ufw.sh [vm100|vm101|lxc|generic]
#
# Design note: public traffic reaches the platform via cloudflared, which makes
# OUTBOUND connections to Cloudflare. Therefore NO inbound 80/443 is opened on
# any guest. All inter-service traffic flows over the private internal subnet.
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run with sudo."; exit 1; }

SSH_PORT="${SSH_PORT:-2222}"
INT_SUBNET="${INT_SUBNET:-10.10.10.0/24}"
ROLE="${1:-generic}"

echo "[arada] resetting UFW (role=${ROLE})"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing

# SSH: allow both legacy 22 and the new port during migration. Remove 22 after
# verifying the hardened port works (see 02-harden-ssh.sh output).
ufw allow 22/tcp                comment 'ssh legacy (remove after migration)'
ufw allow "${SSH_PORT}/tcp"     comment 'ssh'

# Private service mesh: every Arada service talks over the internal bridge only.
ufw allow from "${INT_SUBNET}"  comment 'arada internal network'

case "${ROLE}" in
  vm100)  : ;;  # edge handled by cloudflared (outbound); nothing extra inbound
  vm101)  : ;;  # render-api/piper reached from VM-100 over the internal subnet
  lxc)    : ;;  # prometheus/grafana/backup reached over the internal subnet
  *)      : ;;
esac

ufw --force enable
echo "[arada] UFW enabled:"
ufw status verbose

echo "[arada] After confirming SSH on ${SSH_PORT}, tighten with:  sudo ufw delete allow 22/tcp"
