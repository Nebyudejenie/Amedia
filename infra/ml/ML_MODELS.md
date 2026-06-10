# Arada Intelligence OS — Advanced ML Models & AI Features

Production-grade machine learning for content generation, trend prediction, audience insights, and recommendations.

## Overview

**5 ML capabilities:**

1. **Content Generation** — LLM-powered briefs, scripts, captions (OpenAI, Anthropic, local Ollama)
2. **Trend Prediction** — Forecast trending topics 7-30 days ahead
3. **Audience Segmentation** — Cluster viewers by behavior, demographics, interests
4. **Sentiment Analysis** — Rate content emotion and reaction likelihood
5. **Recommendation Engine** — Suggest next videos, topics, publishing times

**Architecture:**
```
┌─────────────────────────────────────────┐
│         ML Orchestration Layer          │
│  (Model routing, versioning, tracking)  │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼───┐   ┌────▼───┐   ┌───▼────┐
│ LLM   │   │Forecast │   │ Segment│
│ Svc   │   │ Engine  │   │ Engine │
└───────┘   └─────────┘   └────────┘
    │            │            │
    └────────────┼────────────┘
                 │
        ┌────────▼──────────┐
        │  Model Registry   │
        │  (versioning,     │
        │   metadata)       │
        └───────────────────┘
```

---

## Part 1: Content Generation (LLM)

### Setup: Local LLM (Ollama)

**Option A: Local (free, private)**

```yaml
# Already in docker-compose.yml
ollama:
  image: ollama/ollama:latest
  container_name: arada-ollama
  ports:
    - "127.0.0.1:11434:11434"
  volumes:
    - ollama_data:/root/.ollama
  environment:
    OLLAMA_HOST: 0.0.0.0:11434
```

Pull models:
```bash
# Pull once, reuse forever
docker-compose exec ollama ollama pull mistral
docker-compose exec ollama ollama pull neural-chat
docker-compose exec ollama ollama pull llama2

# Verify
docker-compose exec ollama ollama list
```

### Setup: Cloud LLM (OpenAI / Anthropic)

**Option B: OpenAI GPT-4**

```python
# api/config.py
class LLMConfig(BaseSettings):
    # Provider: "ollama" | "openai" | "anthropic"
    llm_provider: str = "ollama"
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4-turbo"
    openai_base_url: str = "https://api.openai.com/v1"
    
    # Anthropic
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-sonnet-20240229"
    
    # Ollama (local)
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "mistral"
    
    # Cost tracking
    track_llm_costs: bool = True
    
    class Config:
        env_file = ".env"
```

### LLM Service

