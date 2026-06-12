"""RSS feed management endpoints."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, HttpUrl

from clients import PostgreSQLPool
from auth.security import get_current_user, TokenData
from services.rss_fetcher import FeedError, validate_feed, process_feed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/feeds", tags=["RSS Feeds"])


# ============================================================================
# Schemas
# ============================================================================


class CreateFeedRequest(BaseModel):
    feed_url: HttpUrl = Field(..., description="RSS or Atom feed URL")
    refresh_interval_minutes: int = Field(15, ge=5, le=1440)


class UpdateFeedRequest(BaseModel):
    is_active: Optional[bool] = None
    refresh_interval_minutes: Optional[int] = Field(None, ge=5, le=1440)


class FeedResponse(BaseModel):
    feed_id: str
    title: Optional[str]
    url: str
    status: str  # active | paused | error
    error_count: int
    last_error: Optional[str]
    last_fetch_at: Optional[str]
    refresh_interval_minutes: int
    article_count: int


def _to_response(row) -> FeedResponse:
    if not row["is_active"]:
        status_label = "error" if row["error_count"] > 0 else "paused"
    else:
        status_label = "active"
    return FeedResponse(
        feed_id=str(row["id"]),
        title=row["title"],
        url=row["url"],
        status=status_label,
        error_count=row["error_count"],
        last_error=row["last_error"],
        last_fetch_at=row["last_fetch_at"].isoformat() if row["last_fetch_at"] else None,
        refresh_interval_minutes=row["refresh_interval_minutes"],
        article_count=row.get("article_count", 0) if hasattr(row, "get") else row["article_count"],
    )


_FEED_COLUMNS = """
    f.id, f.title, f.url, f.is_active, f.error_count, f.last_error,
    f.last_fetch_at, f.refresh_interval_minutes,
    (SELECT COUNT(*) FROM content.feed_articles a WHERE a.feed_id = f.id) AS article_count
"""


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=FeedResponse, status_code=201)
async def create_feed(
    body: CreateFeedRequest,
    current_user: TokenData = Depends(get_current_user),
) -> FeedResponse:
    """Register a feed. Validates that the URL serves parseable RSS/Atom."""
    url = str(body.feed_url)

    # Reject before touching the network if it's already registered
    async with PostgreSQLPool.acquire() as conn:
        existing = await conn.fetchval("SELECT 1 FROM content.rss_feeds WHERE url = $1", url)
        if existing:
            raise HTTPException(status_code=409, detail="Feed already registered")

    try:
        info = await validate_feed(url)
    except FeedError as e:
        raise HTTPException(status_code=400, detail=f"Not a valid RSS/Atom feed: {e}")

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO content.rss_feeds AS f
                (user_id, title, url, refresh_interval_minutes)
            VALUES ($1, $2, $3, $4)
            RETURNING {_FEED_COLUMNS}
            """,
            current_user.user_id,
            info["title"],
            url,
            body.refresh_interval_minutes,
        )

    logger.info(f"Feed created: {url} ({info['entry_count']} entries) by {current_user.user_id}")
    return _to_response(row)


@router.get("", response_model=list[FeedResponse])
async def list_feeds(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
) -> list[FeedResponse]:
    """List the caller's feeds with article counts."""
    async with PostgreSQLPool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM content.rss_feeds WHERE user_id = $1",
            current_user.user_id,
        )
        rows = await conn.fetch(
            f"""
            SELECT {_FEED_COLUMNS}
            FROM content.rss_feeds f
            WHERE f.user_id = $1
            ORDER BY f.created_at DESC
            LIMIT $2 OFFSET $3
            """,
            current_user.user_id,
            limit,
            offset,
        )

    response.headers["X-Total-Count"] = str(total)
    return [_to_response(r) for r in rows]


@router.patch("/{feed_id}", response_model=FeedResponse)
async def update_feed(
    feed_id: UUID,
    body: UpdateFeedRequest,
    current_user: TokenData = Depends(get_current_user),
) -> FeedResponse:
    """Pause/resume a feed or change its refresh interval."""
    updates = []
    params: list = [feed_id, current_user.user_id]

    if body.is_active is not None:
        params.append(body.is_active)
        updates.append(f"is_active = ${len(params)}")
        if body.is_active:
            # Re-enabling clears the error streak and schedules immediately
            updates.append("error_count = 0, last_error = NULL, next_fetch_at = now()")

    if body.refresh_interval_minutes is not None:
        params.append(body.refresh_interval_minutes)
        updates.append(f"refresh_interval_minutes = ${len(params)}")

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE content.rss_feeds AS f SET {", ".join(updates)}
            WHERE f.id = $1 AND f.user_id = $2
            RETURNING {_FEED_COLUMNS}
            """,
            *params,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Feed not found")

    return _to_response(row)


@router.delete("/{feed_id}", status_code=204)
async def delete_feed(
    feed_id: UUID,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Remove a feed and its articles (ON DELETE CASCADE)."""
    async with PostgreSQLPool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM content.rss_feeds WHERE id = $1 AND user_id = $2",
            feed_id,
            current_user.user_id,
        )
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Feed not found")

    logger.info(f"Feed deleted: {feed_id} by {current_user.user_id}")


@router.get("/{feed_id}/articles")
async def list_feed_articles(
    feed_id: UUID,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Paginated articles from one feed (newest first)."""
    async with PostgreSQLPool.acquire() as conn:
        owns = await conn.fetchval(
            "SELECT 1 FROM content.rss_feeds WHERE id = $1 AND user_id = $2",
            feed_id,
            current_user.user_id,
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Feed not found")

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM content.feed_articles WHERE feed_id = $1", feed_id
        )
        rows = await conn.fetch(
            """
            SELECT id, title, description, source_url, author, categories,
                   published_at, fetched_at
            FROM content.feed_articles
            WHERE feed_id = $1
            ORDER BY published_at DESC NULLS LAST, fetched_at DESC
            LIMIT $2 OFFSET $3
            """,
            feed_id,
            limit,
            offset,
        )

    response.headers["X-Total-Count"] = str(total)
    return {
        "articles": [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "description": r["description"],
                "source_url": r["source_url"],
                "author": r["author"],
                "categories": r["categories"],
                "published_at": r["published_at"].isoformat() if r["published_at"] else None,
                "fetched_at": r["fetched_at"].isoformat(),
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{feed_id}/fetch")
async def fetch_feed_now(
    feed_id: UUID,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Manually trigger an immediate fetch of one feed."""
    async with PostgreSQLPool.acquire() as conn:
        feed = await conn.fetchrow(
            """
            SELECT id, user_id, url, error_count, refresh_interval_minutes
            FROM content.rss_feeds
            WHERE id = $1 AND user_id = $2
            """,
            feed_id,
            current_user.user_id,
        )
        if not feed:
            raise HTTPException(status_code=404, detail="Feed not found")

    return await process_feed(dict(feed))
