"""Task orchestrator — processes workflow jobs (brief → script → render → publish)."""
import asyncio
import json
import logging

from clients import PostgreSQLPool, RedisClient
from workflow_service import WorkflowService

logger = logging.getLogger(__name__)


class TaskOrchestrator:
    """Process workflow jobs in parallel, respecting dependencies."""

    _worker_id: str = "orchestrator-1"

    @staticmethod
    async def start():
        """Start the orchestrator loop."""
        await PostgreSQLPool.init()
        await RedisClient.init()

        logger.info("Orchestrator starting")
        try:
            while True:
                await TaskOrchestrator.process_cycle()
                await asyncio.sleep(5)  # Poll every 5 seconds
        except KeyboardInterrupt:
            logger.info("Orchestrator shutting down")
        finally:
            await PostgreSQLPool.close()
            await RedisClient.close()

    @staticmethod
    async def process_cycle():
        """One cycle of job processing."""
        # Process brief jobs
        briefs = await WorkflowService.claim_job(
            TaskOrchestrator._worker_id, "brief", batch_size=5
        )
        for job in briefs:
            await TaskOrchestrator.process_brief_job(job)

        # Process script jobs
        scripts = await WorkflowService.claim_job(
            TaskOrchestrator._worker_id, "script", batch_size=5
        )
        for job in scripts:
            await TaskOrchestrator.process_script_job(job)

        # Process render jobs
        renders = await WorkflowService.claim_job(
            TaskOrchestrator._worker_id, "render", batch_size=3
        )
        for job in renders:
            await TaskOrchestrator.process_render_job(job)

        # Process publish jobs
        publishes = await WorkflowService.claim_job(
            TaskOrchestrator._worker_id, "publish", batch_size=5
        )
        for job in publishes:
            await TaskOrchestrator.process_publish_job(job)

    @staticmethod
    async def process_brief_job(job: dict) -> None:
        """Generate a brief from content items."""
        job_id = job["id"]
        workspace_id = job["workspace_id"]
        input_data = job["input_data"]

        try:
            item_ids = input_data.get("item_ids", [])
            brief_type = input_data.get("brief_type", "daily_digest")

            # Retrieve content items
            async with PostgreSQLPool.acquire() as conn:
                items = await conn.fetch(
                    """SELECT id, title, description, url, author, published_at
                       FROM content.normalized_items
                       WHERE id = ANY($1) AND workspace_id = $2 AND deleted_at IS NULL""",
                    item_ids,
                    workspace_id,
                )

            if not items:
                raise ValueError("No items found for brief")

            # Summarize (placeholder: just concat titles)
            brief_text = "\n".join([f"- {item['title']}" for item in items])

            # Store brief
            async with PostgreSQLPool.acquire() as conn:
                brief = await conn.fetchrow(
                    """INSERT INTO content.content_briefs
                       (workspace_id, brief_type, content, item_count, source_items)
                       VALUES ($1, $2, $3, $4, $5)
                       RETURNING id, workspace_id, brief_type, content, item_count, created_at""",
                    workspace_id,
                    brief_type,
                    brief_text,
                    len(items),
                    json.dumps(item_ids),
                )

            output_data = {
                "brief_id": brief["id"],
                "item_count": brief["item_count"],
                "brief_type": brief_type,
            }

            await WorkflowService.complete_job(job_id, output_data)
            logger.info(f"Completed brief job {job_id}")

        except Exception as e:
            logger.error(f"Brief job {job_id} failed: {e}", exc_info=True)
            await WorkflowService.fail_job(job_id, str(e))

    @staticmethod
    async def process_script_job(job: dict) -> None:
        """Generate a video script from a brief."""
        job_id = job["id"]
        workspace_id = job["workspace_id"]
        input_data = job["input_data"]

        try:
            brief_id = input_data.get("brief_id")
            script_style = input_data.get("script_style", "engaging")

            # Retrieve brief
            async with PostgreSQLPool.acquire() as conn:
                brief = await conn.fetchrow(
                    "SELECT content FROM content.content_briefs WHERE id = $1 AND workspace_id = $2",
                    brief_id,
                    workspace_id,
                )

            if not brief:
                raise ValueError("Brief not found")

            # Generate script (placeholder: add intro/outro)
            script_text = f"""[INTRO]
Hey, here's today's trending stories!

[CONTENT]
{brief['content']}

[OUTRO]
Don't forget to like and subscribe!"""

            # Store script
            async with PostgreSQLPool.acquire() as conn:
                script = await conn.fetchrow(
                    """INSERT INTO content.scripts
                       (workspace_id, brief_id, script_text, style)
                       VALUES ($1, $2, $3, $4)
                       RETURNING id, workspace_id, brief_id, style, created_at""",
                    workspace_id,
                    brief_id,
                    script_text,
                    script_style,
                )

            output_data = {
                "script_id": script["id"],
                "brief_id": brief_id,
                "style": script_style,
            }

            await WorkflowService.complete_job(job_id, output_data)
            logger.info(f"Completed script job {job_id}")

        except Exception as e:
            logger.error(f"Script job {job_id} failed: {e}", exc_info=True)
            await WorkflowService.fail_job(job_id, str(e))

    @staticmethod
    async def process_render_job(job: dict) -> None:
        """Render video from script + assets."""
        job_id = job["id"]
        workspace_id = job["workspace_id"]
        input_data = job["input_data"]

        try:
            script_id = input_data.get("script_id")
            template_id = input_data.get("template_id")
            video_format = input_data.get("video_format", "short-form")

            # Retrieve script and template (placeholder: mock values)
            output_data = {
                "script_id": script_id,
                "video_id": f"video-{job_id[:8]}",
                "video_format": video_format,
                "duration_seconds": 60,
                "status": "ready",
            }

            await WorkflowService.complete_job(job_id, output_data)
            logger.info(f"Completed render job {job_id}")

        except Exception as e:
            logger.error(f"Render job {job_id} failed: {e}", exc_info=True)
            await WorkflowService.fail_job(job_id, str(e))

    @staticmethod
    async def process_publish_job(job: dict) -> None:
        """Publish video to social platforms."""
        job_id = job["id"]
        workspace_id = job["workspace_id"]
        input_data = job["input_data"]

        try:
            video_id = input_data.get("video_id")
            platforms = input_data.get("platforms", ["twitter", "youtube"])
            metadata = input_data.get("metadata", {})

            # Create publish job record
            async with PostgreSQLPool.acquire() as conn:
                publish = await conn.fetchrow(
                    """INSERT INTO analytics.publish_jobs
                       (workspace_id, video_id, platforms, metadata, status)
                       VALUES ($1, $2, $3, $4, $5)
                       RETURNING id, platforms, status""",
                    workspace_id,
                    video_id,
                    platforms,
                    json.dumps(metadata),
                    "queued",
                )

            output_data = {
                "video_id": video_id,
                "publish_job_id": publish["id"],
                "platforms": publish["platforms"],
                "status": publish["status"],
            }

            await WorkflowService.complete_job(job_id, output_data)
            logger.info(f"Completed publish job {job_id}")

        except Exception as e:
            logger.error(f"Publish job {job_id} failed: {e}", exc_info=True)
            await WorkflowService.fail_job(job_id, str(e))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(TaskOrchestrator.start())