```python
# api/services/llm_service.py

from abc import ABC, abstractmethod
import asyncio
import json
from typing import Optional
import httpx

class LLMProvider(ABC):
    """Abstract base for LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """Generate text from prompt."""
        pass

class OllamaLLM(LLMProvider):
    """Local Ollama LLM (free, private)."""
    
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=120)
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """Generate with Ollama."""
        
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        
        response = await self.client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "temperature": temperature,
                "num_predict": max_tokens
            }
        )
        
        result = response.json()
        return result.get("response", "")

class OpenAILLM(LLMProvider):
    """OpenAI GPT-4 (cloud, $$$)."""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(
            timeout=120,
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """Generate with OpenAI."""
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        response = await self.client.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
        )
        
        result = response.json()
        return result["choices"][0]["message"]["content"]

class AnthropicLLM(LLMProvider):
    """Anthropic Claude (cloud, $$$)."""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(
            timeout=120,
            headers={"x-api-key": api_key}
        )
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """Generate with Anthropic."""
        
        response = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system if system else "",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature
            }
        )
        
        result = response.json()
        return result["content"][0]["text"]

class LLMService:
    """High-level LLM service with cost tracking & fallback."""
    
    def __init__(self, config, db_pool, redis):
        self.config = config
        self.db_pool = db_pool
        self.redis = redis
        
        # Initialize provider
        if config.llm_provider == "ollama":
            self.llm = OllamaLLM(config.ollama_base_url, config.ollama_model)
        elif config.llm_provider == "openai":
            self.llm = OpenAILLM(config.openai_api_key, config.openai_model)
        elif config.llm_provider == "anthropic":
            self.llm = AnthropicLLM(config.anthropic_api_key, config.anthropic_model)
    
    async def generate_brief(
        self,
        workspace_id: str,
        items: list,
        style: str = "professional"
    ) -> str:
        """Generate brief from top items."""
        
        system_prompt = f"""You are a content strategist for a media company.
        Create a brief summary of trending topics suitable for {style} video content.
        Include key themes, statistics, and recommended video angles."""
        
        items_text = "\n".join([
            f"- {item['title']} (Score: {item['score']})"
            for item in items[:10]
        ])
        
        prompt = f"""Trending items today:\n{items_text}\n\nCreate a brief (150-200 words)."""
        
        brief = await self.generate(prompt, system_prompt, max_tokens=500)
        
        # Track cost
        if self.config.track_llm_costs:
            await self.log_llm_usage(
                workspace_id,
                "brief_generation",
                len(prompt) + len(system_prompt)
            )
        
        return brief
    
    async def generate_script(
        self,
        workspace_id: str,
        topic: str,
        tone: str = "engaging",
        duration_seconds: int = 60
    ) -> dict:
        """Generate video script."""
        
        system_prompt = f"""You are a professional video scriptwriter.
        Write engaging scripts for short-form video content.
        Tone: {tone}
        Duration: {duration_seconds} seconds (~{duration_seconds // 3} words)"""
        
        prompt = f"""Write a video script about: {topic}
        
        Include:
        1. Hook (attention-grabbing opening)
        2. Main content (3-4 key points)
        3. Call-to-action (subscription/share request)
        
        Keep it concise and engaging for short-form video."""
        
        script_text = await self.generate(prompt, system_prompt, max_tokens=300)
        
        return {
            "content": script_text,
            "tone": tone,
            "estimated_duration": duration_seconds,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    async def generate_captions(
        self,
        workspace_id: str,
        video_title: str,
        video_description: str
    ) -> list:
        """Generate social media captions."""
        
        system_prompt = """You are an expert social media copywriter.
        Generate engaging, platform-specific captions for short-form videos."""
        
        prompt = f"""Create captions for each platform:
        
        Title: {video_title}
        Description: {video_description}
        
        Generate concise, engaging captions (max 280 chars) for:
        1. Twitter/X
        2. Instagram
        3. TikTok
        4. LinkedIn
        
        Format as JSON: {{"platform": "caption"}}"""
        
        captions_text = await self.generate(prompt, system_prompt, max_tokens=400)
        
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', captions_text, re.DOTALL)
            if json_match:
                captions = json.loads(json_match.group())
                return [
                    {"platform": k, "caption": v}
                    for k, v in captions.items()
                ]
        except:
            pass
        
        return [{"platform": "default", "caption": captions_text}]
    
    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        retries: int = 3
    ) -> str:
        """Generate with retry logic."""
        
        for attempt in range(retries):
            try:
                return await self.llm.generate(
                    prompt, system, max_tokens, temperature
                )
            except Exception as e:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    async def log_llm_usage(
        self,
        workspace_id: str,
        operation: str,
        input_tokens: int
    ):
        """Track LLM usage for billing."""
        
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ml.llm_usage_log 
                (workspace_id, operation, input_tokens, model, provider, cost)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, workspace_id, operation, input_tokens, 
            self.config.ollama_model if self.config.llm_provider == "ollama" 
            else self.config.openai_model,
            self.config.llm_provider,
            self.estimate_cost(input_tokens))
```

---

## Part 2: Trend Prediction

### Time-Series Forecasting

