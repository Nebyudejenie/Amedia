"""JWT token generation and validation."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import uuid

import jwt
from jwt import PyJWTError

from api.config import settings

# Token configuration
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days
ALGORITHM = "HS256"


def get_secret_key() -> str:
    """Get JWT secret key from environment."""
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise ValueError("JWT_SECRET_KEY not configured in environment")
    return secret


def create_access_token(
    user_id: str,
    email: str,
    is_admin: bool = False,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create JWT access token.

    Args:
        user_id: User ID (UUID string)
        email: User email address
        is_admin: Whether user is admin
        expires_delta: Custom expiration time delta

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),  # Subject (user ID)
        "email": email,
        "is_admin": is_admin,
        "type": "access",
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),  # JWT ID for revocation
    }

    encoded_jwt = jwt.encode(
        payload,
        get_secret_key(),
        algorithm=ALGORITHM,
    )

    return encoded_jwt


def create_refresh_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create JWT refresh token.

    Args:
        user_id: User ID (UUID string)
        expires_delta: Custom expiration time delta

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": expire,
        "iat": now,
        "jti": str(uuid.uuid4()),
    }

    encoded_jwt = jwt.encode(
        payload,
        get_secret_key(),
        algorithm=ALGORITHM,
    )

    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    Verify and decode JWT token.

    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")

    Returns:
        Decoded token payload

    Raises:
        PyJWTError: If token is invalid, expired, or wrong type
    """
    try:
        payload = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[ALGORITHM],
        )

        # Verify token type
        if payload.get("type") != token_type:
            raise PyJWTError(f"Invalid token type. Expected {token_type}")

        return payload

    except jwt.ExpiredSignatureError:
        raise PyJWTError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise PyJWTError(f"Invalid token: {str(e)}")


def decode_token_unsafe(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode JWT token without verification (for extracting claims).

    WARNING: Use only for extracting user_id from malformed tokens.
    Always verify token with verify_token() before trusting claims.

    Args:
        token: JWT token string

    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            options={"verify_signature": False},
        )
        return payload
    except Exception:
        return None


def is_token_revoked(jti: str, revocation_list: set) -> bool:
    """
    Check if token JTI is in revocation list.

    Args:
        jti: JWT ID from token
        revocation_list: Set of revoked JTIs

    Returns:
        True if token is revoked, False otherwise
    """
    return jti in revocation_list
