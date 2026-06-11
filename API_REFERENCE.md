# Arada Intelligence OS — API Reference

**Version:** 1.0.0  
**Base URL:** `http://localhost:8000` (development) or `https://api.arada.fun` (production)  
**Authentication:** Bearer Token (JWT)  

---

## 🔐 Authentication

All endpoints require a bearer token:

```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/endpoint
```

### Get Token
```bash
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password"
}

# Returns:
{
  "access_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

## 📚 API Endpoints

### ML Services

#### 🧠 Sentiment Analysis

**Analyze sentiment of text**

```bash
POST /ml/sentiment/analyze
Content-Type: application/json
Authorization: Bearer <token>

{
  "text": "This product is amazing!",
  "model_key": "huggingface:distilbert-base-uncased-finetuned-sst-2-english"
}

# Returns:
{
  "data": {
    "sentiment": "positive",
    "confidence": 0.95,
    "score": 0.92,
    "explanation": "Positive sentiment detected"
  },
  "status": "success"
}
```

**Parameters:**
- `text` (string, required): Text to analyze
- `model_key` (string, optional): Model identifier
  - `huggingface:model-name` — HuggingFace model
  - `ollama:model-name` — Ollama local model
  - Default: `huggingface:distilbert-base-uncased-finetuned-sst-2-english`

**Response:**
- `sentiment` — `positive`, `negative`, or `neutral`
- `confidence` — 0.0-1.0 confidence score
- `score` — -1.0 to 1.0 sentiment intensity
- `explanation` — Reasoning for prediction

---

#### 📈 Forecasting

**Generate time-series forecast**

```bash
POST /ml/forecast/predict
Content-Type: application/json

{
  "historical_values": [0.1, 0.15, 0.2, 0.25, 0.3],
  "forecast_days": 7,
  "method": "exponential_smoothing"
}

# Returns:
{
  "data": {
    "forecast": [0.32, 0.34, 0.36, 0.38, 0.40, 0.42, 0.44],
    "confidence_interval": [
      [0.28, 0.36],
      [0.30, 0.38],
      ...
    ],
    "model": "exponential_smoothing",
    "rmse": 0.04,
    "trend": "up"
  },
  "status": "success"
}
```

**Parameters:**
- `historical_values` (array, required): Past values for forecasting
- `forecast_days` (integer, optional): Days to forecast (default: 7)
- `method` (string, optional): `simple`, `arima`, `exponential_smoothing` (default: `simple`)

**Response:**
- `forecast` — Predicted values
- `confidence_interval` — 95% CI for each prediction
- `model` — Model used
- `rmse` — Root mean square error
- `trend` — `up`, `down`, or `stable`

---

#### 🎯 Segmentation

**Cluster entities into segments**

```bash
POST /ml/segmentation/cluster
Content-Type: application/json

{
  "features": [
    [0.1, 0.2, 0.3],
    [0.15, 0.25, 0.35],
    [0.9, 0.8, 0.7],
    [0.85, 0.75, 0.65]
  ],
  "entity_ids": ["user1", "user2", "user3", "user4"],
  "n_clusters": 2,
  "method": "kmeans"
}

# Returns:
{
  "data": {
    "segments": [
      {
        "segment_id": 0,
        "entities": ["user1", "user2"],
        "size": 2
      },
      {
        "segment_id": 1,
        "entities": ["user3", "user4"],
        "size": 2
      }
    ],
    "centroids": [[0.125, 0.225, 0.325], [0.875, 0.775, 0.675]],
    "silhouette_score": 0.92,
    "method": "kmeans",
    "n_clusters": 2
  },
  "status": "success"
}
```

---

#### 💡 Recommendations

**Generate content recommendations**

```bash
POST /ml/recommendations/generate
Content-Type: application/json

