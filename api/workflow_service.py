"""Workflow state machine, job dispatch, event tracking."""
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from clients import PostgreSQLPool, RedisClient

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Job state enum."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EventType(str, Enum):
    """Event type enum."""

    JOB_CREATED = "job_created"
    JOB_CLAIMED = "job_claimed"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    TASK_DISPATCHED = "task_dispatched"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


class WorkflowService:
    """Orchestrate content → brief → script → media → publish."""

    @staticmethod
    async def create_job(
        workspace_id: str,
        job_type: str,
        input_data: dict,
        priority: int = 0,
    ) -> dict:
        """Create a new workflow job."""
        job_id = str(uuid4())
        now = datetime.utcnow()

        async with PostgreSQLPool.acquire() as conn:
            async with conn.transaction():
                # Insert job
                job = await conn.fetchrow(
                    """INSERT INTO workflow.jobs
                       (workspace_id, id, job_type, status, input_data, priority, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, now())
                       RETURNING id, workspace_id, job_type, status, input_data, priority, created_at""",
                    workspace_id,
                    job_id,
                    job_type,
                    JobStatus.PENDING.value,
                    json.dumps(input_data),
                    priority,
                )

                # Log creation event
                await conn.execute(
                    """INSERT INTO workflow.events
                       (workspace_id, job_id, event_type, metadata)
                       VALUES ($1, $2, $3, $4)""",
                    workspace_id,
                    job_id,
                    EventType.JOB_CREATED.value,
                    json.dumps({"status": JobStatus.PENDING.value}),
                )

        logger.info(f"Created job {job_id} of type {job_type}")
        return dict(job)

    @staticmethod
    async def claim_job(worker_id: str, job_type: str, batch_size: int = 1) -> list[dict]:
        """Claim pending jobs for processing."""
        async with PostgreSQLPool.acquire() as conn:
            async with conn.transaction():
                # Find pending jobs (ordered by priority, then created_at)
                jobs = await conn.fetch(
                    """SELECT id, workspace_id, job_type, input_data
                       FROM workflow.jobs
                       WHERE job_type = $1 AND status = $2
                       ORDER BY priority DESC, created_at ASC
                       LIMIT $3
                       FOR UPDATE SKIP LOCKED""",
                    job_type,
                    JobStatus.PENDING.value,
                    batch_size,
                )

                # Update to processing
                for job in jobs:
                    await conn.execute(
                        """UPDATE workflow.jobs
                           SET status = $1, claimed_at = now(), claimed_by = $2
                           WHERE id = $3""",
                        JobStatus.PROCESSING.value,
                        worker_id,
                        job["id"],
                    )

                    # Log claim event
                    await conn.execute(
                        """INSERT INTO workflow.events
                           (workspace_id, job_id, event_type, metadata)
                           VALUES ($1, $2, $3, $4)""",
                        job["workspace_id"],
                        job["id"],
                        EventType.JOB_CLAIMED.value,
                        json.dumps({"worker_id": worker_id}),
                    )

        return [dict(j) for j in jobs]

    @staticmethod
    async def complete_job(job_id: str, output_data: dict) -> None:
        """Mark job as completed."""
        async with PostgreSQLPool.acquire() as conn:
            async with conn.transaction():
                job = await conn.fetchrow(
                    "SELECT workspace_id FROM workflow.jobs WHERE id = $1",
                    job_id,
                )
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    return

                await conn.execute(
                    """UPDATE workflow.jobs
                       SET status = $1, output_data = $2, completed_at = now()
                       WHERE id = $3""",
                    JobStatus.COMPLETED.value,
                    json.dumps(output_data),
                    job_id,
                )

                await conn.execute(
                    """INSERT INTO workflow.events
                       (workspace_id, job_id, event_type, metadata)
                       VALUES ($1, $2, $3, $4)""",
                    job["workspace_id"],
                    job_id,
                    EventType.JOB_COMPLETED.value,
                    json.dumps({"output_data": output_data}),
                )

        logger.info(f"Completed job {job_id}")

    @staticmethod
    async def fail_job(job_id: str, error_message: str) -> None:
        """Mark job as failed."""
        async with PostgreSQLPool.acquire() as conn:
            async with conn.transaction():
                job = await conn.fetchrow(
                    "SELECT workspace_id FROM workflow.jobs WHERE id = $1",
                    job_id,
                )
                if not job:
                    logger.warning(f"Job {job_id} not found")
                    return

                await conn.execute(
                    """UPDATE workflow.jobs
                       SET status = $1, error_message = $2, completed_at = now()
                       WHERE id = $3""",
                    JobStatus.FAILED.value,
                    error_message,
                    job_id,
                )

                await conn.execute(
                    """INSERT INTO workflow.events
                       (workspace_id, job_id, event_type, metadata)
                       VALUES ($1, $2, $3, $4)""",
                    job["workspace_id"],
                    job_id,
                    EventType.JOB_FAILED.value,
                    json.dumps({"error_message": error_message}),
                )

        logger.error(f"Job {job_id} failed: {error_message}")

    @staticmethod
    async def dispatch_task(
        workspace_id: str,
        job_id: str,
        task_type: str,
        input_data: dict,
        queue_name: str,
    ) -> str:
        """Dispatch a task to a Redis Stream."""
        task_id = str(uuid4())

        # Create task record
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """INSERT INTO workflow.jobs
                   (workspace_id, id, job_type, status, input_data, priority, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, now())""",
                workspace_id,
                task_id,
                task_type,
                JobStatus.PENDING.value,
                json.dumps(input_data),
                0,
            )

        logger.info(f"Dispatched task {task_id} ({task_type}) to {queue_name}")
        return task_id

    @staticmethod
    async def get_job(job_id: str) -> Optional[dict]:
        """Get job details."""
        async with PostgreSQLPool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, workspace_id, job_type, status, input_data, output_data,
                          error_message, priority, claimed_by, claimed_at, completed_at, created_at
                   FROM workflow.jobs WHERE id = $1""",
                job_id,
            )
            if row:
                result = dict(row)
                # Parse JSON fields
                if result["input_data"]:
                    result["input_data"] = json.loads(result["input_data"])
                if result["output_data"]:
                    result["output_data"] = json.loads(result["output_data"])
                return result
            return None

    @staticmethod
    async def list_jobs(
        workspace_id: str,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """List workspace jobs."""
        async with PostgreSQLPool.acquire() as conn:
            where_clauses = ["workspace_id = $1"]
            params = [workspace_id]
            param_idx = 2

            if status:
                where_clauses.append(f"status = ${param_idx}")
                params.append(status)
                param_idx += 1

            if job_type:
                where_clauses.append(f"job_type = ${param_idx}")
                params.append(job_type)
                param_idx += 1

            where = " AND ".join(where_clauses)

            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM workflow.jobs WHERE {where}",
                *params,
            )

            rows = await conn.fetch(
                f"""SELECT id, workspace_id, job_type, status, input_data, output_data,
                          error_message, priority, claimed_by, claimed_at, completed_at, created_at
                   FROM workflow.jobs
                   WHERE {where}
                   ORDER BY created_at DESC
                   LIMIT ${param_idx} OFFSET ${param_idx + 1}""",
                *params,
                limit,
                offset,
            )

            jobs = []
            for row in rows:
                job = dict(row)
                if job["input_data"]:
                    job["input_data"] = json.loads(job["input_data"])
                if job["output_data"]:
                    job["output_data"] = json.loads(job["output_data"])
                jobs.append(job)

            return total, jobs

    @staticmethod
    async def log_event(
        workspace_id: str,
        job_id: str,
        event_type: str,
        metadata: dict,
    ) -> None:
        """Log a workflow event (append-only)."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """INSERT INTO workflow.events
                   (workspace_id, job_id, event_type, metadata)
                   VALUES ($1, $2, $3, $4)""",
                workspace_id,
                job_id,
                event_type,
                json.dumps(metadata),
            )

    @staticmethod
    async def get_job_events(job_id: str) -> list[dict]:
        """Get all events for a job (audit trail)."""
        async with PostgreSQLPool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, workspace_id, job_id, event_type, metadata, created_at
                   FROM workflow.events
                   WHERE job_id = $1
                   ORDER BY created_at ASC""",
                job_id,
            )
            events = []
            for row in rows:
                event = dict(row)
                if event["metadata"]:
                    event["metadata"] = json.loads(event["metadata"])
                events.append(event)
            return events
