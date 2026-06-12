"""RSS/Atom feed fetcher: download, parse, dedupe, store.

Handles RSS 2.0 and Atom 1.0 via feedparser (which also resolves
encoding declarations and tolerates malformed XML). Failed feeds back
off exponentially and are disabled after RSS_ERROR_THRESHOLD failures.
"""
import asyncio
import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import feedparser
import httpx
from prometheus_client import Counter, Histogram

from clients import PostgreSQLPool

logger = logging.getLogger(__name__)

# --- Configuration (env-driven) ---------------------------------------------
FETCH_INTERVAL_MINUTES = int(os.getenv("RSS_FETCH_INTERVAL_MINUTES", "15"))
FETCH_TIMEOUT_SECONDS = int(os.getenv("RSS_FETCH_TIMEOUT_SECONDS", "30"))
BATCH_SIZE = int(os.getenv("RSS_BATCH_SIZE", "20"))
ERROR_THRESHOLD = int(os.getenv("RSS_ERROR_THRESHOLD", "5"))
SLOW_FETCH_ALERT_SECONDS = float(os.getenv("RSS_SLOW_FETCH_ALERT_SECONDS", "5"))

USER_AGENT = "AradaOS-RSSFetcher/1.0 (+https://arada.fun)"

# --- Metrics ------------------------------------------------------------------
feeds_processed_total = Counter(
    "rss_feeds_processed_total", "Feeds processed", ["result"]
)
articles_found_total = Counter("rss_articles_found_total", "New articles stored")
duplicates_skipped_total = Counter("rss_duplicates_skipped_total", "Duplicate articles skipped")
fetch_duration_seconds = Histogram(
    "rss_fetch_duration_seconds", "Per-feed fetch+parse duration"
)


class FeedError(Exception):
    """Raised when a feed cannot be fetched or parsed."""


def url_hash(url: str) -> str:
    """Dedup key: SHA256 of the normalized article URL."""
    return hashlib.sha256(url.strip().encode()).hexdigest()


def backoff_delay_minutes(error_count: int, base_minutes: int) -> int:
    """Exponential backoff: base * 2^errors, capped at 24h.

    errors=0 → base, 1 → 2x, 2 → 4x, 3 → 8x, 4 → 16x ...
    """
    return min(base_minutes * (2 ** max(error_count, 0)), 24 * 60)


def _parse_entry_datetime(entry: Any) -> Optional[datetime]:
    """Best-effort published date from RSS (published) or Atom (updated)."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None) or (entry.get(attr) if hasattr(entry, "get") else None)
        if parsed:
            try:
                return datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def parse_feed_content(raw: bytes, feed_url: str) -> dict:
    """Parse raw feed bytes into {title, entries[]}.

    feedparser handles RSS 2.0, Atom 1.0, encoding sniffing, and most
    malformed XML (`bozo` flag). We reject only feeds with zero entries
    AND a parse error — partially-broken feeds with usable entries pass.
    """
    parsed = feedparser.parse(raw)

    if parsed.bozo and not parsed.entries:
        raise FeedError(f"Invalid feed XML: {getattr(parsed, 'bozo_exception', 'unknown error')}")

    if not parsed.entries and not parsed.feed.get("title"):
        raise FeedError("URL is not an RSS/Atom feed")

    entries = []
    for entry in parsed.entries:
        link = entry.get("link", "").strip()
        if not link:
            continue  # an article without a URL can't be deduped or stored

        entries.append({
            "title": (entry.get("title") or "Untitled")[:500],
            "description": entry.get("summary") or entry.get("description") or "",
            "source_url": link[:1000],
            "author": (entry.get("author") or "")[:255] or None,
            "categories": [t.get("term", "") for t in entry.get("tags", []) if t.get("term")][:20],
            "published_at": _parse_entry_datetime(entry),
        })

    return {
        "title": (parsed.feed.get("title") or feed_url)[:255],
        "entries": entries,
    }


async def fetch_feed(url: str) -> dict:
    """Download + parse a feed. Raises FeedError on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return parse_feed_content(resp.content, url)
    except httpx.TimeoutException:
        raise FeedError(f"Timed out after {FETCH_TIMEOUT_SECONDS}s")
    except httpx.HTTPStatusError as e:
        raise FeedError(f"HTTP {e.response.status_code}")
    except httpx.HTTPError as e:
        raise FeedError(f"Network error: {e}")


async def validate_feed(url: str) -> dict:
    """Used by POST /feeds: confirm the URL serves a parseable feed.

    Returns {title, entry_count}. Raises FeedError otherwise.
    """
    parsed = await fetch_feed(url)
    return {"title": parsed["title"], "entry_count": len(parsed["entries"])}