{
  "user_id": "user123",
  "user_features": [0.5, 0.6, 0.4],
  "content_items": [
    {"id": "content1", "features": [0.5, 0.6, 0.4]},
    {"id": "content2", "features": [0.9, 0.8, 0.7]},
    {"id": "content3", "features": [0.1, 0.2, 0.3]}
  ],
  "method": "content_based",
  "top_k": 2
}

# Returns:
{
  "data": {
    "recommendations": [
      {
        "item_id": "content1",
        "score": 0.98,
        "reason": "Similar to user interests"
      },
      {
        "item_id": "content3",
        "score": 0.45,
        "reason": "Similar to user interests"
      }
    ],
    "method": "content_based",
    "user_id": "user123"
  }
}
```

---

### Webhooks

#### 📬 Create Subscription

**Subscribe to events**

```bash
POST /webhooks/subscriptions
Content-Type: application/json

{
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://your-domain.com/webhooks/events",
  "events": [
    "content.ingested",
    "job.completed",
    "publish.success"
  ],
  "headers": {
    "Authorization": "Bearer your-webhook-token"
  }
}

# Returns:
{
  "id": "660e8400-e29b-41d4-a716-446655440000",
  "url": "https://your-domain.com/webhooks/events",
  "events": ["content.ingested", "job.completed", "publish.success"],
  "secret": "whsec_1234567890abcdef",
  "status": "active"
}
```

**Available Events:**
- `content.ingested` — New content fetched
- `content.scored` — Content scoring complete
- `job.created` — Job created
- `job.completed` — Job finished
- `job.failed` — Job failed
- `publish.success` — Video published
- `publish.failed` — Publishing failed
- `user.created` — New user created
- `workspace.upgraded` — Plan upgraded

---

#### 📨 Webhook Payload Format

```json
{
  "event_type": "content.ingested",
  "timestamp": "2026-06-11T14:30:00Z",
  "data": {
    "content_id": "123e4567-e89b-12d3-a456-426614174000",
    "title": "New Article",
    "url": "https://example.com/article"
  }
}
```

**Signature Header:**
```
X-Arada-Signature: sha256=abcdef1234567890...
```

**Verify Signature (Python):**
```python
import hmac
import hashlib

