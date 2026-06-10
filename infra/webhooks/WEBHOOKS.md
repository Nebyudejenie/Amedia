# Arada Intelligence OS — Webhook Integrations & Event Architecture

Send real-time notifications to external services (Slack, Discord, Stripe, custom APIs) when events occur in Arada.

## Overview

**Event-driven architecture:**
1. **Internal events** — Generated when jobs complete, content scores, publishes succeed
2. **Webhooks** — HTTP POST notifications sent to external services
3. **Integrations** — Native connections to popular SaaS platforms
4. **Reliability** — Exponential backoff, dead letter queue, manual retry

```
Arada System Event
    ↓
Event Queue (Redis Streams)
    ↓
Webhook Worker picks up event
    ↓
Lookup registered webhooks
    ↓
HTTP POST to webhook URLs (with signature)
    ↓
Success? Store in audit log
    ↓
Failure? Retry with exponential backoff
    ↓
Dead letter queue after 5 attempts
```

## Architecture

### Event Types

```python
class EventType(str, Enum):
    # Content events
    CONTENT_INGESTED = "content.ingested"           # New item fetched
    CONTENT_SCORED = "content.scored"               # Scoring complete
    CONTENT_DELETED = "content.deleted"             # Item deleted
    
    # Workflow events
    JOB_CREATED = "job.created"                     # New job queued
    JOB_STARTED = "job.started"                     # Job processing started
    JOB_COMPLETED = "job.completed"                 # Job succeeded
    JOB_FAILED = "job.failed"                       # Job failed
    
    # Publishing events
    PUBLISH_STARTED = "publish.started"             # Publishing initiated
    PUBLISH_SUCCESS = "publish.success"             # Posted to platform
    PUBLISH_FAILED = "publish.failed"               # Platform error
    
    # User/workspace events
    USER_CREATED = "user.created"                   # New user registered
    USER_INVITED = "user.invited"                   # User invited to workspace
    WORKSPACE_CREATED = "workspace.created"         # New workspace
    
    # Revenue events (optional)
    AFFILIATE_CLICK = "affiliate.click"             # Affiliate link clicked
    CONVERSION = "conversion"                       # Sale/conversion tracked
```

### Event Payload Structure

```json
{
  "id": "evt_1a2b3c4d5e6f7g8h",
  "type": "job.completed",
  "timestamp": "2026-06-10T14:30:00Z",
  "workspace_id": "ws_12345",
  "user_id": "usr_abcde",
  "data": {
    "job_id": "job_xyz",
    "job_type": "brief",
    "status": "completed",
    "duration_seconds": 45,
    "input_count": 10,
    "output_count": 1,
    "metadata": {
      "brief_title": "Top Stories This Week",
      "source_count": 3
    }
  },
  "retry_count": 0,
  "attempt_at": "2026-06-10T14:30:00Z"
}
```

### Webhook Object

```json
{
  "id": "wh_7f8g9h0i1j2k3l4m",
  "workspace_id": "ws_12345",
  "url": "https://example.com/webhooks/arada",
  "events": ["job.completed", "publish.success", "publish.failed"],
  "active": true,
  "signing_secret": "whsec_1234567890abcdef",
  "rate_limit": 100,
  "rate_limit_window": 60,
  "retry_max_attempts": 5,
  "timeout_seconds": 30,
  "created_at": "2026-06-10T10:00:00Z",
  "updated_at": "2026-06-10T10:00:00Z",
  "last_sent_at": "2026-06-10T14:29:00Z",
  "last_sent_status": 200,
  "metadata": {
    "service": "slack",
    "channel": "#arada-alerts",
    "description": "Job completion alerts"
  }
}
```

---

## Part 1: Database Schema

