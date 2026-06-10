"""Workflow orchestration routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from dependencies import TokenData, get_current_user
from schemas import (
    JobCreateRequest,
    JobResponse,
    PaginatedResponse,
    WorkflowEventResponse,
)
from workflow_service import WorkflowService

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(
    req: JobCreateRequest,
    token: TokenData = Depends(get_current_user),
) -> JobResponse:
    """Create a new workflow job."""
    job = await WorkflowService.create_job(
        workspace_id=token.workspace_id,
        job_type=req.job_type,
        input_data=req.input_data,
        priority=req.priority or 0,
    )
    return JobResponse(**job)


@router.get("/jobs", response_model=PaginatedResponse)
async def list_jobs(
    token: TokenData = Depends(get_current_user),
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> PaginatedResponse:
    """List workflow jobs for the workspace."""
    total, jobs = await WorkflowService.list_jobs(
        workspace_id=token.workspace_id,
        status=status,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[JobResponse(**job) for job in jobs],
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    token: TokenData = Depends(get_current_user),
) -> JobResponse:
    """Get job details."""
    job = await WorkflowService.get_job(job_id)
    if not job or job["workspace_id"] != token.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return JobResponse(**job)


@router.get("/jobs/{job_id}/events", response_model=list[WorkflowEventResponse])
async def get_job_events(
    job_id: str,
    token: TokenData = Depends(get_current_user),
) -> list[WorkflowEventResponse]:
    """Get all events for a job (audit trail)."""
    job = await WorkflowService.get_job(job_id)
    if not job or job["workspace_id"] != token.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    events = await WorkflowService.get_job_events(job_id)
    return [WorkflowEventResponse(**event) for event in events]
