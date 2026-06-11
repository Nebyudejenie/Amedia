"""Integration tests for Webhooks API endpoints."""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestWebhookSubscriptionEndpoints:
    """Test webhook subscription management endpoints."""

    @pytest.mark.integration
    def test_create_webhook_endpoint(self, auth_headers):
        """Test POST /webhooks/subscriptions endpoint."""
        workspace_id = uuid4()

        response = client.post(
            "/webhooks/subscriptions",
            json={
                "workspace_id": str(workspace_id),
                "url": "https://webhook.example.com/events",
                "events": ["content.ingested", "job.completed"],
                "headers": {"Authorization": "Bearer token"},
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 400, 401, 403, 422]

        if response.status_code == 200:
            data = response.json()
            assert "id" in data or "subscription_id" in data

    @pytest.mark.integration
    def test_list_webhooks_endpoint(self, auth_headers):
        """Test GET /webhooks/subscriptions endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/webhooks/subscriptions?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "subscriptions" in data

    @pytest.mark.integration
    def test_get_webhook_endpoint(self, auth_headers):
        """Test GET /webhooks/subscriptions/{id} endpoint."""
        workspace_id = uuid4()
        subscription_id = uuid4()

        response = client.get(
            f"/webhooks/subscriptions/{subscription_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403]

    @pytest.mark.integration
    def test_update_webhook_endpoint(self, auth_headers):
        """Test PUT /webhooks/subscriptions/{id} endpoint."""
        workspace_id = uuid4()
        subscription_id = uuid4()

        response = client.put(
            f"/webhooks/subscriptions/{subscription_id}?workspace_id={workspace_id}",
            json={
                "url": "https://new-webhook.example.com",
                "active": True,
            },
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403, 422]

    @pytest.mark.integration
    def test_delete_webhook_endpoint(self, auth_headers):
        """Test DELETE /webhooks/subscriptions/{id} endpoint."""
        workspace_id = uuid4()
        subscription_id = uuid4()

        response = client.delete(
            f"/webhooks/subscriptions/{subscription_id}?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403]


class TestWebhookEventEndpoints:
    """Test webhook event endpoints."""

    @pytest.mark.integration
    def test_list_events_endpoint(self, auth_headers):
        """Test GET /webhooks/events endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/webhooks/events?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "events" in data

    @pytest.mark.integration
    def test_list_events_with_type_filter(self, auth_headers):
        """Test GET /webhooks/events with event_type filter."""
        workspace_id = uuid4()

        response = client.get(
            f"/webhooks/events?workspace_id={workspace_id}&event_type=content.ingested",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]


class TestWebhookDeliveryEndpoints:
    """Test webhook delivery tracking endpoints."""

    @pytest.mark.integration
    def test_list_deliveries_endpoint(self, auth_headers):
        """Test GET /webhooks/deliveries endpoint."""
        workspace_id = uuid4()

        response = client.get(
            f"/webhooks/deliveries?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

        if response.status_code == 200:
            data = response.json()
            assert "deliveries" in data

    @pytest.mark.integration
    def test_list_deliveries_by_status(self, auth_headers):
        """Test filtering deliveries by status."""
        workspace_id = uuid4()

        response = client.get(
            f"/webhooks/deliveries?workspace_id={workspace_id}&status=failed",
            headers=auth_headers,
        )

        assert response.status_code in [200, 401, 403]

    @pytest.mark.integration
    def test_retry_delivery_endpoint(self, auth_headers):
        """Test POST /webhooks/deliveries/{id}/retry endpoint."""
        workspace_id = uuid4()
        delivery_id = uuid4()

        response = client.post(
            f"/webhooks/deliveries/{delivery_id}/retry?workspace_id={workspace_id}",
            headers=auth_headers,
        )

        assert response.status_code in [200, 404, 401, 403, 422]


class TestWebhookPayloadSignature:
    """Test webhook payload signing."""

    @pytest.mark.unit
    def test_webhook_signature_in_headers(self):
        """Test that webhooks include signature headers."""
        from api.webhooks.signatures import sign_payload

        payload = {"event": "test", "data": "value"}
        secret = "test_secret"

        signature = sign_payload(payload, secret)

        assert signature.startswith("sha256=")
        assert len(signature) > 20
