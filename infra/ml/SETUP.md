# Arada ML Models — Quick Setup Guide

Get advanced AI features running: LLM content generation, trend prediction, audience segmentation.

## Prerequisites

- Arada API running
- PostgreSQL with migrations applied
- Python dependencies installed

## Step 1: Initialize ML Schema

```bash
# Apply ML schema migration
psql -h 127.0.0.1 -U arada -d arada -f infra/ml/init.sql

# Verify
psql -h 127.0.0.1 -U arada -d arada -c "SELECT COUNT(*) FROM ml.models;"
```

## Step 2: Install Python Dependencies

```bash
# Add to requirements.txt
pip install scikit-learn==1.3.2 transformers==4.35.2 torch==2.0.0

# Or use conda for faster installation
conda install -c conda-forge scikit-learn transformers pytorch
```

## Step 3: Setup LLM Provider

### Option A: Local (Ollama) — Recommended for Dev

Already running in docker-compose. Pull a model:

```bash
# Pull a lightweight model
docker-compose exec ollama ollama pull mistral

# Or larger model for better quality
docker-compose exec ollama ollama pull neural-chat

# Verify
docker-compose exec ollama ollama list
```

Update `.env`:
```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=mistral
```

### Option B: OpenAI — Production Quality

```bash
# Set in .env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-3.5-turbo  # or gpt-4 for best quality
```

Cost estimate: $2-5/day for typical usage

### Option C: Anthropic Claude

```bash
# Set in .env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
ANTHROPIC_MODEL=claude-3-sonnet-20240229
```

## Step 4: Test LLM Integration

```bash
TOKEN="your_bearer_token"
WORKSPACE_ID="ws_xxx"

# Generate brief from trending items
curl -X POST http://127.0.0.1:8000/ml/generate/brief \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"title": "AI breakthrough announced", "score": 85},
      {"title": "New GPU released", "score": 82}
    ],
    "style": "professional"
  }' | jq .

# Generate script for a topic
curl -X POST http://127.0.0.1:8000/ml/generate/script \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "topic": "AI trends in 2026",
    "tone": "engaging",
    "duration_seconds": 60
  }' | jq .

# Generate social media captions
curl -X POST http://127.0.0.1:8000/ml/generate/captions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "video_title": "The Future of AI",
    "video_description": "Exploring upcoming AI breakthroughs"
  }' | jq .
```

## Step 5: Setup Forecasting

```bash
# Get trend forecast
curl http://127.0.0.1:8000/ml/forecast/trends?days_ahead=7 \
  -H "Authorization: Bearer $TOKEN" | jq .

# Get optimal publish time
curl http://127.0.0.1:8000/ml/forecast/optimal-publish-time \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Step 6: Setup Audience Segmentation

```bash
# Segment users
curl "http://127.0.0.1:8000/ml/segments?num_segments=5" \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {user_id, segment, engagement_score}'

# Get recommendations for segment
curl "http://127.0.0.1:8000/ml/segments/Power%20Users/recommendations" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Step 7: Setup Sentiment Analysis

```bash
# Analyze content sentiment
curl -X POST http://127.0.0.1:8000/ml/sentiment \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "content": "This is the most exciting news I have heard all year!"
  }' | jq .

# Response:
# {
#   "sentiment": "positive",
#   "emotion": "joy",
#   "predicted_reactions": {
#     "like": 0.85,
#     "share": 0.6,
#     "save": 0.7
#   }
# }
```

## Step 8: Setup Recommendations

```bash
# Get recommendations for a video
VIDEO_ID="item_xyz"
curl "http://127.0.0.1:8000/ml/recommendations/video/$VIDEO_ID?limit=5" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Get trending recommendations for user
curl "http://127.0.0.1:8000/ml/recommendations/trending" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Step 9: Monitor Model Performance

```bash
# List registered models
curl "http://127.0.0.1:8000/ml/models" \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {name, type, version, accuracy}'

# Get LLM usage and costs
curl "http://127.0.0.1:8000/ml/models/performance" \
  -H "Authorization: Bearer $TOKEN" | jq .

# Sample response:
# {
#   "total_requests": 342,
#   "total_cost": 3.42,
#   "by_operation": {
#     "brief_generation": {"cost": 1.23, "count": 145},
#     "script_generation": {"cost": 2.19, "count": 197}
#   }
# }
```

## Step 10: Promote Production Model

Once you've tested models and chosen the best one:

```bash
MODEL_ID="model_uuid"

