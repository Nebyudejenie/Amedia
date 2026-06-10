# Arada Intelligence OS — Security Hardening

Defense-in-depth security architecture covering authentication, authorization, encryption, network isolation, and compliance.

## Overview

**Security layers:**
1. **Authentication** — JWT tokens, API keys, MFA (optional)
2. **Authorization** — RBAC, workspace isolation, row-level security
3. **Encryption** — TLS in-flight, encryption at rest
4. **Network** — Firewall rules, network policies, private subnets
5. **Secrets** — Secret management, rotation, access control
6. **Audit** — Append-only logs, event tracking, compliance

## Layer 1: Authentication

### JWT Configuration

**Current setup** (api/config.py):
```python
jwt_secret_key: str          # Min 32 chars, rotate every 90 days
jwt_algorithm: str = "HS256" # Use HS256 for simplicity, RS256 for high-security
jwt_access_token_expire_minutes: int = 15
jwt_refresh_token_expire_days: int = 7
```

**For production:**
```python
# Stronger secret (min 64 chars, random)
JWT_SECRET_KEY=$(openssl rand -base64 64)

# Shorter access token TTL (15 min)
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15

# Shorter refresh token TTL (7 days, implement rotation)
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Generate strong secret:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

### API Key Security

**Current implementation** (auth_service.py):
```python
# Format: {prefix}.{secret}
# prefix: indexed, publicly shown
# secret: bcrypt-hashed, never stored in plain text
```

**Best practices:**
- Rotate API keys every 90 days
- Limit scopes (read:content, publish:video, etc.)
- Track last_used_at
- Delete unused keys immediately

**Enable key rotation:**
```python
@app.post("/auth/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, token: TokenData = Depends(get_current_user)):
    # Create new key
    new_key = await AuthService.create_api_key(...)
    
    # Mark old key as deprecated
    await db.execute(
        "UPDATE auth.api_keys SET deprecated_at = now() WHERE id = $1",
        key_id
    )
    
    return new_key
```

### Optional: Multi-Factor Authentication (MFA)

Add TOTP (Time-based One-Time Password):

```python
# Install: pip install pyotp qrcode

import pyotp

@app.post("/auth/mfa/setup")
async def setup_mfa(token: TokenData = Depends(get_current_user)):
    secret = pyotp.random_base32()
    
    # Store secret (encrypted)
    await db.execute(
        "UPDATE auth.users SET mfa_secret = pgp_sym_encrypt($1, $2) WHERE id = $3",
        secret,
        settings.encryption_key,
        token.user_id
    )
    
    # Return QR code
    totp = pyotp.totp.TOTP(secret)
    uri = totp.provisioning_uri(token.user_id, issuer_name='Arada')
    
    return {"qr_code_uri": uri}
```

## Layer 2: Authorization

### RBAC Matrix

**Current roles** (db/migrations/009_seed.sql):

| Role | Users | Workspaces | Content | Workflow | Media | Publish |
|------|-------|-----------|---------|----------|-------|---------|
| owner | ✓✓ | ✓✓ | ✓✓ | ✓✓ | ✓✓ | ✓✓ |
| admin | ✓ | ✓ | ✓✓ | ✓✓ | ✓✓ | ✓ |
| editor | - | - | ✓ | ✓ | ✓ | - |
| viewer | - | - | ✓ | - | - | - |
| publisher | - | - | - | - | - | ✓ |
| analyst | - | - | ✓ | - | - | - |

**Enforce via decorators:**

```python
@app.post("/workflow/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    token: TokenData = Depends(require_role("owner", "admin"))
):
    """Only owner/admin can cancel jobs."""
    ...

@app.delete("/auth/users/{user_id}")
async def delete_user(
    user_id: str,
    token: TokenData = Depends(require_role("owner"))
):
    """Only owner can delete users."""
    ...
```

### Row-Level Security (PostgreSQL)

**Enable RLS policies:**

```sql
-- Enable RLS on sensitive tables
ALTER TABLE auth.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE content.content_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE workflow.jobs ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own workspace's data
CREATE POLICY workspace_isolation ON auth.users
  USING (workspace_id = current_setting('app.workspace_id')::uuid);

CREATE POLICY workspace_isolation_jobs ON workflow.jobs
  USING (workspace_id = current_setting('app.workspace_id')::uuid);

-- Set workspace context for each request
SET app.workspace_id = '12345678-1234-1234-1234-123456789abc';
```

**Integrate with FastAPI:**

```python
async def get_items(token: TokenData = Depends(get_current_user)):
    async with db.acquire() as conn:
        # Set workspace context
        await conn.execute(
            f"SET app.workspace_id = '{token.workspace_id}'::uuid"
        )
        
        # Query respects RLS policy
        items = await conn.fetch("SELECT * FROM content.normalized_items")
```

## Layer 3: Encryption

### TLS/SSL (In Transit)

**Already configured:**
- Nginx: TLS 1.2+, modern ciphers (reverse-proxy/nginx.conf)
- API: All external traffic via HTTPS
- Internal: mTLS optional (Kubernetes service mesh)

**Enable mTLS** (Kubernetes + Istio):

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: arada
spec:
  mtls:
    mode: STRICT  # Enforce mTLS for all traffic
```

### Encryption at Rest

**PostgreSQL:**

```sql
-- Enable pgcrypto extension (already done in migrations)
CREATE EXTENSION pgcrypto;

-- Store sensitive data encrypted
INSERT INTO auth.users (email, password_hash, mfa_secret)
VALUES (
  'user@example.com',
  crypt('password', gen_salt('bf')),
  pgp_sym_encrypt('mfa_secret', 'encryption_key')
);

-- Retrieve and decrypt
SELECT email, pgp_sym_decrypt(mfa_secret, 'encryption_key') as mfa_secret
FROM auth.users
WHERE id = $1;
```

**MinIO:**

Enable encryption (at rest):
```yaml
# docker-compose.yml
minio:
  environment:
    MINIO_KMS_AUTO: "on"
    MINIO_KMS_KEY_FILE: /etc/minio/keys
```

**Kubernetes Secrets (encrypted in etcd):**

```bash
# Enable encryption at rest in etcd
kubectl edit cm kube-apiserver -n kube-system
# Add: --encryption-provider-config=/etc/kubernetes/encryption/config.yaml
```

## Layer 4: Network Isolation

### Firewall Rules (Proxmox)

**VM-100 (Core):**
```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp       # SSH (hardened)
sudo ufw allow 8000/tcp     # API (internal only)
sudo ufw allow 5432/tcp from 10.10.10.0/24  # PostgreSQL (internal)
sudo ufw allow 6379/tcp from 10.10.10.0/24  # Redis (internal)
sudo ufw enable
```

**VM-101 (Media):**
```bash
sudo ufw default deny incoming
sudo ufw allow 22/tcp       # SSH (hardened)
sudo ufw allow 9000/tcp from 10.10.10.0/24  # MinIO (internal)
sudo ufw allow 6333/tcp from 10.10.10.0/24  # Qdrant (internal)
sudo ufw allow 11434/tcp from 10.10.10.0/24 # Ollama (internal)
sudo ufw enable
```

### Kubernetes Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: arada-default-deny
  namespace: arada
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: arada-allow-api
  namespace: arada
spec:
  podSelector:
    matchLabels:
      app: api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - podSelector:
        matchLabels:
          app: redis
    ports:
    - protocol: TCP
      port: 6379
```

## Layer 5: Secret Management

### Kubernetes Sealed Secrets

**Install:**
```bash
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml -n kube-system
```

**Store secrets securely:**
```bash
# Create secret
kubectl -n arada create secret generic arada-secrets \
  --from-literal=db-password=... \
  --from-literal=jwt-secret-key=... \
  --dry-run=client -o yaml > secret.yaml

# Seal it
kubeseal -f secret.yaml -w sealed-secret.yaml

# Apply sealed secret (safe to commit)
kubectl apply -f sealed-secret.yaml
```

### Environment Variable Best Practices

**Never commit:**
```
.env                 # Development secrets
secrets.yaml         # Kubernetes secrets (use sealed-secrets instead)
*.pem, *.key         # TLS certificates
```

**Safe practices:**
```bash
# Use Docker secrets (production)
echo $DB_PASSWORD | docker secret create db_password -

# Use Kubernetes secrets (always sealed)
kubeseal -f secret.yaml -w sealed-secret.yaml

# Never log secrets
logging.filter(lambda r: not any(k in str(r) for k in ['password', 'secret']))
```

## Layer 6: Audit Logging

### Append-Only Event Log

**Already implemented:**
- workflow.events table (no updates/deletes)
- audit_logs schema (planned for BP5)

**Extend for all actions:**

```python
async def log_event(
    workspace_id: str,
    user_id: str,
    action: str,
    resource: str,
    details: dict
):
    """Log security-relevant action (append-only)."""
    await db.execute(
        """INSERT INTO audit_logs (workspace_id, user_id, action, resource, details, ip_address, user_agent)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        workspace_id, user_id, action, resource, json.dumps(details),
        request.client.host, request.headers.get('user-agent')
    )

# Use in routes
@app.delete("/auth/users/{user_id}")
async def delete_user(user_id: str, token: TokenData = Depends(get_current_user)):
    await log_event(
        workspace_id=token.workspace_id,
        user_id=token.user_id,
        action="delete_user",
        resource=f"user:{user_id}",
        details={"reason": "manual deletion"}
    )
    ...
```

### Monitor Audit Logs

```promql
# Detect suspicious activity
rate(audit_logs_total{action="failed_login"}[5m]) > 5

# Track permission changes
audit_logs_total{action=~"grant_role|revoke_role"}

# Monitor deletions
audit_logs_total{action=~"delete_.*"}
```

## Layer 7: Input Validation

### Request Validation

**Pydantic (already enforced):**

```python
class UserRegisterRequest(BaseModel):
    email: EmailStr              # Validates email format
    password: str = Field(..., min_length=12)  # Min 12 chars
    workspace_name: str = Field(..., min_length=1, max_length=100)
```

**Additional checks:**

```python
# SQL injection prevention: parameterized queries (already done)
await db.execute("SELECT * FROM users WHERE id = $1", user_id)  # Safe
# NOT: f"SELECT * FROM users WHERE id = {user_id}"  # Unsafe

# XSS prevention: escape HTML (on frontend)
# Not needed in API (returns JSON)

# CSRF prevention: SameSite cookies
response.set_cookie("session", value, samesite="strict")
```

## Layer 8: Rate Limiting & DoS Protection

**Already implemented:**

- Nginx rate limiting (100 req/s general, 10 req/s auth)
- Cloudflare DDoS protection
- Redis-based per-IP rate limiting

**Enhanced:**

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/auth/login")
@limiter.limit("5/minute")  # 5 login attempts per minute
async def login(request: Request, credentials: UserLoginRequest):
    ...
```

## Security Checklist

### Before Deployment

- [ ] JWT secret key (min 64 chars, rotated every 90 days)
- [ ] TLS certificates valid and auto-renewing
- [ ] Database encryption at rest enabled
- [ ] RLS policies enforced on sensitive tables
- [ ] Network policies restrict traffic (K8s) / UFW hardened (Proxmox)
- [ ] Secrets stored in sealed-secrets (K8s) or vault
- [ ] Rate limiting configured (API, auth endpoints)
- [ ] Audit logging enabled and monitored
- [ ] API keys and passwords never in logs
- [ ] SSH hardened (key-only, non-root, port 2222)

### Ongoing

- [ ] Weekly: Review audit logs for anomalies
- [ ] Monthly: Rotate API keys, JWT secrets
- [ ] Quarterly: Run vulnerability scanning (OWASP Dep-Check, Trivy)
- [ ] Annually: Security audit, penetration testing

## Vulnerability Scanning

### OWASP Dependency Check

```bash
# Install
curl -L -o dependency-check.zip https://github.com/jeremylong/DependencyCheck_Release/releases/download/v8.4.0/dependency-check-8.4.0-release.zip
unzip dependency-check.zip

# Scan Python dependencies
./dependency-check/bin/dependency-check.sh --project "Arada" --scan api/
```

### Trivy (Container Images)

```bash
# Scan Docker image
trivy image arada-os:latest

# Scan filesystem
trivy fs infra/k8s/
```

### SAST (Static Analysis)

```bash
# Install Bandit for Python
pip install bandit

# Scan for security issues
bandit -r api/ -ll  # Only high/critical issues
```

## Compliance

**GDPR Readiness:**
- [ ] User data export endpoint (`GET /users/{id}/export`)
- [ ] User deletion endpoint (`DELETE /users/{id}`) with audit trail
- [ ] Privacy policy published
- [ ] Consent tracking (in audit_logs)
- [ ] Data processing agreement signed

**HIPAA/PCI-DSS (if applicable):**
- [ ] Encryption at rest (TDE, EBS encryption)
- [ ] Encryption in transit (TLS 1.2+)
- [ ] Access logging and monitoring
- [ ] Annual penetration testing
- [ ] Security incident response plan

## References

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- CWE Top 25: https://cwe.mitre.org/top25/
- PostgreSQL Security: https://www.postgresql.org/docs/16/sql-syntax-lexical.html#SQL-SYNTAX-IDENTIFIERS
- Kubernetes Security: https://kubernetes.io/docs/concepts/security/

---

**See also**: [REVERSE_PROXY.md](../reverse-proxy/REVERSE_PROXY.md), [PERFORMANCE.md](../performance/PERFORMANCE.md)