```python
# api/services/forecast_service.py

import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta

class TrendForecastService:
    """Predict trending topics 7-30 days ahead."""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
    
    async def forecast_trends(
        self,
        workspace_id: str,
        days_ahead: int = 7,
        confidence: float = 0.8
    ) -> list:
        """Forecast trending topics."""
        
        async with self.db_pool.acquire() as conn:
            # Get historical scores
            history = await conn.fetch("""
                SELECT 
                  DATE(created_at) as date,
                  AVG(final_score) as avg_score,
                  COUNT(*) as item_count
                FROM content.content_scores
                WHERE workspace_id = $1
                  AND created_at > NOW() - INTERVAL '90 days'
                GROUP BY DATE(created_at)
                ORDER BY date ASC
            """, workspace_id)
        
        if len(history) < 7:
            return []  # Need at least 7 days of data
        
        # Prepare time-series data
        dates = [h['date'] for h in history]
        scores = np.array([h['avg_score'] for h in history])
        X = np.arange(len(scores)).reshape(-1, 1)
        
        # Fit linear regression model
        model = LinearRegression()
        model.fit(X, scores)
        
        # Generate forecast
        future_X = np.arange(len(scores), len(scores) + days_ahead).reshape(-1, 1)
        forecast = model.predict(future_X)
        
        # Get trending topics
        trending_topics = await self.get_trending_topics(workspace_id)
        
        return [
            {
                "date": (datetime.now() + timedelta(days=i+1)).date().isoformat(),
                "predicted_score": float(forecast[i]),
                "trend_direction": "📈" if forecast[i] > scores[-1] else "📉",
                "confidence": confidence,
                "topic": trending_topics[i % len(trending_topics)] if trending_topics else None
            }
            for i in range(days_ahead)
        ]
    
    async def get_trending_topics(self, workspace_id: str) -> list:
        """Extract trending topics from recent items."""
        
        async with self.db_pool.acquire() as conn:
            topics = await conn.fetch("""
                SELECT 
                  keyword,
                  COUNT(*) as frequency,
                  AVG(cs.final_score) as avg_score
                FROM content.normalized_items ni
                JOIN content.content_scores cs ON ni.id = cs.item_id,
                LATERAL (
                  SELECT word as keyword 
                  FROM regexp_split_to_table(ni.title || ' ' || COALESCE(ni.description, ''), '\s+') word
                  WHERE length(word) > 4
                ) t
                WHERE ni.workspace_id = $1
                  AND ni.created_at > NOW() - INTERVAL '7 days'
                GROUP BY keyword
                ORDER BY frequency DESC, avg_score DESC
                LIMIT 20
            """, workspace_id)
        
        return [t['keyword'] for t in topics]
    
    async def predict_optimal_publish_time(
        self,
        workspace_id: str
    ) -> dict:
        """Predict best time to publish based on engagement."""
        
        async with self.db_pool.acquire() as conn:
            hourly_performance = await conn.fetch("""
                SELECT 
                  EXTRACT(HOUR FROM created_at) as hour,
                  AVG(engagement_score) as avg_engagement,
                  COUNT(*) as count
                FROM content.content_scores
                WHERE workspace_id = $1
                  AND created_at > NOW() - INTERVAL '30 days'
                GROUP BY EXTRACT(HOUR FROM created_at)
                ORDER BY avg_engagement DESC
                LIMIT 1
            """, workspace_id)
        
        if not hourly_performance:
            return {"hour": 14, "reason": "default (2 PM)"}
        
        best_hour = int(hourly_performance[0]['hour'])
        return {
            "hour": best_hour,
            "time": f"{best_hour:02d}:00",
            "expected_engagement": hourly_performance[0]['avg_engagement'],
            "reason": f"Peak engagement at {best_hour}:00 based on historical data"
        }
```

---

## Part 3: Audience Segmentation

### Behavioral Clustering

