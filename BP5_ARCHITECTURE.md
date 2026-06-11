# Arada Intelligence OS — BP5 Feature Architecture Design

**Date:** 2026-06-11  
**Status:** Design Phase Complete  
**Scope:** ML Services, Webhooks, Advanced Analytics

---

## 🎯 Overview

Three interconnected BP5 features providing intelligence, integrations, and analytics:

1. **ML Services (BP5.4)** — 6 specialized microservices for NLP, forecasting, segmentation, sentiment, recommendations, and model management
2. **Webhooks (BP5.3)** — Event-driven HTTP integrations with retry, signatures, and templates
3. **Advanced Analytics (BP5.5)** — Complex aggregations, cohort analysis, attribution, and predictive KPIs

---

## 1. ML SERVICES (BP5.4) — Content Intelligence Microservices

### Module Structure

```
api/ml/
├── __init__.py
├── base_service.py           # Abstract base for all ML services
├── llm_service.py            # LLMService (Ollama/OpenAI/Anthropic)
├── forecast_service.py       # ForecastService (time-series ARIMA/Prophet)
├── segmentation_service.py   # SegmentationService (K-means clustering)
├── sentiment_service.py      # SentimentService (transformers/NLP)
├── recommendation_service.py # RecommendationService (collaborative filtering)
└── model_service.py          # ModelService (training/versioning/deployment)

api/workers/
└── ml_worker.py              # ML job processor (consumes Redis queue)

api/routers/
└── ml.py                     # REST API endpoints (/ml/predictions, /ml/models, etc.)
```

### Database Schema Addition

```sql
-- Migration: 010_ml_services.sql

CREATE SCHEMA ml;

-- Models registry (versioned)
CREATE TABLE ml.models (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    name            text        NOT NULL,  -- "sentiment-v1", "forecast-daily", etc.
    type            text        NOT NULL,  -- 'llm'|'forecast'|'segmentation'|'sentiment'|'recommendation'
    model_key       text,                   -- 'ollama:neural-chat', 'openai:gpt-4', 'sklearn:kmeans'
    version         integer     NOT NULL DEFAULT 1,
    status          text        NOT NULL DEFAULT 'active',  -- 'active'|'deprecated'|'training'
    config          jsonb       NOT NULL,  -- hyperparams, thresholds, etc.
    metrics         jsonb,                  -- accuracy, f1, mae, etc. (from validation)
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name, version)
);

-- Predictions (cacheable results)
CREATE TABLE ml.predictions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    content_id      uuid        NOT NULL REFERENCES content.normalized_items(id) ON DELETE CASCADE,
    model_id        uuid        NOT NULL REFERENCES ml.models(id) ON DELETE CASCADE,
    prediction_type text        NOT NULL,  -- 'sentiment'|'trend'|'recommendation'|'segment'
    prediction      jsonb       NOT NULL,  -- {"sentiment": "positive", "confidence": 0.92, ...}
    created_at      timestamptz NOT NULL DEFAULT now(),
    INDEX (workspace_id, created_at),
    INDEX (content_id, prediction_type)
);

-- Feature store (computed features for ML)
CREATE TABLE ml.feature_store (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    entity_type     text        NOT NULL,  -- 'user'|'content'|'source'
    entity_id       uuid        NOT NULL,
    features        jsonb       NOT NULL,  -- {"engagement_rate": 0.15, "follower_growth": 100, ...}
    computed_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, entity_type, entity_id)
);

-- Training jobs
CREATE TABLE ml.training_jobs (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    model_name      text        NOT NULL,
    status          text        NOT NULL DEFAULT 'pending',  -- 'pending'|'running'|'completed'|'failed'
    training_params jsonb,
    validation_metrics jsonb,
    error_message   text,
    started_at      timestamptz,
    completed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

### API Endpoints

```python
# api/routers/ml.py

# LLM Service
POST   /ml/llm/generate
GET    /ml/llm/models
POST   /ml/llm/models/{model_key}

# Forecasting
POST   /ml/forecast/predict
GET    /ml/forecast/results
POST   /ml/forecast/train

# Segmentation
POST   /ml/segmentation/cluster
GET    /ml/segmentation/segments
PUT    /ml/segmentation/segments/{segment_id}

# Sentiment Analysis
POST   /ml/sentiment/analyze
GET    /ml/sentiment/bulk-results

