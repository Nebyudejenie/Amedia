"""Telegram integration: webhook receiver + account-link exchange."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from clients import PostgreSQLPool
from auth.security import get_current_user, TokenData
from services.telegram_bot import process_update, send_message, verify_webhook_secret

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Telegram"])


@router.post("/webhooks/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict:
    """Receive Telegram updates.

    No JWT here — Telegram authenticates via the secret token header we
    registered with setWebhook (constant-time compared). Always returns
    200 for verified updates so Telegram doesn't retry-storm us.
    """
    if not verify_webhook_secret(x_telegram_bot_api_secret_token):
        logger.warning("Telegram webhook: bad or missing secret token")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}  # malformed body: ack and drop

    await process_update(update)
    return {"ok": True}


class LinkRequest(BaseModel):
    token: str = Field(..., min_length=6, max_length=12, description="Token from /start")


@router.post("/api/v1/telegram/link")
async def link_telegram_account(
    body: LinkRequest,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Exchange a /start token: bind the Telegram account to this user."""
    async with PostgreSQLPool.acquire() as conn:
        token_row = await conn.fetchrow(
            """
            SELECT token, telegram_user_id, telegram_chat_id, expires_at, used_at
            FROM auth.telegram_link_tokens
            WHERE token = $1
            """,
            body.token.strip(),
        )

        if (
            not token_row
            or token_row["used_at"] is not None
            or token_row["expires_at"] < datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=401, detail="Invalid or expired link token")

        # One Telegram account ↔ one Arada account
        taken = await conn.fetchval(
            "SELECT 1 FROM auth.users WHERE telegram_user_id = $1 AND id != $2",
            token_row["telegram_user_id"],
            current_user.user_id,
        )
        if taken:
            raise HTTPException(status_code=409, detail="Telegram account already linked elsewhere")

        await conn.execute(
            """
            UPDATE auth.users
            SET telegram_user_id = $2, telegram_linked_at = now()
            WHERE id = $1
            """,
            current_user.user_id,
            token_row["telegram_user_id"],
        )
        await conn.execute(
            "UPDATE auth.telegram_link_tokens SET used_at = now() WHERE token = $1",
            token_row["token"],
        )
        await conn.execute(
            "INSERT INTO auth.audit_logs (user_id, action) VALUES ($1, 'telegram.linked')",
            current_user.user_id,
        )

    logger.info(f"Telegram linked: user={current_user.user_id}")
    # Confirm in the Telegram chat (best-effort)
    await send_message(token_row["telegram_chat_id"], "🎉 *Account linked!* Try /submit")

    return {"detail": "Telegram account linked"}


@router.delete("/api/v1/telegram/link", status_code=204)
async def unlink_telegram_account(
    current_user: TokenData = Depends(get_current_user),
) -> None:
    """Remove the Telegram association from the current account."""
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            """
            UPDATE auth.users
            SET telegram_user_id = NULL, telegram_linked_at = NULL
            WHERE id = $1
            """,
            current_user.user_id,
        )
