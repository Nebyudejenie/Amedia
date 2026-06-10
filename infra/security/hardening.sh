#!/usr/bin/env bash
# Arada Intelligence OS — Security Hardening Script
# Run on fresh Proxmox guests (VM-100, VM-101) or before production deployment

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[1;32m'
COLOR_BLUE='\033[1;34m'
COLOR_YELLOW='\033[1;33m'

log() { echo -e "${COLOR_BLUE}→${COLOR_RESET} $1"; }
success() { echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"; }
warn() { echo -e "${COLOR_YELLOW}!${COLOR_RESET} $1"; }

log "Arada Intelligence OS — Security Hardening"
echo

# ============================================================================
# 1. SYSTEM UPDATES
# ============================================================================

log "1. System Updates"
sudo apt-get update
sudo apt-get upgrade -y
success "System updated"
echo

# ============================================================================
# 2. SSH HARDENING
# ============================================================================

log "2. SSH Hardening"

# Already done in infra/guest/scripts/02-harden-ssh.sh, but verify:
if grep -q "^Port 2222" /etc/ssh/sshd_config; then
  success "SSH on port 2222"
else
  warn "SSH not hardened, see infra/guest/scripts/02-harden-ssh.sh"
fi

if grep -q "^PermitRootLogin no" /etc/ssh/sshd_config; then
  success "Root login disabled"
else
  warn "Root login still allowed"
fi

if grep -q "^PasswordAuthentication no" /etc/ssh/sshd_config; then
  success "Password auth disabled"
else
  warn "Password auth still enabled"
fi

echo

# ============================================================================
# 3. FIREWALL (UFW)
# ============================================================================

log "3. Firewall Configuration"

if ! sudo ufw status | grep -q "Status: active"; then
  log "Enabling UFW..."
  sudo ufw default deny incoming
  sudo ufw default allow outgoing
  sudo ufw allow 2222/tcp comment "SSH hardened"
  sudo ufw allow from 10.10.10.0/24 comment "Internal network"
  echo "y" | sudo ufw enable
  success "UFW enabled and configured"
else
  success "UFW already active"
fi

echo

# ============================================================================
# 4. FAIL2BAN (Brute-force protection)
# ============================================================================

log "4. Fail2Ban Installation"

if ! command -v fail2ban-client >/dev/null 2>&1; then
  sudo apt-get install -y fail2ban

  # Configure for SSH (hardened port 2222)
  sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true
port = 2222
logpath = /var/log/auth.log
EOF

  sudo systemctl restart fail2ban
  success "Fail2Ban installed and configured"
else
  success "Fail2Ban already installed"
fi

echo

# ============================================================================
# 5. KERNEL HARDENING
# ============================================================================

log "5. Kernel Hardening"

# Disable IP forwarding (unless this is a router)
sudo sysctl -w net.ipv4.ip_forward=0 2>/dev/null || true
sudo sysctl -w net.ipv6.conf.all.forwarding=0 2>/dev/null || true

# Enable SYN flood protection
sudo sysctl -w net.ipv4.tcp_syncookies=1 2>/dev/null || true

# Disable ICMP redirects
sudo sysctl -w net.ipv4.conf.all.send_redirects=0 2>/dev/null || true

# Disable source packet routing
sudo sysctl -w net.ipv4.conf.all.send_redirects=0 2>/dev/null || true
sudo sysctl -w net.ipv4.conf.default.rp_filter=1 2>/dev/null || true

success "Kernel parameters hardened"
echo

# ============================================================================
# 6. CERTIFICATE RENEWAL (If using Let's Encrypt)
# ============================================================================

log "6. Certificate Auto-Renewal"

if command -v certbot >/dev/null 2>&1; then
  if sudo systemctl is-enabled certbot.timer 2>/dev/null; then
    success "Certbot timer already enabled"
  else
    sudo systemctl enable certbot.timer
    sudo systemctl start certbot.timer
    success "Certbot auto-renewal enabled"
  fi
else
  log "Certbot not installed (using Cloudflare Tunnel?)"
fi

echo

# ============================================================================
# 7. LOG ROTATION
# ============================================================================

log "7. Log Rotation Configuration"

sudo tee /etc/logrotate.d/arada > /dev/null << 'EOF'
/var/log/nginx/arada-*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 www-data www-data
    sharedscripts
    postrotate
        systemctl reload nginx > /dev/null 2>&1 || true
    endscript
}

/var/log/postgresql/postgresql.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0600 postgres postgres
}
EOF