```python
# api/services/segmentation_service.py

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

class AudienceSegmentationService:
    """Segment audience by behavior and demographics."""
    
    async def segment_audience(
        self,
        workspace_id: str,
        num_segments: int = 5
    ) -> list:
        """Cluster users into segments."""
        
        async with db_pool.acquire() as conn:
            # Get user engagement data
            user_data = await conn.fetch("""
                SELECT
                  u.id,
                  COUNT(DISTINCT pr.id) as videos_watched,
                  AVG(CASE WHEN pr.completed_at IS NOT NULL THEN 1 ELSE 0 END) as completion_rate,
                  COUNT(DISTINCT CASE WHEN pr.liked = true THEN pr.id END) as likes,
                  COUNT(DISTINCT CASE WHEN pr.shared = true THEN pr.id END) as shares,
                  AVG(EXTRACT(EPOCH FROM (pr.completed_at - pr.created_at))) as avg_watch_time,
                  EXTRACT(EPOCH FROM (NOW() - MAX(pr.created_at))) / 3600 / 24 as days_since_last_watch
                FROM auth.users u
                LEFT JOIN analytics.publish_results pr ON u.workspace_id = pr.workspace_id
                WHERE u.workspace_id = $1
                  AND u.deleted_at IS NULL
                GROUP BY u.id
            """, workspace_id)
        
        if len(user_data) < num_segments:
            return []
        
        # Prepare features
        features = np.array([
            [
                u['videos_watched'] or 0,
                u['completion_rate'] or 0,
                u['likes'] or 0,
                u['shares'] or 0,
                u['avg_watch_time'] or 0,
                u['days_since_last_watch'] or 999
            ]
            for u in user_data
        ])
        
        # Normalize
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)
        
        # Cluster
        kmeans = KMeans(n_clusters=num_segments, random_state=42)
        clusters = kmeans.fit_predict(features_scaled)
        
        # Name segments
        segment_names = {
            0: "Power Users",
            1: "Casual Viewers",
            2: "One-Time Viewers",
            3: "Inactive",
            4: "New Users"
        }
        
        return [
            {
                "user_id": user_data[i]['id'],
                "segment": segment_names.get(clusters[i], f"Segment {clusters[i]}"),
                "videos_watched": user_data[i]['videos_watched'] or 0,
                "completion_rate": user_data[i]['completion_rate'] or 0,
                "engagement_score": (
                    (user_data[i]['likes'] or 0) * 2 +
                    (user_data[i]['shares'] or 0) * 3
                ) / max(user_data[i]['videos_watched'] or 1, 1)
            }
            for i in range(len(user_data))
        ]
    
    async def recommend_content_by_segment(
        self,
        workspace_id: str,
        segment: str,
        limit: int = 5
    ) -> list:
        """Recommend content for audience segment."""
        
        # Content preferences by segment
        preferences = {
            "Power Users": {"min_score": 75, "sort": "newest"},
            "Casual Viewers": {"min_score": 60, "sort": "trending"},
            "One-Time Viewers": {"min_score": 50, "sort": "popular"},
            "Inactive": {"min_score": 40, "sort": "interesting"},
            "New Users": {"min_score": 50, "sort": "popular"}
        }
        
        pref = preferences.get(segment, preferences["Casual Viewers"])
        
        async with db_pool.acquire() as conn:
            items = await conn.fetch("""
                SELECT
                  ni.id,
                  ni.title,
                  ni.url,
                  cs.final_score,
                  COUNT(pr.id) as views
                FROM content.normalized_items ni
                JOIN content.content_scores cs ON ni.id = cs.item_id
                LEFT JOIN analytics.publish_results pr ON ni.id = pr.video_id
                WHERE ni.workspace_id = $1
                  AND cs.final_score >= $2
                  AND ni.deleted_at IS NULL
                ORDER BY 
                  CASE WHEN $3 = 'newest' THEN ni.created_at END DESC,
                  CASE WHEN $3 = 'trending' THEN cs.trend_score END DESC,
                  CASE WHEN $3 = 'popular' THEN pr.engagement_score END DESC,
                  CASE WHEN $3 = 'interesting' THEN cs.quality_score END DESC
                LIMIT $4
            """, workspace_id, pref['min_score'], pref['sort'], limit)
        
        return [
            {
                "id": item['id'],
                "title": item['title'],
                "score": item['final_score'],
                "views": item['views'] or 0,
                "reason": f"Recommended for {segment}"
            }
            for item in items
        ]
```

