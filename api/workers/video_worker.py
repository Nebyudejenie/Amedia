"""Video generation worker.

Claims `queued` rows from content.videos with FOR UPDATE SKIP LOCKED (so
multiple worker replicas never grab the same job), runs the pipeline with a
bounded concurrency, and retries failures up to MAX_ATTEMPTS with backoff.

Runs as a standalone container (docker-compose video-worker service).
"""
import asyncio
import logging
import os

from clients import MinIOClient, PostgreSQLPool
from services.video_service import (
    MAX_ATTEMPTS,
    VideoError,
    backoff_seconds,
    produce_video,
)

logger = logging.getLogger(__name__)

CONCURRENCY = int(os.getenv("VIDEO_CONCURRENCY", "3"))
POLL_INTERVAL_SECONDS = int(os.getenv("VIDEO_POLL_SECONDS", "10"))

_semaphore = asyncio.Semaphore(CONCURRENCY)


async def _claim_jobs(limit: int) -> list[str]:
    """Atomically claim up to `limit` queued videos, flipping them to generating."""
    async with PostgreSQLPool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE content.videos SET status = 'generating', updated_at = now()
            WHERE id IN (
                SELECT id FROM content.videos
                WHERE status = 'queued'
                ORDER BY created_at
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """,
            limit,
        )
    return [str(r["id"]) for r in rows]


async def _mark_failed(video_id: str, attempts: int, message: str) -> None:
    """Record a failure. Re-queue with backoff if attempts remain, else fail."""
    if attempts < MAX_ATTEMPTS:
        delay = backoff_seconds(attempts)
        logger.warning(
            f"Video {video_id} failed (attempt {attempts}/{MAX_ATTEMPTS}); "
            f"retrying in {delay}s: {message}"
        )
        await asyncio.sleep(delay)
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                "UPDATE content.videos SET status = 'queued', stage = 'queued', "
                "error_message = $2, updated_at = now() WHERE id = $1",
                video_id, message,
            )
    else:
        logger.error(f"Video {video_id} permanently failed after {attempts} attempts: {message}")
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                "UPDATE content.videos SET status = 'failed', error_message = $2, "
                "updated_at = now() WHERE id = $1",
                video_id, message,
            )


async def _process(video_id: str) -> None:
    """Run one job under the concurrency semaphore; never raises."""
    async with _semaphore:
        # Count this attempt up-front so a hard crash still records it
        async with PostgreSQLPool.acquire() as conn:
            attempts = await conn.fetchval(
                "UPDATE content.videos SET attempts = attempts + 1 "
                "WHERE id = $1 RETURNING attempts",
                video_id,
            )
        try:
            await produce_video(video_id)
        except VideoError as e:
            await _mark_failed(video_id, attempts, str(e))
        except Exception as e:
            logger.exception(f"Unexpected error generating {video_id}")
            await _mark_failed(video_id, attempts, f"internal error: {type(e).__name__}")


async def run_cycle() -> None:
    """Claim and process a batch. Never raises."""
    try:
        free = CONCURRENCY  # claim at most what we can run now
        job_ids = await _claim_jobs(free)
        if job_ids:
            logger.info(f"Claimed {len(job_ids)} video job(s)")
            await asyncio.gather(*(_process(jid) for jid in job_ids))
    except Exception:
        logger.exception("Video worker cycle failed")


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info(f"Video worker starting (concurrency={CONCURRENCY})")

    await PostgreSQLPool.init()
    MinIOClient.init()

    try:
        while True:
            await run_cycle()
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Video worker stopping")
    finally:
        await PostgreSQLPool.close()


if __name__ == "__main__":
    asyncio.run(main())