def verify_webhook(payload: bytes, secret: str, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

---

#### 📋 List Subscriptions

```bash
GET /webhooks/subscriptions?workspace_id=550e8400-e29b-41d4-a716-446655440000

# Returns:
{
  "subscriptions": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440000",
      "url": "https://your-domain.com/webhooks",
      "events": ["content.ingested", "job.completed"],
      "active": true,
      "created_at": "2026-06-10T10:00:00Z",
      "last_triggered_at": "2026-06-11T14:30:00Z"
    }
  ],
  "count": 1
}
```

---

#### 🔄 Retry Failed Delivery

```bash
POST /webhooks/deliveries/{delivery_id}/retry?workspace_id=550e8400-e29b-41d4-a716-446655440000

# Returns:
{
  "status": "queued"
}
```

---

### Analytics

#### 📊 Create Custom Metric

```bash
POST /analytics/metrics
Content-Type: application/json

{
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "engagement_rate",
  "definition": "SELECT COUNT(*) FROM content.normalized_items WHERE engagement > 0",
  "metric_type": "count",
  "dimension": "daily"
}

# Returns:
{
  "metric_id": "770e8400-e29b-41d4-a716-446655440000",
  "status": "created"
}
```

---

#### 📈 Get Metric Data

```bash
GET /analytics/metrics/{metric_id}/data?workspace_id=550e8400-e29b-41d4-a716-446655440000&start_date=2026-06-01&end_date=2026-06-11

# Returns:
{
  "metric": {
    "metric_name": "engagement_rate",
    "value": 0.18,
    "dimension": "daily",
    "data_points": [
      {"date": "2026-06-01", "value": 0.15},
      {"date": "2026-06-02", "value": 0.18},
      ...
    ],
    "trend": "up",
    "computed_at": "2026-06-11T14:30:00Z"
  }
}
```

---

#### 👥 Create Cohort

```bash
POST /analytics/cohorts
Content-Type: application/json

{
  "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "power_users",
  "criteria": {
    "engagement_rate": {">": 0.1},
    "source_type": {"in": ["rss", "telegram"]},
    "created_after": "2026-05-01"
  }
}

# Returns:
{
  "cohort_id": "880e8400-e29b-41d4-a716-446655440000",
  "status": "created"
}
```

---

#### 🎯 Predict Churn

```bash
GET /analytics/predictions/churn?workspace_id=550e8400-e29b-41d4-a716-446655440000&user_id=user123

# Returns:
{
  "prediction": {
    "churn_probability": 0.75,
    "confidence": 0.92,
    "risk_factors": [
      "inactive_7d",
      "low_engagement"
    ],
    "predicted_churn_date": "2026-07-11",
    "recommended_action": "Send re-engagement email"
  }
}
```

---

#### 💰 Predict LTV

```bash
GET /analytics/predictions/ltv?workspace_id=550e8400-e29b-41d4-a716-446655440000&user_id=user123

# Returns:
{
  "prediction": {
    "ltv": 1250.50,
    "confidence": 0.78,
    "factors": {
      "avg_monthly_value": 125.05,
      "estimated_months": 10,
      "growth_trend": 1.05
    }
  }
}
```

---

## 🔍 Common Response Formats

### Success Response
```json
{
  "data": {},
  "status": "success"
}
```

### Error Response
```json
{
  "detail": "Error message",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Paginated Response
```json
{
  "items": [],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

---

## 📊 Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad Request |
| `401` | Unauthorized |
| `403` | Forbidden |
| `404` | Not Found |
| `422` | Validation Error |
| `500` | Internal Server Error |

---

## 🔗 Interactive Documentation

**Swagger UI:** `GET /docs`  
**ReDoc:** `GET /redoc`  
**OpenAPI Schema:** `GET /openapi.json`

---

## 📚 Rate Limiting

| Tier | Requests/minute | Burst |
|------|-----------------|-------|
| Free | 60 | 10 |
| Creator | 300 | 50 |
| Agency | 1000 | 200 |
| Enterprise | Unlimited | Unlimited |

---

## 💾 Webhook Retry Schedule

Failed deliveries retry with exponential backoff:

1. **Attempt 1:** Immediate
2. **Attempt 2:** 1 minute
3. **Attempt 3:** 5 minutes
4. **Attempt 4:** 30 minutes
5. **Attempt 5:** 24 hours

After 5 failed attempts, the event moves to **dead letter queue**.

---

## 🎓 Example Workflows

### Workflow 1: Analyze Content & Emit Event

```python
import requests

# 1. Analyze sentiment
response = requests.post(
    "http://localhost:8000/ml/sentiment/analyze",
    json={"text": "Great content!"},
    headers={"Authorization": "Bearer token"}
)
sentiment = response.json()["data"]["sentiment"]

# 2. Emit webhook event
requests.post(
    "http://localhost:8000/webhooks/events",
    json={
        "event_type": "content.scored",
        "entity_id": "content123",
        "payload": {"sentiment": sentiment}
    },
    headers={"Authorization": "Bearer token"}
)
```

### Workflow 2: Predict Churn & Create Cohort

```python
# 1. Predict churn for all users
churn = requests.get(
    f"http://localhost:8000/analytics/predictions/churn?user_id=user123",
    headers={"Authorization": "Bearer token"}
).json()

# 2. Create cohort of at-risk users
requests.post(
    "http://localhost:8000/analytics/cohorts",
    json={
        "name": "at_risk",
        "criteria": {"churn_probability": {">": 0.7}}
    },
    headers={"Authorization": "Bearer token"}
)
```

---

**Version:** 1.0.0  
**Last Updated:** 2026-06-11  
**Status:** ✅ Production Ready