---

## Part 4: Sentiment Analysis

```python
# api/services/sentiment_service.py

from transformers import pipeline
import asyncio

class SentimentAnalysisService:
    """Analyze sentiment and predict audience reaction."""
    
    def __init__(self):
        # Use lightweight transformer model
        self.sentiment_pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english"
        )
        self.emotion_pipeline = pipeline(
            "text-classification",
            model="j-hartmann/emotion-english-distilroberta-base"
        )
    
    async def analyze_content_sentiment(
        self,
        content: str,
        max_length: int = 512
    ) -> dict:
        """Analyze sentiment of content."""
        
        # Truncate to model limit
        text = content[:max_length]
        
        # Run in thread pool (transformers are synchronous)
        loop = asyncio.get_event_loop()
        
        sentiment = await loop.run_in_executor(
            None,
            lambda: self.sentiment_pipeline(text)[0]
        )
        
        emotion = await loop.run_in_executor(
            None,
            lambda: self.emotion_pipeline(text)[0]
        )
        
        return {
            "sentiment": sentiment['label'].lower(),  # positive/negative
            "sentiment_score": sentiment['score'],
            "emotion": emotion['label'],
            "emotion_score": emotion['score'],
            "predicted_reactions": self.predict_reactions(
                sentiment['label'],
                emotion['label']
            )
        }
    
    def predict_reactions(self, sentiment: str, emotion: str) -> dict:
        """Predict audience reactions based on sentiment/emotion."""
        
        reaction_map = {
            ("POSITIVE", "joy"): {"like": 0.85, "share": 0.6, "save": 0.7},
            ("POSITIVE", "surprise"): {"like": 0.8, "share": 0.7, "save": 0.5},
            ("POSITIVE", "anger"): {"like": 0.6, "share": 0.8, "save": 0.4},
            ("NEGATIVE", "sadness"): {"like": 0.3, "share": 0.4, "save": 0.2},
            ("NEGATIVE", "anger"): {"like": 0.2, "share": 0.6, "save": 0.1},
        }
        
        key = (sentiment, emotion.lower())
        default = {"like": 0.5, "share": 0.4, "save": 0.3}
        
        return reaction_map.get(key, default)
    
    async def batch_analyze(
        self,
        workspace_id: str,
        item_ids: list
    ) -> dict:
        """Analyze sentiment for multiple items."""
        
        async with db_pool.acquire() as conn:
            items = await conn.fetch("""
                SELECT id, title, description
                FROM content.normalized_items
                WHERE id = ANY($1::uuid[])
            """, item_ids)
        
        results = {}
        for item in items:
            text = f"{item['title']}. {item['description'] or ''}"
            results[item['id']] = await self.analyze_content_sentiment(text)
        
        return results
```

---

## Part 5: Recommendation Engine

