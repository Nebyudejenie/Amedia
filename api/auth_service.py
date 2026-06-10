"""Authentication and authorization service."""
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import settings
from clients import PostgreSQLPool

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Auth operations: tokens, passwords, users."""

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        """Verify a password against hash."""
        return pwd_context.verify(plain, hashed)

    @staticmethod
    def create_access_token(user_id: str, workspace_id: str, role: str) -> tuple[str, int]:
        """Create a JWT access token."""
        expires = datetime.utcnow() + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
        payload = {
            "sub": user_id,
            "workspace_id": workspace_id,
            "role": role,
            "exp": expires,
            "type": "access",
        }
        token = jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        return token, int(expires.timestamp())

    @staticmethod
    def create_refresh_token(user_id: str, workspace_id: str) -> str:
        """Create a JWT refresh token."""
        expires = datetime.utcnow() + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        payload = {
            "sub": user_id,
            "workspace_id": workspace_id,
            "exp": expires,
            "type": "refresh",
        }
        token = jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        return token

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            return payload
        except JWTError:
            return None

    @staticmethod
    async def get_user_by_email(email: str) -> Optional[dict]:
        """Get user by email."""
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, email, workspace_id, role, status, password_hash, last_login_at, created_at
                   FROM auth.users WHERE email = $1 AND deleted_at IS NULL""",
                email,
            )
            return dict(row) if row else None

    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[dict]:
        """Get user by ID."""
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, email, workspace_id, role, status, last_login_at, created_at
                   FROM auth.users WHERE id = $1 AND deleted_at IS NULL""",
                user_id,
            )
            return dict(row) if row else None

    @staticmethod
    async def register_user(email: str, password: str, workspace_name: str) -> dict:
        """Register a new user."""
        async with PostgreSQLPool.acquire() as conn:
            async with conn.transaction():
                # Create workspace
                workspace_row = await conn.fetchrow(
                    """INSERT INTO auth.workspaces (name, slug, plan)
                       VALUES ($1, $2, 'free')
                       RETURNING id, name, slug, plan, created_at""",
                    workspace_name,
                    workspace_name.lower().replace(" ", "-"),
                )
                workspace_id = workspace_row["id"]

                # Create user with owner role
                password_hash = AuthService.hash_password(password)
                user_row = await conn.fetchrow(
                    """INSERT INTO auth.users (workspace_id, email, password_hash, role, status)
                       VALUES ($1, $2, $3, 'owner', 'active')
                       RETURNING id, email, workspace_id, role, status, created_at""",
                    workspace_id,
                    email,
                    password_hash,
                )
                return dict(user_row)

    @staticmethod
    async def update_last_login(user_id: str) -> None:
        """Update user's last login timestamp."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                "UPDATE auth.users SET last_login_at = now() WHERE id = $1",
                user_id,
            )

    @staticmethod
    async def create_api_key(workspace_id: str, name: str, scopes: list[str]) -> dict:
        """Create an API key."""
        import secrets

        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        key_hash = AuthService.hash_password(secret)

        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO auth.api_keys (workspace_id, name, prefix, key_hash, scopes)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING id, name, prefix, scopes, created_at""",
                workspace_id,
                name,
                prefix,
                key_hash,
                scopes,
            )
            result = dict(row)
            result["secret"] = secret
            return result

    @staticmethod
    async def verify_api_key(api_key: str) -> Optional[dict]:
        """Verify an API key and return workspace info."""
        # Extract prefix from key format "prefix.secret"
        parts = api_key.split(".", 1)
        if len(parts) != 2:
            return None

        prefix, secret = parts
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, workspace_id, key_hash, scopes FROM auth.api_keys
                   WHERE prefix = $1 AND deleted_at IS NULL""",
                prefix,
            )
            if not row:
                return None

            # Verify secret hash
            if not AuthService.verify_password(secret, row["key_hash"]):
                return None

            # Update last_used_at
            await conn.execute(
                "UPDATE auth.api_keys SET last_used_at = now() WHERE id = $1",
                row["id"],
            )

            return {
                "api_key_id": row["id"],
                "workspace_id": row["workspace_id"],
                "scopes": row["scopes"],
            }
