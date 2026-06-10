# Arada Webhook Integrations — Quick Setup Guide

Enable real-time notifications to Slack, Discord, custom APIs, and more.

## Prerequisites

- Arada API running (http://127.0.0.1:8000)
- PostgreSQL with migrations applied
- Bearer token for API access

## Step 1: Initialize Webhook Schema

```bash
# Apply webhook database migration
psql -h 127.0.0.1 -U arada -d arada -f infra/webhooks/init.sql

# Verify
psql -h 127.0.0.1 -U arada -d arada -c "SELECT * FROM webhooks.webhooks LIMIT 1;"
```

Expected output: `(0 rows)` — table is empty and ready.

## Step 2: Create Your First Webhook

### Slack Example

```bash
WORKSPACE_ID="ws_xxx"  # Your workspace ID
TOKEN="your_bearer_token"

# Create webhook
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
    "events": ["job.completed", "publish.success", "publish.failed"],
    "active": true,
    "retry_max_attempts": 5,
    "metadata": {
      "service": "slack",
      "channel": "#arada-alerts"
    }
  }' | jq .
```

Response:
```json
{
  "id": "wh_7f8g9h0i1j2k3l4m",
  "url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
  "signing_secret": "whsec_1234567890abcdef",
  "created_at": "2026-06-10T14:30:00Z"
}
```

### Discord Example

```bash
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://discord.com/api/webhooks/YOUR/WEBHOOK",
    "events": ["job.completed", "job.failed"],
    "active": true,
    "metadata": {
      "service": "discord",
      "channel": "arada-alerts"
    }
  }' | jq .
```

### Custom API Webhook

```bash
curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/webhooks/arada",
    "events": ["job.completed", "content.scored", "publish.success"],
    "active": true,
    "timeout_seconds": 30,
    "retry_max_attempts": 5
  }' | jq .
```

## Step 3: Test Webhook Delivery

```bash
WEBHOOK_ID="wh_7f8g9h0i1j2k3l4m"

# Send test webhook
curl -X POST "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID/test" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Response should be:
# {
#   "status": "sent",
#   "http_code": 200,
#   "response_time_ms": 234
# }
```

## Step 4: List and Manage Webhooks

```bash
# List all webhooks
curl "http://127.0.0.1:8000/webhooks?active=true" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Get webhook details
curl "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Update webhook
curl -X PATCH "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "events": ["job.completed", "publish.success"],
    "active": true
  }' | jq .

# Delete webhook
curl -X DELETE "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## Step 5: Monitor Webhook Deliveries

```bash
# View recent deliveries
curl "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID/deliveries?limit=10" \
  -H "Authorization: Bearer $TOKEN" | jq .

# View failed deliveries
curl "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID/deliveries?status=failed" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {id, event_type, http_status, error_message}'

# Retry a failed delivery
DELIVERY_ID="wd_xyz"
curl -X POST "http://127.0.0.1:8000/webhooks/deliveries/$DELIVERY_ID/retry" \
  -H "Authorization: Bearer $TOKEN" | jq .

# View dead letter queue
curl "http://127.0.0.1:8000/webhooks/dead-letters" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Step 6: Handle Webhooks in Your Application

### Node.js / Express Example

```javascript
// routes/webhooks.js

const crypto = require('crypto');

function verifySignature(payload, signature, secret) {
  const expectedSignature = 'sha256=' + crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(payload))
    .digest('hex');
  
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expectedSignature)
  );
}

app.post('/webhooks/arada', (req, res) => {
  const signature = req.headers['x-arada-signature'];
  const eventId = req.headers['x-arada-event-id'];
  const eventType = req.headers['x-arada-event-type'];
  
  // Verify signature
  if (!verifySignature(req.body, signature, process.env.ARADA_WEBHOOK_SECRET)) {
    return res.status(401).json({ error: 'Invalid signature' });
  }
  
  // Deduplicate by event ID (check database)
  if (await isEventProcessed(eventId)) {
    return res.json({ status: 'already_processed' });
  }
  
  // Queue for async processing
  await queue.add('process-webhook', {
    eventId,
    eventType,
    payload: req.body
  });
  
  // Return immediately
  res.status(202).json({ status: 'accepted' });
});

// Handle webhook in background
queue.process('process-webhook', async (job) => {
  const { eventType, payload } = job.data;
  
  switch (eventType) {
    case 'job.completed':
      await handleJobCompleted(payload);
      break;
    case 'publish.success':
      await handlePublishSuccess(payload);
      break;
    case 'job.failed':
      await handleJobFailed(payload);
      break;
  }
});
```

### Python / FastAPI Example

```python
# routers/webhooks.py

import hmac
import hashlib
from fastapi import APIRouter, Header, Request

router = APIRouter()

def verify_signature(payload: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

@router.post("/webhooks/arada")
async def handle_arada_webhook(
    request: Request,
    x_arada_signature: str = Header(None),
    x_arada_event_id: str = Header(None),
    x_arada_event_type: str = Header(None),
):
    """Receive webhook from Arada."""
    
    body = await request.body()
    payload = await request.json()
    
    # 1. Verify signature
    if not verify_signature(
        body.decode(),
        x_arada_signature,
        os.getenv("ARADA_WEBHOOK_SECRET")
    ):
        return {"error": "Invalid signature"}, 401
    
    # 2. Deduplicate
    if await event_cache.get(x_arada_event_id):
        return {"status": "already_processed"}, 200
    
    # 3. Queue async
    await queue.enqueue(
        "process_webhook",
        x_arada_event_type,
        payload
    )
    
    # 4. Return immediately
    return {"status": "accepted"}, 202

async def process_webhook(event_type: str, payload: dict):
    """Process webhook in background."""
    
    if event_type == "job.completed":
        await handle_job_completed(payload)
    elif event_type == "publish.success":
        await handle_publish_success(payload)
    elif event_type == "job.failed":
        await handle_job_failed(payload)
```

## Step 7: Setup Slack Integration

### Create Slack Webhook

1. Go to https://api.slack.com/apps
2. Create a new app
3. Enable "Incoming Webhooks"
4. Click "Add New Webhook to Workspace"
5. Select channel → Authorize
6. Copy webhook URL

### Register with Arada

```bash
SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$SLACK_WEBHOOK\",
    \"events\": [\"job.completed\", \"publish.success\", \"publish.failed\"],
    \"active\": true,
    \"metadata\": {
      \"service\": \"slack\",
      \"channel\": \"#arada-alerts\",
      \"description\": \"Job completion alerts\"
    }
  }" | jq .
```

Now Arada will send messages to Slack when jobs complete!

## Step 8: Setup Discord Integration

### Create Discord Webhook

1. Right-click channel → Edit Channel
2. Go to "Integrations"
3. Click "Webhooks" → "New Webhook"
4. Name it "Arada"
5. Copy webhook URL

### Register with Arada

```bash
DISCORD_WEBHOOK="https://discord.com/api/webhooks/YOUR/WEBHOOK"

curl -X POST http://127.0.0.1:8000/webhooks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"url\": \"$DISCORD_WEBHOOK\",
    \"events\": [\"job.completed\", \"job.failed\"],
    \"active\": true,
    \"metadata\": {
      \"service\": \"discord\",
      \"channel\": \"arada-alerts\"
    }
  }" | jq .
```

## Troubleshooting

### Webhook not firing

```bash
# Check if webhook is active
curl "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.active'

# Verify webhook is registered for event type
curl "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.events'

# Check event is being emitted
psql -c "SELECT COUNT(*) FROM webhooks.events WHERE type = 'job.completed' AND created_at > NOW() - INTERVAL '1 hour';"
```

### Webhook receiving 4xx/5xx errors

```bash
# View error details
curl "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID/deliveries?status=failed&limit=5" \
  -H "Authorization: Bearer $TOKEN" | jq '.data[] | {http_status, error_message, response_time_ms}'

# Common issues:
# - 401: Webhook endpoint requires authentication
# - 403: IP not whitelisted
# - 404: Endpoint doesn't exist
# - 409: Signature verification failed
```

### Dead letter queue buildup

```bash
# Check dead letter queue size
curl "http://127.0.0.1:8000/webhooks/dead-letters?resolved=false" \
  -H "Authorization: Bearer $TOKEN" | jq '.total'

# Fix webhook URL
curl -X PATCH "http://127.0.0.1:8000/webhooks/$WEBHOOK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"url": "https://new-endpoint.com/webhook"}'

# Resolve dead letters
curl -X POST "http://127.0.0.1:8000/webhooks/dead-letters/$DLQ_ID/resolve" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"resolution_notes": "Endpoint fixed, ready for retry"}'

# Retry all
curl -X POST "http://127.0.0.1:8000/webhooks/dead-letters/retry-all" \
  -H "Authorization: Bearer $TOKEN"
```

## Reference

- Full guide: [WEBHOOKS.md](WEBHOOKS.md)
- Event types: [WEBHOOKS.md#part-1](WEBHOOKS.md#part-1-database-schema)
- Security: [WEBHOOKS.md#part-6](WEBHOOKS.md#part-6-webhook-security)
- Testing: [WEBHOOKS.md#part-8](WEBHOOKS.md#part-8-testing-webhooks)