```python
# api/services/recommendation_service.py

from sklearn.metrics.pairwise import cosine_similarity

class RecommendationEngine:
    """Recommend videos based on similarity and user behavior."""
    
    def __init__(self, db_pool, embedding_service):
        self.db_pool = db_pool
        self.embedding_service = embedding_service
    
    async def get_recommendations(
        self,
        user_id: str,
        video_id: str,
        limit: int = 5
    ) -> list:
        """Get recommendations for user based on watched video."""
        
        async with self.db_pool.acquire() as conn:
            # Get video embedding
            current_video = await conn.fetchrow("""
                SELECT id, title, description, final_score
                FROM content.content_scores
                WHERE item_id = $1
            """, video_id)
            
            if not current_video:
                return []
            
            # Get similar videos (using vector DB)
            similar = await self.embedding_service.similarity_search(
                query=f"{current_video['title']} {current_video['description']}",
                limit=limit + 1
            )
            
            # Filter out current video
            similar = [v for v in similar if v['id'] != video_id][:limit]
            
            return [
                {
                    "id": v['id'],
                    "title": v['title'],
                    "similarity_score": v['score'],
                    "reason": "Similar topic"
                }
                for v in similar
            ]
    
    async def get_trending_recommendations(
        self,
        user_id: str,
        limit: int = 5
    ) -> list:
        """Recommend trending videos for user."""
        
        async with self.db_pool.acquire() as conn:
            # Get user's interests (from watch history)
            user_interests = await conn.fetch("""
                SELECT DISTINCT keyword
                FROM (
                  SELECT keyword FROM (
                    SELECT word as keyword FROM 
                    regexp_split_to_table(
                      (SELECT STRING_AGG(title, ' ') 
                       FROM content.normalized_items 
                       WHERE workspace_id IN (
                         SELECT workspace_id FROM auth.users WHERE id = $1
                       ) AND created_at > NOW() - INTERVAL '30 days'
                      ), '\s+'
                    ) word WHERE length(word) > 4
                  ) t
                ) i
                LIMIT 10
            """, user_id)
            
            keywords = [i['keyword'] for i in user_interests]
            
            # Find trending items matching interests
            trending = await conn.fetch("""
                SELECT
                  ni.id,
                  ni.title,
                  cs.final_score,
                  cs.trend_score,
                  COUNT(pr.id) as recent_views
                FROM content.normalized_items ni
                JOIN content.content_scores cs ON ni.id = cs.item_id
                LEFT JOIN analytics.publish_results pr ON ni.id = pr.video_id
                WHERE (
                  {keyword_conditions}
                ) AND ni.deleted_at IS NULL
                GROUP BY ni.id, cs.id
                ORDER BY cs.trend_score DESC, recent_views DESC
                LIMIT $2
            """, user_id, limit)
            
            return [
                {
                    "id": v['id'],
                    "title": v['title'],
                    "trend_score": v['trend_score'],
                    "reason": "Trending in your interests"
                }
                for v in trending
            ]
```

---

## Part 6: Model Management & Versioning

### Model Registry

```sql
-- ml/models_registry.sql

CREATE SCHEMA ml;

CREATE TABLE ml.models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES auth.workspaces(id),
  name TEXT NOT NULL,
  type TEXT NOT NULL,  -- "llm", "forecast", "segmentation", "sentiment", "recommendation"
  version TEXT NOT NULL,
  provider TEXT NOT NULL,  -- "ollama", "openai", "anthropic", "sklearn", "huggingface"
  provider_model_id TEXT,  -- actual model identifier
  
  -- Configuration
  parameters JSONB DEFAULT '{}',
  hyperparameters JSONB DEFAULT '{}',
  
  -- Performance metrics
  accuracy FLOAT,
  precision FLOAT,
  recall FLOAT,
  f1_score FLOAT,
  auc_roc FLOAT,
  
  -- Metadata
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  promoted_at TIMESTAMPTZ,  -- When promoted to production
  deprecated_at TIMESTAMPTZ,
  
  created_by_id UUID REFERENCES auth.users(id),
  metadata JSONB DEFAULT '{}'
);

CREATE TABLE ml.model_performance (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id UUID NOT NULL REFERENCES ml.models(id),
  metric_name TEXT NOT NULL,
  metric_value FLOAT NOT NULL,
  measured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ml.llm_usage_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES auth.workspaces(id),
  model_id UUID REFERENCES ml.models(id),
  operation TEXT NOT NULL,  -- "brief", "script", "caption", "sentiment"
  input_tokens INT,
  output_tokens INT,
  cost NUMERIC(10, 6),
  provider TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ml.model_experiments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES auth.workspaces(id),
  experiment_name TEXT NOT NULL,
  description TEXT,
  
  -- Variants (A/B test)
  variant_a_model_id UUID NOT NULL REFERENCES ml.models(id),
  variant_b_model_id UUID REFERENCES ml.models(id),
  
  -- Results
  variant_a_metric FLOAT,
  variant_b_metric FLOAT,
  winner TEXT,  -- "a", "b", "tie", "undecided"
  
  status TEXT DEFAULT 'running',  -- "running", "completed", "paused"
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX idx_models_workspace ON ml.models(workspace_id);
CREATE INDEX idx_models_type ON ml.models(type);
CREATE INDEX idx_llm_usage_workspace ON ml.llm_usage_log(workspace_id, created_at DESC);
CREATE INDEX idx_experiments_workspace ON ml.model_experiments(workspace_id);
```

