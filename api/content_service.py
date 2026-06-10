"""Content ingestion, normalization, and scoring service."""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import feedparser
import httpx

from clients import PostgreSQLPool

logger = logging.getLogger(__name__)


class ContentService:
    """Ingest, normalize, deduplicate, and score content."""

    @staticmethod
    async def fetch_rss_source(url: str) -> list[dict]:
        """Fetch items from an RSS feed."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch RSS: {url}: {e}")
            return []

        feed = feedparser.parse(resp.content)
        items = []

        for entry in feed.entries[:100]:  # Limit to 100 entries per fetch
            item = {
                "external_id": entry.get("id", entry.get("link", "")),
                "title": entry.get("title", ""),
                "description": entry.get("summary", entry.get("description", "")),
                "url": entry.get("link", ""),
                "author": entry.get("author", ""),
                "published_at": None,
            }

            # Parse published date
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    item["published_at"] = datetime(*entry.published_parsed[:6])
                except (ValueError, TypeError):
                    pass

            if item["title"] and item["url"]:
                items.append(item)

        return items

    @staticmethod
    async def fetch_http_json_source(url: str, config: dict) -> list[dict]:
        """Fetch items from a JSON API endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                headers = config.get("headers", {})
                resp = await client.get(url, headers=headers, follow_redirects=True)
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch JSON API: {url}: {e}")
            return []

        try:
            data = resp.json()
        except Exception as e:
            logger.error(f"Invalid JSON response from {url}: {e}")
            return []

        items_key = config.get("items_key", "items")
        items_data = data.get(items_key, []) if isinstance(data, dict) else data
        items = []

        for entry in items_data[:100]:
            item = {
                "external_id": entry.get(config.get("id_field", "id"), ""),
                "title": entry.get(config.get("title_field", "title"), ""),
                "description": entry.get(config.get("description_field", "description"), ""),
                "url": entry.get(config.get("url_field", "url"), ""),
                "author": entry.get(config.get("author_field", "author"), ""),
                "published_at": None,
            }

            if item["title"] and (item["url"] or item["external_id"]):
                items.append(item)

        return items

    @staticmethod
    async def ingest_source(
        workspace_id: str, source_id: str, source_type: str, url: str, config: dict
    ) -> int:
        """Fetch and ingest items from a source."""
        if source_type == "rss":
            items = await ContentService.fetch_rss_source(url)
        elif source_type == "http_json":
            items = await ContentService.fetch_http_json_source(url, config)
        else:
            logger.warning(f"Unknown source type: {source_type}")
            return 0

        if not items:
            return 0

        # Insert raw items
        ingested = 0
        async with PostgreSQLPool.acquire() as conn:
            for item in items:
                try:
                    await conn.execute(
                        """INSERT INTO content.raw_items (workspace_id, source_id, external_id,
                                                           title, description, url, author, published_at)
                           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                           ON CONFLICT (workspace_id, external_id) DO NOTHING""",
                        workspace_id,
                        source_id,
                        item["external_id"],
                        item["title"],
                        item["description"],
                        item["url"],
                        item["author"],
                        item["published_at"],
                    )
                    ingested += 1
                except Exception as e:
                    logger.error(f"Failed to insert raw item: {e}")

            # Update source last_fetched_at
            await conn.execute(
                "UPDATE content.sources SET last_fetched_at = now() WHERE id = $1",
                source_id,
            )

        logger.info(f"Ingested {ingested} items from source {source_id}")
        return ingested

    @staticmethod
    def compute_content_hash(title: str, description: str) -> str:
        """Compute SHA256 hash of normalized content for deduplication."""
        text = (title + " " + description).lower().strip()
        text = " ".join(text.split())  # Normalize whitespace
        return hashlib.sha256(text.encode()).hexdigest()

    @staticmethod
    async def normalize_item(
        workspace_id: str, raw_item_id: str, raw_item: dict
    ) -> Optional[dict]:
        """Normalize a raw item and check for duplicates."""
        content_hash = ContentService.compute_content_hash(
            raw_item["title"], raw_item["description"]
        )

        # Check for duplicate
        async with PostgreSQLPool.acquire() as conn:
            existing = await conn.fetchval(
                """SELECT id FROM content.normalized_items
                   WHERE workspace_id = $1 AND content_hash = $2 AND deleted_at IS NULL
                   LIMIT 1""",
                workspace_id,
                content_hash,
            )

            if existing:
                # Mark raw item as duplicate
                await conn.execute(
                    "UPDATE content.raw_items SET is_duplicate = true WHERE id = $1",
                    raw_item_id,
                )
                return None

            # Insert normalized item
            normalized = {
                "workspace_id": workspace_id,
                "source_id": raw_item["source_id"],
                "external_id": raw_item["external_id"],
                "title": raw_item["title"],
                "description": raw_item["description"],
                "url": raw_item["url"],
                "author": raw_item["author"],
                "published_at": raw_item["published_at"],
                "content_hash": content_hash,
            }

            row = await conn.fetchrow(
                """INSERT INTO content.normalized_items
                   (workspace_id, source_id, external_id, title, description, url, author, published_at, content_hash)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                   RETURNING id""",
                normalized["workspace_id"],
                normalized["source_id"],
                normalized["external_id"],
                normalized["title"],
                normalized["description"],
                normalized["url"],
                normalized["author"],
                normalized["published_at"],
                normalized["content_hash"],
            )

            normalized["id"] = row["id"]
            return normalized

    @staticmethod
    async def score_item(workspace_id: str, item_id: str, item: dict) -> float:
        """Score a normalized item based on relevance, engagement, trend, quality."""
        relevance_score = ContentService._score_relevance(item)
        engagement_score = ContentService._score_engagement(item)
        trend_score = ContentService._score_trend(item)
        quality_score = ContentService._score_quality(item)

        # Weighted average
        final_score = (
            relevance_score * 0.3
            + engagement_score * 0.2
            + trend_score * 0.3
            + quality_score * 0.2
        )

        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """INSERT INTO content.content_scores
                   (workspace_id, item_id, relevance_score, engagement_score, trend_score, quality_score, final_score)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   ON CONFLICT (item_id) DO UPDATE SET
                     relevance_score = $3, engagement_score = $4, trend_score = $5, quality_score = $6, final_score = $7""",
                workspace_id,
                item_id,
                relevance_score,
                engagement_score,
                trend_score,
                quality_score,
                final_score,
            )

        return final_score

    @staticmethod
    def _score_relevance(item: dict) -> float:
        """Score relevance (title + description length, keyword presence)."""
        title = item.get("title", "").lower()
        description = item.get("description", "").lower()
        text = title + " " + description

        # Keyword presence (simple heuristic)
        keywords = ["trend", "viral", "breaking", "exclusive", "new", "update"]
        keyword_hits = sum(1 for kw in keywords if kw in text)

        # Length heuristic
        length_score = min(len(text) / 500, 1.0)

        return min((keyword_hits * 0.2 + length_score * 0.8), 1.0)

    @staticmethod
    def _score_engagement(item: dict) -> float:
        """Score engagement potential (author reputation, domain authority)."""
        author = item.get("author", "")
        url = item.get("url", "")

        # Simple domain authority heuristic
        if url:
            domain = urlparse(url).netloc
            trusted_domains = ["bbc.com", "cnn.com", "reuters.com", "techcrunch.com"]
            if any(domain.endswith(d) for d in trusted_domains):
                return 0.9

        # Author reputation heuristic
        if author and len(author) > 3:
            return 0.6

        return 0.3

    @staticmethod
    def _score_trend(item: dict) -> float:
        """Score trend relevance (freshness, keyword trends)."""
        # Placeholder: would integrate with analytics data
        return 0.5

    @staticmethod
    def _score_quality(item: dict) -> float:
        """Score content quality (grammar, completeness, source credibility)."""
        title = item.get("title", "")
        description = item.get("description", "")

        # Completeness
        if not title or not description:
            return 0.3

        # Grammar heuristic (very basic)
        title_words = len(title.split())
        desc_words = len(description.split())

        if title_words < 3 or desc_words < 10:
            return 0.4

        return 0.7