async def store_articles(conn, feed_id: UUID, user_id: UUID, entries: list[dict]) -> tuple[int, int]:
    """Insert new articles; skip URL-hash duplicates silently.

    Returns (new_count, duplicate_count).
    """
    new_count = 0
    duplicates = 0

    for entry in entries:
        result = await conn.execute(
            """
            INSERT INTO content.feed_articles
                (feed_id, user_id, title, description, source_url, url_hash,
                 author, categories, published_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (url_hash) DO NOTHING
            """,
            feed_id,
            user_id,
            entry["title"],
            entry["description"],
            entry["source_url"],
            url_hash(entry["source_url"]),
            entry["author"],
            entry["categories"],
            entry["published_at"],
        )
        if result == "INSERT 0 1":
            new_count += 1
        else:
            duplicates += 1

    return new_count, duplicates


async def process_feed(feed: dict) -> dict:
    """Fetch one feed and persist results + status.

    Success: store articles, reset error_count, schedule next run.
    Failure: bump error_count, schedule with exponential backoff,
             disable + alert after ERROR_THRESHOLD consecutive errors.
    """
    feed_id: UUID = feed["id"]
    started = time.monotonic()

    try:
        parsed = await fetch_feed(feed["url"])
        duration = time.monotonic() - started
        fetch_duration_seconds.observe(duration)

        async with PostgreSQLPool.acquire() as conn:
            new_count, dup_count = await store_articles(
                conn, feed_id, feed["user_id"], parsed["entries"]
            )
            await conn.execute(
                """
                UPDATE content.rss_feeds
                SET last_fetch_at = now(),
                    next_fetch_at = now() + make_interval(mins => refresh_interval_minutes),
                    error_count = 0,
                    last_error = NULL,
                    title = COALESCE(NULLIF(title, ''), $2)
                WHERE id = $1
                """,
                feed_id,
                parsed["title"],
            )

        feeds_processed_total.labels(result="success").inc()
        articles_found_total.inc(new_count)
        duplicates_skipped_total.inc(dup_count)

        logger.info(
            f"RSS ok feed_id={feed_id} new={new_count} dup={dup_count} "
            f"duration_ms={duration * 1000:.0f}"
        )
        if duration > SLOW_FETCH_ALERT_SECONDS:
            logger.warning(f"RSS slow fetch feed_id={feed_id} url={feed['url']} {duration:.1f}s")

        return {"feed_id": str(feed_id), "status": "ok", "new": new_count, "duplicates": dup_count}

    except FeedError as e:
        duration = time.monotonic() - started
        error_count = feed.get("error_count", 0) + 1
        disable = error_count >= ERROR_THRESHOLD
        delay = backoff_delay_minutes(error_count, feed.get("refresh_interval_minutes", 15))

        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                UPDATE content.rss_feeds
                SET error_count = $2,
                    last_error = $3,
                    last_fetch_at = now(),
                    next_fetch_at = now() + make_interval(mins => $4),
                    is_active = CASE WHEN $5 THEN false ELSE is_active END
                WHERE id = $1
                """,
                feed_id,
                error_count,
                str(e)[:500],
                delay,
                disable,
            )

        feeds_processed_total.labels(result="error").inc()
        logger.error(
            f"RSS error feed_id={feed_id} url={feed['url']} error={e} "
            f"errors={error_count} backoff={delay}m duration_ms={duration * 1000:.0f}"
        )
        if disable:
            # Surfaces in logs/alerting; email hook can attach here
            logger.critical(
                f"RSS feed DISABLED after {error_count} consecutive errors: "
                f"feed_id={feed_id} url={feed['url']}"
            )

        return {"feed_id": str(feed_id), "status": "error", "error": str(e)}


async def process_all_feeds() -> dict:
    """Process every due, active feed in parallel batches of BATCH_SIZE."""
    async with PostgreSQLPool.acquire() as conn:
        feeds = await conn.fetch(
            """
            SELECT id, user_id, url, error_count, refresh_interval_minutes
            FROM content.rss_feeds
            WHERE is_active = true AND next_fetch_at <= now()
            ORDER BY next_fetch_at
            """
        )

    if not feeds:
        return {"processed": 0, "ok": 0, "errors": 0}

    semaphore = asyncio.Semaphore(BATCH_SIZE)

    async def bounded(feed) -> dict:
        async with semaphore:
            return await process_feed(dict(feed))

    results = await asyncio.gather(*(bounded(f) for f in feeds), return_exceptions=True)

    ok = sum(1 for r in results if isinstance(r, dict) and r["status"] == "ok")
    errors = len(results) - ok
    logger.info(f"RSS cycle complete: {len(results)} feeds, {ok} ok, {errors} errors")
    return {"processed": len(results), "ok": ok, "errors": errors}
