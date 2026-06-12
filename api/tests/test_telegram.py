"""Tests for Telegram bot integration."""
import os
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app
from auth.jwt_handler import create_access_token
from services.telegram_bot import (
    extract_domain,
    format_status_line,
    generate_link_token,
    parse_command,
    parse_submit_args,
    url_hash,
    verify_webhook_secret,
)

client = TestClient(app)

WEBHOOK_SECRET = "test-telegram-webhook-secret"


def webhook_headers(secret: str = WEBHOOK_SECRET) -> dict:
    return {"X-Telegram-Bot-Api-Secret-Token": secret}


def make_update(text: str, user_id: int = 11111, chat_id: int = 22222) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 100,
            "from": {"id": user_id, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


# ============================================================================
# Pure helpers
# ============================================================================


class TestCommandParsing:
    @pytest.mark.unit
    def test_parses_command_and_args(self):
        assert parse_command("/submit https://e.com #ai") == ("submit", "https://e.com #ai")
        assert parse_command("/start") == ("start", "")
        assert parse_command("/help@AradaBot extra") == ("help", "extra")

    @pytest.mark.unit
    def test_non_commands(self):
        assert parse_command("hello there") == ("", "hello there")
        assert parse_command("") == ("", "")

    @pytest.mark.unit
    def test_submit_args_url_and_hash_tags(self):
        url, tags = parse_submit_args("https://example.com/post #tech #ai")
        assert url == "https://example.com/post"
        assert tags == ["tech", "ai"]

    @pytest.mark.unit
    def test_submit_args_comma_separated_tags(self):
        url, tags = parse_submit_args("https://e.com/a tech,ai,news")
        assert url == "https://e.com/a"
        assert tags == ["tech", "ai", "news"]

    @pytest.mark.unit
    def test_submit_args_no_url(self):
        url, tags = parse_submit_args("#justtags no-url-here")
        assert url is None

    @pytest.mark.unit
    def test_submit_args_caps_tags_at_ten(self):
        _, tags = parse_submit_args("https://e.com " + " ".join(f"#t{i}" for i in range(15)))
        assert len(tags) == 10


class TestHelpers:
    @pytest.mark.unit
    def test_url_hash_stable_sha256(self):
        assert url_hash("https://e.com/x") == url_hash(" https://e.com/x ")
        assert len(url_hash("https://e.com/x")) == 64

    @pytest.mark.unit
    def test_extract_domain(self):
        assert extract_domain("https://news.example.com/a/b?q=1") == "news.example.com"
        assert extract_domain("not a url") == ""

    @pytest.mark.unit
    def test_link_token_shape(self):
        tokens = {generate_link_token() for _ in range(50)}
        assert all(len(t) == 6 for t in tokens)
        assert len(tokens) == 50  # no collisions in a small sample
        # No ambiguous characters
        assert not any(c in t for t in tokens for c in "0O1lI")

    @pytest.mark.unit
    def test_status_line_formatting(self):
        line = format_status_line(
            {"url": "https://e.com/a", "domain": "e.com", "status": "complete",
             "sentiment_score": 0.82}
        )
        assert "✅" in line and "+0.82" in line

        pending = format_status_line(
            {"url": "https://e.com/b", "domain": "e.com", "status": "pending",
             "sentiment_score": None}
        )
        assert "⏳" in pending and "sentiment" not in pending


# ============================================================================
# Webhook signature verification
# ============================================================================


class TestWebhookVerification:
    @pytest.mark.unit
    def test_secret_comparison(self):
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "s3cret"}):
            assert verify_webhook_secret("s3cret") is True
            assert verify_webhook_secret("wrong") is False
            assert verify_webhook_secret(None) is False

    @pytest.mark.unit
    def test_unconfigured_secret_rejects_everything(self):
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": ""}):
            assert verify_webhook_secret("anything") is False

    @pytest.mark.integration
    def test_webhook_rejects_missing_secret(self):
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            resp = client.post("/webhooks/telegram", json=make_update("/help"))
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_webhook_rejects_wrong_secret(self):
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            resp = client.post(
                "/webhooks/telegram",
                json=make_update("/help"),
                headers=webhook_headers("wrong-secret"),
            )
        assert resp.status_code == 403

    @pytest.mark.integration
    def test_webhook_accepts_valid_secret(self):
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": WEBHOOK_SECRET}), \
             patch("routers.telegram.process_update", new=AsyncMock()) as mock_process:
            resp = client.post(
                "/webhooks/telegram",
                json=make_update("/help"),
                headers=webhook_headers(),
            )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_process.assert_awaited_once()

    @pytest.mark.integration
    def test_webhook_acks_malformed_body(self):
        """Garbage payloads are acked (200) so Telegram doesn't retry-storm."""
        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            resp = client.post(
                "/webhooks/telegram",
                content=b"not-json",
                headers={**webhook_headers(), "Content-Type": "application/json"},
            )
        assert resp.status_code == 200


