"""Account management: change/reset password, email verification."""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from clients import PostgreSQLPool
from auth.security import get_current_user, TokenData, revoke_token
from routers.auth import (
    hash_password,
    verify_password,
    validate_password_strength,
)
from services import email_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Account Management"])

RESET_TOKEN_TTL_HOURS = 24
VERIFY_TOKEN_TTL_HOURS = 24


# ============================================================================
# Schemas
# ============================================================================


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=12, description="New password")


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(..., description="Token from reset email")
    new_password: str = Field(..., min_length=12)


class VerifyEmailRequest(BaseModel):
    verification_token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# ============================================================================
# Helpers
# ============================================================================


def _hash_token(raw_token: str) -> str:
    """Hash a one-time token for storage (SHA-256; raw token never stored)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _generate_token() -> str:
    """Generate a secure 32-byte URL-safe token."""
    return secrets.token_urlsafe(32)


async def _audit(
    conn,
    user_id: Optional[str],
    action: str,
    request: Optional[Request] = None,
    details: Optional[dict] = None,
) -> None:
    """Write an audit log entry."""
    ip = request.client.host if request and request.client else None
    ua = request.headers.get("user-agent") if request else None
    await conn.execute(
        """
        INSERT INTO auth.audit_logs (user_id, action, details, ip_address, user_agent)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_id,
        action,
        details,
        ip,
        ua,
    )


async def _revoke_all_user_tokens(conn, user_id: str) -> None:
    """Invalidate all sessions by bumping password_changed_at.

    Tokens issued before this timestamp are rejected by the security layer.
    """
    await conn.execute(
        "UPDATE auth.users SET password_changed_at = now() WHERE id = $1",
        user_id,
    )


# ============================================================================
# Password Management
# ============================================================================


@router.post("/change-password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Change password for the authenticated user.

    Validates the current password, then updates the hash and invalidates
    all existing sessions (the user must log in again).
    """
    error = validate_password_strength(body.new_password)
    if error:
        raise HTTPException(status_code=422, detail=error)

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT password_hash FROM auth.users WHERE id = $1",
            current_user.user_id,
        )
        if not row or not verify_password(body.current_password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        await conn.execute(
            "UPDATE auth.users SET password_hash = $2, password_changed_at = now() WHERE id = $1",
            current_user.user_id,
            hash_password(body.new_password),
        )
        await _revoke_all_user_tokens(conn, current_user.user_id)
        await _audit(conn, current_user.user_id, "password.changed", request)

    revoke_token(current_user.jti)
    logger.info(f"Password changed for user {current_user.user_id}")


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotPasswordRequest, request: Request) -> dict:
    """Request a password reset email.

    Always returns 202 regardless of whether the email exists,
    to prevent account enumeration.
    """
    async with PostgreSQLPool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, is_active FROM auth.users WHERE email = $1",
            body.email,
        )

        if user and user["is_active"]:
            raw_token = _generate_token()
            await conn.execute(
                """
                INSERT INTO auth.password_reset_tokens (user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                """,
                user["id"],
                _hash_token(raw_token),
                datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS),
            )
            await _audit(conn, user["id"], "password.reset_requested", request)

            try:
                await email_service.send_password_reset_email(body.email, raw_token)
            except email_service.EmailError:
                logger.error(f"Failed to send reset email to {body.email}")

    return {"detail": "If that email exists, a reset link has been sent"}


@router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordRequest, request: Request) -> None:
    """Reset password using a token from the reset email."""
    error = validate_password_strength(body.new_password)
    if error:
        raise HTTPException(status_code=422, detail=error)

    token_hash = _hash_token(body.reset_token)

    async with PostgreSQLPool.acquire() as conn:
        token_row = await conn.fetchrow(
            """
            SELECT id, user_id, expires_at, used_at
            FROM auth.password_reset_tokens
            WHERE token_hash = $1
            """,
            token_hash,
        )

        if not token_row or token_row["used_at"] is not None:
            raise HTTPException(status_code=401, detail="Invalid or expired reset token")

        if token_row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Invalid or expired reset token")

        await conn.execute(
            """
            UPDATE auth.users
            SET password_hash = $2, password_changed_at = now(),
                failed_login_attempts = 0, locked_until = NULL
            WHERE id = $1
            """,
            token_row["user_id"],
            hash_password(body.new_password),
        )
        await conn.execute(
            "UPDATE auth.password_reset_tokens SET used_at = now() WHERE id = $1",
            token_row["id"],
        )
        await _revoke_all_user_tokens(conn, token_row["user_id"])
        await _audit(conn, token_row["user_id"], "password.reset_completed", request)

    logger.info(f"Password reset completed for user {token_row['user_id']}")


# ============================================================================
# Email Verification
# ============================================================================


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, request: Request) -> dict:
    """Verify email address using token from the verification email."""
    token_hash = _hash_token(body.verification_token)

    async with PostgreSQLPool.acquire() as conn:
        token_row = await conn.fetchrow(
            """
            SELECT t.id, t.user_id, t.expires_at, t.used_at,
                   u.email, u.full_name, u.email_verified_at
            FROM auth.email_verification_tokens t
            JOIN auth.users u ON u.id = t.user_id
            WHERE t.token_hash = $1
            """,
            token_hash,
        )

        if not token_row or token_row["used_at"] is not None:
            raise HTTPException(status_code=401, detail="Invalid or expired verification token")

        if token_row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Invalid or expired verification token")

        already_verified = token_row["email_verified_at"] is not None

        await conn.execute(
            "UPDATE auth.users SET email_verified_at = COALESCE(email_verified_at, now()) WHERE id = $1",
            token_row["user_id"],
        )
        await conn.execute(
            "UPDATE auth.email_verification_tokens SET used_at = now() WHERE id = $1",
            token_row["id"],
        )
        await _audit(conn, token_row["user_id"], "email.verified", request)

    if not already_verified:
        try:
            await email_service.send_welcome_email(
                token_row["email"], token_row["full_name"]
            )
        except email_service.EmailError:
            pass

    return {"detail": "Email verified successfully"}


@router.post("/resend-verification", status_code=202)
async def resend_verification(body: ResendVerificationRequest) -> dict:
    """Resend verification email. Always returns 202 (no enumeration)."""
    async with PostgreSQLPool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, email_verified_at FROM auth.users WHERE email = $1 AND is_active = true",
            body.email,
        )

        if user and user["email_verified_at"] is None:
            raw_token = _generate_token()
            await conn.execute(
                """
                INSERT INTO auth.email_verification_tokens (user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                """,
                user["id"],
                _hash_token(raw_token),
                datetime.now(timezone.utc) + timedelta(hours=VERIFY_TOKEN_TTL_HOURS),
            )
            try:
                await email_service.send_verification_email(body.email, raw_token)
            except email_service.EmailError:
                logger.error(f"Failed to send verification email to {body.email}")

    return {"detail": "If that email exists and is unverified, a link has been sent"}


# ============================================================================
# Dependency: require verified email (use for payments / API key generation)
# ============================================================================


async def require_verified_email(
    current_user: TokenData = Depends(get_current_user),
) -> TokenData:
    """Dependency: reject users who haven't verified their email."""
    async with PostgreSQLPool.acquire() as conn:
        verified = await conn.fetchval(
            "SELECT email_verified_at FROM auth.users WHERE id = $1",
            current_user.user_id,
        )
        if verified is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email verification required for this operation",
            )
    return current_user
