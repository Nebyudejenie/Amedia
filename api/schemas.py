"""Pydantic schemas for all API requests/responses."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# Auth schemas
class UserRegisterRequest(BaseModel):
    """User registration."""

    email: EmailStr
    password: str = Field(..., min_length=12)
    workspace_name: str = Field(..., min_length=1, max_length=100)


class UserLoginRequest(BaseModel):
    """User login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token pair response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


class UserResponse(BaseModel):
    """User model for API responses."""

    id: str
    email: str
    workspace_id: str
    role: str
    status: str
    last_login_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreateRequest(BaseModel):
    """Create an API key."""

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=list)


class APIKeyResponse(BaseModel):
    """API key response (secret only on creation)."""

    id: str
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class APIKeyCreateResponse(APIKeyResponse):
    """API key creation response includes the full secret."""

    secret: str


class WorkspaceResponse(BaseModel):
    """Workspace model."""

    id: str
    name: str
    slug: str
    plan: str
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    checks: dict[str, str]


class MetricsResponse(BaseModel):
    """Placeholder for /metrics; actual response is text/plain Prometheus format."""

    pass


# Content schemas
class ContentSourceCreateRequest(BaseModel):
    """Create a content source."""

    name: str = Field(..., min_length=1, max_length=200)
    source_type: str = Field(..., pattern="^(rss|http_json|manual)$")
    url: Optional[str] = None
    config: dict = Field(default_factory=dict)


class ContentSourceResponse(BaseModel):
    """Content source model."""

    id: str
    workspace_id: str
    name: str
    source_type: str
    url: Optional[str] = None
    config: dict
    is_active: bool
    last_fetched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContentItemResponse(BaseModel):
    """Normalized content item."""

    id: str
    workspace_id: str
    source_id: str
    external_id: str
    title: str
    description: str
    url: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    content_hash: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    """Generic paginated response."""

    total: int
    limit: int
    offset: int
    items: list


# Workflow schemas
class JobCreateRequest(BaseModel):
    """Create a workflow job."""

    job_type: str = Field(..., pattern="^(brief|script|render|publish)$")
    input_data: dict = Field(default_factory=dict)
    priority: Optional[int] = Field(None, ge=0, le=100)


class JobResponse(BaseModel):
    """Workflow job model."""

    id: str
    workspace_id: str
    job_type: str
    status: str
    input_data: Optional[dict] = None
    output_data: Optional[dict] = None
    error_message: Optional[str] = None
    priority: int
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowEventResponse(BaseModel):
    """Workflow event (append-only audit trail)."""

    id: str
    workspace_id: str
    job_id: str
    event_type: str
    metadata: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Media schemas
class MediaTemplateCreateRequest(BaseModel):
    """Create a video template."""

    name: str = Field(..., min_length=1, max_length=200)
    template_type: str = Field(..., pattern="^(short-form|long-form|story|reel)$")
    config: dict = Field(default_factory=dict)


class MediaTemplateResponse(BaseModel):
    """Video template model."""

    id: str
    workspace_id: str
    name: str
    template_type: str
    config: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PublishJobResponse(BaseModel):
    """Publishing job model."""

    id: str
    workspace_id: str
    video_id: str
    platforms: list[str]
    status: str
    metadata: Optional[dict] = None
    published_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
