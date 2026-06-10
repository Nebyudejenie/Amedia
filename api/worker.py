"""Background worker for content ingestion and processing."""
import asyncio
import json
import logging

from clients import PostgreSQLPool, RedisClient
from content_service import ContentService

logger = logging.getLogger(__name__)


class ContentWorker:
    """Process content ingestion jobs from Redis queue."""

    @staticmethod
    async def start():
        """Start the worker loop."""
        await PostgreSQLPool.init()
        await RedisClient.init()

        logger.info("Content worker starting")
        try:
            while True:
                await ContentWorker.process_batch()
                await asyncio.sleep(5)  # Poll every 5 seconds
        except KeyboardInterrupt:
            logger.info("Content worker shutting down")
        finally:
            await PostgreSQLPool.close()
            await RedisClient.close()

    @staticmethod
    async def process_batch():
        """Process a batch of fetch jobs from the queue."""
        job_json = await RedisClient.lpop("content:fetch-queue")
        if not job_json:
            return

        try:
            job = json.loads(job_json)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid job JSON: {e}")
            return

        job_id = job.get("job_id")
        source_id = job.get("source_id")
        workspace_id = job.get("workspace_id")
        source_type = job.get("source_type")
        url = job.get("url")
        config = job.get("config", {})

        logger.info(f"Processing fetch job {job_id} for source {source_id}")

        try:
            # Fetch and ingest
            ingested_count = await ContentService.ingest_source(
                workspace_id, source_id, source_type, url, config
            )

            # Normalize and score raw items
            await ContentWorker.process_raw_items(workspace_id)

            # Mark job as complete
            await RedisClient.set(f"job:{job_id}:status", "completed")
            logger.info(f"Fetch job {job_id} completed ({ingested_count} items)")
        except Exception as e:
            logger.error(f"Fetch job {job_id} failed: {e}", exc_info=True)
            await RedisClient.set(f"job:{job_id}:status", "failed")

    @staticmethod
    async def process_raw_items(workspace_id: str):
        """Normalize and score all unprocessed raw items."""
        async with PostgreSQLPool.acquire() as conn:
            # Get unprocessed raw items
            rows = await conn.fetch(
                """SELECT id, source_id, external_id, title, description, url, author, published_at
                   FROM content.raw_items
                   WHERE workspace_id = $1 AND is_duplicate IS NULL AND deleted_at IS NULL
                   LIMIT 100""",
                workspace_id,
            )

            for row in rows:
                raw_item = dict(row)
                normalized = await ContentService.normalize_item(
                    workspace_id, raw_item["id"], raw_item
                )

                if normalized:
                    # Score the normalized item
                    score = await ContentService.score_item(
                        workspace_id, normalized["id"], normalized
                    )
                    logger.debug(f"Scored item {normalized['id']}: {score:.2f}")

                    # Mark raw item as processed
                    await conn.execute(
                        "UPDATE content.raw_items SET is_processed = true WHERE id = $1",
                        raw_item["id"],
                    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(ContentWorker.start())
