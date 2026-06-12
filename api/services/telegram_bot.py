"""Telegram bot: command processing + Bot API client.

Update flow: Telegram → POST /webhooks/telegram (secret-token verified)
→ process_update() → command handler → sendMessage reply.

The bot token never appears in logs or outgoing message text.
"""
import hashlib
import hmac
import logging
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from clients import PostgreSQLPool
from middleware.validation import validate_url

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://arada.fun")

SUBMIT_LIMIT_PER_HOUR = int(os.getenv("TELEGRAM_SUBMIT_LIMIT_PER_HOUR", "10"))
LINK_TOKEN_TTL_MINUTES = 15

# Unambiguous alphabet for short link tokens (no 0/O/1/l/I)
_TOKEN_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"

HELP_TEXT = (
    "*Arada Bot — commands*\n\n"
    "/start — link your Arada account\n"
    "/submit `<url>` `#tags` — submit an article for analysis\n"
    "/status — your last 5 submissions\n"
    "/stats — your usage totals\n"
    "/settings — account + notification info\n"
    "/help — this message"
)


def get_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    return token


def verify_webhook_secret(header_value: Optional[str]) -> bool:
    """Constant-time check of X-Telegram-Bot-Api-Secret-Token."""
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected or not header_value:
        return False
    return hmac.compare_digest(expected, header_value)


# ============================================================================
# Pure helpers (unit-testable without network/DB)
# ============================================================================


def parse_command(text: str) -> tuple[str, str]:
    """'/submit https://x #a' → ('submit', 'https://x #a').

    Strips the @BotName suffix Telegram appends in groups.
    """
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", text
    first, _, rest = text.partition(" ")
    command = first[1:].split("@")[0].lower()
    return command, rest.strip()


def parse_submit_args(args: str) -> tuple[Optional[str], list[str]]:
    """Extract (url, tags) from '/submit' arguments.

    Tags may be '#tag' tokens or comma/space-separated words after the URL.
    """
    tokens = args.replace(",", " ").split()
    url = next((t for t in tokens if t.lower().startswith(("http://", "https://"))), None)
    tags = [
        t.lstrip("#").lower()
        for t in tokens
        if t != url and t.strip("#")
    ][:10]
    return url, tags


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()


def extract_domain(url: str) -> str:
    try:
        return (urlparse(url).hostname or "")[:255]
    except ValueError:
        return ""


def generate_link_token() -> str:
    """6-char unambiguous token for the account-linking URL."""
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(6))


STATUS_EMOJI = {"pending": "⏳", "analyzing": "🔍", "complete": "✅", "error": "⚠️"}


def format_status_line(row: dict) -> str:
    """One /status line: '✅ [Title or domain] — sentiment +0.82'."""
    emoji = STATUS_EMOJI.get(row["status"], "⏳")
    label = row.get("domain") or row["url"][:50]
    line = f"{emoji} [{label}]({row['url']}) — {row['status']}"
    if row["status"] == "complete" and row.get("sentiment_score") is not None:
        score = float(row["sentiment_score"])
        line += f", sentiment {'+' if score >= 0 else ''}{score:.2f}"
    return line


# ============================================================================
# Bot API client
# ============================================================================


async def send_message(
    chat_id: int,
    text: str,
    reply_to: Optional[int] = None,
    buttons: Optional[list[list[dict]]] = None,
) -> None:
    """sendMessage with Markdown + optional inline keyboard. Never raises."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
        payload["allow_sending_without_reply"] = True
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{TELEGRAM_API}/bot{get_bot_token()}/sendMessage", json=payload
            )
            if resp.status_code != 200:
                logger.warning(f"Telegram sendMessage failed: HTTP {resp.status_code}")
    except Exception as e:
        # A messaging failure must never break webhook processing
        logger.error(f"Telegram sendMessage error: {type(e).__name__}")


# ============================================================================
# DB helpers
# ============================================================================


async def get_linked_user_id(telegram_user_id: int) -> Optional[str]:
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchval(
            "SELECT id FROM auth.users WHERE telegram_user_id = $1", telegram_user_id
        )
        return str(row) if row else None


async def is_rate_limited(telegram_user_id: int) -> bool:
    """True when the user already submitted SUBMIT_LIMIT_PER_HOUR in the last hour."""
    async with PostgreSQLPool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM content.telegram_submissions
            WHERE telegram_user_id = $1 AND created_at > now() - INTERVAL '1 hour'
            """,
            telegram_user_id,
        )
        return (count or 0) >= SUBMIT_LIMIT_PER_HOUR


