"""Per-plan usage tracking and limit enforcement.

Free: 5 analyses/month · Pro: 500/month · Enterprise: unlimited.
Usage = COUNT(billing.usage_events) since the start of the calendar month.
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status

from clients import PostgreSQLPool
from auth.security import get_current_user, TokenData
from services.stripe_service import plan_limit

logger = logging.getLogger(__name__)


def is_over_limit(used: int, limit: Optional[int]) -> bool:
    """Pure check: None limit = unlimited (enterprise)."""
    return limit is not None and used >= limit


async def get_user_plan(user_id: str) -> str:
    async with PostgreSQLPool.acquire() as conn:
        plan = await conn.fetchval(
            "SELECT current_plan FROM auth.users WHERE id = $1", user_id
        )
    return plan or "free"


async def get_monthly_usage(user_id: str) -> int:
    """Analyses completed since the start of the current calendar month."""
    async with PostgreSQLPool.acquire() as conn:
        count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM billing.usage_events
            WHERE user_id = $1
              AND event_type = 'analysis'
              AND created_at >= date_trunc('month', now())
            """,
            user_id,
        )
    return count or 0


async def record_usage(user_id: str, event_type: str = "analysis") -> None:
    """Call after each completed analysis."""
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            "INSERT INTO billing.usage_events (user_id, event_type) VALUES ($1, $2)",
            user_id,
            event_type,
        )


async def usage_summary(user_id: str) -> dict:
    """Plan + usage snapshot for /billing/current and the dashboard."""
    plan = await get_user_plan(user_id)
    used = await get_monthly_usage(user_id)
    limit = plan_limit(plan)
    return {
        "plan": plan,
        "used_this_month": used,
        "monthly_limit": limit,  # null = unlimited
        "remaining": None if limit is None else max(0, limit - used),
        "over_limit": is_over_limit(used, limit),
    }


async def require_within_usage_limit(
    current_user: TokenData = Depends(get_current_user),
) -> TokenData:
    """FastAPI dependency for analysis endpoints.

    Over-limit → 403 with an upgrade hint matched to the user's plan.
    """
    plan = await get_user_plan(current_user.user_id)
    limit = plan_limit(plan)
    if limit is None:
        return current_user  # enterprise: unlimited

    used = await get_monthly_usage(current_user.user_id)
    if is_over_limit(used, limit):
        upgrade_hint = (
            "Upgrade to Pro for 500 analyses/month."
            if plan == "free"
            else "Contact sales for Enterprise (unlimited analyses)."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Monthly limit reached ({used}/{limit} analyses on the "
                   f"{plan.capitalize()} plan). {upgrade_hint}",
        )
    return current_user
