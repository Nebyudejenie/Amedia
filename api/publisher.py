"""Publisher worker — publishes videos to social platforms."""
import asyncio
import json
import logging

from clients import PostgreSQLPool
from media_service import MediaService

logger = logging.getLogger(__name__)


class PublisherWorker:
    """Process publish jobs and dispatch to platforms."""

    _worker_id: str = "publisher-1"

    @staticmethod
    async def start():
        """Start the publisher loop."""
        await PostgreSQLPool.init()

        logger.info("Publisher worker starting")
        try:
            while True:
                await PublisherWorker.process_batch()
                await asyncio.sleep(10)  # Poll every 10 seconds
        except KeyboardInterrupt:
            logger.info("Publisher worker shutting down")
        finally:
            await PostgreSQLPool.close()

    @staticmethod
    async def process_batch():
        """Process a batch of publish jobs."""
        async with PostgreSQLPool.acquire() as conn:
            # Find queued publish jobs
            jobs = await conn.fetch(
                """SELECT id, workspace_id, video_id, platforms
                   FROM analytics.publish_jobs
                   WHERE status = 'queued'
                   ORDER BY created_at ASC
                   LIMIT 10"""
            )

            for job in jobs:
                await PublisherWorker.process_publish_job(job)

    @staticmethod
    async def process_publish_job(job: dict) -> None:
        """Publish a video to all platforms."""
        job_id = job["id"]
        workspace_id = job["workspace_id"]
        platforms = job["platforms"]

        logger.info(f"Processing publish job {job_id} for platforms: {platforms}")

        try:
            # Publish to each platform
            for platform in platforms:
                await MediaService.publish_to_platform(
                    workspace_id, job_id, platform
                )
                logger.info(f"Published to {platform}")

            logger.info(f"Completed publish job {job_id}")

        except Exception as e:
            logger.error(f"Publish job {job_id} failed: {e}", exc_info=True)

            # Mark as failed
            async with PostgreSQLPool.acquire() as conn:
                await conn.execute(
                    "UPDATE analytics.publish_jobs SET status = 'failed' WHERE id = $1",
                    job_id,
                )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(PublisherWorker.start())