# ============================================================================
# Command behavior (DB + Telegram API mocked)
# ============================================================================


class TestCommands:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_without_link_prompts_start(self):
        from services import telegram_bot

        with patch.object(telegram_bot, "get_linked_user_id", new=AsyncMock(return_value=None)), \
             patch.object(telegram_bot, "send_message", new=AsyncMock()) as send:
            await telegram_bot.handle_submit(22222, 11111, 100, "https://e.com/a")

        text = send.await_args.args[1]
        assert "/start" in text

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_without_url_shows_usage(self):
        from services import telegram_bot

        with patch.object(telegram_bot, "get_linked_user_id", new=AsyncMock(return_value="u1")), \
             patch.object(telegram_bot, "send_message", new=AsyncMock()) as send:
            await telegram_bot.handle_submit(22222, 11111, 100, "")

        assert "Usage:" in send.await_args.args[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_rejects_internal_url(self):
        """SSRF guard applies to bot submissions too."""
        from services import telegram_bot

        with patch.object(telegram_bot, "get_linked_user_id", new=AsyncMock(return_value="u1")), \
             patch.object(telegram_bot, "send_message", new=AsyncMock()) as send:
            await telegram_bot.handle_submit(22222, 11111, 100, "http://192.168.1.200:8000/x")

        assert "Invalid URL" in send.await_args.args[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_rate_limited(self):
        from services import telegram_bot

        with patch.object(telegram_bot, "get_linked_user_id", new=AsyncMock(return_value="u1")), \
             patch.object(telegram_bot, "is_rate_limited", new=AsyncMock(return_value=True)), \
             patch.object(telegram_bot, "send_message", new=AsyncMock()) as send:
            await telegram_bot.handle_submit(22222, 11111, 100, "https://example.com/article")

        assert "Limit reached" in send.await_args.args[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unknown_command_sends_help(self):
        from services import telegram_bot

        with patch.object(telegram_bot, "send_message", new=AsyncMock()) as send:
            await telegram_bot.process_update(make_update("/bogus"))

        assert "Arada Bot" in send.await_args.args[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_update_never_raises(self):
        from services import telegram_bot

        # DB unavailable → handler raises internally → swallowed + logged
        with patch.object(
            telegram_bot, "handle_start", new=AsyncMock(side_effect=RuntimeError("db down"))
        ):
            await telegram_bot.process_update(make_update("/start"))  # must not raise


# ============================================================================
# Link exchange endpoint
# ============================================================================


class TestLinkEndpoint:
    @pytest.mark.integration
    def test_link_requires_auth(self):
        resp = client.post("/api/v1/telegram/link", json={"token": "ABC234"})
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_link_token_length_validated(self):
        token = create_access_token(user_id=str(uuid4()), email="tg@example.com")
        resp = client.post(
            "/api/v1/telegram/link",
            json={"token": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_unlink_requires_auth(self):
        resp = client.delete("/api/v1/telegram/link")
        assert resp.status_code == 401
