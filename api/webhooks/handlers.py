"""Webhook event handlers and routing."""
import logging
from uuid import UUID
from datetime import datetime
from typing import Optional

from clients import PostgreSQLPool, RedisClient

logger = logging.getLogger(__name__)

# All event types that can be emitted
VALID_EVENTS = {
    "content.ingested",
    "content.scored",
    "job.created",
    "job.claimed",
    "job.completed",
    "job.failed",
    "publish.success",
    "publish.failed",
    "user.created",
    "workspace.upgraded",
}


async def emit_event(
    workspace_id: UUID,
    event_type: str,
    entity_id: Optional[UUID] = None,
    payload: Optional[dict] = None,
) -> None:
    """
    Emit an event to all matching webhook subscriptions.

    Args:
        workspace_id: Workspace that triggered the event
        event_type: Type of event (e.g., 'content.ingested')
        entity_id: ID of related entity (content, job, etc.)
        payload: Event-specific data
    """
    if event_type not in VALID_EVENTS:
        logger.warning(f"Unknown event type: {event_type}")
        return

    if payload is None:
        payload = {}

    try:
        async with PostgreSQLPool.acquire() as conn:
            # Store event in database
            event_id = await conn.fetchval(
                """
                INSERT INTO webhooks.events
                    (workspace_id, event_type, entity_id, payload, occurred_at)
                VALUES
                    ($1, $2, $3, $4, now())
                RETURNING id
                """,
                workspace_id,
                event_type,
                entity_id,
                payload,
            )

            # Find all subscriptions matching this event
            subscriptions = await conn.fetch(
                """
                SELECT id, url, secret, headers, retry_policy
                FROM webhooks.subscriptions
                WHERE workspace_id = $1 AND active = true
                AND $2 = ANY(events)
                """,
                workspace_id,
                event_type,
            )

            # Queue delivery for each matching subscription
            for sub in subscriptions:
                await conn.execute(
                    """
                    INSERT INTO webhooks.deliveries
                        (subscription_id, event_id, status, attempt_number)
                    VALUES
                        ($1, $2, 'pending', 1)
                    """,
                    sub["id"],
                    event_id,
                )

                # Push to Redis queue for worker
                await RedisClient.lpush(
                    f"webhook_queue",
                    str(sub["id"]),
                    str(event_id),
                )

        logger.info(f"Event {event_type} emitted to workspace {workspace_id}")

    except Exception as e:
        logger.error(f"Error emitting event: {e}")


async def get_subscriptions(
    workspace_id: UUID,
    event_type: Optional[str] = None,
) -> list[dict]:
    """Get webhook subscriptions."""
    async with PostgreSQLPool.acquire() as conn:
        if event_type:
            rows = await conn.fetch(
                """
                SELECT id, url, events, active, created_at, last_triggered_at
                FROM webhooks.subscriptions
                WHERE workspace_id = $1 AND $2 = ANY(events)
                ORDER BY created_at DESC
                """,
                workspace_id,
                event_type,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, url, events, active, created_at, last_triggered_at
                FROM webhooks.subscriptions
                WHERE workspace_id = $1
                ORDER BY created_at DESC
                """,
                workspace_id,
            )

        return [dict(r) for r in rows]


async def create_subscription(
    workspace_id: UUID,
    user_id: UUID,
    url: str,
    events: list[str],
    secret: str,
    headers: Optional[dict] = None,
) -> UUID:
    """Create webhook subscription."""
    async with PostgreSQLPool.acquire() as conn:
        subscription_id = await conn.fetchval(
            """
            INSERT INTO webhooks.subscriptions
                (workspace_id, user_id, url, events, secret, headers, active)
            VALUES
                ($1, $2, $3, $4, $5, $6, true)
            RETURNING id
            """,
            workspace_id,
            user_id,
            url,
            events,
            secret,
            headers,
        )

        return subscription_id


async def delete_subscription(
    workspace_id: UUID,
    subscription_id: UUID,
) -> None:
    """Delete webhook subscription."""
    async with PostgreSQLPool.acquire() as conn:
        await conn.execute(
            """
            UPDATE webhooks.subscriptions
            SET active = false
            WHERE id = $1 AND workspace_id = $2
            """,
            subscription_id,
            workspace_id,
        )


async def get_delivery_attempts(
    workspace_id: UUID,
    subscription_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Get webhook delivery attempts."""
    async with PostgreSQLPool.acquire() as conn:
        if subscription_id:
            rows = await conn.fetch(
                """
                SELECT id, subscription_id, event_id, status, http_status,
                       attempt_number, created_at
                FROM webhooks.deliveries
                WHERE workspace_id = $1 AND subscription_id = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                workspace_id,
                subscription_id,
                limit,
            )
        elif status:
            rows = await conn.fetch(
                """
                SELECT id, subscription_id, event_id, status, http_status,
                       attempt_number, created_at
                FROM webhooks.deliveries
                WHERE workspace_id = $1 AND status = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                workspace_id,
                status,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, subscription_id, event_id, status, http_status,
                       attempt_number, created_at
                FROM webhooks.deliveries
                WHERE workspace_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                workspace_id,
                limit,
            )

        return [dict(r) for r in rows]