# Recommendations
POST   /ml/recommendations/generate
GET    /ml/recommendations/similar-content

# Model Management
GET    /ml/models
GET    /ml/models/{model_id}
POST   /ml/models/{model_id}/validate
DELETE /ml/models/{model_id}

# Training Jobs
GET    /ml/training-jobs
POST   /ml/training-jobs
GET    /ml/training-jobs/{job_id}
```

### Data Flow Diagram

```
Content Item (normalized_items)
    ↓
ContentWorker triggers ML pipeline
    ↓
POST /ml/sentiment/analyze → MLWorker consumes from Redis queue
    ↓
SentimentService.predict()
    ├─ Load model from ml.models
    ├─ Transform features from feature_store
    ├─ Call transformers library or OpenAI API
    └─ Write prediction to ml.predictions
    ↓
Prediction cached in Redis (TTL: 7 days)
    ↓
Metadata workflow can reference prediction for job decisions
```

### Service Signatures

```python
# api/ml/base_service.py
class MLServiceBase(ABC):
    @abstractmethod
    async def predict(self, input_data: dict) -> dict:
        """Prediction logic."""
    
    @abstractmethod
    async def train(self, training_data: list[dict]) -> dict:
        """Training logic. Returns metrics."""

# api/ml/sentiment_service.py
class SentimentService(MLServiceBase):
    async def predict(self, text: str, model_key: str = "ollama:neural-chat") -> dict:
        """
        Returns: {
            "sentiment": "positive|negative|neutral",
            "confidence": 0.95,
            "score": -1 to 1,
            "explanation": "text"
        }
        """
    
    async def train(self, labeled_texts: list[tuple[str, str]]) -> dict:
        """Fine-tune model on labeled data."""

# api/ml/forecast_service.py
class ForecastService(MLServiceBase):
    async def predict(self, 
        historical_values: list[float],
        forecast_days: int = 7
    ) -> dict:
        """
        Returns: {
            "forecast": [0.15, 0.18, 0.20, ...],
            "confidence_interval": [[0.12, 0.18], ...],
            "model": "ARIMA(1,1,1)",
            "rmse": 0.04
        }
        """
```

### Configuration

```env
# ML Service Config
ML_ENABLED=true
LLM_PROVIDER=ollama              # ollama|openai|anthropic
OLLAMA_MODEL=neural-chat:latest
OPENAI_API_KEY=sk-...            # if using OpenAI
ANTHROPIC_API_KEY=sk-...         # if using Anthropic

ML_MODEL_CACHE_TTL=604800        # 7 days
ML_FEATURE_STORE_REFRESH_INTERVAL=86400  # 1 day
ML_MAX_TRAINING_WORKERS=2
```

### Error Handling

```python
class MLServiceError(Exception): pass
class MLModelNotFound(MLServiceError): pass
class MLPredictionFailed(MLServiceError): pass
class MLTrainingFailed(MLServiceError): pass
```

---

## 2. WEBHOOKS (BP5.3) — Event-Driven HTTP Integrations

### Module Structure

```
api/webhooks/
├── __init__.py
├── models.py                 # Webhook config/event models
├── handlers.py               # Event-to-webhook routing logic
├── signatures.py             # HMAC-SHA256 signing
└── templates.py              # Integration templates (Slack, Discord, etc.)

api/routers/
└── webhooks.py               # REST API (/webhooks/subscriptions, etc.)

api/workers/
└── webhook_worker.py         # Webhook delivery worker (retry logic)
```

### Database Schema Addition

```sql
-- Migration: 011_webhooks.sql

CREATE SCHEMA webhooks;

-- Webhook subscriptions
CREATE TABLE webhooks.subscriptions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    user_id         uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    url             text        NOT NULL,
    events          text[]      NOT NULL,  -- ['content.ingested', 'job.completed', ...]
    secret          text        NOT NULL,  -- HMAC signing key
    headers         jsonb,                  -- custom headers
    active          boolean     NOT NULL DEFAULT true,
    retry_policy    jsonb       NOT NULL DEFAULT '{"max_attempts": 5, "backoff": "exponential"}',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    last_triggered_at timestamptz
);