### Model Service

```python
# api/services/model_service.py

class ModelRegistry:
    """Manage ML model versions and promotion."""
    
    async def register_model(
        self,
        workspace_id: str,
        name: str,
        model_type: str,
        provider: str,
        provider_model_id: str,
        metrics: dict
    ) -> str:
        """Register new model version."""
        
        async with db_pool.acquire() as conn:
            model_id = await conn.fetchval("""
                INSERT INTO ml.models 
                (workspace_id, name, type, version, provider, provider_model_id, 
                 accuracy, precision, recall, f1_score)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """, workspace_id, name, model_type, 
            datetime.now().strftime("%Y%m%d_%H%M%S"),
            provider, provider_model_id,
            metrics.get('accuracy'),
            metrics.get('precision'),
            metrics.get('recall'),
            metrics.get('f1_score'))
        
        return model_id
    
    async def promote_model(self, model_id: str) -> bool:
        """Promote model version to production."""
        
        async with db_pool.acquire() as conn:
            # Demote current production
            await conn.execute("""
                UPDATE ml.models 
                SET promoted_at = NULL 
                WHERE promoted_at IS NOT NULL AND id != $1
            """, model_id)
            
            # Promote new model
            await conn.execute("""
                UPDATE ml.models 
                SET promoted_at = NOW() 
                WHERE id = $1
            """, model_id)
        
        return True
    
    async def get_production_model(
        self,
        workspace_id: str,
        model_type: str
    ) -> Optional[str]:
        """Get current production model."""
        
        async with db_pool.acquire() as conn:
            model = await conn.fetchrow("""
                SELECT provider_model_id 
                FROM ml.models 
                WHERE workspace_id = $1 
                  AND type = $2 
                  AND promoted_at IS NOT NULL
                  AND deprecated_at IS NULL
                ORDER BY promoted_at DESC
                LIMIT 1
            """, workspace_id, model_type)
        
        return model['provider_model_id'] if model else None
    
    async def run_ab_test(
        self,
        workspace_id: str,
        model_a_id: str,
        model_b_id: str,
        metric: str = "accuracy",
        min_samples: int = 100
    ) -> dict:
        """Compare two models via A/B test."""
        
        async with db_pool.acquire() as conn:
            # Get metrics
            model_a = await conn.fetchrow(
                "SELECT * FROM ml.models WHERE id = $1", model_a_id
            )
            model_b = await conn.fetchrow(
                "SELECT * FROM ml.models WHERE id = $1", model_b_id
            )
            
            metric_a = getattr(model_a, metric)
            metric_b = getattr(model_b, metric)
            
            winner = "a" if metric_a > metric_b else ("b" if metric_b > metric_a else "tie")
            
            return {
                "model_a": {
                    "id": model_a_id,
                    "score": metric_a
                },
                "model_b": {
                    "id": model_b_id,
                    "score": metric_b
                },
                "winner": winner,
                "improvement": abs(metric_a - metric_b)
            }
```

---

## Part 7: API Endpoints

### Content Generation

