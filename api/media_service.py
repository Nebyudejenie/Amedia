"""Media rendering, asset management, and publishing service."""
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from clients import MinIOClient, PostgreSQLPool

logger = logging.getLogger(__name__)


class MediaService:
    """Render videos from scripts + templates, publish to platforms."""

    @staticmethod
    async def create_template(
        workspace_id: str,
        name: str,
        template_type: str,
        config: dict,
    ) -> dict:
        """Create a video template."""
        template_id = str(uuid4())

        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO media.templates
                   (workspace_id, id, name, template_type, config, is_active)
                   VALUES ($1, $2, $3, $4, $5, true)
                   RETURNING id, workspace_id, name, template_type, config, is_active, created_at, updated_at""",
                workspace_id,
                template_id,
                name,
                template_type,
                json.dumps(config),
            )

        logger.info(f"Created template {template_id} ({template_type})")
        return dict(row)

    @staticmethod
    async def get_template(template_id: str, workspace_id: str) -> Optional[dict]:
        """Get template details."""
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, workspace_id, name, template_type, config, is_active, created_at, updated_at
                   FROM media.templates
                   WHERE id = $1 AND workspace_id = $2 AND deleted_at IS NULL""",
                template_id,
                workspace_id,
            )
            if row:
                result = dict(row)
                if result["config"]:
                    result["config"] = json.loads(result["config"])
                return result
            return None

    @staticmethod
    async def list_templates(
        workspace_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[int, list[dict]]:
        """List workspace templates."""
        async with PostgreSQLPool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM media.templates WHERE workspace_id = $1 AND deleted_at IS NULL",
                workspace_id,
            )
            rows = await conn.fetch(
                """SELECT id, workspace_id, name, template_type, config, is_active, created_at, updated_at
                   FROM media.templates
                   WHERE workspace_id = $1 AND deleted_at IS NULL
                   ORDER BY created_at DESC
                   LIMIT $2 OFFSET $3""",
                workspace_id,
                limit,
                offset,
            )
            templates = []
            for row in rows:
                t = dict(row)
                if t["config"]:
                    t["config"] = json.loads(t["config"])
                templates.append(t)
            return total, templates

    @staticmethod
    async def add_asset(
        workspace_id: str,
        asset_type: str,
        name: str,
        minio_path: str,
        metadata: dict,
    ) -> dict:
        """Add an asset to the workspace library."""
        asset_id = str(uuid4())

        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO media.audio_assets (workspace_id, id, name, minio_path, metadata)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING id, workspace_id, name, minio_path, metadata, created_at"""
                if asset_type == "audio"
                else """INSERT INTO media.video_assets (workspace_id, id, name, minio_path, metadata)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING id, workspace_id, name, minio_path, metadata, created_at""",
                workspace_id,
                asset_id,
                name,
                minio_path,
                json.dumps(metadata),
            )

        logger.info(f"Added {asset_type} asset {asset_id}")
        return dict(row)

    @staticmethod
    async def list_assets(
        workspace_id: str, asset_type: str, limit: int = 20, offset: int = 0
    ) -> tuple[int, list[dict]]:
        """List workspace assets."""
        table = "media.audio_assets" if asset_type == "audio" else "media.video_assets"
        async with PostgreSQLPool.acquire() as conn:
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table} WHERE workspace_id = $1 AND deleted_at IS NULL",
                workspace_id,
            )
            rows = await conn.fetch(
                f"""SELECT id, workspace_id, name, minio_path, metadata, created_at
                   FROM {table}
                   WHERE workspace_id = $1 AND deleted_at IS NULL
                   ORDER BY created_at DESC
                   LIMIT $2 OFFSET $3""",
                workspace_id,
                limit,
                offset,
            )
            assets = []
            for row in rows:
                a = dict(row)
                if a["metadata"]:
                    a["metadata"] = json.loads(a["metadata"])
                assets.append(a)
            return total, assets

    @staticmethod
    async def render_video(
        workspace_id: str,
        script_id: str,
        template_id: str,
        output_format: str = "short-form",
    ) -> dict:
        """Render a video from script + template (placeholder: mock rendering)."""
        async with PostgreSQLPool.acquire() as conn:
            # Retrieve script
            script = await conn.fetchrow(
                "SELECT id, script_text FROM content.scripts WHERE id = $1 AND workspace_id = $2",
                script_id,
                workspace_id,
            )
            if not script:
                raise ValueError("Script not found")

            # Retrieve template
            template = await conn.fetchrow(
                "SELECT id, config FROM media.templates WHERE id = $1 AND workspace_id = $2",
                template_id,
                workspace_id,
            )
            if not template:
                raise ValueError("Template not found")

            # Mock rendering: create a "video" file with metadata
            video_id = str(uuid4())
            video_content = json.dumps({
                "type": "video",
                "script_id": script_id,
                "template_id": template_id,
                "format": output_format,
                "duration_seconds": 60,
                "resolution": "1080p",
                "fps": 30,
                "script_excerpt": script["script_text"][:200],
            })

            # Store in MinIO
            minio_path = f"videos/{workspace_id}/{video_id}.json"
            try:
                MinIOClient.put_object(
                    f"arada-{workspace_id}",
                    minio_path,
                    video_content.encode(),
                )
            except Exception as e:
                logger.error(f"Failed to store video in MinIO: {e}")
                raise

            # Record in database
            row = await conn.fetchrow(
                """INSERT INTO media.video_assets
                   (workspace_id, name, minio_path, metadata)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id, workspace_id, name, minio_path, created_at""",
                workspace_id,
                f"Rendered-{video_id}",
                minio_path,
                json.dumps({"script_id": script_id, "template_id": template_id}),
            )

        logger.info(f"Rendered video {video_id}")
        return dict(row)

    @staticmethod
    async def create_publish_job(
        workspace_id: str,
        video_id: str,
        platforms: list[str],
        metadata: dict,
    ) -> dict:
        """Create a publishing job."""
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO analytics.publish_jobs
                   (workspace_id, video_id, platforms, metadata, status)
                   VALUES ($1, $2, $3, $4, 'queued')
                   RETURNING id, workspace_id, video_id, platforms, status, created_at""",
                workspace_id,
                video_id,
                platforms,
                json.dumps(metadata),
            )

        logger.info(f"Created publish job {row['id']} for video {video_id}")
        return dict(row)

    @staticmethod
    async def list_publish_jobs(
        workspace_id: str, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> tuple[int, list[dict]]:
        """List publishing jobs."""
        async with PostgreSQLPool.acquire() as conn:
            where = "workspace_id = $1 AND deleted_at IS NULL"
            params = [workspace_id]

            if status:
                where += " AND status = $2"
                params.append(status)

            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM analytics.publish_jobs WHERE {where}",
                *params,
            )

            param_limit = 3 if status else 2
            rows = await conn.fetch(
                f"""SELECT id, workspace_id, video_id, platforms, status, metadata,
                          published_at, created_at
                   FROM analytics.publish_jobs
                   WHERE {where}
                   ORDER BY created_at DESC
                   LIMIT ${param_limit} OFFSET ${param_limit + 1}""",
                *params,
                limit,
                offset,
            )

            jobs = []
            for row in rows:
                job = dict(row)
                if job["metadata"]:
                    job["metadata"] = json.loads(job["metadata"])
                jobs.append(job)
            return total, jobs

    @staticmethod
    async def publish_to_platform(
        workspace_id: str, publish_job_id: str, platform: str
    ) -> dict:
        """Publish video to a specific platform (mock integration)."""
        async with PostgreSQLPool.acquire() as conn:
            # Retrieve publish job
            job = await conn.fetchrow(
                "SELECT id, video_id, metadata FROM analytics.publish_jobs WHERE id = $1 AND workspace_id = $2",
                publish_job_id,
                workspace_id,
            )
            if not job:
                raise ValueError("Publish job not found")

            # Mock platform publishing
            publish_result = {
                "platform": platform,
                "post_id": f"{platform}-{str(uuid4())[:8]}",
                "url": f"https://{platform}.com/post/{str(uuid4())[:8]}",
                "published_at": datetime.utcnow().isoformat(),
            }

            # Record result
            row = await conn.fetchrow(
                """INSERT INTO analytics.publish_results
                   (workspace_id, publish_job_id, platform, post_id, url, status)
                   VALUES ($1, $2, $3, $4, $5, 'success')
                   RETURNING id, workspace_id, publish_job_id, platform, post_id, url, status, created_at""",
                workspace_id,
                publish_job_id,
                platform,
                publish_result["post_id"],
                publish_result["url"],
            )

            # Update publish job status if all platforms done
            platforms_done = await conn.fetchval(
                "SELECT COUNT(DISTINCT platform) FROM analytics.publish_results WHERE publish_job_id = $1",
                publish_job_id,
            )
            total_platforms = await conn.fetchval(
                "SELECT array_length(platforms, 1) FROM analytics.publish_jobs WHERE id = $1",
                publish_job_id,
            )

            if platforms_done == total_platforms:
                await conn.execute(
                    "UPDATE analytics.publish_jobs SET status = 'completed', published_at = now() WHERE id = $1",
                    publish_job_id,
                )

        logger.info(f"Published to {platform}: {publish_result['url']}")
        return dict(row)
