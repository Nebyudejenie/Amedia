"""FastAPI dependency injection for auth and RBAC."""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth_service import AuthService
from schemas import UserResponse

security = HTTPBearer()


class TokenData:
    """Extracted token claims."""

    def __init__(self, user_id: str, workspace_id: str, role: str):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.role = role


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenData:
    """Verify JWT token and extract claims."""
    token = credentials.credentials
    payload = AuthService.decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    workspace_id = payload.get("workspace_id")
    role = payload.get("role")

    if not all([user_id, workspace_id, role]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenData(user_id=user_id, workspace_id=workspace_id, role=role)


def require_role(*allowed_roles: str):
    """Decorator to require specific roles."""

    async def check_role(token: TokenData = Depends(get_current_user)) -> TokenData:
        if token.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return token

    return check_role


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenData]:
    """Extract claims from optional JWT token."""
    if not credentials:
        return None

    token = credentials.credentials
    payload = AuthService.decode_token(token)

    if not payload or payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    workspace_id = payload.get("workspace_id")
    role = payload.get("role")

    if all([user_id, workspace_id, role]):
        return TokenData(user_id=user_id, workspace_id=workspace_id, role=role)

    return None