```sql
-- Webhooks table
CREATE TABLE webhooks.webhooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES auth.workspaces(id),
  url TEXT NOT NULL,
  events TEXT[] NOT NULL,
  active BOOLEAN DEFAULT true,
  signing_secret TEXT NOT NULL,
  rate_limit INT DEFAULT 100,
  rate_limit_window INT DEFAULT 60,  -- seconds
  retry_max_attempts INT DEFAULT 5,
  timeout_seconds INT DEFAULT 30,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  last_sent_at TIMESTAMPTZ,
  last_sent_status INT,
  metadata JSONB,
  deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_webhooks_workspace ON webhooks.webhooks(workspace_id);
CREATE INDEX idx_webhooks_active ON webhooks.webhooks(active) WHERE active = true;

-- Webhook delivery log
CREATE TABLE webhooks.webhook_deliveries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  webhook_id UUID NOT NULL REFERENCES webhooks.webhooks(id) ON DELETE CASCADE,
  event_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  http_status INT,
  response_body TEXT,
  error_message TEXT,
  attempt_number INT NOT NULL,
  response_time_ms INT,
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  next_retry_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_webhook_deliveries_webhook ON webhooks.webhook_deliveries(webhook_id);
CREATE INDEX idx_webhook_deliveries_event ON webhooks.webhook_deliveries(event_id);
CREATE INDEX idx_webhook_deliveries_status ON webhooks.webhook_deliveries(http_status);
CREATE INDEX idx_webhook_deliveries_retry ON webhooks.webhook_deliveries(next_retry_at);

-- Dead letter queue
CREATE TABLE webhooks.dead_letter_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  webhook_id UUID NOT NULL REFERENCES webhooks.webhooks(id),
  event_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  event_payload JSONB NOT NULL,
  last_error TEXT,
  attempt_count INT DEFAULT 5,
  moved_at TIMESTAMPTZ DEFAULT NOW(),
  resolved BOOLEAN DEFAULT false,
  resolution_notes TEXT
);

CREATE INDEX idx_dlq_webhook ON webhooks.dead_letter_queue(webhook_id);
CREATE INDEX idx_dlq_resolved ON webhooks.dead_letter_queue(resolved);
```

---

## Part 2: API Endpoints

### Create Webhook

```http
POST /webhooks
Content-Type: application/json
Authorization: Bearer {token}

{
  "url": "https://example.com/webhooks/arada",
  "events": ["job.completed", "publish.success"],
  "active": true,
  "retry_max_attempts": 5,
  "timeout_seconds": 30,
  "metadata": {
    "service": "slack",
    "description": "Job completion alerts"
  }
}

Response: 201 Created
{
  "id": "wh_7f8g9h0i1j2k3l4m",
  "url": "https://example.com/webhooks/arada",
  "signing_secret": "whsec_1234567890abcdef",
  "created_at": "2026-06-10T14:30:00Z"
}
```

### List Webhooks

```http
GET /webhooks?active=true&workspace_id={ws_id}
Authorization: Bearer {token}

Response: 200 OK
{
  "data": [
    {
      "id": "wh_xxx",
      "url": "https://...",
      "events": [...],
      "active": true,
      "last_sent_at": "2026-06-10T14:30:00Z",
      "last_sent_status": 200
    }
  ],
  "total": 5
}
```

### Update Webhook

```http
PATCH /webhooks/{webhook_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "events": ["job.completed", "publish.success", "content.scored"],
  "active": false,
  "timeout_seconds": 45
}

Response: 200 OK
```

### Delete Webhook

```http
DELETE /webhooks/{webhook_id}
Authorization: Bearer {token}

Response: 204 No Content
```

### Test Webhook

```http
POST /webhooks/{webhook_id}/test
Authorization: Bearer {token}

Response: 200 OK
{
  "status": "sent",
  "http_code": 200,
  "response_time_ms": 234,
  "delivery_id": "wd_xxx"
}
```

### Get Webhook Deliveries

```http
GET /webhooks/{webhook_id}/deliveries?limit=50&status=failed
Authorization: Bearer {token}

Response: 200 OK
{
  "data": [
    {
      "id": "wd_xxx",
      "event_type": "job.completed",
      "http_status": 500,
      "error_message": "Internal Server Error",
      "attempt_number": 3,
      "next_retry_at": "2026-06-10T14:35:00Z"
    }
  ],
  "total": 3
}
```

### Retry Failed Delivery