# ============================================================================
# Command handlers
# ============================================================================


async def handle_start(chat_id: int, telegram_user_id: int, message_id: int) -> None:
    """Generate a linking token and send the linking URL."""
    if await get_linked_user_id(telegram_user_id):
        await send_message(chat_id, "✅ Your account is already linked. Try /submit!", message_id)
        return

    token = generate_link_token()
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO auth.telegram_link_tokens
                (token, telegram_user_id, telegram_chat_id, expires_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (token) DO NOTHING
            """,
            token,
            telegram_user_id,
            chat_id,
            datetime.now(timezone.utc) + timedelta(minutes=LINK_TOKEN_TTL_MINUTES),
        )

    await send_message(
        chat_id,
        "👋 *Welcome to Arada!*\n\n"
        f"To link this Telegram account, open:\n{FRONTEND_URL}/link?token={token}\n\n"
        f"_The link expires in {LINK_TOKEN_TTL_MINUTES} minutes._",
        message_id,
    )


async def handle_submit(chat_id: int, telegram_user_id: int, message_id: int, args: str) -> None:
    """Validate + store a URL submission, reply with inline action buttons."""
    user_id = await get_linked_user_id(telegram_user_id)
    if not user_id:
        await send_message(chat_id, "🔗 Link your account first — send /start", message_id)
        return

    url, tags = parse_submit_args(args)
    if not url:
        await send_message(
            chat_id, "Usage: `/submit https://example.com #tag1 #tag2`", message_id
        )
        return

    # Same SSRF/format guard the API uses for webhook URLs
    url_error = validate_url(url)
    if url_error:
        await send_message(chat_id, f"❌ Invalid URL: {url_error}", message_id)
        return

    if await is_rate_limited(telegram_user_id):
        await send_message(
            chat_id,
            f"🚦 Limit reached: {SUBMIT_LIMIT_PER_HOUR} submissions per hour. Try again later.",
            message_id,
        )
        return

    async with PostgreSQLPool.acquire() as conn:
        submission_id = await conn.fetchval(
            """
            INSERT INTO content.telegram_submissions
                (user_id, telegram_user_id, telegram_chat_id, url, url_hash, domain, tags)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (url_hash) DO NOTHING
            RETURNING id
            """,
            user_id,
            telegram_user_id,
            chat_id,
            url[:1000],
            url_hash(url),
            extract_domain(url),
            tags,
        )

    if submission_id is None:
        await send_message(chat_id, "♻️ Already submitted — duplicates are skipped.", message_id)
        return

    logger.info(f"Telegram submission {submission_id} from tg:{telegram_user_id}")
    await send_message(
        chat_id,
        f"✅ *Article submitted!* Analyzing…\n_{extract_domain(url)}_"
        + (f"\nTags: {', '.join(tags)}" if tags else ""),
        message_id,
        buttons=[[
            {"text": "🗑 Delete", "callback_data": f"del:{submission_id}"},
            {"text": "📊 Status", "callback_data": "status"},
        ]],
    )


async def handle_status(chat_id: int, telegram_user_id: int, message_id: int) -> None:
    """Last 5 submissions with status emoji + sentiment when complete."""
    user_id = await get_linked_user_id(telegram_user_id)
    if not user_id:
        await send_message(chat_id, "🔗 Link your account first — send /start", message_id)
        return

    async with PostgreSQLPool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT url, domain, status, sentiment_score
            FROM content.telegram_submissions
            WHERE telegram_user_id = $1
            ORDER BY created_at DESC LIMIT 5
            """,
            telegram_user_id,
        )

    if not rows:
        await send_message(chat_id, "📭 No submissions yet. Try /submit!", message_id)
        return

    lines = "\n".join(format_status_line(dict(r)) for r in rows)
    await send_message(chat_id, f"📰 *Your recent submissions*\n\n{lines}", message_id)


