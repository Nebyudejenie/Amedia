# Stripe Billing — Setup & Operations

## Plans
| Plan | Price | Monthly analyses | Checkout |
|---|---|---|---|
| Free | $0 | 5 | none needed |
| Pro | $29/mo | 500 | Stripe Checkout |
| Enterprise | custom | unlimited | contact sales |

## One-time Stripe setup (dashboard)
1. Create a Product **"Arada Pro"** with a recurring **$29/month USD** price
   → copy the price id into `.env` as `STRIPE_PRICE_PRO`
2. Developers → API keys → copy the secret key → `STRIPE_SECRET_KEY`
3. Developers → Webhooks → add endpoint `https://arada.fun/webhooks/stripe`
   with events: `customer.subscription.created|updated|deleted`,
   `invoice.payment_succeeded`, `invoice.payment_failed`
   → copy the signing secret → `STRIPE_WEBHOOK_SECRET`
4. Apply migration 017.

Local testing: `stripe listen --forward-to localhost:8000/webhooks/stripe`
(the CLI prints a whsec_ for your .env), then `stripe trigger
customer.subscription.created`.

## Flow
```
POST /api/v1/billing/checkout {plan: pro}
  → ensure Stripe customer (stored on auth.users.stripe_customer_id)
  → Checkout session (mode=subscription, metadata.user_id)
  → user pays on Stripe-hosted page
  → webhook customer.subscription.created
      → billing.subscriptions upserted, users.current_plan = pro
  → invoice.payment_succeeded → billing.invoices + invoice email
```
Cancellation (via customer portal) → `customer.subscription.deleted`
→ plan back to `free`. `past_due` keeps the plan (grace period);
`canceled/unpaid/incomplete_expired` downgrade immediately.

## Security
- Webhook verified against the raw body: HMAC-SHA256 over `"{t}.{body}"`,
  constant-time compare, 5-minute timestamp tolerance (replay guard)
- `billing.stripe_events` makes processing idempotent across Stripe retries
- `/webhooks/stripe` exempt from the generic rate limiter (own auth)

## Usage enforcement
- Every completed analysis inserts a `billing.usage_events` row
- `require_within_usage_limit` dependency 403s over-limit requests with a
  plan-appropriate upgrade hint (free→Pro, pro→Enterprise)
- Applied to `/ml/sentiment/analyze`; add the same dependency to any new
  analysis endpoint

## Endpoints
| Method | Path | Auth |
|---|---|---|
| GET | /api/v1/billing/plans | public |
| GET | /api/v1/billing/current | user |
| GET | /api/v1/billing | user (dashboard snapshot) |
| POST | /api/v1/billing/checkout | user |
| POST | /api/v1/billing/customer-portal | user |
| GET | /api/v1/billing/invoices[/{id}] | user |
| POST | /webhooks/stripe | Stripe signature |
