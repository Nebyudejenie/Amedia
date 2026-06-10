# 🚀 Arada Deployment Options

GitHub Actions CI/CD pipeline **automatically tests and builds** your Docker image. However, **deploying to private Proxmox infrastructure requires different approaches** since GitHub's cloud runners cannot reach your private network (192.168.1.200).

---

## ✅ What GitHub Actions Does (Automatically)

```
Push to main branch
    ↓
GitHub Actions runs automatically
    ├─ Test & Lint ✅ (runs successfully)
    ├─ Build Docker image ✅ (pushes to ghcr.io)
    └─ Deploy to Proxmox ❌ (fails - no network access)
```

**The issue:** GitHub Actions runs on GitHub's cloud infrastructure → Cannot SSH into your private Proxmox network.

---

## 🔧 Deployment Methods

### **Option 1: Manual Deployment Script ⭐ RECOMMENDED**

**Best for:** Small teams, manual deployments, learning the process

```bash
./scripts/deploy-manual.sh
```

Or deploy to a specific IP:
```bash
./scripts/deploy-manual.sh 192.168.1.150
```

**What it does:**
- ✅ Pulls latest Docker image from GitHub registry
- ✅ Stops old containers
- ✅ Runs database migrations
- ✅ Starts new containers
- ✅ Verifies health check
- ✅ Shows deployment status

**Prerequisites:**
```bash
# 1. Generate SSH key
ssh-keygen -t ed25519 -f ~/.ssh/proxmox_deploy -N ""

# 2. Copy to Proxmox
ssh-copy-id -i ~/.ssh/proxmox_deploy root@192.168.1.200

# 3. Test connection
ssh -i ~/.ssh/proxmox_deploy root@192.168.1.200 "docker ps"
```

**Environment variables:**
```bash
# Skip database migrations
SKIP_MIGRATIONS=1 ./scripts/deploy-manual.sh

# Deploy to specific IP
./scripts/deploy-manual.sh 192.168.1.150
```

---

### **Option 2: Self-Hosted GitHub Actions Runner**

**Best for:** Full automation, continuous deployment, enterprise workflows

#### **Setup:**

1. **On your Proxmox VM:**

```bash
# Create runner directory
mkdir -p /opt/github-runner
cd /opt/github-runner

# Download runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

tar xzf actions-runner-linux-x64-2.311.0.tar.gz

# Get token from GitHub
# Go to: Repo Settings → Actions → Runners → New self-hosted runner
# Copy the token from the configure command

# Configure runner
./config.sh \
  --url https://github.com/Nebyudejenie/Amedia \
  --token YOUR_TOKEN_HERE \
  --name arada-proxmox-runner \
  --work _work
```

2. **Install as systemd service:**

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```

3. **Update GitHub Actions workflow:**

```yaml
deploy:
  runs-on: self-hosted  # ← Change from ubuntu-latest
  # ... rest stays the same
```

4. **Verify in GitHub:**
   - Go to: Repo Settings → Actions → Runners
   - Should show "arada-proxmox-runner" as Online

#### **Advantages:**
- ✅ Full automation from GitHub
- ✅ Deploy on every push to main
- ✅ Same workflow for all environments
- ✅ No manual steps needed

#### **Maintenance:**
```bash
# View logs
journalctl -u actions.runner.*.service -f

# Stop/start
sudo ./svc.sh stop
sudo ./svc.sh start

# Update runner
./config.sh --url https://github.com/Nebyudejenie/Amedia --token YOUR_TOKEN
```

---

### **Option 3: Webhook-Based Pull Deployment**

**Best for:** Decoupled systems, webhook integrations, multi-region deployments

#### **How it works:**
```
GitHub releases Docker image
    ↓
GitHub sends webhook to Proxmox
    ↓
Proxmox pulls image and deploys
```

#### **Setup on Proxmox:**

1. **Create webhook listener:**

```bash
cat > /opt/arada/webhook-listener.py << 'EOF'
#!/usr/bin/env python3
import os
import hmac
import hashlib
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "change-me")
DEPLOYMENT_SCRIPT = "/opt/arada/deploy.sh"

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        
        # Verify signature
        signature = self.headers.get('X-Hub-Signature-256', '').replace('sha256=', '')
        expected = hmac.new(
            WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected):
            self.send_response(403)
            self.end_headers()
            return
        
        # Deploy on push
        payload = json.loads(body)
        if payload.get('ref') == 'refs/heads/main':
            try:
                subprocess.run([DEPLOYMENT_SCRIPT], check=True)
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'Deployment started')
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())
        else:
            self.send_response(200)
            self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('0.0.0.0', 9000), WebhookHandler)
    print("Webhook listener running on :9000")
    server.serve_forever()
EOF

chmod +x /opt/arada/webhook-listener.py
```

2. **Create systemd service:**

```bash
sudo tee /etc/systemd/system/arada-webhook.service << 'EOF'
[Unit]
Description=Arada GitHub Webhook Listener
After=network.target

[Service]
Type=simple
User=arada
WorkingDirectory=/opt/arada
Environment="GITHUB_WEBHOOK_SECRET=your-secret-here"
ExecStart=/usr/bin/python3 /opt/arada/webhook-listener.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable arada-webhook
sudo systemctl start arada-webhook
```

3. **Add GitHub webhook:**
   - Go to: Repo Settings → Webhooks → Add webhook
   - Payload URL: `https://your-domain.com/webhook` (with reverse proxy/port forwarding)
   - Content type: `application/json`
   - Secret: `your-secret-here`
   - Events: `Push events`

---

## 📊 Comparison

| Method | Setup Time | Automation | Cost | Reliability |
|--------|-----------|-----------|------|-------------|
| **Manual Script** | 5 min | Manual | Free | High |
| **Self-Hosted Runner** | 30 min | Full | Free | Very High |
| **Webhook** | 1 hour | Full | Free | Medium |

---

## 🎯 Recommended Workflow

### **For Development:**
```bash
# 1. Push to main
git push origin main

# 2. GitHub Actions builds image automatically

# 3. When ready, deploy manually
./scripts/deploy-manual.sh
```

### **For Production:**
```bash
# 1. Set up self-hosted runner (one-time, 30 min)
# 2. Push to main
# 3. Automatic deployment via GitHub Actions
```

---

## 🔍 Troubleshooting

### **"ssh: connect to host 192.168.1.200 port 22: Connection timed out"**
- **Cause:** GitHub Actions cannot reach private network
- **Solution:** Use manual script or self-hosted runner

### **"Permission denied (publickey)"**
- **Cause:** SSH key not authorized on Proxmox
- **Solution:** Run `ssh-copy-id -i ~/.ssh/proxmox_deploy root@192.168.1.200`

### **"docker-compose: command not found"**
- **Cause:** docker-compose not installed on Proxmox
- **Solution:** Run `apt-get install -y docker-compose-plugin`

### **"API is not healthy"**
- **Cause:** Containers not fully started
- **Solution:** Check logs: `docker logs arada-api-1`

---

## 📚 Related Docs

- [DEPLOYMENT_QUICKSTART.md](./DEPLOYMENT_QUICKSTART.md) — Quick 15-min setup
- [infra/DEVOPS.md](./infra/DEVOPS.md) — Detailed DevOps guide
- [.github/workflows/ci-cd.yml](./.github/workflows/ci-cd.yml) — Workflow configuration

---

## ❓ Questions?

- GitHub Actions docs: https://docs.github.com/actions
- Proxmox SSH: https://pve.proxmox.com/wiki/SSH
- Docker Compose: https://docs.docker.com/compose/

Generated: 2026-06-10  
Last Updated: $(date)
