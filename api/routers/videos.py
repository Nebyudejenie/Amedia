"""Video generation API: queue a job, poll status, list, download, delete."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from clients import MinIOClient, PostgreSQLPool
from auth.security import get_current_user, TokenData
from services.usage_service import require_within_usage_limit, record_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/videos", tags=["Videos"])

# Frontend progress copy keyed by the pipeline stage
STAGE_LABELS = {
    "queued": "Queued…",
    "script": "Generating script…",
    "images": "Fetching images…",
    "audio": "Creating audio…",
    "compose": "Composing video…",
    "upload": "Uploading…",
    "done": "Complete",
}


class GenerateRequest(BaseModel):
    article_id: Optional[UUID] = Field(None, description="Source article (feed_articles.id)")
    title: Optional[str] = Field(None, max_length=255, description="Required if no article_id")
    tone: str = Field("professional", pattern="^(professional|casual|educational)$")
    voice: str = Field("female", pattern="^(female|male)$")


def _playback_url(bucket: Optional[str], key: Optional[str]) -> Optional[str]:
    if not bucket or not key:
        return None
    try:
        return MinIOClient.presigned_get(bucket, key, expires_seconds=3600)
    except Exception:
        return None


def _serialize(row: dict, with_url: bool = False) -> dict:
    out = {
        "id": str(row["id"]),
        "title": row["title"],
        "status": row["status"],
        "stage": row["stage"],
        "progress_label": STAGE_LABELS.get(row["stage"], row["stage"]),
        "tone": row["tone"],
        "voice": row["voice"],
        "duration_seconds": row["duration_seconds"],
        "file_size_mb": float(row["file_size_mb"]) if row["file_size_mb"] is not None else None,
        "generation_time_seconds": row["generation_time_seconds"],
        "error_message": row["error_message"] if row["status"] == "failed" else None,
        "created_at": row["created_at"].isoformat(),
    }
    if with_url and row["status"] == "complete":
        out["playback_url"] = _playback_url(row["minio_bucket"], row["minio_key"])
    return out


@router.post("/generate", status_code=202)
async def generate_video(
    body: GenerateRequest,
    current_user: TokenData = Depends(require_within_usage_limit),
) -> dict:
    """Queue a video. Returns immediately; the worker processes it async."""
    title = body.title

    async with PostgreSQLPool.acquire() as conn:
        if body.article_id:
            article = await conn.fetchrow(
                "SELECT title FROM content.feed_articles WHERE id = $1 AND user_id = $2",
                body.article_id, current_user.user_id,
            )
            if not article:
                raise HTTPException(status_code=404, detail="Article not found")
            title = title or article["title"] or "Untitled"
        elif not title:
            raise HTTPException(status_code=422, detail="article_id or title is required")

        video_id = await conn.fetchval(
            """
            INSERT INTO content.videos (user_id, article_id, title, tone, voice)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            current_user.user_id, body.article_id, title[:255], body.tone, body.voice,
        )

    # A queued generation counts against the plan's monthly quota
    await record_usage(current_user.user_id, event_type="video")
    logger.info(f"Video queued: {video_id} by {current_user.user_id}")
    return {"video_id": str(video_id), "status": "queued"}


@router.get("")
async def list_videos(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    async with PostgreSQLPool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM content.videos WHERE user_id = $1", current_user.user_id
        )
        rows = await conn.fetch(
            """
            SELECT id, title, status, stage, tone, voice, duration_seconds,
                   file_size_mb, generation_time_seconds, error_message,
                   minio_bucket, minio_key, created_at
            FROM content.videos
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            current_user.user_id, limit, offset,
        )
    response.headers["X-Total-Count"] = str(total)
    return {"videos": [_serialize(dict(r), with_url=True) for r in rows], "total": total}


@router.get("/{video_id}")
async def get_video(
    video_id: UUID,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, title, status, stage, tone, voice, script, image_urls,
                   duration_seconds, file_size_mb, generation_time_seconds,
                   stage_timings, error_message, minio_bucket, minio_key, created_at
            FROM content.videos
            WHERE id = $1 AND user_id = $2
            """,
            video_id, current_user.user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    data = _serialize(dict(row), with_url=True)
    data["script"] = row["script"]
    data["image_urls"] = list(row["image_urls"]) if row["image_urls"] else []
    return data


@router.delete("/{video_id}", status_code=204)
async def delete_video(
    video_id: UUID,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Delete the row and remove the MP4 from MinIO."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT minio_bucket, minio_key FROM content.videos "
            "WHERE id = $1 AND user_id = $2",
            video_id, current_user.user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Video not found")
        await conn.execute("DELETE FROM content.videos WHERE id = $1", video_id)

    if row["minio_bucket"] and row["minio_key"]:
        try:
            MinIOClient.remove_object(row["minio_bucket"], row["minio_key"])
        except Exception:
            logger.warning(f"MinIO object for video {video_id} not removed (already gone?)")
