# Arada Intelligence OS — System Architecture

**Version:** 1.0.0  
**Date:** 2026-06-11  
**Status:** Production Ready  

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Client Applications                          │
│         (Web, Mobile, Webhooks, Third-party APIs)              │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS / REST / WebSocket
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (Nginx/Caddy)                   │
│              ▼ Authentication (JWT + RBAC)                     │
│              ▼ Rate Limiting (60-unlimited req/min)            │
└────────────────────────┬────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
┌───────────────┐ ┌───────────────┐ ┌─────────────────┐
│  FastAPI      │ │  ML Workers   │ │  Webhook        │
│  (Port 8000)  │ │  (Async)      │ │  Workers        │
└───────────────┘ └───────────────┘ └─────────────────┘
     │ Routers:         │ Jobs:          │ Jobs:
     │ • /auth          │ • Sentiment    │ • HTTP Delivery
     │ • /content       │ • Forecast     │ • Retry Logic
     │ • /workflow      │ • Segment      │ • Dead Letter
     │ • /ml            │ • Training     │
     │ • /webhooks      │                │
     │ • /analytics     │                │
     │                  │                │
     └──────────────────┼────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌────────────────┐ ┌────────────────┐ ┌──────────────┐
│  PostgreSQL    │ │    Redis       │ │   MinIO      │
│  (Multi-DB)    │ │  (Caching)     │ │  (Storage)   │
│                │ │  (Job Queue)   │ │              │
│  9 Schemas:    │ │                │ │              │
│  • auth        │ │  TTLs:         │ │ Buckets:     │
│  • content     │ │  • ML: 7d      │ │ • videos     │
│  • workflow    │ │  • Metrics: 1h │ │ • assets     │
│  • media       │ │  • Dashboard:5m│ │ • logs       │
│  • ml          │ │                │ │              │
│  • webhooks    │ │                │ │              │
│  • analytics   │ │                │ │              │
│  • revenue     │ │                │ │              │
│  • system      │ │                │ │              │
└────────────────┘ └────────────────┘ └──────────────┘
        │
        ├── Qdrant (Vector DB, 6333)
        ├── Ollama (LLM, 11434)
        └── Monitoring (Prometheus 9090, Grafana 3001, Metabase 3000)
```

---

## 📊 Data Model

### Schema: `auth` — Authentication & Multi-Tenancy

```sql
workspaces
├── id (uuid, primary key)
├── name (text)
├── plan (enum: free|creator|agency|enterprise)
├── owner_id (uuid → users)
└── created_at

users
├── id (uuid, primary key)
├── workspace_id (uuid → workspaces)
├── email (text, unique within workspace)
├── name (text)
├── role (enum: owner|admin|editor|publisher|analyst|viewer)
├── password_hash (text)
└── created_at

api_keys
├── id (uuid)
├── user_id (uuid → users)
├── key_hash (text, hashed)
├── scopes (text[])
└── created_at

roles
├── id (uuid)
├── workspace_id (uuid → workspaces)
├── name (text)
└── permissions (jsonb)
```

### Schema: `content` — Content Management

```sql
sources
├── id (uuid, primary key)
├── workspace_id (uuid → workspaces)
├── source_type (enum: rss|telegram|news|custom)
├── url (text)
├── refresh_interval (interval)
├── reputation_score (numeric)
└── created_at

raw_items
├── id (uuid)
├── source_id (uuid → sources)
├── raw_content (text, append-only)
├── fetched_at (timestamptz)
└── created_at

normalized_items
├── id (uuid)
├── workspace_id (uuid)
├── source_id (uuid → sources)
├── title (text)
├── description (text)
├── content_type (enum: article|video|image|etc)
├── url (text)
├── entities (jsonb) — extracted entities
├── language (text)
└── created_at

