#!/usr/bin/env bash
# Verify Prompt 0.1 acceptance criteria from the Proxmox host:
#   - all four guests exist and are running
#   - the internal bridge is up
#   - the host can reach each guest on the internal subnet
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${HERE}/00-config.sh"
source "${HERE}/lib.sh"
require_root; require_pve

fail=0
pass() { echo -e "  \033[1;32mPASS\033[0m $*"; }
bad()  { echo -e "  \033[1;31mFAIL\033[0m $*"; fail=1; }

echo "== Guest status =="
for spec in "vm:${VM100_ID}:${VM100_NAME}" "vm:${VM101_ID}:${VM101_NAME}" \
            "ct:${LXC200_ID}:${LXC200_NAME}" "ct:${LXC201_ID}:${LXC201_NAME}"; do
  IFS=: read -r kind id name <<<"${spec}"
  if [[ "${kind}" == "vm" ]]; then st=$(qm status "${id}" 2>/dev/null | awk '{print $2}') || st="missing"
  else st=$(pct status "${id}" 2>/dev/null | awk '{print $2}') || st="missing"; fi
  [[ "${st}" == "running" ]] && pass "${name} (${id}) running" || bad "${name} (${id}) status=${st:-missing}"
done

echo "== Internal bridge =="
ip link show "${BRIDGE_INT}" >/dev/null 2>&1 && pass "${BRIDGE_INT} present" || bad "${BRIDGE_INT} missing"

echo "== Internal connectivity (host -> guest) =="
for ip in "${IP_VM100}" "${IP_VM101}" "${IP_LXC200}" "${IP_LXC201}"; do
  if ping -c1 -W2 "${ip}" >/dev/null 2>&1; then pass "ping ${ip}"
  else bad "ping ${ip} (guest may still be booting / cloud-init not finished)"; fi
done

echo
if [[ ${fail} -eq 0 ]]; then echo -e "\033[1;32mPrompt 0.1 verification PASSED\033[0m"
else echo -e "\033[1;33mSome checks failed — VMs can take 1-2 min to finish cloud-init on first boot. Re-run after they settle.\033[0m"; exit 1; fi
