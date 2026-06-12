"""Webhook delivery worker - processes events and sends HTTP requests."""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from uuid import UUID

import httpx

from clients import PostgreSQLPool, RedisClient
from webhooks.signatures import sign_payload
from config import settings

logger = logging.getLogger(__name__)

RETRY_SCHEDULE = [
    60,      # 1 minute
    300,     # 5 minutes
    1800,    # 30 minutes
    86400,   # 24 hours
]


async def process_webhook_delivery(delivery_id: str, event_id: str) -> None:
    """
    Process a single webhook delivery attempt.

    Flow:
    1. Load subscription and event from DB
    2. Sign payload with secret
    3. POST to webhook URL
    4. Update delivery status (success/retry/failed)
    """
    try:
        async with PostgreSQLPool.acquire() as conn:
            # Load delivery + subscription + event
            delivery = await conn.fetchrow(
                """
                SELECT d.id, d.subscription_id, d.event_id, d.attempt_number,
                       s.url, s.secret, s.headers,
                       e.payload, e.event_type, e.workspace_id
                FROM webhooks.deliveries d
                JOIN webhooks.subscriptions s ON d.subscription_id = s.id
                JOIN webhooks.events e ON d.event_id = e.id
                WHERE d.id = $1
                """,
                UUID(delivery_id),
            )

            if not delivery:
                logger.warning(f"Delivery {delivery_id} not found")
                return

            attempt = delivery["attempt_number"]
            max_attempts = 5

            try:
                # Prepare payload
                payload = delivery["payload"] or {}
                payload["event_type"] = delivery["event_type"]
                payload["timestamp"] = datetime.utcnow().isoformat()

                # Sign with HMAC
                signature = sign_payload(payload, delivery["secret"])

                # Prepare headers
                headers = delivery["headers"] or {}
                headers.update({
                    "Content-Type": "application/json",
                    "X-Arada-Signature": signature,
                    "User-Agent": "AradaOS/1.0",
                })

                # Send HTTP request
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        delivery["url"],
                        json=payload,
                        headers=headers,
                    )

                    # Success (2xx)
                    if 200 <= resp.status_code < 300:
                        await conn.execute(
                            """
                            UPDATE webhooks.deliveries
                            SET status = 'success', http_status = $2,
                                completed_at = now()
                            WHERE id = $1
                            """,
                            delivery_id,
                            resp.status_code,
                        )

                        await conn.execute(
                            """
                            UPDATE webhooks.subscriptions
                            SET last_triggered_at = now()
                            WHERE id = $1
                            """,
                            delivery["subscription_id"],
                        )

                        logger.info(
                            f"Webhook delivery {delivery_id} succeeded "
                            f"(attempt {attempt}, HTTP {resp.status_code})"
                        )
                        return

                    # Server error or rate limit - retry
                    if resp.status_code >= 500 or resp.status_code == 429:
                        if attempt < max_attempts:
                            next_retry = datetime.utcnow() + timedelta(
                                seconds=RETRY_SCHEDULE[attempt - 1]
                            )

                            await conn.execute(
                                """
                                UPDATE webhooks.deliveries
                                SET status = 'retry', http_status = $2,
                                    attempt_number = $3, next_retry_at = $4,
                                    error_message = $5
                                WHERE id = $1
                                """,
                                delivery_id,
                                resp.status_code,
                                attempt + 1,
                                next_retry,
                                f"HTTP {resp.status_code}",
                            )

                            logger.info(
                                f"Webhook {delivery_id} will retry in "
                                f"{RETRY_SCHEDULE[attempt - 1]}s (attempt {attempt})"
                            )
                        else:
                            # Max retries exceeded
                            await _move_to_dead_letter(
                                conn,
                                delivery["subscription_id"],
                                delivery["event_id"],
                                f"Max retries exceeded (HTTP {resp.status_code})",
                            )
                        return

                    # Client error (4xx) - don't retry
                    if 400 <= resp.status_code < 500:
                        await _move_to_dead_letter(
                            conn,
                            delivery["subscription_id"],
                            delivery["event_id"],
                            f"HTTP {resp.status_code}: {resp.text[:200]}",
                        )
                        return

            except httpx.TimeoutException:
                if attempt < max_attempts:
                    next_retry = datetime.utcnow() + timedelta(
                        seconds=RETRY_SCHEDULE[attempt - 1]
                    )

                    await conn.execute(
                        """
                        UPDATE webhooks.deliveries
                        SET status = 'retry', http_status = 0,
                            attempt_number = $2, next_retry_at = $3,
                            error_message = 'Timeout'
                        WHERE id = $1
                        """,
                        delivery_id,
                        attempt + 1,
                        next_retry,
                    )
                else:
                    await _move_to_dead_letter(
                        conn,
                        delivery["subscription_id"],
                        delivery["event_id"],
                        "Timeout on all attempts",
                    )

            except Exception as e:
                logger.error(f"Webhook delivery error: {e}")
                if attempt < max_attempts:
                    next_retry = datetime.utcnow() + timedelta(
                        seconds=RETRY_SCHEDULE[attempt - 1]
                    )

                    await conn.execute(
                        """
                        UPDATE webhooks.deliveries
                        SET status = 'retry', attempt_number = $2,
                            next_retry_at = $3, error_message = $4
                        WHERE id = $1
                        """,
                        delivery_id,
                        attempt + 1,
                        next_retry,
                        str(e)[:200],
                    )
                else:
                    await _move_to_dead_letter(
                        conn,
                        delivery["subscription_id"],
                        delivery["event_id"],
                        f"Error: {str(e)[:200]}",
                    )

    except Exception as e:
        logger.error(f"Fatal error processing delivery {delivery_id}: {e}")