success "Log rotation configured"
echo

# ============================================================================
# 8. AIDE (File Integrity Monitoring)
# ============================================================================

log "8. AIDE Installation (File Integrity)"

if ! command -v aide >/dev/null 2>&1; then
  sudo apt-get install -y aide aide-common

  sudo aideinit
  sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db

  # Schedule weekly check
  sudo tee /etc/cron.d/aide-check > /dev/null << 'EOF'
0 2 * * 0 root /usr/bin/aide --check | mail -s "AIDE Report for $(hostname)" root
EOF

  success "AIDE installed and configured"
else
  success "AIDE already installed"
fi

echo

# ============================================================================
# 9. AUDIT DAEMON (auditd)
# ============================================================================

log "9. Audit Daemon Configuration"

if ! command -v auditctl >/dev/null 2>&1; then
  sudo apt-get install -y auditd audispd-plugins

  # Monitor sensitive files
  sudo tee -a /etc/audit/rules.d/arada.rules > /dev/null << 'EOF'
# Monitor /etc/passwd and /etc/shadow
-w /etc/passwd -p wa -k passwd_changes
-w /etc/shadow -p wa -k shadow_changes

# Monitor sudo usage
-w /etc/sudoers -p wa -k sudoers_changes

# Monitor Docker daemon
-w /var/lib/docker/ -k docker_changes

# Monitor system calls
-a always,exit -F arch=b64 -S execve -F key=command_execution
EOF

  sudo systemctl restart auditd
  success "Audit daemon configured"
else
  success "Audit daemon already installed"
fi

echo

# ============================================================================
# 10. AUTOMATIC SECURITY UPDATES
# ============================================================================

log "10. Unattended Upgrades"

if ! dpkg -l | grep -q unattended-upgrades; then
  sudo apt-get install -y unattended-upgrades apt-listchanges

  sudo tee /etc/apt/apt.conf.d/50unattended-upgrades > /dev/null << 'EOF'
Unattended-Upgrade::Allowed-Origins {
  "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
EOF

  sudo systemctl enable unattended-upgrades
  success "Unattended upgrades configured"
else
  success "Unattended upgrades already installed"
fi

echo

# ============================================================================
# 11. VERIFY HARDENING
# ============================================================================

log "11. Hardening Verification"

echo "Security Configuration Status:"
echo
echo "SSH:"
sudo sshd -T 2>/dev/null | grep -E "^port|permitrootlogin|passwordauthentication" || true

echo
echo "Firewall:"
sudo ufw status | head -10

echo
echo "Fail2Ban:"
sudo fail2ban-client status sshd 2>/dev/null || echo "  (Not configured yet)"

echo
echo "Audit:"
sudo auditctl -l | wc -l | xargs echo "  Rules loaded:"

echo

# ============================================================================
# SUMMARY
# ============================================================================

success "Security hardening complete!"
echo
echo "Next steps:"
echo "  1. Verify SSH key-only access: ssh -i ~/.ssh/id_rsa -p 2222 user@host"
echo "  2. Check UFW rules: sudo ufw status verbose"
echo "  3. Monitor fail2ban: sudo fail2ban-client status sshd"
echo "  4. Review audit logs: sudo ausearch -i"
echo
echo "For more details, see: infra/security/SECURITY.md"
