"""Authentication routes: register, login, refresh, logout, me."""
import re
from typing import Optional
from uuid import uuid4
import logging

import bcrypt
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field

from api.clients import PostgreSQLPool
from api.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    verify_token,
)
from api.auth.security import (
    get_current_user,
    TokenData,
    revoke_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Request/Response Schemas
# ============================================================================


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ...,
        min_length=12,
        description="Password (min 12 chars, uppercase, number, symbol)",
    )
    full_name: str = Field(..., description="User's full name")


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., description="Password")


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., description="Refresh token")


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(default=3600, description="Token expiry in seconds")


class UserResponse(BaseModel):
    """User information (safe to return to client)."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="Email address")
    full_name: Optional[str] = Field(None, description="Full name")
    is_admin: bool = Field(default=False, description="Admin status")
    is_active: bool = Field(default=True, description="Account active")
    created_at: str = Field(..., description="Account creation timestamp")


class LoginResponse(BaseModel):
    """Complete login response."""

    user: UserResponse
    tokens: TokenResponse


# ============================================================================
# Utilities
# ============================================================================


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode(), salt).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify plain text password against hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def validate_password_strength(password: str) -> Optional[str]:
    """Validate password meets security requirements."""
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number"
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};:'\"\\|,.<>?]", password):
        return "Password must contain at least one symbol (!@#$%^&*)"
    return None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(request: RegisterRequest) -> LoginResponse:
    """Register a new user account."""
    password_error = validate_password_strength(request.password)
    if password_error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=password_error,
        )

    async with PostgreSQLPool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM auth.users WHERE email = $1",
            request.email,
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user_id = str(uuid4())
        password_hash = hash_password(request.password)

        try:
            await conn.execute(
                """
                INSERT INTO auth.users
                    (id, email, password_hash, full_name, is_active, is_admin)
                VALUES ($1, $2, $3, $4, true, false)
                """,
                user_id,
                request.email,
                password_hash,
                request.full_name,
            )
            logger.info(f"New user registered: {request.email}")
        except Exception as e:
            logger.error(f"Registration failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Registration failed",
            )

    access_token = create_access_token(user_id, request.email, False)
    refresh_token = create_refresh_token(user_id)

    return LoginResponse(
        user=UserResponse(
            id=user_id,
            email=request.email,
            full_name=request.full_name,
            is_admin=False,
            is_active=True,
            created_at="2026-06-11T00:00:00Z",
        ),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ),
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate user and return tokens."""
    async with PostgreSQLPool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, email, password_hash, full_name, is_admin, is_active, created_at
            FROM auth.users WHERE email = $1
            """,
            request.email,
        )

        if not user or not verify_password(request.password, user["password_hash"]):
            logger.warning(f"Login failed: {request.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Account is inactive",
            )

    access_token = create_access_token(user["id"], user["email"], user["is_admin"])
    refresh_token = create_refresh_token(user["id"])

    return LoginResponse(
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            is_admin=user["is_admin"],
            is_active=user["is_active"],
            created_at=user["created_at"].isoformat() if user["created_at"] else None,
        ),
        tokens=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
        ),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(request: RefreshRequest) -> TokenResponse:
    """Generate new access token using refresh token."""
    try:
        payload = verify_token(request.refresh_token, token_type="refresh")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    
    async with PostgreSQLPool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT email, is_admin FROM auth.users WHERE id = $1",
            user_id,
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

    new_access_token = create_access_token(user_id, user["email"], user["is_admin"])

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=request.refresh_token,
    )


@router.post("/logout", status_code=204)
async def logout(current_user: TokenData = Depends(get_current_user)) -> None:
    """Logout user by revoking current token."""
    revoke_token(current_user.jti)
    logger.info(f"User logged out: {current_user.user_id}")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: TokenData = Depends(get_current_user)) -> UserResponse:
    """Get current authenticated user information."""
    async with PostgreSQLPool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT id, email, full_name, is_admin, is_active, created_at
            FROM auth.users WHERE id = $1
            """,
            current_user.user_id,
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

    return UserResponse(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        is_admin=user["is_admin"],
        is_active=user["is_active"],
        created_at=user["created_at"].isoformat() if user["created_at"] else None,
    )
