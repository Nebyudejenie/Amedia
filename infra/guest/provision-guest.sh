#!/usr/bin/env bash
# Run INSIDE each guest after first boot, as a sudo-capable user (default: arada).
#
#   sudo ROLE=vm100 ./provision-guest.sh
#   sudo ROLE=vm101 ./provision-guest.sh
#   sudo ROLE=lxc   ./provision-guest.sh
#
# Order matters: UFW opens the new SSH port BEFORE sshd is switched to it, so you
# are never locked out. Your current session stays alive; reconnect on ${SSH_PORT}.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export ROLE="${ROLE:-generic}"
export GUEST_USER="${GUEST_USER:-arada}"
export SSH_PORT="${SSH_PORT:-2222}"
export INT_SUBNET="${INT_SUBNET:-10.10.10.0/24}"
export GUEST_TZ="${GUEST_TZ:-Africa/Addis_Ababa}"

[[ ${EUID} -eq 0 ]] || { echo "Run with sudo."; exit 1; }

echo "[arada] provisioning $(hostname) as role=${ROLE}"
bash "${HERE}/scripts/00-post-install.sh"
bash "${HERE}/scripts/01-install-docker.sh"
bash "${HERE}/scripts/03-ufw.sh" "${ROLE}"
bash "${HERE}/scripts/02-harden-ssh.sh"

cat <<EOF

[arada] Guest provisioned (role=${ROLE}).
  - Docker installed; '${GUEST_USER}' added to the docker group (re-login to use docker without sudo).
  - SSH now listens on port ${SSH_PORT}, key-only, root login disabled.
  - UFW: default deny inbound; allows ${SSH_PORT}/tcp and the internal subnet ${INT_SUBNET}.

VERIFY a new SSH connection on port ${SSH_PORT}, THEN remove the legacy rule:
  sudo ufw delete allow 22/tcp
EOF
