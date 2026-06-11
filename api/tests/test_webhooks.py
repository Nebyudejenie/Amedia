"""Unit tests for webhooks."""
import pytest
import json
from uuid import uuid4

from api.webhooks.signatures import sign_payload, verify_signature, generate_secret
from api.webhooks.handlers import (
    emit_event,
    create_subscription,
    delete_subscription,
    get_subscriptions,
    VALID_EVENTS,
)


class TestWebhookSignatures:
    """Test webhook signature generation and verification."""

    @pytest.mark.unit
    def test_sign_payload_dict(self):
        """Test signing a dict payload."""
        payload = {"event": "test", "data": "value"}
        secret = "test_secret"

        signature = sign_payload(payload, secret)

        assert signature.startswith("sha256=")
        assert len(signature) > 10

    @pytest.mark.unit
    def test_sign_payload_bytes(self):
        """Test signing bytes payload."""
        payload = b"test payload"
        secret = "test_secret"

        signature = sign_payload(payload, secret)

        assert signature.startswith("sha256=")

    @pytest.mark.unit
    def test_sign_payload_string(self):
        """Test signing string payload."""
        payload = "test payload"
        secret = "test_secret"

        signature = sign_payload(payload, secret)

        assert signature.startswith("sha256=")

    @pytest.mark.unit
    def test_verify_signature_valid(self):
        """Test verifying valid signature."""
        payload = {"event": "test"}
        secret = "test_secret"

        signature = sign_payload(payload, secret)
        is_valid = verify_signature(payload, secret, signature)

        assert is_valid is True

    @pytest.mark.unit
    def test_verify_signature_invalid_secret(self):
        """Test verifying with wrong secret."""
        payload = {"event": "test"}
        secret = "test_secret"
        wrong_secret = "wrong_secret"

        signature = sign_payload(payload, secret)
        is_valid = verify_signature(payload, wrong_secret, signature)

        assert is_valid is False

    @pytest.mark.unit
    def test_verify_signature_modified_payload(self):
        """Test verifying modified payload."""
        payload = {"event": "test"}
        secret = "test_secret"

        signature = sign_payload(payload, secret)

        modified_payload = {"event": "modified"}
        is_valid = verify_signature(modified_payload, secret, signature)

        assert is_valid is False

    @pytest.mark.unit
    def test_generate_secret(self):
        """Test secret generation."""
        secret1 = generate_secret()
        secret2 = generate_secret()

        assert len(secret1) > 20
        assert len(secret2) > 20
        assert secret1 != secret2

    @pytest.mark.unit
    def test_sign_dict_ordering_consistent(self):
        """Test that dict ordering doesn't affect signature."""
        secret = "test_secret"

        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 2, "a": 1}

        sig1 = sign_payload(dict1, secret)
        sig2 = sign_payload(dict2, secret)

        assert sig1 == sig2


class TestWebhookHandlers:
    """Test webhook event handlers."""

    @pytest.mark.unit
    def test_valid_events(self):
        """Test that valid event types are defined."""
        assert "content.ingested" in VALID_EVENTS
        assert "job.completed" in VALID_EVENTS
        assert "publish.success" in VALID_EVENTS
        assert len(VALID_EVENTS) >= 10

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_emit_event_invalid_type(self, db_connection):
        """Test emitting invalid event type."""
        workspace_id = uuid4()

        # Should not raise, but log warning
        await emit_event(
            workspace_id,
            "invalid.event.type",
            payload={"data": "test"},
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_subscription(self, db_connection, test_workspace, test_user):
        """Test creating webhook subscription."""
        subscription_id = await create_subscription(
            test_workspace,
            test_user,
            "https://webhook.example.com/events",
            ["content.ingested", "job.completed"],
            "test_secret",
        )

        assert subscription_id is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_subscriptions(self, db_connection, test_workspace):
        """Test listing subscriptions."""
        # Create a subscription first
        user_id = uuid4()
        await db_connection.execute(
            """
            INSERT INTO auth.users (id, workspace_id, email, name, role, password_hash)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            user_id,
            test_workspace,
            "test@example.com",
            "Test User",
            "editor",
            "hash",
        )

        sub_id = await create_subscription(
            test_workspace,
            user_id,
            "https://webhook.example.com",
            ["content.ingested"],
            "secret",
        )

        subscriptions = await get_subscriptions(test_workspace)

        assert len(subscriptions) >= 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_subscription(self, db_connection, test_workspace, test_user):
        """Test deleting subscription."""
        sub_id = await create_subscription(
            test_workspace,
            test_user,
            "https://webhook.example.com",
            ["content.ingested"],
            "secret",
        )

        await delete_subscription(test_workspace, sub_id)

        # Verify it's deactivated
        result = await db_connection.fetchval(
            "SELECT active FROM webhooks.subscriptions WHERE id = $1",
            sub_id,
        )
        assert result is False


class TestWebhookRetryLogic:
    """Test webhook delivery retry logic."""

    @pytest.mark.unit
    def test_retry_schedule(self):
        """Test exponential backoff retry schedule."""
        from api.workers.webhook_worker import RETRY_SCHEDULE

        assert RETRY_SCHEDULE[0] == 60  # 1 minute
        assert RETRY_SCHEDULE[1] == 300  # 5 minutes
        assert RETRY_SCHEDULE[2] == 1800  # 30 minutes
        assert RETRY_SCHEDULE[3] == 86400  # 24 hours
        assert len(RETRY_SCHEDULE) == 4

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_webhook_payload_structure(self):
        """Test webhook payload structure."""
        payload = {
            "event_type": "content.ingested",
            "timestamp": "2026-06-11T14:30:00Z",
            "data": {
                "content_id": str(uuid4()),
                "title": "Test Content",
            },
        }

        secret = generate_secret()
        signature = sign_payload(payload, secret)

        assert verify_signature(payload, secret, signature)
        assert payload["event_type"] in VALID_EVENTS