```http
POST /webhooks/deliveries/{delivery_id}/retry
Authorization: Bearer {token}

Response: 200 OK
{
  "status": "retried",
  "attempt_number": 4,
  "next_retry_at": "2026-06-10T14:35:00Z"
}
```

### Resolve Dead Letter

```http
POST /webhooks/dead-letters/{dlq_id}/resolve
Authorization: Bearer {token}

{
  "resolution_notes": "Endpoint updated, ready to retry"
}

Response: 200 OK
```

---

## Part 3: Webhook Worker Implementation

```python
# api/workers/webhook_worker.py

import asyncio
import json
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx
import asyncpg
from aioredis import Redis

class WebhookWorker:
    """Process webhook events from Redis streams."""
    
    def __init__(self, db_pool, redis: Redis, config):
        self.db_pool = db_pool
        self.redis = redis
        self.config = config
        self.client = httpx.AsyncClient(timeout=30)
    
    async def start(self):
        """Start consuming webhook events."""
        print("🪝 Webhook worker started")
        while True:
            try:
                await self.process_events()
                await self.process_retries()
            except Exception as e:
                print(f"❌ Webhook worker error: {e}")
                await asyncio.sleep(5)
    
    async def process_events(self):
        """Process new events from Redis stream."""
        async with self.db_pool.acquire() as conn:
            # Get pending events
            events = await conn.fetch("""
                SELECT id, type, workspace_id, data 
                FROM events 
                WHERE webhooks_sent = false 
                ORDER BY created_at ASC 
                LIMIT 100
            """)
            
            for event in events:
                await self.send_event(conn, event)
    
    async def send_event(self, conn, event):
        """Send event to all registered webhooks."""
        webhooks = await conn.fetch("""
            SELECT id, url, events, signing_secret, timeout_seconds, retry_max_attempts
            FROM webhooks.webhooks
            WHERE workspace_id = $1 
              AND active = true
              AND $2::TEXT = ANY(events)
            LIMIT 100
        """, event['workspace_id'], event['type'])
        
        for webhook in webhooks:
            # Check rate limit
            if not await self.check_rate_limit(webhook['id']):
                continue
            
            # Prepare payload
            payload = {
                "id": str(event['id']),
                "type": event['type'],
                "timestamp": event['created_at'].isoformat(),
                "data": event['data']
            }
            
            # Sign payload
            signature = self.sign_payload(
                json.dumps(payload),
                webhook['signing_secret']
            )
            
            try:
                # Send webhook
                response = await self.client.post(
                    webhook['url'],
                    json=payload,
                    headers={
                        "X-Arada-Signature": signature,
                        "X-Arada-Event-ID": str(event['id']),
                        "X-Arada-Event-Type": event['type'],
                        "X-Arada-Timestamp": datetime.utcnow().isoformat(),
                        "Content-Type": "application/json"
                    },
                    timeout=webhook['timeout_seconds']
                )
                
                # Log delivery
                await conn.execute("""
                    INSERT INTO webhooks.webhook_deliveries 
                    (webhook_id, event_id, event_type, http_status, response_time_ms, attempt_number)
                    VALUES ($1, $2, $3, $4, $5, 1)
                """, webhook['id'], event['id'], event['type'], response.status_code, 
                response.elapsed.total_seconds() * 1000)
                
                if response.status_code >= 200 and response.status_code < 300:
                    # Success
                    await conn.execute(
                        "UPDATE events SET webhooks_sent = true WHERE id = $1",
                        event['id']
                    )
                else:
                    # Schedule retry
                    await self.schedule_retry(conn, webhook['id'], event['id'], 1)
                    
            except Exception as e:
                # Error sending webhook
                await conn.execute("""
                    INSERT INTO webhooks.webhook_deliveries 
                    (webhook_id, event_id, event_type, error_message, attempt_number)
                    VALUES ($1, $2, $3, $4, 1)
                """, webhook['id'], event['id'], event['type'], str(e))
                
                await self.schedule_retry(conn, webhook['id'], event['id'], 1)
    
    async def process_retries(self):
        """Process failed webhook deliveries with exponential backoff."""
        async with self.db_pool.acquire() as conn:
            retries = await conn.fetch("""
                SELECT id, webhook_id, event_id, event_type, attempt_number
                FROM webhooks.webhook_deliveries
                WHERE next_retry_at <= NOW()
                  AND completed_at IS NULL
                  AND attempt_number < (
                    SELECT retry_max_attempts FROM webhooks.webhooks 
                    WHERE id = webhook_id
                  )
                ORDER BY next_retry_at ASC
                LIMIT 50
            """)
            
            for retry in retries:
                await self.retry_webhook(conn, retry)
    
    async def retry_webhook(self, conn, delivery):
        """Retry a failed webhook with exponential backoff."""
        webhook = await conn.fetchrow(
            "SELECT url, signing_secret, timeout_seconds FROM webhooks.webhooks WHERE id = $1",
            delivery['webhook_id']
        )
        
        # Get original event
        event = await conn.fetchrow(
            "SELECT * FROM events WHERE id = $1",
            delivery['event_id']
        )
        
        payload = {
            "id": str(delivery['event_id']),
            "type": delivery['event_type'],
            "data": event['data'],
            "retry_count": delivery['attempt_number']
        }
        
        signature = self.sign_payload(json.dumps(payload), webhook['signing_secret'])
        
        try:
            response = await self.client.post(
                webhook['url'],
                json=payload,
                headers={
                    "X-Arada-Signature": signature,
                    "X-Arada-Retry-Attempt": str(delivery['attempt_number'] + 1),
                    "Content-Type": "application/json"
                },
                timeout=webhook['timeout_seconds']
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                # Success
                await conn.execute(
                    "UPDATE webhooks.webhook_deliveries SET completed_at = NOW() WHERE id = $1",
                    delivery['id']
                )
            else:
                # Schedule next retry
                await self.schedule_retry(conn, delivery['webhook_id'], delivery['event_id'], 
                                        delivery['attempt_number'])
                
        except Exception as e:
            # Failure - schedule retry or move to DLQ
            await self.schedule_retry(conn, delivery['webhook_id'], delivery['event_id'],
                                    delivery['attempt_number'])
    
    async def schedule_retry(self, conn, webhook_id, event_id, attempt_number):
        """Schedule webhook retry with exponential backoff."""
        max_attempts = await conn.fetchval(
            "SELECT retry_max_attempts FROM webhooks.webhooks WHERE id = $1",
            webhook_id
        )
        
        next_attempt = attempt_number + 1
        
        if next_attempt > max_attempts:
            # Move to dead letter queue
            await conn.execute("""
                INSERT INTO webhooks.dead_letter_queue 
                (webhook_id, event_id, event_type, attempt_count)
                SELECT webhook_id, event_id, event_type, $3
                FROM webhooks.webhook_deliveries
                WHERE webhook_id = $1 AND event_id = $2
                LIMIT 1
            """, webhook_id, event_id, next_attempt)
        else:
            # Schedule retry with exponential backoff (2^attempt minutes)
            backoff_minutes = 2 ** (next_attempt - 1)
            next_retry = datetime.utcnow() + timedelta(minutes=backoff_minutes)
            
            await conn.execute("""
                UPDATE webhooks.webhook_deliveries
                SET 
                  attempt_number = $1,
                  next_retry_at = $2
                WHERE webhook_id = $3 AND event_id = $4
                ORDER BY attempt_number DESC
                LIMIT 1
            """, next_attempt, next_retry, webhook_id, event_id)
    
    async def check_rate_limit(self, webhook_id: str) -> bool:
        """Check if webhook is within rate limit."""
        webhook = await self.db_pool.fetchrow(
            "SELECT rate_limit, rate_limit_window FROM webhooks.webhooks WHERE id = $1",
            webhook_id
        )
        
        key = f"webhook_rate:{webhook_id}"
        count = await self.redis.incr(key)
        
        if count == 1:
            await self.redis.expire(key, webhook['rate_limit_window'])
        
        return count <= webhook['rate_limit']
    
    @staticmethod
    def sign_payload(payload: str, secret: str) -> str:
        """Create HMAC-SHA256 signature for webhook."""
        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
```

