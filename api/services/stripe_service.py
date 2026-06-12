"""Stripe integration: checkout, customer portal, webhook event handling.

Implemented as a thin async client over Stripe's REST API (form-encoded)
so everything stays async-native and trivially mockable. Webhook
signatures are verified per Stripe's scheme:
    Stripe-Signature: t=<ts>,v1=<hmac_sha256(secret, f"{ts}.{body}")>
"""
import hmac
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from clients import PostgreSQLPool
from services import email_service

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300  # reject events older than 5 minutes (replay guard)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://arada.fun")


def _secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    return key


# ============================================================================
# Plan catalog
# ============================================================================

PLANS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "price_usd": 0,
        "monthly_limit": 5,
        "stripe_price_env": None,
        "features": ["5 analyses / month", "1 content source", "Community support"],
    },
    "pro": {
        "name": "Pro",
        "price_usd": 29,
        "monthly_limit": 500,
        "stripe_price_env": "STRIPE_PRICE_PRO",
        "features": ["500 analyses / month", "Unlimited sources", "Webhooks", "Email support"],
    },
    "enterprise": {
        "name": "Enterprise",
        "price_usd": None,  # custom — contact sales
        "monthly_limit": None,  # unlimited
        "stripe_price_env": None,
        "features": ["Unlimited analyses", "SLA", "Dedicated support", "Custom integrations"],
    },
}


def plan_limit(plan: str) -> Optional[int]:
    """Monthly analysis limit; None = unlimited."""
    return PLANS.get(plan, PLANS["free"])["monthly_limit"]


def price_id_for_plan(plan: str) -> Optional[str]:
    env = PLANS.get(plan, {}).get("stripe_price_env")
    return os.getenv(env) if env else None


def plan_for_price_id(price_id: str) -> str:
    """Reverse lookup used by webhook handlers."""
    for plan_key in PLANS:
        if price_id and price_id == price_id_for_plan(plan_key):
            return plan_key
    return "free"


# ============================================================================
# Signature verification (pure, unit-testable)
# ============================================================================


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    secret: Optional[str] = None,
    tolerance: int = SIGNATURE_TOLERANCE_SECONDS,
    now: Optional[int] = None,
) -> bool:
    """Validate a Stripe-Signature header against the raw request body."""
    secret = secret if secret is not None else os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret or not sig_header:
        return False

    timestamp: Optional[str] = None
    candidates: list[str] = []
    for part in sig_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            candidates.append(value)

    if not timestamp or not candidates:
        return False

    try:
        ts = int(timestamp)
    except ValueError:
        return False

    current = now if now is not None else int(time.time())
    if abs(current - ts) > tolerance:
        return False  # too old / clock-skewed → possible replay

    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, c) for c in candidates)


# ============================================================================
# Stripe REST client
# ============================================================================


async def stripe_request(method: str, path: str, data: Optional[dict] = None) -> dict:
    """Form-encoded request to Stripe. Raises httpx.HTTPStatusError on 4xx/5xx."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(
            method,
            f"{STRIPE_API}{path}",
            data=data,
            auth=(_secret_key(), ""),
        )
        resp.raise_for_status()
        return resp.json()


async def ensure_stripe_customer(user_id: str, email: str) -> str:
    """Return the user's Stripe customer id, creating one on first use."""
    async with PostgreSQLPool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT stripe_customer_id FROM auth.users WHERE id = $1", user_id
        )
    if existing:
        return existing

    customer = await stripe_request(
        "POST", "/customers", {"email": email, "metadata[user_id]": user_id}
    )
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            "UPDATE auth.users SET stripe_customer_id = $2 WHERE id = $1",
            user_id,
            customer["id"],
        )
    return customer["id"]


async def create_checkout_session(user_id: str, email: str, plan: str) -> dict:
    """Subscription-mode Checkout session for the requested plan."""
    price_id = price_id_for_plan(plan)
    if not price_id:
        raise ValueError(f"Plan '{plan}' is not purchasable via checkout")

    customer_id = await ensure_stripe_customer(user_id, email)
    session = await stripe_request(
        "POST",
        "/checkout/sessions",
        {
            "mode": "subscription",
            "customer": customer_id,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": 1,
            "success_url": f"{FRONTEND_URL}/dashboard/settings?billing=success",
            "cancel_url": f"{FRONTEND_URL}/dashboard/settings?billing=cancelled",
            "metadata[user_id]": user_id,
            "subscription_data[metadata][user_id]": user_id,
        },
    )
    return {"session_id": session["id"], "checkout_url": session["url"]}


async def create_portal_session(user_id: str, email: str) -> dict:
    """Stripe customer portal: manage payment method, view invoices, cancel."""
    customer_id = await ensure_stripe_customer(user_id, email)
    portal = await stripe_request(
        "POST",
        "/billing_portal/sessions",
        {
            "customer": customer_id,
            "return_url": f"{FRONTEND_URL}/dashboard/settings",
        },
    )
    return {"portal_url": portal["url"]}


# ============================================================================
# DB helpers (patchable seams for tests)
# ============================================================================


async def resolve_user_id(metadata: dict, customer_id: Optional[str]) -> Optional[str]:
    """Find the local user for a Stripe object (metadata first, then customer)."""
    if metadata.get("user_id"):
        return metadata["user_id"]
    if customer_id:
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT id FROM auth.users WHERE stripe_customer_id = $1", customer_id
            )
            return str(row) if row else None
    return None


