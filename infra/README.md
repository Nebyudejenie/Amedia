# Arada Intelligence OS — Infrastructure (Prompt 0.1)

Provisions the Proxmox foundation: an internal-only bridge, the Ubuntu 24.04
images, and four guests — then hardens each one.

```
Proxmox host
├── VM-100  arada-core    8 vCPU / 20 GB / 350 GB   core platform
├── VM-101  arada-media   4 vCPU /  8 GB / 500 GB   media factory (FFmpeg/Piper)
├── LXC-200 arada-obs     2 core /  2 GB /  50 GB   monitoring
└── LXC-201 arada-backup  1 core /  2 GB / 100 GB   backups
```

Networking: each guest has `eth0/net0` on `vmbr0` (LAN/DHCP, outbound internet)
and `eth1/net1` on `vmbr1` (private `10.10.10.0/24` service mesh). The Proxmox
host sits at `10.10.10.1`. Public access later arrives via **cloudflared**
(outbound tunnel) on VM-100 — so **no inbound 80/443** is ever opened.

## Prerequisites
- Proxmox VE **≥ 7.2** (uses the `import-from` disk syntax), running `ifupdown2`
  (default on PVE) for `ifreload`.
- A **thin-provisioned** storage (`local-lvm` / ZFS). The 1000 GB of *virtual*
  disk is allocated on demand; monitor real usage.
- An SSH keypair on the host for guest access:
  ```bash
  ssh-keygen -t ed25519 -f /root/.ssh/arada_ed25519 -C arada
  # public key path must match SSH_PUBKEY_FILE in 00-config.sh
  ```

## 1. Create the guests (on the Proxmox host, as root)
```bash
cd arada-os/infra/proxmox
# review/edit 00-config.sh first (storage, bridges, IPs, key path)
./create-all.sh
./verify.sh
```
`create-all.sh` is idempotent — existing guests/bridge/images are skipped.

## 2. Provision each guest
Copy the `guest/` folder into the guest and run it as the `arada` user:
```bash
# from the Proxmox host, push to the VM's LAN IP (qm guest cmd <id> network-get-interfaces)
scp -r ../guest arada@<guest-lan-ip>:~/arada-guest
ssh arada@<guest-lan-ip>
cd ~/arada-guest
sudo ROLE=vm100 ./provision-guest.sh     # VM-100
# ROLE=vm101 on VM-101 ; ROLE=lxc on LXC-200 and LXC-201
```
For LXC you can also run it directly from the host: `pct push 200 ...` or
`pct exec 200 -- bash -lc '...'`.

Each guest gets: base packages + time sync, Docker CE + Compose, UFW
(default-deny + SSH + internal subnet), and SSH hardening (port **2222**,
key-only, no root). **Re-login on 2222**, then `sudo ufw delete allow 22/tcp`.

## Acceptance criteria (Prompt 0.1)
- [x] All four guests boot and run (`verify.sh`).
- [x] Docker runs on VM-100 and VM-101 (and LXCs via nesting).
- [x] SSH is key-only on port 2222; root login disabled.
- [x] UFW default-denies inbound; SSH + internal subnet allowed.
- [x] Guests reach each other over the `vmbr1` internal bridge.

## Files
```
proxmox/
  00-config.sh          all tunables (storage, bridges, IPs, sizes, key path)
  lib.sh                shared helpers + create_vm / create_ct
  01-network-bridge.sh  create vmbr1 internal bridge (idempotent)
  02-download-images.sh fetch Ubuntu cloud image + LXC template
  10-create-vm100.sh    VM-100 core
  11-create-vm101.sh    VM-101 media
  12-create-lxc200.sh   LXC-200 monitoring
  13-create-lxc201.sh   LXC-201 backup
  create-all.sh         run everything in order
  verify.sh             check Prompt 0.1 acceptance criteria
guest/
  provision-guest.sh    orchestrates the guest scripts (ROLE=vm100|vm101|lxc)
  scripts/
    00-post-install.sh  base packages, time, guest agent
    01-install-docker.sh Docker CE + Compose plugin
    02-harden-ssh.sh    port 2222, key-only, no root (disables ssh.socket)
    03-ufw.sh           default-deny firewall + SSH + internal subnet
```

Next prompt: **1.1 — PostgreSQL schema & migrations** (the data core on VM-100).