---

## Part 4: Pre-built Integrations

### Slack Integration

```python
# api/integrations/slack_integration.py

from typing import Optional

class SlackIntegration:
    """Send Arada events to Slack channels."""
    
    def __init__(self, webhook_url: str, channel: str = "#notifications"):
        self.webhook_url = webhook_url
        self.channel = channel
    
    async def format_event(self, event: dict) -> dict:
        """Format Arada event as Slack message."""
        event_type = event.get('type', 'unknown')
        data = event.get('data', {})
        
        if event_type == 'job.completed':
            return {
                "channel": self.channel,
                "text": f"✅ Job Completed: {data.get('job_type')}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Job Completed"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Job Type:*\n{data.get('job_type')}"},
                            {"type": "mrkdwn", "text": f"*Duration:*\n{data.get('duration_seconds')}s"},
                            {"type": "mrkdwn", "text": f"*Status:*\n{data.get('status')}"},
                            {"type": "mrkdwn", "text": f"*Items:*\n{data.get('input_count')} → {data.get('output_count')}"}
                        ]
                    }
                ]
            }
        
        elif event_type == 'publish.success':
            return {
                "channel": self.channel,
                "text": f"📤 Published to {data.get('platform')}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📤 *Published to {data.get('platform')}*\n`{data.get('post_id')}`"
                        }
                    }
                ]
            }
        
        elif event_type == 'job.failed':
            return {
                "channel": self.channel,
                "text": f"❌ Job Failed: {data.get('job_type')}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *Job Failed*\n*Error:* {data.get('error_message')}"
                        }
                    }
                ]
            }
        
        return {}
```

