#!/usr/bin/env bash
# Install Docker CE + Compose plugin from Docker's official apt repo. Run as root.
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run with sudo."; exit 1; }

GUEST_USER="${GUEST_USER:-arada}"
export DEBIAN_FRONTEND=noninteractive

if command -v docker >/dev/null 2>&1; then
  echo "[arada] docker already installed: $(docker --version)"
else
  echo "[arada] adding Docker apt repository…"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker

# Allow the operator user to run docker without sudo (effective after re-login).
if id -u "${GUEST_USER}" >/dev/null 2>&1; then
  usermod -aG docker "${GUEST_USER}" || true
fi

echo "[arada] docker smoke test…"
if docker run --rm hello-world >/dev/null 2>&1; then
  echo "[arada] docker OK ($(docker --version); $(docker compose version | head -1))"
else
  echo "[arada:warn] docker smoke test failed."
  echo "[arada:warn] If this is an unprivileged LXC, ensure the CT has features nesting=1,keyctl=1 (set by create_ct)."
fi