async def set_user_plan(user_id: str, plan: str) -> None:
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            "UPDATE auth.users SET current_plan = $2 WHERE id = $1", user_id, plan
        )
    logger.info(f"Plan set: user={user_id} plan={plan}")


async def upsert_subscription(user_id: str, sub: dict, plan: str) -> None:
    period_end = sub.get("current_period_end")
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO billing.subscriptions
                (user_id, stripe_subscription_id, stripe_customer_id, plan, status,
                 current_period_end)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (stripe_subscription_id) DO UPDATE
            SET plan = $4, status = $5, current_period_end = $6, updated_at = now()
            """,
            user_id,
            sub["id"],
            sub.get("customer"),
            plan,
            sub.get("status", "active"),
            datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None,
        )


async def record_invoice(user_id: str, invoice: dict) -> None:
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO billing.invoices
                (user_id, stripe_invoice_id, amount_cents, currency, status,
                 hosted_url, pdf_url)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (stripe_invoice_id) DO UPDATE
            SET status = $5, hosted_url = $6, pdf_url = $7
            """,
            user_id,
            invoice["id"],
            invoice.get("amount_paid") or invoice.get("amount_due") or 0,
            invoice.get("currency", "usd"),
            invoice.get("status", "open"),
            invoice.get("hosted_invoice_url"),
            invoice.get("invoice_pdf"),
        )


async def was_event_processed(event_id: str) -> bool:
    """Idempotency: Stripe retries webhooks; process each event once."""
    async with PostgreSQLPool.acquire() as conn:
        inserted = await conn.execute(
            """
            INSERT INTO billing.stripe_events (stripe_event_id, event_type)
            VALUES ($1, 'seen') ON CONFLICT DO NOTHING
            """,
            event_id,
        )
        return inserted == "INSERT 0 0"


# ============================================================================
# Webhook event handlers
# ============================================================================


def _subscription_plan(sub: dict) -> str:
    items = sub.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id", "") if items else ""
    return plan_for_price_id(price_id)


async def handle_subscription_event(event_type: str, sub: dict) -> None:
    """customer.subscription.created / .updated / .deleted"""
    user_id = await resolve_user_id(sub.get("metadata", {}), sub.get("customer"))
    if not user_id:
        logger.warning(f"Stripe {event_type}: no matching user (customer={sub.get('customer')})")
        return

    if event_type == "customer.subscription.deleted":
        await upsert_subscription(user_id, sub, "free")
        await set_user_plan(user_id, "free")
        return

    plan = _subscription_plan(sub)
    await upsert_subscription(user_id, sub, plan)

    # Only an alive subscription grants the paid plan
    if sub.get("status") in ("active", "trialing"):
        await set_user_plan(user_id, plan)
    elif sub.get("status") in ("canceled", "unpaid", "incomplete_expired"):
        await set_user_plan(user_id, "free")


async def handle_invoice_paid(invoice: dict) -> None:
    """invoice.payment_succeeded / invoice.paid → record + send invoice email."""
    user_id = await resolve_user_id(invoice.get("metadata", {}), invoice.get("customer"))
    if not user_id:
        return
    await record_invoice(user_id, invoice)

    email = invoice.get("customer_email")
    if email:
        amount = (invoice.get("amount_paid") or 0) / 100
        try:
            await email_service._send(  # reuse transport; template below
                email,
                "Your Arada invoice",
                email_service._render(
                    "Payment received ✅",
                    f"We've received your payment of <b>${amount:.2f} USD</b>. "
                    "Thanks for being an Arada subscriber!",
                    button_url=invoice.get("hosted_invoice_url"),
                    button_label="View invoice",
                ),
            )
        except email_service.EmailError:
            pass


async def handle_invoice_failed(invoice: dict) -> None:
    """invoice.payment_failed → alert the user to update their card."""
    user_id = await resolve_user_id(invoice.get("metadata", {}), invoice.get("customer"))
    if user_id:
        await record_invoice(user_id, invoice)

    email = invoice.get("customer_email")
    if email:
        try:
            await email_service._send(
                email,
                "Payment failed — action needed",
                email_service._render(
                    "Payment failed ⚠️",
                    "We couldn't charge your payment method. Please update it to keep "
                    "your Pro features — we'll retry automatically over the next days.",
                    button_url=f"{FRONTEND_URL}/dashboard/settings",
                    button_label="Update payment method",
                ),
            )
        except email_service.EmailError:
            pass
    logger.warning(f"Stripe payment failed: invoice={invoice.get('id')} user={user_id}")


async def process_stripe_event(event: dict) -> None:
    """Dispatch one verified Stripe event. Idempotent; never raises."""
    event_id = event.get("id", "")
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    try:
        if event_id and await was_event_processed(event_id):
            logger.info(f"Stripe event replay skipped: {event_id}")
            return

        if event_type.startswith("customer.subscription."):
            await handle_subscription_event(event_type, obj)
        elif event_type in ("invoice.payment_succeeded", "invoice.paid"):
            await handle_invoice_paid(obj)
        elif event_type == "invoice.payment_failed":
            await handle_invoice_failed(obj)
        else:
            logger.debug(f"Stripe event ignored: {event_type}")
    except Exception:
        logger.exception(f"Stripe event processing failed: {event_type} ({event_id})")