async def handle_stats(chat_id: int, telegram_user_id: int, message_id: int) -> None:
    user_id = await get_linked_user_id(telegram_user_id)
    if not user_id:
        await send_message(chat_id, "🔗 Link your account first — send /start", message_id)
        return

    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'complete') AS complete,
                   COUNT(*) FILTER (WHERE created_at > now() - INTERVAL '1 hour') AS last_hour
            FROM content.telegram_submissions
            WHERE telegram_user_id = $1
            """,
            telegram_user_id,
        )

    remaining = max(0, SUBMIT_LIMIT_PER_HOUR - row["last_hour"])
    await send_message(
        chat_id,
        "📊 *Your stats*\n\n"
        f"Articles submitted: *{row['total']}*\n"
        f"Analyses complete: *{row['complete']}*\n"
        f"Submissions left this hour: *{remaining}*",
        message_id,
    )


async def handle_settings(chat_id: int, telegram_user_id: int, message_id: int) -> None:
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT email, telegram_linked_at FROM auth.users WHERE telegram_user_id = $1",
            telegram_user_id,
        )

    if not row:
        await send_message(chat_id, "🔗 No linked account — send /start", message_id)
        return

    # Mask the email; never expose tokens or internal ids
    email = row["email"]
    masked = email[0] + "***" + email[email.index("@"):] if "@" in email else "***"
    linked = row["telegram_linked_at"].strftime("%Y-%m-%d") if row["telegram_linked_at"] else "—"
    await send_message(
        chat_id,
        "⚙️ *Settings*\n\n"
        f"Linked account: `{masked}`\n"
        f"Linked since: {linked}\n"
        f"Result notifications: *on* (sent to this chat)\n\n"
        f"Manage preferences: {FRONTEND_URL}/dashboard/settings",
        message_id,
    )


async def handle_callback(callback: dict) -> None:
    """Inline button presses: delete a submission or show status."""
    data = callback.get("data", "")
    chat_id = callback.get("message", {}).get("chat", {}).get("id")
    telegram_user_id = callback.get("from", {}).get("id")
    if not chat_id or not telegram_user_id:
        return

    if data.startswith("del:"):
        submission_id = data[4:]
        async with PostgreSQLPool.acquire() as conn:
            deleted = await conn.execute(
                """
                DELETE FROM content.telegram_submissions
                WHERE id = $1::uuid AND telegram_user_id = $2
                """,
                submission_id,
                telegram_user_id,
            )
        text = "🗑 Submission deleted." if deleted != "DELETE 0" else "Already gone."
        await send_message(chat_id, text)
    elif data == "status":
        await handle_status(chat_id, telegram_user_id, 0)


# ============================================================================
# Update dispatcher
# ============================================================================

COMMANDS = {
    "start": handle_start,
    "status": handle_status,
    "stats": handle_stats,
    "settings": handle_settings,
}


async def process_update(update: dict) -> None:
    """Route one Telegram update. Never raises (webhook must stay 200)."""
    try:
        if "callback_query" in update:
            await handle_callback(update["callback_query"])
            return

        message = update.get("message") or {}
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")
        telegram_user_id = message.get("from", {}).get("id")
        message_id = message.get("message_id")
        if not chat_id or not telegram_user_id or not text:
            return

        command, args = parse_command(text)

        if command == "submit":
            await handle_submit(chat_id, telegram_user_id, message_id, args)
        elif command in COMMANDS:
            await COMMANDS[command](chat_id, telegram_user_id, message_id)
        elif command == "help" or command:
            await send_message(chat_id, HELP_TEXT, message_id)
        # Non-command chatter is ignored

    except Exception:
        logger.exception("Telegram update processing failed")


async def notify_analysis_complete(submission_id: str) -> None:
    """Called by the analysis pipeline when a submission finishes."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT telegram_chat_id, url, domain, sentiment_score
            FROM content.telegram_submissions
            WHERE id = $1::uuid AND status = 'complete'
            """,
            submission_id,
        )
    if row:
        score = row["sentiment_score"]
        sentiment = (
            f"{'+' if score >= 0 else ''}{float(score):.2f}" if score is not None else "n/a"
        )
        await send_message(
            row["telegram_chat_id"],
            f"🏁 *Analysis complete*\n[{row['domain']}]({row['url']})\nSentiment: *{sentiment}*",
        )
