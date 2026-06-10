"""Media, templates, and publishing routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import TokenData, get_current_user
from media_service import MediaService
from schemas import (
    MediaTemplateCreateRequest,
    MediaTemplateResponse,
    PaginatedResponse,
    PublishJobResponse,
)

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/templates", response_model=MediaTemplateResponse, status_code=201)
async def create_template(
    req: MediaTemplateCreateRequest,
    token: TokenData = Depends(get_current_user),
) -> MediaTemplateResponse:
    """Create a video template."""
    template = await MediaService.create_template(
        workspace_id=token.workspace_id,
        name=req.name,
        template_type=req.template_type,
        config=req.config,
    )
    return MediaTemplateResponse(**template)


@router.get("/templates", response_model=PaginatedResponse)
async def list_templates(
    token: TokenData = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    """List video templates."""
    total, templates = await MediaService.list_templates(
        workspace_id=token.workspace_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[MediaTemplateResponse(**t) for t in templates],
    )


@router.get("/templates/{template_id}", response_model=MediaTemplateResponse)
async def get_template(
    template_id: str,
    token: TokenData = Depends(get_current_user),
) -> MediaTemplateResponse:
    """Get template details."""
    template = await MediaService.get_template(template_id, token.workspace_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )
    return MediaTemplateResponse(**template)


@router.post("/render", response_model=dict, status_code=202)
async def render_video(
    req: dict,
    token: TokenData = Depends(get_current_user),
) -> dict:
    """Render a video from script + template."""
    try:
        video = await MediaService.render_video(
            workspace_id=token.workspace_id,
            script_id=req.get("script_id"),
            template_id=req.get("template_id"),
            output_format=req.get("output_format", "short-form"),
        )
        return {
            "video_id": video["id"],
            "minio_path": video["minio_path"],
            "status": "rendering",
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/publish", response_model=PublishJobResponse, status_code=201)
async def create_publish_job(
    req: dict,
    token: TokenData = Depends(get_current_user),
) -> PublishJobResponse:
    """Create a publishing job."""
    job = await MediaService.create_publish_job(
        workspace_id=token.workspace_id,
        video_id=req.get("video_id"),
        platforms=req.get("platforms", ["twitter"]),
        metadata=req.get("metadata", {}),
    )
    return PublishJobResponse(**job)


@router.get("/publish", response_model=PaginatedResponse)
async def list_publish_jobs(
    token: TokenData = Depends(get_current_user),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    """List publishing jobs."""
    total, jobs = await MediaService.list_publish_jobs(
        workspace_id=token.workspace_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[PublishJobResponse(**job) for job in jobs],
    )


@router.get("/publish/{job_id}", response_model=PublishJobResponse)
async def get_publish_job(
    job_id: str,
    token: TokenData = Depends(get_current_user),
) -> PublishJobResponse:
    """Get publishing job details."""
    from clients import PostgreSQLPool

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, workspace_id, video_id, platforms, status, metadata, published_at, created_at
               FROM analytics.publish_jobs WHERE id = $1 AND workspace_id = $2""",
            job_id,
            token.workspace_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        return PublishJobResponse(**dict(row))


@router.post("/publish/{job_id}/{platform}", status_code=200)
async def publish_to_platform(
    job_id: str,
    platform: str,
    token: TokenData = Depends(get_current_user),
) -> dict:
    """Publish to a specific platform."""
    try:
        result = await MediaService.publish_to_platform(
            workspace_id=token.workspace_id,
            publish_job_id=job_id,
            platform=platform,
        )
        return {
            "platform": result["platform"],
            "post_id": result["post_id"],
            "url": result["url"],
            "status": result["status"],
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
