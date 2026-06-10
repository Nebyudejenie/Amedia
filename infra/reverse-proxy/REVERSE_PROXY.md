# Arada Intelligence OS — Reverse Proxy & SSL/TLS

Production-ready reverse proxy setup with SSL, rate limiting, security headers, and multiple access methods.

## Overview

**Three access patterns:**

1. **Local/Private** — Internal network only (Proxmox, K8s internal)
2. **Cloudflare Tunnel** — Zero-trust, no exposed IP (recommended)
3. **Nginx + Let's Encrypt** — Traditional reverse proxy with managed TLS

## Architecture

```
┌─────────────────────────────────────┐
│         Internet Users              │
│  arada.fun → Cloudflare DNS        │
└────────────┬────────────────────────┘
             │ (encrypted)
             ▼
┌──────────────────────────────┐
│   Cloudflare Edge           │
│  (DDoS protection, cache)   │
└──────────────┬───────────────┘
               │ (Tunnel)
               ▼
┌──────────────────────────────┐
│  Nginx Reverse Proxy        │
│  (443 TLS termination)      │
│  (rate limiting)            │
│  (security headers)         │
└──────────────┬───────────────┘
               │ (http://api:8000)
               ▼
        ┌─────────────┐
        │  FastAPI    │
        │  (port 8000)│
        └─────────────┘
```

## Option 1: Cloudflare Tunnel (Recommended)

**Advantages:**
- No exposed IP address
- Built-in DDoS protection
- Global CDN caching
- Free tier available
- Zero firewall configuration needed
- Automatic HTTPS

### Setup

**1. Install cloudflared**

```bash
# On VM-100 (or any host with API access)
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb
```

**2. Authenticate**

```bash
cloudflared tunnel login
# Opens browser to Cloudflare → authorize → returns token
```

**3. Create tunnel**

```bash
cloudflared tunnel create arada
# Returns: Tunnel UUID and credentials file location
```

**4. Configure tunnel** (`~/.cloudflared/config.yml`)

```yaml
tunnel: arada-abc123  # Your tunnel UUID
credentials-file: /root/.cloudflared/arada-abc123.json
logLevel: info

ingress:
  # API
  - hostname: arada.fun
    service: http://localhost:8000
    
  # Grafana (monitoring)
  - hostname: monitoring.arada.fun
    service: http://localhost:3000
    
  # MinIO console (optional)
  - hostname: s3.arada.fun
    service: http://localhost:9001
    
  # Catch-all (return 404)
  - service: http_status:404
```

**5. Start tunnel**

```bash
cloudflared tunnel run arada
# Or install as systemd service:
sudo cloudflared service install
sudo systemctl start cloudflared
sudo systemctl enable cloudflared
```

**6. Configure DNS** (Cloudflare dashboard)

```
arada.fun    CNAME    arada-abc123.cfargotunnel.com
```

**7. Test**

```bash
curl https://arada.fun/system/health
```

