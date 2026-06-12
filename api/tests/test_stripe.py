"""Tests for Stripe billing: signatures, plans, checkout, webhooks, usage limits."""
import hashlib
import hmac
import json
import os
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app
from auth.jwt_handler import create_access_token
from services.stripe_service import (
    PLANS,
    plan_for_price_id,
    plan_limit,
    verify_stripe_signature,
)
from services.usage_service import is_over_limit

client = TestClient(app)

WEBHOOK_SECRET = "whsec_test_secret"


def auth_header(user_id=None) -> dict:
    token = create_access_token(user_id=str(user_id or uuid4()), email="pay@example.com")
    return {"Authorization": f"Bearer {token}"}


def sign(payload: bytes, secret: str = WEBHOOK_SECRET, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


# ============================================================================
# Signature verification
# ============================================================================


class TestSignatureVerification:
    PAYLOAD = b'{"id": "evt_123", "type": "invoice.paid"}'

    @pytest.mark.unit
    def test_valid_signature_accepted(self):
        header = sign(self.PAYLOAD)
        assert verify_stripe_signature(self.PAYLOAD, header, WEBHOOK_SECRET) is True

    @pytest.mark.unit
    def test_wrong_secret_rejected(self):
        header = sign(self.PAYLOAD, secret="whsec_other")
        assert verify_stripe_signature(self.PAYLOAD, header, WEBHOOK_SECRET) is False

    @pytest.mark.unit
    def test_tampered_payload_rejected(self):
        header = sign(self.PAYLOAD)
        assert verify_stripe_signature(b'{"id":"evil"}', header, WEBHOOK_SECRET) is False

    @pytest.mark.unit
    def test_old_timestamp_rejected(self):
        """Replay guard: events older than the tolerance window fail."""
        stale = int(time.time()) - 600  # 10 minutes ago, tolerance is 5
        header = sign(self.PAYLOAD, ts=stale)
        assert verify_stripe_signature(self.PAYLOAD, header, WEBHOOK_SECRET) is False

    @pytest.mark.unit
    def test_missing_or_malformed_header_rejected(self):
        assert verify_stripe_signature(self.PAYLOAD, None, WEBHOOK_SECRET) is False
        assert verify_stripe_signature(self.PAYLOAD, "", WEBHOOK_SECRET) is False
        assert verify_stripe_signature(self.PAYLOAD, "t=abc,v1=zzz", WEBHOOK_SECRET) is False
        assert verify_stripe_signature(self.PAYLOAD, "v1=deadbeef", WEBHOOK_SECRET) is False

    @pytest.mark.unit
    def test_unconfigured_secret_rejects(self):
        assert verify_stripe_signature(self.PAYLOAD, sign(self.PAYLOAD), "") is False


# ============================================================================
# Plan catalog
# ============================================================================


class TestPlans:
    @pytest.mark.unit
    def test_plan_limits(self):
        assert plan_limit("free") == 5
        assert plan_limit("pro") == 500
        assert plan_limit("enterprise") is None  # unlimited
        assert plan_limit("bogus") == 5  # unknown → free limits

    @pytest.mark.unit
    def test_price_id_reverse_lookup(self):
        with patch.dict(os.environ, {"STRIPE_PRICE_PRO": "price_pro_123"}):
            assert plan_for_price_id("price_pro_123") == "pro"
            assert plan_for_price_id("price_unknown") == "free"
            assert plan_for_price_id("") == "free"

    @pytest.mark.integration
    def test_plans_endpoint_is_public(self):
        resp = client.get("/api/v1/billing/plans")
        assert resp.status_code == 200
        plans = {p["id"]: p for p in resp.json()["plans"]}
        assert plans["free"]["price_usd"] == 0
        assert plans["pro"]["price_usd"] == 29
        assert plans["enterprise"]["price_usd"] is None
        assert set(plans) == set(PLANS)


# ============================================================================
# Usage limits
# ============================================================================


class TestUsageLimits:
    @pytest.mark.unit
    def test_is_over_limit(self):
        assert is_over_limit(5, 5) is True
        assert is_over_limit(4, 5) is False
        assert is_over_limit(10_000, None) is False  # unlimited

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_free_user_blocked_at_limit(self):
        from services import usage_service

        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="free")), \
             patch.object(usage_service, "get_monthly_usage", new=AsyncMock(return_value=5)):
            from fastapi import HTTPException
            from auth.security import TokenData

            user = TokenData(user_id=str(uuid4()), email="f@e.com")
            with pytest.raises(HTTPException) as exc:
                await usage_service.require_within_usage_limit(user)

        assert exc.value.status_code == 403
        assert "Upgrade to Pro" in exc.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pro_user_over_limit_offered_enterprise(self):
        from services import usage_service

        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="pro")), \
             patch.object(usage_service, "get_monthly_usage", new=AsyncMock(return_value=500)):
            from fastapi import HTTPException
            from auth.security import TokenData

            user = TokenData(user_id=str(uuid4()), email="p@e.com")
            with pytest.raises(HTTPException) as exc:
                await usage_service.require_within_usage_limit(user)

        assert "Enterprise" in exc.value.detail

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_under_limit_passes_through(self):
        from services import usage_service
        from auth.security import TokenData

        user = TokenData(user_id=str(uuid4()), email="ok@e.com")
        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="free")), \
             patch.object(usage_service, "get_monthly_usage", new=AsyncMock(return_value=2)):
            result = await usage_service.require_within_usage_limit(user)
        assert result is user

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_enterprise_never_limited(self):
        from services import usage_service
        from auth.security import TokenData

        user = TokenData(user_id=str(uuid4()), email="ent@e.com")
        with patch.object(usage_service, "get_user_plan", new=AsyncMock(return_value="enterprise")):
            # get_monthly_usage must not even be needed
            result = await usage_service.require_within_usage_limit(user)
        assert result is user