### Discord Integration

```python
# api/integrations/discord_integration.py

class DiscordIntegration:
    """Send Arada events to Discord channels."""
    
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def format_event(self, event: dict) -> dict:
        """Format Arada event as Discord embed."""
        event_type = event.get('type', 'unknown')
        data = event.get('data', {})
        
        colors = {
            'job.completed': 0x00FF00,  # Green
            'publish.success': 0x0000FF,  # Blue
            'job.failed': 0xFF0000,  # Red
            'content.scored': 0xFFFF00,  # Yellow
        }
        
        if event_type == 'job.completed':
            return {
                "embeds": [
                    {
                        "title": "✅ Job Completed",
                        "color": colors.get(event_type, 0x808080),
                        "fields": [
                            {"name": "Job Type", "value": data.get('job_type'), "inline": True},
                            {"name": "Duration", "value": f"{data.get('duration_seconds')}s", "inline": True},
                            {"name": "Input Items", "value": str(data.get('input_count')), "inline": True},
                            {"name": "Output Items", "value": str(data.get('output_count')), "inline": True}
                        ],
                        "timestamp": event.get('timestamp')
                    }
                ]
            }
        
        return {}
```

### Stripe Integration

```python
# api/integrations/stripe_integration.py

import stripe

class StripeIntegration:
    """Send Arada conversion events to Stripe."""
    
    def __init__(self, api_key: str):
        stripe.api_key = api_key
    
    async def track_event(self, event: dict):
        """Track Arada event in Stripe."""
        event_type = event.get('type', 'unknown')
        data = event.get('data', {})
        
        if event_type == 'conversion':
            # Create or update customer event
            stripe.Event.create(
                type='arada.conversion',
                data={
                    'customer_id': data.get('customer_id'),
                    'amount': data.get('amount'),
                    'currency': data.get('currency', 'usd'),
                    'source': 'arada',
                    'workspace_id': event.get('workspace_id')
                }
            )
```

### Custom HTTP Webhook

