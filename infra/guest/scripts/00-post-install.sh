#!/usr/bin/env bash
# Base packages, time sync, timezone, guest agent. Run as root (via sudo).
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run with sudo."; exit 1; }

GUEST_TZ="${GUEST_TZ:-Africa/Addis_Ababa}"
export DEBIAN_FRONTEND=noninteractive

echo "[arada] apt update + upgrade…"
apt-get update -y
apt-get upgrade -y

PKGS=(ca-certificates curl gnupg lsb-release apt-transport-https \
      htop jq git vim ufw fail2ban chrony unattended-upgrades)

# qemu-guest-agent only inside a full VM (lets Proxmox read the VM's IP/state).
if systemd-detect-virt --quiet --vm; then
  PKGS+=(qemu-guest-agent)
fi

echo "[arada] installing: ${PKGS[*]}"
apt-get install -y "${PKGS[@]}"

systemctl enable --now chrony 2>/dev/null || true
if systemctl list-unit-files | grep -q '^qemu-guest-agent'; then
  systemctl enable --now qemu-guest-agent 2>/dev/null || true
fi

timedatectl set-timezone "${GUEST_TZ}" 2>/dev/null || echo "[arada:warn] could not set timezone ${GUEST_TZ}"

echo "[arada] post-install complete on $(hostname) (tz=${GUEST_TZ})"
