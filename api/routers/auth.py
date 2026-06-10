"""Authentication routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from auth_service import AuthService
from dependencies import TokenData, get_current_user, require_role
from schemas import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    WorkspaceResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: UserRegisterRequest) -> TokenResponse:
    """Register a new user and return JWT tokens."""
    # Check if user exists
    user = await AuthService.get_user_by_email(req.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create workspace + user
    user = await AuthService.register_user(
        email=req.email, password=req.password, workspace_name=req.workspace_name
    )

    # Generate tokens
    access_token, expires_in = AuthService.create_access_token(
        user_id=user["id"],
        workspace_id=user["workspace_id"],
        role=user["role"],
    )
    refresh_token = AuthService.create_refresh_token(
        user_id=user["id"],
        workspace_id=user["workspace_id"],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: UserLoginRequest) -> TokenResponse:
    """Authenticate user and return JWT tokens."""
    user = await AuthService.get_user_by_email(req.email)
    if not user or not AuthService.verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account suspended",
        )

    # Update last login
    await AuthService.update_last_login(user["id"])

    # Generate tokens
    access_token, expires_in = AuthService.create_access_token(
        user_id=user["id"],
        workspace_id=user["workspace_id"],
        role=user["role"],
    )
    refresh_token = AuthService.create_refresh_token(
        user_id=user["id"],
        workspace_id=user["workspace_id"],
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(token: TokenData = Depends(get_current_user)) -> TokenResponse:
    """Use a refresh token to get a new access token."""
    user = await AuthService.get_user_by_id(token.user_id)
    if not user or user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user",
        )

    # Generate new access token
    access_token, expires_in = AuthService.create_access_token(
        user_id=token.user_id,
        workspace_id=token.workspace_id,
        role=token.role,
    )

    # Keep the same refresh token (or issue new one here if desired)
    refresh_token = AuthService.create_refresh_token(
        user_id=token.user_id,
        workspace_id=token.workspace_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(token: TokenData = Depends(get_current_user)) -> UserResponse:
    """Get the current authenticated user."""
    user = await AuthService.get_user_by_id(token.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse(**user)


@router.get("/workspace", response_model=WorkspaceResponse)
async def get_workspace(
    token: TokenData = Depends(get_current_user),
) -> WorkspaceResponse:
    """Get current user's workspace."""
    from clients import PostgreSQLPool

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, slug, plan, created_at FROM auth.workspaces WHERE id = $1 AND deleted_at IS NULL",
            token.workspace_id,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
        return WorkspaceResponse(**dict(row))


@router.post("/api-keys", response_model=APIKeyCreateResponse, status_code=201)
async def create_api_key(
    req: APIKeyCreateRequest,
    token: TokenData = Depends(require_role("owner", "admin")),
) -> APIKeyCreateResponse:
    """Create an API key (owner/admin only)."""
    api_key = await AuthService.create_api_key(
        workspace_id=token.workspace_id,
        name=req.name,
        scopes=req.scopes,
    )
    return APIKeyCreateResponse(**api_key)


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    token: TokenData = Depends(require_role("owner", "admin")),
) -> list[APIKeyResponse]:
    """List API keys for the workspace (owner/admin only)."""
    from clients import PostgreSQLPool

    async with PostgreSQLPool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, name, prefix, scopes, last_used_at, created_at
               FROM auth.api_keys
               WHERE workspace_id = $1 AND deleted_at IS NULL
               ORDER BY created_at DESC""",
            token.workspace_id,
        )
        return [APIKeyResponse(**dict(row)) for row in rows]


@router.delete("/api-keys/{api_key_id}", status_code=204)
async def delete_api_key(
    api_key_id: str,
    token: TokenData = Depends(require_role("owner", "admin")),
) -> None:
    """Delete an API key (owner/admin only)."""
    from clients import PostgreSQLPool

    async with PostgreSQLPool.acquire() as conn:
        result = await conn.execute(
            """UPDATE auth.api_keys
               SET deleted_at = now()
               WHERE id = $1 AND workspace_id = $2""",
            api_key_id,
            token.workspace_id,
        )
        if result == "UPDATE 0":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
            )