**Benefits:**
- SSL automatically managed (no Let's Encrypt hassle)
- No firewall rules needed
- DDoS protection included
- Geographic load balancing available
- Cache rules available

**Cost:** Free tier covers personal use; $20/month for additional features

## Option 2: Nginx + Let's Encrypt (Traditional)

**Advantages:**
- Full control
- Can customize every header
- Works on any network
- No third-party dependency

### Setup

**1. Install Nginx**

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

**2. Install Nginx config** (`/etc/nginx/sites-available/arada`)

See [nginx.conf](./nginx.conf) for complete configuration.

Key settings:
```nginx
upstream api {
    server localhost:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name arada.fun www.arada.fun;
    
    # Redirect HTTP → HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name arada.fun www.arada.fun;
    
    # TLS certificates
    ssl_certificate /etc/letsencrypt/live/arada.fun/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/arada.fun/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
    limit_req zone=api burst=200 nodelay;
    
    # Compression
    gzip on;
    gzip_vary on;
    gzip_types text/plain text/css application/json application/javascript;
    
    # Proxy to API
    location / {
        proxy_pass http://api;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }
}
```

**3. Enable site**

```bash
sudo ln -s /etc/nginx/sites-available/arada /etc/nginx/sites-enabled/
sudo nginx -t  # Test config
sudo systemctl restart nginx
```

**4. Get SSL certificate**

```bash
sudo certbot certonly --nginx -d arada.fun -d www.arada.fun
# Choose automatic renewal

# Verify renewal is configured
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

**5. Test**

```bash
curl https://arada.fun/system/health
```

### Configuration Details

**Rate Limiting:**
```nginx
# Per-IP rate limit: 100 req/s, burst 200
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
limit_req zone=api burst=200 nodelay;
```

**Security Headers:**
```
Strict-Transport-Security: max-age=31536000  # Force HTTPS
X-Frame-Options: SAMEORIGIN                  # Prevent clickjacking
X-Content-Type-Options: nosniff              # Prevent MIME sniffing
X-XSS-Protection: 1; mode=block              # Enable XSS filter
Content-Security-Policy: ...                 # Control allowed resources
```

**Compression:**
```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript;
gzip_min_length 1000;
gzip_vary on;
```

**Connection Settings:**
```nginx
proxy_http_version 1.1;
proxy_set_header Connection "";  # Keep-alive
proxy_read_timeout 60s;
proxy_connect_timeout 60s;
proxy_buffering off;  # Stream responses
```

## Option 3: Hybrid (Nginx + Cloudflare Tunnel)

Combine both for maximum flexibility:

```yaml
# cloudflared config.yml
ingress:
  - hostname: arada.fun
    service: https://localhost:443
    originRequest:
      httpVersion: h2
```

Benefits:
- Cloudflare CDN + DDoS
- Full Nginx control
- Better performance (cached at edge)
- Cost: Cloudflare tunnel (free) + own Nginx (free)

## Kubernetes Setup

### Ingress with cert-manager (automatic TLS)

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@arada.fun
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: arada
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - arada.fun
    secretName: arada-tls
  rules:
  - host: arada.fun
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: api
            port:
              number: 8000
```

Install cert-manager:
```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --set installCRDs=true
```

## Monitoring Proxy Health

**Check Nginx status:**
```bash
sudo systemctl status nginx
sudo nginx -t  # Verify config
```

**View logs:**
```bash
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log
```

**Check certificate expiry:**
```bash
sudo certbot certificates
```

**Monitor Cloudflare Tunnel:**
```bash
cloudflared tunnel info arada
cloudflared tunnel logs arada
```

## Troubleshooting

### SSL Certificate Errors

```bash
# Check certificate validity
openssl x509 -in /etc/letsencrypt/live/arada.fun/cert.pem -text -noout

# Force renewal
sudo certbot renew --force-renewal

# Test renewal
sudo certbot renew --dry-run
```

### Nginx Proxy Issues

```bash
# Check upstream connectivity
curl -I http://localhost:8000/system/health

# Check Nginx status
sudo systemctl status nginx

# Reload config (no downtime)
sudo systemctl reload nginx
```

### Rate Limit Issues

```bash
# Increase limits if needed
limit_req_zone $binary_remote_addr zone=api:10m rate=1000r/s;
```

### Cloudflare Tunnel Issues

```bash
# Check tunnel status
cloudflared tunnel list

# Debug connection
cloudflared tunnel run --loglevel debug arada

# Check credentials
ls -la ~/.cloudflared/
```

## Performance Optimization

### Caching (Cloudflare)

```
Caching Rules:
- Cache /system/health: 1 minute (health check endpoint)
- Cache /metrics: 30 seconds (monitoring data)
- Don't cache /auth/* (authentication)
- Don't cache /workflow/* (real-time jobs)
```

### Connection Pooling

```nginx
# Upstream keep-alive
upstream api {
    server localhost:8000;
    keepalive 32;  # Connection pool size
}
```

### Compression

Pre-compressed assets in FastAPI:
```python
from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

## Cost Analysis

| Option | Setup | Monthly | Benefits |
|--------|-------|---------|----------|
| Cloudflare Tunnel | 5 min | Free | Zero IP, DDoS, CDN |
| Nginx + Let's Encrypt | 15 min | $0 | Full control |
| AWS ALB + ACM | 30 min | $20 | AWS ecosystem |
| Kubernetes Ingress | 20 min | $0 | K8s native |

**Recommendation:** Cloudflare Tunnel for simplicity, Nginx for control.

## References

- Nginx: https://nginx.org/en/docs/
- Certbot: https://certbot.eff.org/
- Cloudflare Tunnel: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- Let's Encrypt: https://letsencrypt.org/docs/

---

**See also**: [DEPLOYMENT.md](../DEPLOYMENT.md), [K8S_DEPLOYMENT.md](../K8S_DEPLOYMENT.md)
