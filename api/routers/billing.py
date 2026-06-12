"""Billing endpoints: plans, checkout, invoices, portal + Stripe webhook."""
import logging
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from clients import PostgreSQLPool
from auth.security import get_current_user, TokenData
from services import stripe_service
from services.stripe_service import PLANS, verify_stripe_signature, process_stripe_event
from services.usage_service import usage_summary

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Billing"])


class CheckoutRequest(BaseModel):
    plan: str = Field(..., description="Plan to purchase: pro")


# ============================================================================
# Plans & current subscription
# ============================================================================


@router.get("/api/v1/billing/plans")
async def list_plans() -> dict:
    """Public plan catalog (no auth — shown on the pricing page)."""
    return {
        "plans": [
            {
                "id": key,
                "name": p["name"],
                "price_usd": p["price_usd"],  # null = contact sales
                "monthly_limit": p["monthly_limit"],  # null = unlimited
                "features": p["features"],
                "purchasable": stripe_service.price_id_for_plan(key) is not None,
            }
            for key, p in PLANS.items()
        ]
    }


@router.get("/api/v1/billing/current")
async def current_billing(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Current plan, usage, and subscription state."""
    summary = await usage_summary(current_user.user_id)

    async with PostgreSQLPool.acquire() as conn:
        sub = await conn.fetchrow(
            """
            SELECT plan, status, current_period_end
            FROM billing.subscriptions
            WHERE user_id = $1
            ORDER BY updated_at DESC LIMIT 1
            """,
            current_user.user_id,
        )

    return {
        **summary,
        "subscription": (
            {
                "plan": sub["plan"],
                "status": sub["status"],
                "renews_at": sub["current_period_end"].isoformat()
                if sub["current_period_end"]
                else None,
            }
            if sub
            else None
        ),
    }


@router.get("/api/v1/billing")
async def billing_overview(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Combined snapshot consumed by the dashboard settings page."""
    summary = await usage_summary(current_user.user_id)

    async with PostgreSQLPool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT stripe_invoice_id, amount_cents, currency, status,
                   hosted_url, created_at
            FROM billing.invoices
            WHERE user_id = $1
            ORDER BY created_at DESC LIMIT 10
            """,
            current_user.user_id,
        )

    return {
        "plan": summary["plan"].capitalize(),
        "usage": summary["used_this_month"],
        "limit": summary["monthly_limit"] or 999999,
        "invoices": [
            {
                "id": r["stripe_invoice_id"],
                "date": r["created_at"].strftime("%Y-%m-%d"),
                "amount": f"${r['amount_cents'] / 100:.2f}",
                "status": r["status"],
                "url": r["hosted_url"],
            }
            for r in rows
        ],
    }


# ============================================================================
# Checkout & customer portal
# ============================================================================


@router.post("/api/v1/billing/checkout")
async def create_checkout(
    body: CheckoutRequest,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Start a Stripe Checkout session for a paid plan."""
    plan = body.plan.lower()
    if plan not in PLANS:
        raise HTTPException(status_code=422, detail="Unknown plan")
    if plan == "free":
        raise HTTPException(status_code=422, detail="Free plan needs no checkout")
    if plan == "enterprise":
        # Custom pricing — no self-serve checkout
        return {
            "checkout_url": None,
            "contact_sales": True,
            "detail": "Enterprise is custom-priced. Email sales@arada.fun and "
                      "we'll get you set up.",
        }

    try:
        session = await stripe_service.create_checkout_session(
            current_user.user_id, current_user.email, plan
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except httpx.HTTPStatusError as e:
        logger.error(f"Stripe checkout failed: HTTP {e.response.status_code}")
        raise HTTPException(status_code=502, detail="Payment provider error — try again")

    return session


@router.post("/api/v1/billing/customer-portal")
async def customer_portal(current_user: TokenData = Depends(get_current_user)) -> dict:
    """Stripe-hosted portal: payment methods, invoices, cancellation."""
    try:
        return await stripe_service.create_portal_session(
            current_user.user_id, current_user.email
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Stripe portal failed: HTTP {e.response.status_code}")
        raise HTTPException(status_code=502, detail="Payment provider error — try again")


# ============================================================================
# Invoices
# ============================================================================


@router.get("/api/v1/billing/invoices")
async def list_invoices(
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    async with PostgreSQLPool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM billing.invoices WHERE user_id = $1",
            current_user.user_id,
        )
        rows = await conn.fetch(
            """
            SELECT id, stripe_invoice_id, amount_cents, currency, status,
                   hosted_url, pdf_url, created_at
            FROM billing.invoices
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            current_user.user_id,
            limit,
            offset,
        )

    response.headers["X-Total-Count"] = str(total)
    return {
        "invoices": [
            {
                "id": str(r["id"]),
                "stripe_invoice_id": r["stripe_invoice_id"],
                "amount": f"${r['amount_cents'] / 100:.2f}",
                "currency": r["currency"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/api/v1/billing/invoices/{invoice_id}")
async def get_invoice_pdf(
    invoice_id: UUID,
    current_user: TokenData = Depends(get_current_user),
) -> dict:
    """Return the Stripe-hosted PDF URL for one invoice."""
    async with PostgreSQLPool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pdf_url, hosted_url FROM billing.invoices
            WHERE id = $1 AND user_id = $2
            """,
            invoice_id,
            current_user.user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"pdf_url": row["pdf_url"], "hosted_url": row["hosted_url"]}


# ============================================================================
# Stripe webhook
# ============================================================================


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
) -> dict:
    """Receive Stripe events. Signature-verified against the raw body."""
    payload = await request.body()

    if not verify_stripe_signature(payload, stripe_signature):
        logger.warning("Stripe webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    await process_stripe_event(event)
    return {"received": True}
