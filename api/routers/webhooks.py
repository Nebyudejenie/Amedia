"""Webhooks API endpoints."""
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from dependencies import get_current_user, TokenData, require_role
from webhooks.handlers import (
    create_subscription,
    delete_subscription,
    get_subscriptions,
    get_delivery_attempts,
)
from webhooks.signatures import generate_secret
from clients import PostgreSQLPool

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/subscriptions")
async def create_webhook(
    workspace_id: UUID,
    url: str,
    events: list[str],
    headers: Optional[dict] = None,
    token: TokenData = Depends(get_current_user),
):
    """Create webhook subscription."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        secret = generate_secret()
        subscription_id = await create_subscription(
            UUID(token.workspace_id),
            UUID(token.user_id),
            url,
            events,
            secret,
            headers,
        )

        return {
            "id": subscription_id,
            "url": url,
            "events": events,
            "secret": secret,
            "status": "active",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions")
async def list_webhooks(
    workspace_id: UUID,
    event_type: Optional[str] = None,
    token: TokenData = Depends(get_current_user),
):
    """List webhook subscriptions."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        subscriptions = await get_subscriptions(
            UUID(token.workspace_id), event_type=event_type
        )
        return {"subscriptions": subscriptions, "count": len(subscriptions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/subscriptions/{subscription_id}")
async def get_webhook(
    workspace_id: UUID,
    subscription_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Get webhook details."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT id, url, events, active, created_at, last_triggered_at
                FROM webhooks.subscriptions
                WHERE id = $1 AND workspace_id = $2
                """,
                subscription_id,
                workspace_id,
            )

            if not result:
                raise HTTPException(status_code=404, detail="Webhook not found")

            return dict(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/subscriptions/{subscription_id}")
async def update_webhook(
    workspace_id: UUID,
    subscription_id: UUID,
    url: Optional[str] = None,
    events: Optional[list[str]] = None,
    active: Optional[bool] = None,
    token: TokenData = Depends(get_current_user),
):
    """Update webhook subscription."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        async with PostgreSQLPool.acquire() as conn:
            updates = []
            params = [subscription_id, workspace_id]

            if url:
                updates.append(f"url = ${len(params) + 1}")
                params.append(url)

            if events:
                updates.append(f"events = ${len(params) + 1}")
                params.append(events)

            if active is not None:
                updates.append(f"active = ${len(params) + 1}")
                params.append(active)

            if updates:
                query = f"""
                    UPDATE webhooks.subscriptions
                    SET {", ".join(updates)}
                    WHERE id = $1 AND workspace_id = $2
                """
                await conn.execute(query, *params)

            return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subscriptions/{subscription_id}")
async def delete_webhook(
    workspace_id: UUID,
    subscription_id: UUID,
    token: TokenData = Depends(get_current_user),
):
    """Delete webhook subscription."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        await delete_subscription(UUID(token.workspace_id), subscription_id)
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events")
async def list_events(
    workspace_id: UUID,
    event_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    token: TokenData = Depends(get_current_user),
):
    """List webhook events."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        async with PostgreSQLPool.acquire() as conn:
            if event_type:
                rows = await conn.fetch(
                    """
                    SELECT id, event_type, entity_id, created_at
                    FROM webhooks.events
                    WHERE workspace_id = $1 AND event_type = $2
                    ORDER BY created_at DESC
                    LIMIT $3 OFFSET $4
                    """,
                    workspace_id,
                    event_type,
                    limit,
                    offset,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, event_type, entity_id, created_at
                    FROM webhooks.events
                    WHERE workspace_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    workspace_id,
                    limit,
                    offset,
                )

            return {
                "events": [dict(r) for r in rows],
                "limit": limit,
                "offset": offset,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deliveries")
async def list_deliveries(
    workspace_id: UUID,
    subscription_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = 50,
    token: TokenData = Depends(get_current_user),
):
    """List webhook delivery attempts."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        deliveries = await get_delivery_attempts(
            UUID(token.workspace_id),
            subscription_id=subscription_id,
            status=status,
            limit=limit,
        )
        return {"deliveries": deliveries, "count": len(deliveries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deliveries/{delivery_id}/retry")
async def retry_delivery(
    workspace_id: UUID,
    delivery_id: UUID,
    token: TokenData = Depends(require_role("owner", "admin")),
):
    """Manually retry failed webhook delivery."""
    if str(token.workspace_id) != str(workspace_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                UPDATE webhooks.deliveries
                SET status = 'pending', attempt_number = 1, next_retry_at = now()
                WHERE id = $1
                """,
                delivery_id,
            )

            from clients import RedisClient
            await RedisClient.lpush("webhook_queue", str(delivery_id))

            return {"status": "queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
