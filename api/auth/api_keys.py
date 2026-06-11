"""Service API key management for worker services.

Keys are generated once, shown once, and only the SHA-256 hash is stored.
Keys expire after 90 days and must be rotated.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import Header, HTTPException, status

from api.clients import PostgreSQLPool

logger = logging.getLogger(__name__)

KEY_LIFETIME_DAYS = 90
KEY_PREFIX = "ak_"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_service_key(service_name: str, scopes: list[str]) -> dict:
    """Generate a new API key for a service.

    Returns the raw key exactly once — it cannot be retrieved later.
    """
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    key_hash = _hash_key(raw_key)
    expires_at = datetime.now(timezone.utc) + timedelta(days=KEY_LIFETIME_DAYS)

    async with PostgreSQLPool.acquire() as conn:
        key_id = await conn.fetchval(
            """
            INSERT INTO auth.service_api_keys
                (service_name, key_hash, key_prefix, scopes, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            service_name,
            key_hash,
            raw_key[:12],
            scopes,
            expires_at,
        )

    logger.info(f"Service API key created: {service_name} ({raw_key[:12]}...)")
    return {
        "id": str(key_id),
        "api_key": raw_key,  # shown once
        "service_name": service_name,
        "scopes": scopes,
        "expires_at": expires_at.isoformat(),
    }


async def verify_service_key(raw_key: str, required_scope: Optional[str] = None) -> dict:
    """Verify a service API key. Raises 401/403 on failure."""
    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid API key")

    key_hash = _hash_key(raw_key)

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, service_name, scopes, expires_at, revoked_at
            FROM auth.service_api_keys
            WHERE key_hash = $1
            """,
            key_hash,
        )

        if not row or row["revoked_at"] is not None:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if row["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API key expired — rotate it")

        if required_scope and required_scope not in row["scopes"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key lacks required scope",
            )

        await conn.execute(
            "UPDATE auth.service_api_keys SET last_used_at = now() WHERE id = $1",
            row["id"],
        )

    return {"service_name": row["service_name"], "scopes": row["scopes"]}


async def revoke_service_key(key_id: UUID) -> None:
    """Immediately revoke a leaked or retired key."""
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            "UPDATE auth.service_api_keys SET revoked_at = now() WHERE id = $1",
            key_id,
        )
    logger.warning(f"Service API key revoked: {key_id}")


async def list_service_keys() -> list[dict]:
    """List keys (prefix only, never the key) with rotation status."""
    async with PostgreSQLPool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, service_name, key_prefix, scopes,
                   last_used_at, expires_at, revoked_at, created_at
            FROM auth.service_api_keys
            ORDER BY created_at DESC
            """
        )
    now = datetime.now(timezone.utc)
    return [
        {
            "id": str(r["id"]),
            "service_name": r["service_name"],
            "key_prefix": r["key_prefix"] + "...",
            "scopes": r["scopes"],
            "expires_at": r["expires_at"].isoformat(),
            "needs_rotation": r["expires_at"] < now + timedelta(days=14),
            "revoked": r["revoked_at"] is not None,
        }
        for r in rows
    ]


async def get_service_identity(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> dict:
    """FastAPI dependency: authenticate a worker service via X-API-Key header."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    return await verify_service_key(x_api_key)
