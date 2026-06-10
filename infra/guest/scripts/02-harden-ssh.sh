#!/usr/bin/env bash
# Harden SSH: custom port, key-only, no root login, single allowed user. Run as root.
# IMPORTANT: run 03-ufw.sh FIRST so the new port is already permitted by the firewall.
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run with sudo."; exit 1; }

GUEST_USER="${GUEST_USER:-arada}"
SSH_PORT="${SSH_PORT:-2222}"
CONF="/etc/ssh/sshd_config.d/99-arada.conf"

echo "[arada] writing ${CONF} (port ${SSH_PORT}, key-only, AllowUsers ${GUEST_USER})"
cat >"${CONF}" <<EOF
Port ${SSH_PORT}
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers ${GUEST_USER}
EOF

# Ubuntu 24.04 ships socket-activated SSH (ssh.socket), which IGNORES the Port
# directive in sshd_config. Disable the socket so our Port setting takes effect.
if systemctl is-enabled ssh.socket >/dev/null 2>&1; then
  echo "[arada] disabling socket-activated ssh.socket so Port ${SSH_PORT} applies"
  systemctl disable --now ssh.socket || true
fi

echo "[arada] validating sshd config…"
sshd -t

systemctl enable ssh >/dev/null 2>&1 || true
systemctl restart ssh

echo "[arada] sshd hardened and listening on port ${SSH_PORT}."
echo "[arada] KEEP THIS SESSION OPEN. Open a NEW terminal and confirm:"
echo "          ssh -p ${SSH_PORT} ${GUEST_USER}@<guest-ip>"
echo "        Only then close this session."