```python
# Example: Receive webhook at your application

@app.post("/webhooks/arada")
async def handle_arada_webhook(request: Request, payload: dict):
    """Receive webhook from Arada."""
    
    # Verify signature
    signature = request.headers.get('X-Arada-Signature')
    event_id = request.headers.get('X-Arada-Event-ID')
    event_type = request.headers.get('X-Arada-Event-Type')
    
    # Verify HMAC signature
    if not verify_signature(signature, json.dumps(payload), YOUR_WEBHOOK_SECRET):
        return {"error": "Invalid signature"}, 401
    
    # Process event
    if event_type == 'job.completed':
        await handle_job_completed(payload)
    elif event_type == 'publish.success':
        await handle_publish_success(payload)
    
    return {"status": "received"}
```

---

## Part 5: Event Emission

### Emit Event from Workflow Service

```python
# api/services/workflow_service.py

async def emit_event(
    workspace_id: str,
    event_type: str,
    data: dict,
    user_id: Optional[str] = None
):
    """Emit event (triggers webhooks)."""
    
    async with db_pool.acquire() as conn:
        # Insert event
        event_id = await conn.fetchval("""
            INSERT INTO events (workspace_id, user_id, type, data)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """, workspace_id, user_id, event_type, json.dumps(data))
        
        # Push to Redis stream for immediate processing
        await redis.xadd(
            f"webhooks:events:{workspace_id}",
            {"event_id": str(event_id), "event_type": event_type},
            maxlen=10000
        )
        
        return event_id

# Usage in job completion
async def complete_job(job_id: str):
    job = await get_job(job_id)
    
    # ... complete job logic ...
    
    # Emit completion event
    await emit_event(
        workspace_id=job.workspace_id,
        event_type="job.completed",
        data={
            "job_id": str(job_id),
            "job_type": job.job_type,
            "status": "completed",
            "duration_seconds": (job.completed_at - job.created_at).total_seconds(),
            "output": job.output
        },
        user_id=job.user_id
    )
```

---

## Part 6: Webhook Security

### Signature Verification (Client Side)

```python
import hmac
import hashlib

def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected_signature = "sha256=" + hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)

# In your webhook handler
@app.post("/webhooks/arada")
async def handle_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Arada-Signature")
    
    if not verify_webhook_signature(body.decode(), signature, YOUR_SECRET):
        return {"error": "Invalid signature"}, 401
    
    payload = json.loads(body)
    # Process webhook...
```

### IP Whitelisting

```python
# Arada API whitelist (in your firewall)
ARADA_WEBHOOK_IPS = [
    "52.1.2.3",      # us-east-1
    "52.50.1.2",     # eu-west-1
]

@app.post("/webhooks/arada")
async def handle_webhook(request: Request):
    client_ip = request.client.host
    if client_ip not in ARADA_WEBHOOK_IPS:
        return {"error": "Forbidden"}, 403
```

---

## Part 7: Monitoring & Debugging

### Webhook Health Dashboard

```sql
-- Find slow webhooks
SELECT 
  w.id,
  w.url,
  COUNT(wd.id) as total_deliveries,
  AVG(wd.response_time_ms) as avg_response_time,
  COUNT(CASE WHEN wd.http_status >= 400 THEN 1 END) as failures,
  ROUND(100.0 * COUNT(CASE WHEN wd.http_status >= 400 THEN 1 END) / NULLIF(COUNT(*), 0), 2) as failure_rate
FROM webhooks.webhooks w
LEFT JOIN webhooks.webhook_deliveries wd ON w.id = wd.webhook_id
WHERE w.deleted_at IS NULL
  AND wd.sent_at > NOW() - INTERVAL '24 hours'
GROUP BY w.id, w.url
ORDER BY failure_rate DESC;

-- Count items in dead letter queue
SELECT 
  w.url,
  COUNT(dlq.id) as dead_letter_count
FROM webhooks.webhooks w
LEFT JOIN webhooks.dead_letter_queue dlq ON w.id = dlq.webhook_id
WHERE dlq.resolved = false
GROUP BY w.url
HAVING COUNT(dlq.id) > 0
ORDER BY dead_letter_count DESC;
```

### Metrics & Alerts