async def _move_to_dead_letter(
    conn, subscription_id: UUID, event_id: UUID, reason: str
) -> None:
    """Move failed delivery to dead letter queue."""
    await conn.execute(
        """
        UPDATE webhooks.deliveries
        SET status = 'failed', completed_at = now()
        WHERE subscription_id = $1 AND event_id = $2
        """,
        subscription_id,
        event_id,
    )

    await conn.execute(
        """
        INSERT INTO webhooks.dead_letters
            (subscription_id, event_id, reason, last_error)
        VALUES ($1, $2, $3, $3)
        """,
        subscription_id,
        event_id,
        reason,
    )

    logger.warning(f"Webhook moved to dead letter: {reason}")


async def worker_loop() -> None:
    """Main webhook worker loop - processes delivery queue."""
    logger.info("Starting webhook worker...")

    await RedisClient.init()
    await PostgreSQLPool.init()

    try:
        while True:
            try:
                # Get pending deliveries from queue
                delivery_id = await RedisClient.lpop("webhook_queue")

                if delivery_id:
                    # Get associated event_id from DB
                    async with PostgreSQLPool.acquire() as conn:
                        event_id = await conn.fetchval(
                            "SELECT event_id FROM webhooks.deliveries WHERE id = $1",
                            UUID(delivery_id),
                        )

                    if event_id:
                        await process_webhook_delivery(delivery_id, str(event_id))
                else:
                    # No pending deliveries, check for retries
                    async with PostgreSQLPool.acquire() as conn:
                        retry_ready = await conn.fetch(
                            """
                            SELECT id, event_id FROM webhooks.deliveries
                            WHERE status = 'retry' AND next_retry_at <= now()
                            ORDER BY next_retry_at ASC
                            LIMIT 10
                            """
                        )

                        for row in retry_ready:
                            await process_webhook_delivery(str(row["id"]), str(row["event_id"]))

                    await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(10)

    except KeyboardInterrupt:
        logger.info("Webhook worker stopping...")
    finally:
        await RedisClient.close()
        await PostgreSQLPool.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop())