content_scores
├── content_id (uuid → normalized_items)
├── relevance_score (numeric: 0-1)
├── engagement_score (numeric: 0-1)
├── trend_score (numeric: -1 to 1)
├── quality_score (numeric: 0-1)
└── computed_at (timestamptz)
```

### Schema: `workflow` — Job Orchestration

```sql
jobs
├── id (uuid, primary key)
├── workspace_id (uuid → workspaces)
├── user_id (uuid → users)
├── job_type (enum: brief|script|render|publish)
├── status (enum: pending|running|completed|failed)
├── payload (jsonb)
├── priority (integer: 1-10)
├── claimed_by (uuid → users, worker who claimed it)
└── created_at

events
├── id (uuid)
├── job_id (uuid → jobs)
├── event_type (enum: created|started|completed|failed|etc)
├── actor_type (enum: human|agent|system)
├── actor_id (uuid)
├── data (jsonb)
├── timestamp (timestamptz)
└── created_at (append-only)

audit_logs
├── id (uuid)
├── workspace_id (uuid)
├── actor_id (uuid)
├── action (text)
├── resource_type (text)
├── resource_id (uuid)
├── changes (jsonb)
└── created_at (immutable)
```

### Schema: `ml` — Machine Learning

```sql
models
├── id (uuid)
├── workspace_id (uuid)
├── name (text)
├── type (enum: llm|forecast|segmentation|sentiment|recommendation)
├── model_key (text) — provider:model_name
├── version (integer)
├── status (enum: active|deprecated|training)
├── config (jsonb) — hyperparameters
├── metrics (jsonb) — accuracy, f1, mae, etc.
└── created_at

predictions
├── id (uuid)
├── workspace_id (uuid)
├── content_id (uuid → normalized_items)
├── model_id (uuid → models)
├── prediction_type (enum: sentiment|trend|recommendation|segment)
├── prediction (jsonb)
└── created_at

feature_store
├── id (uuid)
├── workspace_id (uuid)
├── entity_type (enum: user|content|source)
├── entity_id (uuid)
├── features (jsonb) — computed features
└── computed_at (timestamptz)

training_jobs
├── id (uuid)
├── workspace_id (uuid)
├── model_name (text)
├── status (enum: pending|running|completed|failed)
├── training_params (jsonb)
├── validation_metrics (jsonb)
├── error_message (text)
└── created_at
```

### Schema: `webhooks` — Event Delivery

```sql
subscriptions
├── id (uuid)
├── workspace_id (uuid)
├── user_id (uuid → users)
├── url (text)
├── events (text[]) — event types to receive
├── secret (text) — HMAC signing key
├── headers (jsonb) — custom HTTP headers
├── active (boolean)
├── retry_policy (jsonb)
└── created_at

events
├── id (uuid)
├── workspace_id (uuid)
├── event_type (text) — content.ingested, job.completed, etc.
├── entity_id (uuid)
├── payload (jsonb)
├── occurred_at (timestamptz)
└── created_at

deliveries
├── id (uuid)
├── subscription_id (uuid → subscriptions)
├── event_id (uuid → events)
├── status (enum: pending|success|retry|failed)
├── http_status (integer)
├── response_body (text)
├── attempt_number (integer: 1-5)
├── next_retry_at (timestamptz)
└── created_at

dead_letters
├── id (uuid)
├── subscription_id (uuid)
├── event_id (uuid)
├── reason (text) — why it failed
├── last_error (text)
└── created_at
```

### Schema: `analytics` — Metrics & Predictions

```sql
custom_metrics
├── id (uuid)
├── workspace_id (uuid)
├── name (text) — engagement_rate, roi, etc.
├── definition (text) — SQL query or formula
├── metric_type (enum: count|sum|avg|ratio|custom)
├── dimension (text) — daily, weekly, by_source, etc.
└── created_at

metric_snapshots
├── id (uuid)
├── metric_id (uuid → custom_metrics)
├── dimension_value (text) — '2026-06-11' or 'source:123'
├── value (numeric)
└── computed_at (timestamptz)

cohorts
├── id (uuid)
├── workspace_id (uuid)
├── name (text) — power_users, at_risk, etc.
├── definition (jsonb) — selection criteria
├── members (uuid[]) — user IDs in cohort
└── created_at

attribution
├── id (uuid)
├── workspace_id (uuid)
├── conversion_id (uuid) — what converted
├── touch_points (jsonb) — events with credit attribution
├── model (enum: first_touch|last_touch|linear|time_decay|custom)
└── created_at