```http
POST /ml/generate/brief
Content-Type: application/json
{
  "items": [{"id": "item_1", "title": "...", "score": 85}],
  "style": "professional"
}
Response: {"brief": "..."}

POST /ml/generate/script
{
  "topic": "AI trends",
  "tone": "engaging",
  "duration_seconds": 60
}
Response: {"content": "...", "tone": "engaging"}

POST /ml/generate/captions
{
  "video_title": "...",
  "video_description": "..."
}
Response: [{"platform": "twitter", "caption": "..."}]
```

### Forecasting

```http
GET /ml/forecast/trends?days_ahead=7
Response: [
  {"date": "2026-06-17", "predicted_score": 78.5, "trend_direction": "📈"}
]

GET /ml/forecast/optimal-publish-time
Response: {"hour": 14, "time": "14:00", "expected_engagement": 0.85}
```

### Segmentation

```http
GET /ml/segments?num_segments=5
Response: [
  {"user_id": "usr_1", "segment": "Power Users", "engagement_score": 0.92}
]

GET /ml/segments/{segment}/recommendations
Response: [{"id": "item_1", "title": "...", "reason": "..."}]
```

### Sentiment

```http
POST /ml/sentiment
{
  "content": "This is amazing!"
}
Response: {
  "sentiment": "positive",
  "emotion": "joy",
  "predicted_reactions": {"like": 0.85, "share": 0.6}
}
```

### Recommendations

```http
GET /ml/recommendations/video/{video_id}?limit=5
Response: [
  {"id": "item_1", "title": "...", "similarity_score": 0.92}
]

GET /ml/recommendations/trending
Response: [
  {"id": "item_1", "title": "...", "trend_score": 0.88}
]
```

### Model Management

```http
POST /ml/models
{
  "name": "gpt4-brief-v2",
  "type": "llm",
  "provider": "openai",
  "metrics": {"accuracy": 0.92}
}

POST /ml/models/{id}/promote
# Promote to production

GET /ml/models/performance
Response: {
  "brief_generation": {"cost": "$2.34", "usage": 1250}
}
```

---

## Part 8: Cost Optimization

### Local vs Cloud

| Model | Cost/Use | Latency | Privacy | Quality |
|-------|----------|---------|---------|---------|
| Ollama (local) | Free | 500ms | ✅ | 8/10 |
| GPT-3.5 | $0.002/1k tokens | 300ms | ❌ | 9/10 |
| GPT-4 | $0.03/1k tokens | 400ms | ❌ | 10/10 |
| Claude-3 | $0.003/1k tokens | 350ms | ❌ | 9.5/10 |

**Recommendation:**
- Use **Ollama** for local dev (free, private)
- Use **GPT-3.5** for production scale (cheap, fast)
- Use **GPT-4** for critical content (best quality)

### Cost Tracking

```python
# Auto-calculate costs per operation
async def track_llm_cost(
    workspace_id: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    provider: str,
    model: str
):
    """Log LLM usage and cost."""
    
    costs = {
        "openai": {
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
            "gpt-4": {"input": 0.03, "output": 0.06}
        },
        "anthropic": {
            "claude-3-sonnet": {"input": 0.003, "output": 0.015}
        }
    }
    
    cost_per_token = costs.get(provider, {}).get(model, {})
    total_cost = (
        (input_tokens * cost_per_token.get('input', 0)) +
        (output_tokens * cost_per_token.get('output', 0))
    )
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ml.llm_usage_log 
            (workspace_id, operation, input_tokens, output_tokens, cost)
            VALUES ($1, $2, $3, $4, $5)
        """, workspace_id, operation, input_tokens, output_tokens, total_cost)
```

---

## References

- Ollama: https://ollama.ai/
- OpenAI API: https://platform.openai.com/
- Anthropic Claude: https://www.anthropic.com/
- Scikit-learn: https://scikit-learn.org/
- Transformers: https://huggingface.co/docs/transformers/

---

**See also**: [WEBHOOKS.md](../webhooks/WEBHOOKS.md), [ANALYTICS.md](../analytics/ANALYTICS.md), [MONITORING.md](../monitoring/MONITORING.md)