```python
from prometheus_client import Counter, Histogram, Gauge

webhook_deliveries = Counter(
    'webhook_deliveries_total',
    'Total webhook deliveries',
    ['workspace_id', 'event_type', 'status']
)

webhook_delivery_time = Histogram(
    'webhook_delivery_duration_seconds',
    'Webhook delivery time',
    ['event_type']
)

webhook_failures = Counter(
    'webhook_failures_total',
    'Failed webhook deliveries',
    ['workspace_id', 'event_type', 'error_type']
)

dead_letter_queue_size = Gauge(
    'webhook_dead_letter_queue_size',
    'Dead letter queue size',
    ['workspace_id']
)
```

### Alerting Rules

```yaml
groups:
  - name: webhooks
    rules:
      - alert: WebhookHighFailureRate
        expr: |
          (
            rate(webhook_failures_total[5m]) /
            rate(webhook_deliveries_total[5m])
          ) > 0.1  # > 10% failure rate
        for: 10m
        annotations:
          summary: "Webhook failure rate > 10%"

      - alert: WebhookLongDelay
        expr: webhook_delivery_duration_seconds > 30
        for: 5m
        annotations:
          summary: "Webhook delivery > 30 seconds"

      - alert: DeadLetterQueueBuildup
        expr: webhook_dead_letter_queue_size > 100
        for: 1h
        annotations:
          summary: "Dead letter queue > 100 items"
```

---

## Part 8: Testing Webhooks

### Webhook Testing Tool

```bash
#!/bin/bash
# test-webhook.sh - Test webhook delivery locally

WEBHOOK_ID=$1
TOKEN=$2

if [ -z "$WEBHOOK_ID" ] || [ -z "$TOKEN" ]; then
  echo "Usage: bash test-webhook.sh <webhook_id> <bearer_token>"
  exit 1
fi

echo "Testing webhook: $WEBHOOK_ID"

# Test delivery
curl -X POST "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID/test" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  | jq .

# Get recent deliveries
curl -s "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID/deliveries?limit=5" \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.data[] | {id, event_type, http_status, response_time_ms, sent_at}'
```

### Mock Webhook Server

```python
# tools/mock-webhook-server.py

from fastapi import FastAPI, Header, Request
import json
import hmac
import hashlib

app = FastAPI()

@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_arada_signature: str = Header(None),
    x_arada_event_type: str = Header(None),
):
    """Mock webhook endpoint for testing."""
    body = await request.body()
    payload = json.loads(body)
    
    print(f"\n📨 Webhook Received")
    print(f"Event Type: {x_arada_event_type}")
    print(f"Signature: {x_arada_signature}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    return {"status": "received"}

# Run: uvicorn mock-webhook-server:app --port 8001
```

---

## Part 9: Best Practices

### Webhook Design

1. **Idempotent**: Use `event_id` to deduplicate retries
2. **Timeout**: Set webhook timeouts to 30 seconds
3. **Retry**: Implement exponential backoff (1m, 2m, 4m, 8m, 16m)
4. **Signature**: Always verify HMAC-SHA256 signature
5. **Async**: Respond immediately with 202 Accepted

### Consumer Implementation

```python
@app.post("/webhooks/arada")
async def handle_arada_webhook(
    payload: dict,
    x_arada_event_id: str = Header(),
    x_arada_signature: str = Header(),
):
    # 1. Verify signature
    if not verify_signature(payload, x_arada_signature):
        return {"error": "Invalid signature"}, 401
    
    # 2. Deduplicate by event_id
    if await event_already_processed(x_arada_event_id):
        return {"status": "already_processed"}, 200
    
    # 3. Queue async processing
    await queue_background_job("process_webhook", payload)
    
    # 4. Return immediately
    return {"status": "accepted"}, 202
```

---

## References

- Webhook Standards: https://www.w3.org/TR/webhooks/
- HMAC-SHA256: https://tools.ietf.org/html/rfc2104
- Slack Webhooks: https://api.slack.com/messaging/webhooks
- Discord Webhooks: https://discord.com/developers/docs/resources/webhook

---

**See also**: [MONITORING.md](../monitoring/MONITORING.md), [SECURITY.md](../security/SECURITY.md)
