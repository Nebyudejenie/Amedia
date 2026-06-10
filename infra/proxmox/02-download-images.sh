#!/usr/bin/env bash
# Download the Ubuntu 24.04 cloud image (for VMs) and CT template (for LXCs).
# Idempotent: skips downloads that already exist.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=00-config.sh
source "${HERE}/00-config.sh"
# shellcheck source=lib.sh
source "${HERE}/lib.sh"

require_root
require_pve

# --- VM cloud image ---------------------------------------------------------
if [[ -f "${CLOUDIMG_PATH}" ]]; then
  msg "Cloud image already present: ${CLOUDIMG_PATH}"
else
  msg "Downloading Ubuntu 24.04 cloud image…"
  mkdir -p "$(dirname "${CLOUDIMG_PATH}")"
  curl -fL --retry 3 --retry-delay 5 -o "${CLOUDIMG_PATH}.part" "${CLOUDIMG_URL}"
  mv "${CLOUDIMG_PATH}.part" "${CLOUDIMG_PATH}"
  msg "Saved to ${CLOUDIMG_PATH}"
fi

# --- LXC template -----------------------------------------------------------
msg "Refreshing CT template catalog…"
pveam update || warn "pveam update failed (continuing with cached catalog)"

if pveam list "${TEMPLATE_STORAGE}" 2>/dev/null | awk '{print $1}' | grep -q "${LXC_TEMPLATE_FILTER}"; then
  msg "LXC template matching '${LXC_TEMPLATE_FILTER}' already downloaded."
else
  tmpl=$(pveam available --section system | awk '{print $2}' \
           | grep "${LXC_TEMPLATE_FILTER}" | sort | tail -1) || true
  [[ -n "${tmpl:-}" ]] || die "No available CT template matching '${LXC_TEMPLATE_FILTER}'."
  msg "Downloading CT template ${tmpl} to ${TEMPLATE_STORAGE}…"
  pveam download "${TEMPLATE_STORAGE}" "${tmpl}"
fi

msg "Images ready."
