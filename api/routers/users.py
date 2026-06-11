"""User management: profile + admin user administration."""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, HttpUrl

from api.clients import PostgreSQLPool
from api.auth.security import get_current_user, get_current_admin, TokenData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["User Management"])


# ============================================================================
# Schemas
# ============================================================================


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_admin: bool = False
    is_active: bool = True
    email_verified: bool = False
    last_login_at: Optional[str] = None
    created_at: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    avatar_url: Optional[HttpUrl] = Field(None, description="Avatar image URL")


class AdminUpdateUserRequest(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


def _to_profile(row) -> UserProfile:
    return UserProfile(
        id=str(row["id"]),
        email=row["email"],
        full_name=row["full_name"],
        avatar_url=row["avatar_url"],
        is_admin=row["is_admin"],
        is_active=row["is_active"],
        email_verified=row["email_verified_at"] is not None,
        last_login_at=row["last_login_at"].isoformat() if row["last_login_at"] else None,
        created_at=row["created_at"].isoformat() if row["created_at"] else None,
    )


_PROFILE_COLUMNS = """
    id, email, full_name, avatar_url, is_admin, is_active,
    email_verified_at, last_login_at, created_at
"""


async def _audit(conn, actor_id: str, action: str, request: Request, details: dict) -> None:
    ip = request.client.host if request.client else None
    await conn.execute(
        """
        INSERT INTO auth.audit_logs (user_id, action, details, ip_address, user_agent)
        VALUES ($1, $2, $3, $4, $5)
        """,
        actor_id,
        action,
        details,
        ip,
        request.headers.get("user-agent"),
    )


# ============================================================================
# Current User Profile
# ============================================================================


@router.get("/users/me", response_model=UserProfile)
async def get_my_profile(
    current_user: TokenData = Depends(get_current_user),
) -> UserProfile:
    """Get the authenticated user's profile."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_PROFILE_COLUMNS} FROM auth.users WHERE id = $1",
            current_user.user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
    return _to_profile(row)


@router.patch("/users/me", response_model=UserProfile)
async def update_my_profile(
    body: UpdateProfileRequest,
    current_user: TokenData = Depends(get_current_user),
) -> UserProfile:
    """Update the authenticated user's profile (full_name, avatar_url)."""
    updates = []
    params: list = [current_user.user_id]

    if body.full_name is not None:
        params.append(body.full_name.strip())
        updates.append(f"full_name = ${len(params)}")

    if body.avatar_url is not None:
        params.append(str(body.avatar_url))
        updates.append(f"avatar_url = ${len(params)}")

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE auth.users SET {", ".join(updates)}
            WHERE id = $1
            RETURNING {_PROFILE_COLUMNS}
            """,
            *params,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

    return _to_profile(row)


# ============================================================================
# Admin: User Administration
# ============================================================================


@router.get("/admin/users", response_model=list[UserProfile])
async def admin_list_users(
    response: Response,
    is_active: Optional[bool] = Query(None),
    is_admin: Optional[bool] = Query(None),
    email: Optional[str] = Query(None, description="Email substring search"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: TokenData = Depends(get_current_admin),
) -> list[UserProfile]:
    """List all users with filters and pagination (admin only).

    Sets X-Total-Count header for pagination.
    """
    conditions = []
    params: list = []

    if is_active is not None:
        params.append(is_active)
        conditions.append(f"is_active = ${len(params)}")

    if is_admin is not None:
        params.append(is_admin)
        conditions.append(f"is_admin = ${len(params)}")

    if email:
        params.append(f"%{email}%")
        conditions.append(f"email ILIKE ${len(params)}")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with PostgreSQLPool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM auth.users {where}", *params
        )

        params.extend([limit, offset])
        rows = await conn.fetch(
            f"""
            SELECT {_PROFILE_COLUMNS} FROM auth.users {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )

    response.headers["X-Total-Count"] = str(total)
    return [_to_profile(r) for r in rows]


@router.get("/admin/users/{user_id}", response_model=UserProfile)
async def admin_get_user(
    user_id: UUID,
    admin: TokenData = Depends(get_current_admin),
) -> UserProfile:
    """Get a specific user's details (admin only)."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_PROFILE_COLUMNS} FROM auth.users WHERE id = $1",
            user_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
    return _to_profile(row)


@router.patch("/admin/users/{user_id}", response_model=UserProfile)
async def admin_update_user(
    user_id: UUID,
    body: AdminUpdateUserRequest,
    request: Request,
    admin: TokenData = Depends(get_current_admin),
) -> UserProfile:
    """Update a user's is_active / is_admin flags (admin only). Logged to audit."""
    updates = []
    params: list = [user_id]
    changes: dict = {}

    if body.is_active is not None:
        params.append(body.is_active)
        updates.append(f"is_active = ${len(params)}")
        changes["is_active"] = body.is_active

    if body.is_admin is not None:
        params.append(body.is_admin)
        updates.append(f"is_admin = ${len(params)}")
        changes["is_admin"] = body.is_admin

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE auth.users SET {", ".join(updates)}
            WHERE id = $1
            RETURNING {_PROFILE_COLUMNS}
            """,
            *params,
        )
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        await _audit(
            conn, admin.user_id, "admin.user_updated", request,
            {"target_user_id": str(user_id), "changes": changes},
        )

    logger.info(f"Admin {admin.user_id} updated user {user_id}: {changes}")
    return _to_profile(row)


@router.delete("/admin/users/{user_id}", status_code=204)
async def admin_delete_user(
    user_id: UUID,
    request: Request,
    admin: TokenData = Depends(get_current_admin),
) -> None:
    """Soft-delete a user (set is_active=false). Admins cannot delete themselves."""
    if str(user_id) == str(admin.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete your own account",
        )

    async with PostgreSQLPool.acquire() as conn:
        result = await conn.execute(
            "UPDATE auth.users SET is_active = false WHERE id = $1",
            user_id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="User not found")

        await _audit(
            conn, admin.user_id, "admin.user_deleted", request,
            {"target_user_id": str(user_id)},
        )

    logger.info(f"Admin {admin.user_id} soft-deleted user {user_id}")