# ============================================================================
# Checkout endpoint
# ============================================================================


class TestCheckout:
    @pytest.mark.integration
    def test_checkout_requires_auth(self):
        resp = client.post("/api/v1/billing/checkout", json={"plan": "pro"})
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_unknown_plan_rejected(self):
        resp = client.post(
            "/api/v1/billing/checkout", json={"plan": "platinum"}, headers=auth_header()
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_free_plan_needs_no_checkout(self):
        resp = client.post(
            "/api/v1/billing/checkout", json={"plan": "free"}, headers=auth_header()
        )
        assert resp.status_code == 422

    @pytest.mark.integration
    def test_enterprise_routes_to_sales(self):
        resp = client.post(
            "/api/v1/billing/checkout", json={"plan": "enterprise"}, headers=auth_header()
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["contact_sales"] is True
        assert body["checkout_url"] is None

    @pytest.mark.integration
    def test_pro_checkout_creates_session(self):
        with patch(
            "routers.billing.stripe_service.create_checkout_session",
            new=AsyncMock(return_value={"session_id": "cs_123", "checkout_url": "https://checkout.stripe.com/c/cs_123"}),
        ):
            resp = client.post(
                "/api/v1/billing/checkout", json={"plan": "pro"}, headers=auth_header()
            )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "cs_123"
        assert resp.json()["checkout_url"].startswith("https://checkout.stripe.com/")


# ============================================================================
# Webhook endpoint + event handlers
# ============================================================================


def make_subscription_event(event_type: str, status: str = "active",
                            price_id: str = "price_pro_123") -> dict:
    return {
        "id": f"evt_{uuid4().hex[:12]}",
        "type": event_type,
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": status,
                "metadata": {"user_id": str(uuid4())},
                "items": {"data": [{"price": {"id": price_id}}]},
                "current_period_end": int(time.time()) + 86400 * 30,
            }
        },
    }


