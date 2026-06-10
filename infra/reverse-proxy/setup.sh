#!/usr/bin/env bash
# Setup Nginx reverse proxy + Let's Encrypt for Arada Intelligence OS

set -euo pipefail

COLOR_RESET='\033[0m'
COLOR_GREEN='\033[1;32m'
COLOR_BLUE='\033[1;34m'
COLOR_YELLOW='\033[1;33m'

log() { echo -e "${COLOR_BLUE}→${COLOR_RESET} $1"; }
success() { echo -e "${COLOR_GREEN}✓${COLOR_RESET} $1"; }
warn() { echo -e "${COLOR_YELLOW}!${COLOR_RESET} $1"; }

log "Arada Intelligence OS — Reverse Proxy Setup"
echo

# Detect method
log "Choose setup method:"
echo "  1. Cloudflare Tunnel (recommended, no DNS/TLS config needed)"
echo "  2. Nginx + Let's Encrypt (traditional, full control)"
read -p "Select (1 or 2): " METHOD

case $METHOD in
  1)
    log "Cloudflare Tunnel Setup"
    echo

    # Check if cloudflared is installed
    if ! command -v cloudflared >/dev/null 2>&1; then
      log "Installing cloudflared..."
      curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
      sudo dpkg -i cloudflared.deb
      rm cloudflared.deb
      success "cloudflared installed"
    else
      success "cloudflared already installed"
    fi
    echo

    # Login
    log "Authenticating with Cloudflare..."
    cloudflared tunnel login
    echo

    # Create tunnel
    TUNNEL_NAME="arada"
    log "Creating tunnel: $TUNNEL_NAME"
    cloudflared tunnel create $TUNNEL_NAME || warn "Tunnel may already exist"
    echo

    # Configure tunnel
    log "Creating tunnel configuration..."
    mkdir -p ~/.cloudflared
    cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: arada
credentials-file: /root/.cloudflared/arada.json
logLevel: info

ingress:
  - hostname: arada.fun
    service: http://localhost:8000
  - hostname: monitoring.arada.fun
    service: http://localhost:3000
  - service: http_status:404
EOF
    success "Tunnel configuration created at ~/.cloudflared/config.yml"
    echo

    # Start tunnel
    log "Starting tunnel..."
    sudo cloudflared service install
    sudo systemctl start cloudflared
    sudo systemctl enable cloudflared
    success "Tunnel started and enabled"
    echo

    # DNS configuration
    TUNNEL_UUID=$(cloudflared tunnel info arada | grep "ID" | awk '{print $NF}')
    log "Tunnel created! Configure DNS in Cloudflare:"
    echo "  arada.fun  CNAME  ${TUNNEL_UUID}.cfargotunnel.com"
    echo
    success "Setup complete! Tunnel is running."
    echo "Monitor: cloudflared tunnel logs arada"
    ;;

  2)
    log "Nginx + Let's Encrypt Setup"
    echo

    # Check domain
    read -p "Enter domain (default: arada.fun): " DOMAIN
    DOMAIN=${DOMAIN:-arada.fun}
    read -p "Enter email (default: admin@arada.fun): " EMAIL
    EMAIL=${EMAIL:-admin@arada.fun}
    echo

    # Install packages
    log "Installing Nginx and Certbot..."
    sudo apt-get update
    sudo apt-get install -y nginx certbot python3-certbot-nginx
    success "Nginx and Certbot installed"
    echo

    # Create directories
    log "Creating certificate directories..."
    sudo mkdir -p /var/www/certbot
    sudo chown -R www-data:www-data /var/www/certbot
    success "Directories created"
    echo

    # Setup Nginx config
    log "Setting up Nginx configuration..."
    sudo cp ./nginx.conf /etc/nginx/sites-available/arada
    sudo ln -sf /etc/nginx/sites-available/arada /etc/nginx/sites-enabled/arada
    sudo rm -f /etc/nginx/sites-enabled/default

    # Test config
    if ! sudo nginx -t; then
      warn "Nginx config test failed"
      exit 1
    fi
    success "Nginx configuration validated"
    echo

    # Start Nginx
    log "Starting Nginx..."
    sudo systemctl start nginx
    sudo systemctl enable nginx
    success "Nginx started and enabled"
    echo

    # Get SSL certificate
    log "Obtaining SSL certificate from Let's Encrypt..."
    sudo certbot certonly --nginx -d "$DOMAIN" -d "www.$DOMAIN" \
      --agree-tos --no-eff-email --email "$EMAIL"
    success "SSL certificate obtained"
    echo

    # Enable auto-renewal
    log "Enabling automatic certificate renewal..."
    sudo systemctl enable certbot.timer
    sudo systemctl start certbot.timer
    success "Auto-renewal enabled"
    echo

    # Test HTTPS
    log "Testing HTTPS connection..."
    sleep 2
    if curl -s -k https://localhost/system/health >/dev/null 2>&1; then
      success "HTTPS working!"
    else
      warn "HTTPS test inconclusive (API may not be running)"
    fi
    echo

    success "Setup complete!"
    echo "Next steps:"
    echo "  1. Point DNS to this server: $DOMAIN A $(hostname -I | awk '{print $1}')"
    echo "  2. Monitor Nginx: sudo systemctl status nginx"
    echo "  3. View logs: tail -f /var/log/nginx/arada-access.log"
    ;;

  *)
    warn "Invalid selection"
    exit 1
    ;;
esac