-- Event queue (durable delivery tracking)
CREATE TABLE webhooks.events (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    event_type      text        NOT NULL,  -- 'content.ingested', 'job.completed', etc.
    entity_id       uuid,                   -- reference to content/job/etc.
    payload         jsonb       NOT NULL,
    occurred_at     timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Delivery attempts (audit trail)
CREATE TABLE webhooks.deliveries (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id uuid        NOT NULL REFERENCES webhooks.subscriptions(id) ON DELETE CASCADE,
    event_id        uuid        NOT NULL REFERENCES webhooks.events(id) ON DELETE CASCADE,
    status          text        NOT NULL,  -- 'pending'|'success'|'retry'|'failed'
    http_status     integer,
    response_body   text,
    error_message   text,
    attempt_number  integer     NOT NULL DEFAULT 1,
    next_retry_at   timestamptz,
    completed_at    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    INDEX (subscription_id, status),
    INDEX (status, next_retry_at)
);

-- Dead letter queue (permanently failed events)
CREATE TABLE webhooks.dead_letters (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id uuid        NOT NULL REFERENCES webhooks.subscriptions(id) ON DELETE CASCADE,
    event_id        uuid        REFERENCES webhooks.events(id) ON DELETE SET NULL,
    reason          text        NOT NULL,  -- 'max_retries_exceeded', 'invalid_url', etc.
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);
```

### API Endpoints

```python
# api/routers/webhooks.py

# Subscriptions
POST   /webhooks/subscriptions        # Create subscription
GET    /webhooks/subscriptions        # List subscriptions
GET    /webhooks/subscriptions/{id}   # Get subscription
PUT    /webhooks/subscriptions/{id}   # Update subscription
DELETE /webhooks/subscriptions/{id}   # Deactivate subscription

# Events (view-only, system-generated)
GET    /webhooks/events               # List events (filterable by type, date)
GET    /webhooks/events/{id}          # Get event details

# Delivery tracking
GET    /webhooks/deliveries           # List delivery attempts
GET    /webhooks/deliveries/{id}      # Get delivery details
POST   /webhooks/deliveries/{id}/retry  # Manually retry failed delivery

# Dead letter queue
GET    /webhooks/dead-letters         # List failed-permanently events
POST   /webhooks/dead-letters/{id}/restore  # Move back to pending
```

### Webhook Signature Format

```
Header: X-Arada-Signature
Value: sha256=<hex(HMAC-SHA256(secret, body))>

Example:
X-Arada-Signature: sha256=abcdef123456...

Verification (Python):
import hmac
import hashlib

def verify_signature(payload: bytes, secret: str, signature: str) -> bool:
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Retry Logic

```python
# Exponential backoff with jitter
attempt 1: immediate
attempt 2: 60s (1 min)
attempt 3: 300s (5 min)
attempt 4: 1800s (30 min)
attempt 5: 86400s (24 hours)

# If all fail → move to dead_letters
```

### Integration Templates

```python
# api/webhooks/templates.py

class SlackTemplate:
    """Posts webhook events to Slack channel."""
    def format_message(self, event: dict) -> dict:
        # Returns Slack Block Kit JSON
        
class DiscordTemplate:
    """Posts to Discord webhook."""
    
class StripeTemplate:
    """Creates Stripe usage records for metering."""
    
class GitHubTemplate:
    """Triggers GitHub Actions workflow."""
```

### Event Types Emitted

```
content.ingested          # New content item fetched
content.scored           # Scoring complete
job.created              # Brief/script/render/publish job created
job.claimed              # Worker claimed job
job.completed            # Job finished
job.failed               # Job failed
publish.success          # Video published to platform
publish.failed           # Publishing failed
user.created             # New user in workspace
workspace.upgraded       # Plan upgraded
```

---

## 3. ADVANCED ANALYTICS (BP5.5) — Complex Aggregations & Dashboards

### Module Structure

```
api/analytics/
├── __init__.py
├── metrics.py            # Custom metric calculations
├── cohorts.py            # Cohort analysis
├── attribution.py        # Multi-touch attribution
├── predictions.py        # Predictive KPIs
└── aggregations.py       # Complex SQL aggregations

api/routers/
└── analytics.py          # REST API (/analytics/metrics, /analytics/cohorts, etc.)
```

### Database Schema Addition

```sql
-- Migration: 012_analytics.sql

CREATE SCHEMA analytics;

-- Custom metrics (user-defined KPIs)
CREATE TABLE analytics.custom_metrics (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    name            text        NOT NULL,  -- "engagement_rate", "roi", etc.
    definition      text        NOT NULL,  -- SQL query or formula
    metric_type     text        NOT NULL,  -- 'count'|'sum'|'avg'|'ratio'|'custom'
    dimension       text,                   -- 'daily'|'weekly'|'content'|'source'
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name)
);

-- Metric snapshots (cached aggregations)
CREATE TABLE analytics.metric_snapshots (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    metric_id       uuid        NOT NULL REFERENCES analytics.custom_metrics(id) ON DELETE CASCADE,
    dimension_value text,                   -- '2026-06-11' (if daily), 'source:123' (if by source)
    value           numeric     NOT NULL,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE(metric_id, dimension_value, computed_at::date)
);

-- Cohorts (user segments)
CREATE TABLE analytics.cohorts (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    name            text        NOT NULL,  -- "power-users", "churn-risk", etc.
    definition      jsonb       NOT NULL,  -- {"criteria": {"engagement_rate": {">": 0.1}}, ...}
    members         uuid[]      NOT NULL,  -- user IDs in cohort
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE(workspace_id, name)
);

-- Cohort analytics (performance comparison)
CREATE TABLE analytics.cohort_metrics (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    cohort_id       uuid        NOT NULL REFERENCES analytics.cohorts(id) ON DELETE CASCADE,
    metric_name     text        NOT NULL,  -- 'avg_engagement', 'churn_rate', etc.
    value           numeric,
    computed_at     timestamptz NOT NULL DEFAULT now()
);

-- Attribution (multi-touch credit assignment)
CREATE TABLE analytics.attribution (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    conversion_id   uuid        NOT NULL,  -- job/publish event that converted
    touch_points    jsonb       NOT NULL,  -- [{"event": "content.ingested", "source_id": "...", "credit": 0.3}, ...]
    model           text        NOT NULL,  -- 'first_touch'|'last_touch'|'linear'|'time_decay'|'custom'
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Predictive KPIs (ML-based forecasts)
CREATE TABLE analytics.predictions (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid        NOT NULL REFERENCES auth.workspaces(id) ON DELETE CASCADE,
    kpi_name        text        NOT NULL,  -- 'churn_probability', 'ltv', 'engagement_forecast'
    entity_id       uuid,                   -- user_id, content_id, source_id
    prediction      jsonb       NOT NULL,  -- {"value": 0.75, "confidence": 0.92, ...}
    predicted_date  date        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    INDEX (workspace_id, entity_id, predicted_date)
);
```

### API Endpoints

```python
# api/routers/analytics.py

# Custom Metrics
GET    /analytics/metrics              # List metrics
POST   /analytics/metrics              # Create metric
GET    /analytics/metrics/{id}/data    # Get metric data (with filters)
DELETE /analytics/metrics/{id}         # Delete metric

# Cohort Analysis
GET    /analytics/cohorts              # List cohorts
POST   /analytics/cohorts              # Create cohort (based on criteria)
GET    /analytics/cohorts/{id}/metrics # Cohort performance vs. baseline
PUT    /analytics/cohorts/{id}         # Update cohort

# Attribution
GET    /analytics/attribution          # Multi-touch attribution report
POST   /analytics/attribution/model    # Change attribution model

# Predictions
GET    /analytics/predictions          # Predictive KPI forecasts
GET    /analytics/predictions/churn    # Churn risk predictions
GET    /analytics/predictions/ltv      # Lifetime value predictions

# Dashboard Data
GET    /analytics/dashboard            # All metrics for dashboard (cacheable)
POST   /analytics/dashboard/refresh    # Force recompute
```

### Service Signatures

```python
# api/analytics/metrics.py
class MetricsService:
    async def calculate_metric(
        self, 
        metric_id: uuid, 
        start_date: date, 
        end_date: date,
        dimension: Optional[str] = None,
        filters: Optional[dict] = None
    ) -> dict:
        """
        Returns: {
            "metric_name": "engagement_rate",
            "value": 0.18,
            "dimension": "daily",
            "data_points": [
                {"date": "2026-06-11", "value": 0.20},
                {"date": "2026-06-10", "value": 0.16},
                ...
            ],
            "trend": "up",
            "computed_at": "2026-06-11T14:30:00Z"
        }
        """

# api/analytics/cohorts.py
class CohortService:
    async def create_cohort(
        self,
        workspace_id: uuid,
        name: str,
        criteria: dict
    ) -> dict:
        """
        Criteria example:
        {
            "engagement_rate": {">": 0.1},
            "source_type": {"in": ["rss", "telegram"]},
            "created_after": "2026-05-01"
        }
        
        Returns: list of matching user IDs
        """
    
    async def compare_cohorts(
        self,
        cohort_ids: list[uuid],
        metric_names: list[str]
    ) -> dict:
        """Compare multiple cohorts across metrics."""

# api/analytics/predictions.py
class PredictionService:
    async def predict_churn(self, user_id: uuid) -> dict:
        """
        Returns: {
            "churn_probability": 0.75,
            "confidence": 0.92,
            "risk_factors": ["low_engagement", "inactive_7d"],
            "predicted_churn_date": "2026-07-11"
        }
        """
```

### Caching Strategy

```python
# All metrics cached in Redis with workspace-specific TTL
REDIS_KEY = f"analytics:metric:{metric_id}:{dimension}:{start_date}:{end_date}"
TTL = 3600  # 1 hour, refresh every hour via async job

# Dashboard aggregates cached separately
REDIS_KEY = f"analytics:dashboard:{workspace_id}"
TTL = 300   # 5 minutes (more frequently updated)

# Use background job to pre-compute frequent queries
# Schedule: Every 1 hour for daily metrics, every 24 hours for weekly
```

### Integration with Metabase

```python
# Metabase can query:
# 1. analytics.metric_snapshots (materialized views)
# 2. analytics.cohort_metrics
# 3. analytics.attribution
# 4. analytics.predictions

# Create Metabase questions/dashboards from these tables
# Leverage native SQL to build complex visualizations
```

---

## 📋 Implementation Roadmap

| Phase | Feature | Effort | Timeline |
|-------|---------|--------|----------|
| 1 | Architecture & Design | ✓ Done | - |
| 2 | Code Implementation | In Progress | 3-5 days |
| 2a | ML Services | ~40 hours | Days 1-2 |
| 2b | Webhooks | ~20 hours | Days 2-3 |
| 2c | Analytics | ~30 hours | Days 3-5 |
| 3 | Testing Strategy | ~20 hours | Days 5-6 |
| 4 | Documentation | ~10 hours | Day 6 |

---

## 🔗 Integration Points Summary

```
┌─────────────────────────────────────────────────────────┐
│ FastAPI (Port 8000)                                     │
├─────────────────────────────────────────────────────────┤
│ Existing Routes        │ New ML Routes  │ New Webhooks  │
│ /auth                  │ /ml/sentiment  │ /webhooks     │
│ /content               │ /ml/forecast   │ /events       │
│ /workflow              │ /ml/recommendation             │
│ /media                 │ /ml/models                     │
│ /system/health         │ /analytics/*                   │
└─────────────────────────────────────────────────────────┘
              │
    ┌─────────┼──────────┬────────────┐
    ↓         ↓          ↓            ↓
PostgreSQL  Redis    MinIO      Qdrant
(+3 schemas) (Jobs)   (Models)   (Vectors)
    │         │        │         │
    └────┬────┴────┬───┴─────┬───┘
         ↓         ↓         ↓
    ┌────────────────────────────────┐
    │ Background Workers             │
    ├────────────────────────────────┤
    │ • ContentWorker (existing)      │
    │ • TaskOrchestrator (existing)   │
    │ • PublisherWorker (existing)    │
    │ • MLWorker (NEW)                │
    │ • WebhookWorker (NEW)           │
    │ • AnalyticsWorker (NEW)         │
    └────────────────────────────────┘
         │
    [Ollama, OpenAI, Anthropic]
    [External APIs: Slack, Discord, etc.]
```

---

## ✅ Next Phase: Code Implementation

Ready to build:
1. Database migrations (3 files)
2. ML service modules (7 files)
3. Webhook handler modules (4 files)
4. Analytics service modules (5 files)
5. Router endpoints (3 files)
6. Worker processors (3 files)

Total: ~22 new files, ~3,500 lines of Python code.

