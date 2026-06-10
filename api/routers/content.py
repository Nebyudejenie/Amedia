"""Content ingestion routes."""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from clients import PostgreSQLPool, RedisClient
from dependencies import TokenData, get_current_user
from schemas import (
    ContentItemResponse,
    ContentSourceCreateRequest,
    ContentSourceResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/content", tags=["content"])


@router.post("/sources", response_model=ContentSourceResponse, status_code=201)
async def create_source(
    req: ContentSourceCreateRequest,
    token: TokenData = Depends(get_current_user),
) -> ContentSourceResponse:
    """Create a content source (RSS, API, manual)."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO content.sources (workspace_id, name, source_type, url, config, is_active)
               VALUES ($1, $2, $3, $4, $5, true)
               RETURNING id, workspace_id, name, source_type, url, config, is_active,
                         last_fetched_at, created_at, updated_at""",
            token.workspace_id,
            req.name,
            req.source_type,
            req.url,
            req.config,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create source",
            )
        return ContentSourceResponse(**dict(row))


@router.get("/sources", response_model=PaginatedResponse)
async def list_sources(
    token: TokenData = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    """List content sources for the workspace."""
    async with PostgreSQLPool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM content.sources WHERE workspace_id = $1 AND deleted_at IS NULL",
            token.workspace_id,
        )
        rows = await conn.fetch(
            """SELECT id, workspace_id, name, source_type, url, config, is_active,
                      last_fetched_at, created_at, updated_at
               FROM content.sources
               WHERE workspace_id = $1 AND deleted_at IS NULL
               ORDER BY created_at DESC
               LIMIT $2 OFFSET $3""",
            token.workspace_id,
            limit,
            offset,
        )
        items = [ContentSourceResponse(**dict(row)) for row in rows]
        return PaginatedResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/sources/{source_id}", response_model=ContentSourceResponse)
async def get_source(
    source_id: str,
    token: TokenData = Depends(get_current_user),
) -> ContentSourceResponse:
    """Get a specific source."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, workspace_id, name, source_type, url, config, is_active,
                      last_fetched_at, created_at, updated_at
               FROM content.sources
               WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL""",
            source_id,
            token.workspace_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source not found",
            )
        return ContentSourceResponse(**dict(row))


@router.post("/sources/{source_id}/fetch", status_code=202)
async def trigger_source_fetch(
    source_id: str,
    token: TokenData = Depends(get_current_user),
) -> dict:
    """Trigger ingestion from a source (async via Redis queue)."""
    async with PostgreSQLPool.acquire() as conn:
        source = await conn.fetchrow(
            "SELECT id, workspace_id, source_type, url, config FROM content.sources WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL",
            source_id,
            token.workspace_id,
        )
        if not source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Source not found",
            )

    # Queue fetch job in Redis
    job_id = f"fetch-{source_id}"
    job_data = json.dumps({
        "job_id": job_id,
        "source_id": source_id,
        "workspace_id": token.workspace_id,
        "source_type": source["source_type"],
        "url": source["url"],
        "config": source["config"],
    })
    await RedisClient.lpush("content:fetch-queue", job_data)

    return {"job_id": job_id, "status": "queued"}


@router.get("/items", response_model=PaginatedResponse)
async def list_items(
    token: TokenData = Depends(get_current_user),
    normalized: bool = Query(True),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    """List content items (normalized by default)."""
    table = "content.normalized_items" if normalized else "content.raw_items"
    async with PostgreSQLPool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM {table} WHERE workspace_id = $1 AND deleted_at IS NULL",
            token.workspace_id,
        )
        rows = await conn.fetch(
            f"""SELECT id, workspace_id, source_id, external_id, title, description,
                       url, author, published_at, content_hash, created_at, updated_at
               FROM {table}
               WHERE workspace_id = $1 AND deleted_at IS NULL
               ORDER BY published_at DESC, created_at DESC
               LIMIT $2 OFFSET $3""",
            token.workspace_id,
            limit,
            offset,
        )
        items = [ContentItemResponse(**dict(row)) for row in rows]
        return PaginatedResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/items/{item_id}", response_model=ContentItemResponse)
async def get_item(
    item_id: str,
    token: TokenData = Depends(get_current_user),
) -> ContentItemResponse:
    """Get a specific content item."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, workspace_id, source_id, external_id, title, description,
                      url, author, published_at, content_hash, created_at, updated_at
               FROM content.normalized_items
               WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL""",
            item_id,
            token.workspace_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found",
            )
        return ContentItemResponse(**dict(row))


@router.get("/items/{item_id}/score", response_model=dict)
async def get_item_score(
    item_id: str,
    token: TokenData = Depends(get_current_user),
) -> dict:
    """Get scoring details for a content item."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, relevance_score, engagement_score, trend_score, quality_score, final_score
               FROM content.content_scores
               WHERE item_id = $1 AND workspace_id = $2""",
            item_id,
            token.workspace_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Score not found",
            )
        return dict(row)