# Promote to production
curl -X POST "http://127.0.0.1:8000/ml/models/$MODEL_ID/promote" \
  -H "Authorization: Bearer $TOKEN"

# Verify it's now in production
curl "http://127.0.0.1:8000/ml/models/$MODEL_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.promoted_at'
```

## Cost Optimization

### 1. Use Local Ollama for Development

```env
# Free, private, no rate limits
LLM_PROVIDER=ollama
OLLAMA_MODEL=mistral
```

Cost: **$0/month**

### 2. Use GPT-3.5 for Production

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-3.5-turbo
```

Cost: **~$3-5/month** for 1000 generations/month

### 3. Enable Caching

Arada automatically caches identical requests:

```bash
# Check cache hit rate
psql -c "
  SELECT
    COUNT(*) as total_requests,
    COUNT(CASE WHEN accessed_at > NOW() - INTERVAL '1 day' THEN 1 END) as cache_hits,
    ROUND(100.0 * COUNT(CASE WHEN accessed_at > NOW() - INTERVAL '1 day' THEN 1 END) / NULLIF(COUNT(*), 0), 2) as cache_hit_rate
  FROM ml.generation_cache
  WHERE workspace_id = 'ws_xxx';
"
```

### 4. Batch API Calls

```bash
# Instead of 1 API call per item, batch multiple items:
curl -X POST http://127.0.0.1:8000/ml/batch/sentiment \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "items": [
      {"id": "item_1", "content": "Amazing news!"},
      {"id": "item_2", "content": "Disappointing results"},
      {"id": "item_3", "content": "Best day ever!"}
    ]
  }' | jq .
```

## A/B Testing Models

Compare two models to see which performs better:

```bash
MODEL_A="model_a_uuid"
MODEL_B="model_b_uuid"

# Create A/B test
curl -X POST http://127.0.0.1:8000/ml/experiments \
  -H "Authorization: Bearer $TOKEN" \
  -d "{
    \"experiment_name\": \"GPT-3.5 vs Mistral\",
    \"variant_a_model_id\": \"$MODEL_A\",
    \"variant_b_model_id\": \"$MODEL_B\",
    \"metric_name\": \"engagement_rate\",
    \"min_samples\": 100
  }" | jq .

# Wait for experiment to collect data, then check results
curl "http://127.0.0.1:8000/ml/experiments" \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {experiment_name, winner, improvement}'
```

## Troubleshooting

### Ollama not responding

```bash
# Check if running
docker-compose ps ollama

# Restart
docker-compose restart ollama

# Check logs
docker-compose logs ollama | tail -50
```

### OpenAI rate limit

```bash
# Reduce request rate or upgrade plan
# https://platform.openai.com/account/billing/limits
```

### Sentiment analysis too slow

```bash
# Use smaller model (faster but less accurate)
# SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english (default)
# EMOTION_MODEL=distilbert-emotion (lighter alternative)
```

### High LLM costs

```bash
# 1. Check cache hit rate
psql -c "SELECT COUNT(*), COUNT(DISTINCT workspace_id) FROM ml.generation_cache;"

# 2. Switch to cheaper model (GPT-3.5 vs GPT-4)
# 3. Use Ollama for non-critical content
# 4. Batch requests
```

## API Reference

Full endpoints available in [ML_MODELS.md](ML_MODELS.md#part-7-api-endpoints)

### Content Generation
- `POST /ml/generate/brief` — Generate content brief
- `POST /ml/generate/script` — Generate video script
- `POST /ml/generate/captions` — Generate social captions

### Analytics
- `GET /ml/forecast/trends` — Predict trending topics
- `GET /ml/forecast/optimal-publish-time` — Best time to publish
- `GET /ml/segments` — Segment users
- `GET /ml/segments/{segment}/recommendations` — Recommendations per segment

### Insights
- `POST /ml/sentiment` — Analyze sentiment
- `GET /ml/recommendations/video/{id}` — Similar videos
- `GET /ml/recommendations/trending` — Trending for user

### Management
- `GET /ml/models` — List models
- `POST /ml/models/{id}/promote` — Promote to production
- `GET /ml/models/performance` — View costs and usage
- `GET /ml/experiments` — View A/B tests

---

**Questions?** See [ML_MODELS.md](ML_MODELS.md) for comprehensive guide.
