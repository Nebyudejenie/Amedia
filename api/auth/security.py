"""Authentication and authorization decorators and utilities."""
from functools import wraps
from typing import Optional, Callable, Any
import logging

from fastapi import HTTPException, Request, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import PyJWTError

from auth.jwt_handler import verify_token, decode_token_unsafe

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Token revocation list (in production, use Redis)
TOKEN_REVOCATION_LIST: set = set()


class AuthenticationError(HTTPException):
    """Raised when authentication fails."""

    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Raised when user lacks required permissions."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


class TokenData:
    """Extracted and verified token claims."""

    def __init__(
        self,
        user_id: str,
        email: str,
        is_admin: bool = False,
        jti: Optional[str] = None,
    ):
        self.user_id = user_id
        self.email = email
        self.is_admin = is_admin
        self.jti = jti


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """
    Extract and verify current user from JWT token.

    This dependency can be used in FastAPI routes:
        @app.get("/me")
        async def get_me(current_user: TokenData = Depends(get_current_user)):
            return {"user_id": current_user.user_id}

    Raises:
        AuthenticationError: If token is missing, invalid, or expired

    Returns:
        TokenData with verified claims
    """
    if not credentials:
        raise AuthenticationError("No authorization credentials provided")

    token = credentials.credentials

    try:
        payload = verify_token(token, token_type="access")
    except PyJWTError as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise AuthenticationError(f"Invalid token: {str(e)}")

    # Check revocation list
    jti = payload.get("jti")
    if jti and jti in TOKEN_REVOCATION_LIST:
        raise AuthenticationError("Token has been revoked (logged out)")

    user_id = payload.get("sub")
    email = payload.get("email")
    is_admin = payload.get("is_admin", False)

    if not user_id or not email:
        raise AuthenticationError("Invalid token claims")

    return TokenData(
        user_id=user_id,
        email=email,
        is_admin=is_admin,
        jti=jti,
    )


async def get_current_admin(
    current_user: TokenData = Depends(get_current_user),
) -> TokenData:
    """
    Verify current user is an admin.

    Usage:
        @app.delete("/users/{user_id}")
        async def delete_user(user_id: str, admin: TokenData = Depends(get_current_admin)):
            ...

    Raises:
        AuthorizationError: If user is not admin

    Returns:
        TokenData with verified admin status
    """
    if not current_user.is_admin:
        raise AuthorizationError("Admin role required")

    return current_user


def revoke_token(jti: str) -> None:
    """
    Add token JTI to revocation list (logout).

    In production, save to Redis:
        redis.sadd("revoked_tokens", jti, ex=expiry_time)

    Args:
        jti: JWT ID from token
    """
    if jti:
        TOKEN_REVOCATION_LIST.add(jti)
        logger.info(f"Token revoked: {jti}")


def require_auth(
    allowed_roles: Optional[list] = None,
) -> Callable:
    """
    Decorator to require authentication on a function.

    NOT recommended for FastAPI routes (use Depends instead).
    Use for background jobs, scripts, or non-HTTP handlers.

    Usage:
        @require_auth(allowed_roles=["admin"])
        async def admin_task(user: TokenData):
            pass

    Args:
        allowed_roles: List of required roles (not implemented yet)

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            # Extract token from kwargs if passed
            token = kwargs.get("token")

            if not token:
                raise AuthenticationError("Token required")

            try:
                payload = verify_token(token, token_type="access")
            except PyJWTError as e:
                raise AuthenticationError(f"Invalid token: {str(e)}")

            jti = payload.get("jti")
            if jti and jti in TOKEN_REVOCATION_LIST:
                raise AuthenticationError("Token revoked")

            user = TokenData(
                user_id=payload.get("sub"),
                email=payload.get("email"),
                is_admin=payload.get("is_admin", False),
                jti=jti,
            )

            kwargs["current_user"] = user
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def clear_revocation_list() -> None:
    """Clear all revoked tokens (for testing)."""
    global TOKEN_REVOCATION_LIST
    TOKEN_REVOCATION_LIST.clear()