predictions
├── id (uuid)
├── workspace_id (uuid)
├── kpi_name (text) — churn_probability, ltv, etc.
├── entity_id (uuid) — user or content
├── prediction (jsonb) — value, confidence, factors
├── predicted_date (date)
└── created_at
```

---

## 🔄 Data Flow

### Flow 1: Content Ingestion → Analysis → Scoring

```
1. Content Source (RSS, Telegram)
   ↓
2. ContentWorker fetches raw items
   ├─ Store in raw_items (audit trail)
   └─ Emit event: content.ingested
   ↓
3. ContentWorker normalizes
   └─ Store in normalized_items
   ↓
4. ML Worker analyzes (sentiment, entities, language)
   ├─ SentimentService.predict()
   ├─ Cache prediction in ml.predictions (TTL: 7 days)
   └─ Emit event: content.scored
   ↓
5. Webhook Worker routes event
   ├─ Find matching subscriptions
   └─ HTTP POST to user-configured URLs (with HMAC signature)
   ↓
6. User receives webhook → processes externally
```

### Flow 2: Job Orchestration

```
1. User creates job (brief/script/render/publish)
   ├─ Store in workflow.jobs
   ├─ Emit event: job.created
   └─ Push to Redis queue
   ↓
2. TaskOrchestrator claims job
   ├─ Update job status → running
   ├─ Emit event: job.claimed
   └─ Execute task
   ↓
3. Task completes
   ├─ Update job status → completed
   ├─ Store in workflow.events (immutable audit trail)
   ├─ Emit event: job.completed
   └─ Trigger dependent jobs
   ↓
4. Webhook Worker delivers notification
   └─ HTTP POST to subscribed endpoints
```

### Flow 3: Analytics & Predictions

```
1. Metrics calculated
   ├─ Execute custom metric query
   ├─ Store snapshot in metric_snapshots
   ├─ Cache in Redis (TTL: 1 hour)
   └─ Dashboard aggregates from cache
   ↓
2. Churn prediction
   ├─ PredictionService.predict_churn(user_id)
   ├─ Score based on: engagement, inactivity, trends
   ├─ Store in analytics.predictions
   └─ Recommend action
   ↓
3. Attribution calculation
   ├─ Collect touch_points (impressions, clicks, conversions)
   ├─ Calculate credit by model (linear, time_decay, etc.)
   ├─ Store in analytics.attribution
   └─ Provide multi-touch reporting
```

---

## 🔌 Integration Points

### External Services

| Service | Purpose | Protocol | Fallback |
|---------|---------|----------|----------|
| **Ollama** | Local LLM (default) | HTTP | Lexicon-based |
| **OpenAI** | GPT-4 text generation | HTTP API | Ollama |
| **Anthropic** | Claude text generation | HTTP API | Ollama |
| **HuggingFace** | Sentiment models | HTTP API | Simple lexicon |

### Data Pipeline

```
External Sources (RSS, Telegram)
    ↓
ContentWorker (fetch + normalize)
    ↓
PostgreSQL (durable storage)
    ↓
Redis Queue (job scheduling)
    ├─ ML Worker (sentiment, forecast, segmentation)
    ├─ TaskOrchestrator (job workflow)
    └─ PublisherWorker (social publishing)
    ↓
Webhook Worker (event delivery)
    ↓
User Webhooks (external integrations)
```

---

## 🔐 Security Architecture

### Authentication & Authorization

```
1. User logs in → POST /auth/login
   ├─ Email + password → hash + compare
   └─ Generate JWT (15 min access, 7 day refresh)

2. Request with JWT
   ├─ FastAPI dependency: get_current_user()
   ├─ Extract user_id, workspace_id, role from token
   └─ Enforce RBAC via require_role() decorator

3. Multi-tenancy isolation
   ├─ Every query filters by workspace_id
   ├─ Users can only access own workspace
   └─ API keys scoped to specific endpoints