class TestStripeWebhook:
    @pytest.mark.integration
    def test_webhook_rejects_bad_signature(self):
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            resp = client.post(
                "/webhooks/stripe",
                content=b"{}",
                headers={"Stripe-Signature": "t=1,v1=bad", "Content-Type": "application/json"},
            )
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_webhook_rejects_missing_signature(self):
        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            resp = client.post("/webhooks/stripe", json={})
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_webhook_accepts_valid_signature_and_dispatches(self):
        event = make_subscription_event("customer.subscription.created")
        payload = json.dumps(event).encode()

        with patch.dict(os.environ, {"STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET}), \
             patch("routers.billing.process_stripe_event", new=AsyncMock()) as dispatch:
            resp = client.post(
                "/webhooks/stripe",
                content=payload,
                headers={
                    "Stripe-Signature": sign(payload),
                    "Content-Type": "application/json",
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}
        dispatch.assert_awaited_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_created_sets_pro_plan(self):
        from services import stripe_service as svc

        event = make_subscription_event("customer.subscription.created")
        sub = event["data"]["object"]
        user_id = sub["metadata"]["user_id"]

        with patch.dict(os.environ, {"STRIPE_PRICE_PRO": "price_pro_123"}), \
             patch.object(svc, "was_event_processed", new=AsyncMock(return_value=False)), \
             patch.object(svc, "upsert_subscription", new=AsyncMock()) as upsert, \
             patch.object(svc, "set_user_plan", new=AsyncMock()) as set_plan:
            await svc.process_stripe_event(event)

        upsert.assert_awaited_once()
        set_plan.assert_awaited_once_with(user_id, "pro")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_subscription_deleted_downgrades_to_free(self):
        from services import stripe_service as svc

        event = make_subscription_event("customer.subscription.deleted", status="canceled")
        user_id = event["data"]["object"]["metadata"]["user_id"]

        with patch.object(svc, "was_event_processed", new=AsyncMock(return_value=False)), \
             patch.object(svc, "upsert_subscription", new=AsyncMock()), \
             patch.object(svc, "set_user_plan", new=AsyncMock()) as set_plan:
            await svc.process_stripe_event(event)

        set_plan.assert_awaited_once_with(user_id, "free")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_past_due_subscription_does_not_grant_plan(self):
        from services import stripe_service as svc

        event = make_subscription_event("customer.subscription.updated", status="past_due")

        with patch.dict(os.environ, {"STRIPE_PRICE_PRO": "price_pro_123"}), \
             patch.object(svc, "was_event_processed", new=AsyncMock(return_value=False)), \
             patch.object(svc, "upsert_subscription", new=AsyncMock()), \
             patch.object(svc, "set_user_plan", new=AsyncMock()) as set_plan:
            await svc.process_stripe_event(event)

        set_plan.assert_not_awaited()  # grace period: keep current plan

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_payment_failed_sends_alert_email(self):
        from services import stripe_service as svc
        from services import email_service

        event = {
            "id": "evt_fail1",
            "type": "invoice.payment_failed",
            "data": {"object": {
                "id": "in_123", "customer": "cus_123",
                "customer_email": "payer@example.com",
                "amount_due": 2900, "status": "open", "metadata": {},
            }},
        }

        with patch.object(svc, "was_event_processed", new=AsyncMock(return_value=False)), \
             patch.object(svc, "resolve_user_id", new=AsyncMock(return_value=str(uuid4()))), \
             patch.object(svc, "record_invoice", new=AsyncMock()), \
             patch.object(email_service, "_send", new=AsyncMock()) as send:
            await svc.process_stripe_event(event)

        send.assert_awaited_once()
        assert "Payment failed" in send.await_args.args[1]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_replayed_event_skipped(self):
        from services import stripe_service as svc

        event = make_subscription_event("customer.subscription.created")
        with patch.object(svc, "was_event_processed", new=AsyncMock(return_value=True)), \
             patch.object(svc, "set_user_plan", new=AsyncMock()) as set_plan:
            await svc.process_stripe_event(event)
        set_plan.assert_not_awaited()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_event_processing_never_raises(self):
        from services import stripe_service as svc

        event = make_subscription_event("customer.subscription.created")
        with patch.object(
            svc, "was_event_processed", new=AsyncMock(side_effect=RuntimeError("db down"))
        ):
            await svc.process_stripe_event(event)  # must not raise


# ============================================================================
# Billing info endpoints (auth gates)
# ============================================================================


class TestBillingEndpoints:
    @pytest.mark.integration
    def test_protected_endpoints_require_auth(self):
        assert client.get("/api/v1/billing/current").status_code == 401
        assert client.get("/api/v1/billing").status_code == 401
        assert client.get("/api/v1/billing/invoices").status_code == 401
        assert client.post("/api/v1/billing/customer-portal").status_code == 401
        assert client.get(f"/api/v1/billing/invoices/{uuid4()}").status_code == 401