```

### Webhook Security

```
1. Subscription creation
   ├─ Generate random secret (secrets.token_urlsafe)
   └─ Store hashed in database

2. Event emission
   ├─ Serialize payload to JSON
   ├─ Sign with HMAC-SHA256(secret, payload)
   ├─ Add X-Arada-Signature header
   └─ POST to subscribed URLs

3. Subscriber verification
   ├─ Receive webhook + signature
   ├─ Recompute HMAC with stored secret
   ├─ Verify signature matches (constant-time comparison)
   └─ Validate timestamp to prevent replay
```

### Data Protection

- **At Rest:** PostgreSQL encryption, MinIO versioning
- **In Transit:** HTTPS/TLS 1.3+
- **In Memory:** Redis password authentication
- **Audit:** Immutable event_log + audit_logs tables

---

## 📈 Scalability

### Horizontal Scaling

```
Load Balancer (Round Robin)
    ├─ API Server 1 (8000)
    ├─ API Server 2 (8000)
    └─ API Server N (8000)
         ↓ (shared connection pools)
    PostgreSQL Primary
         ↓ (read replicas)
    PostgreSQL Replica 1
    PostgreSQL Replica 2
    
Redis Cluster (3+ nodes)
    ├─ Data replication
    ├─ Failover
    └─ Keyspace partitioning

Workers (Autoscaling)
    ├─ ML Worker: CPU-bound (scale by CPU)
    ├─ Webhook Worker: I/O-bound (scale by queue length)
    └─ Task Orchestrator: Job-bound (scale by pending jobs)
```

### Caching Strategy

| Component | TTL | Size |
|-----------|-----|------|
| ML Predictions | 7 days | ~1MB per 1000 items |
| Metrics Snapshots | 1 hour | ~100KB per metric |
| Dashboard Cache | 5 minutes | ~500KB per workspace |
| User Sessions | 15 minutes | ~1KB per session |

### Database Optimization

```sql
-- Indexes on frequently filtered columns
CREATE INDEX idx_content_workspace_created ON normalized_items(workspace_id, created_at);
CREATE INDEX idx_jobs_workspace_status ON jobs(workspace_id, status);
CREATE INDEX idx_predictions_workspace_kpi ON predictions(workspace_id, kpi_name);

-- Partitioning for large tables
PARTITION BY RANGE (created_at) FOR normalized_items (monthly);
PARTITION BY RANGE (created_at) FOR webhook_events (daily);

-- Materialized views for expensive aggregations
CREATE MATERIALIZED VIEW daily_metrics AS
  SELECT workspace_id, DATE(created_at), COUNT(*) as count
  FROM normalized_items
  GROUP BY workspace_id, DATE(created_at);
```

---

## 🔧 Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **API** | FastAPI | 0.104+ | REST framework, async |
| **Database** | PostgreSQL | 14+ | Relational storage, multi-tenant |
| **Cache** | Redis | 7.0+ | Job queue, predictions cache |
| **Storage** | MinIO | 2024+ | S3-compatible object storage |
| **Vector DB** | Qdrant | 1.18+ | Semantic search, embeddings |
| **LLM** | Ollama | Latest | Local text generation |
| **Monitoring** | Prometheus | Latest | Metrics collection |
| **Dashboards** | Grafana | Latest | Visualization |
| **Analytics** | Metabase | Latest | Business intelligence |

---

## 📋 Deployment Architecture

```
Development
  └─ localhost:8000 (single container)

Staging
  ├─ API x1 (Load Balancer)
  ├─ PostgreSQL + 1 replica
  ├─ Redis Cluster (3 nodes)
  └─ Monitoring (Prometheus, Grafana)

Production
  ├─ API x3+ (Kubernetes, Auto-scaling)
  ├─ PostgreSQL + 2 replicas (HA cluster)
  ├─ Redis Cluster (5+ nodes)
  ├─ Workers x10+ (CPU/IO bound)
  ├─ MinIO Cluster (3+ nodes)
  ├─ Monitoring + Alerting
  └─ Backup + DR
```

---

**Version:** 1.0.0  
**Last Updated:** 2026-06-11  
**Status:** ✅ Production Ready
