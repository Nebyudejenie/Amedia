"""Model Service for ML model management."""
import logging
from uuid import UUID
from typing import Optional
from datetime import datetime

from api.clients import PostgreSQLPool
from api.ml.base_service import MLServiceError, MLModelNotFound

logger = logging.getLogger(__name__)


class ModelService:
    """Manage ML models: registration, versioning, deployment."""

    @classmethod
    async def register_model(
        cls,
        workspace_id: UUID,
        name: str,
        model_type: str,
        model_key: str,
        config: dict,
        metrics: Optional[dict] = None,
    ) -> dict:
        """Register a new model version."""
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO ml.models
                    (workspace_id, name, type, model_key, version, config, metrics, status)
                VALUES
                    ($1, $2, $3, $4, 1, $5, $6, 'active')
                ON CONFLICT (workspace_id, name, version) DO UPDATE
                SET updated_at = now()
                RETURNING id, version, status, created_at
                """,
                workspace_id,
                name,
                model_type,
                model_key,
                config,
                metrics,
            )
            return dict(result) if result else None

    @classmethod
    async def get_model(cls, workspace_id: UUID, model_id: UUID) -> dict:
        """Retrieve model details."""
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT id, name, type, model_key, version, status, config, metrics, created_at
                FROM ml.models
                WHERE id = $1 AND workspace_id = $2
                """,
                model_id,
                workspace_id,
            )

            if not result:
                raise MLModelNotFound(f"Model {model_id} not found")

            return dict(result)

    @classmethod
    async def list_models(cls, workspace_id: UUID, model_type: Optional[str] = None) -> list[dict]:
        """List all models for workspace."""
        async with PostgreSQLPool.acquire() as conn:
            if model_type:
                results = await conn.fetch(
                    """
                    SELECT id, name, type, version, status, created_at
                    FROM ml.models
                    WHERE workspace_id = $1 AND type = $2 AND status = 'active'
                    ORDER BY name, version DESC
                    """,
                    workspace_id,
                    model_type,
                )
            else:
                results = await conn.fetch(
                    """
                    SELECT id, name, type, version, status, created_at
                    FROM ml.models
                    WHERE workspace_id = $1 AND status = 'active'
                    ORDER BY name, version DESC
                    """,
                    workspace_id,
                )

            return [dict(r) for r in results]

    @classmethod
    async def deprecate_model(cls, workspace_id: UUID, model_id: UUID) -> None:
        """Mark model as deprecated."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ml.models
                SET status = 'deprecated', updated_at = now()
                WHERE id = $1 AND workspace_id = $2
                """,
                model_id,
                workspace_id,
            )

    @classmethod
    async def create_training_job(
        cls,
        workspace_id: UUID,
        model_name: str,
        training_params: dict,
    ) -> UUID:
        """Create a training job."""
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO ml.training_jobs
                    (workspace_id, model_name, status, training_params)
                VALUES
                    ($1, $2, 'pending', $3)
                RETURNING id
                """,
                workspace_id,
                model_name,
                training_params,
            )
            return result

    @classmethod
    async def update_training_job(
        cls,
        job_id: UUID,
        status: str,
        metrics: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update training job status."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ml.training_jobs
                SET
                    status = $2,
                    validation_metrics = $3,
                    error_message = $4,
                    started_at = CASE WHEN status = 'pending' THEN now() ELSE started_at END,
                    completed_at = CASE WHEN $2 IN ('completed', 'failed') THEN now() ELSE NULL END
                WHERE id = $1
                """,
                job_id,
                status,
                metrics,
                error,
            )

    @classmethod
    async def store_prediction(
        cls,
        workspace_id: UUID,
        content_id: UUID,
        model_id: UUID,
        prediction_type: str,
        prediction: dict,
    ) -> None:
        """Cache prediction result."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ml.predictions
                    (workspace_id, content_id, model_id, prediction_type, prediction)
                VALUES
                    ($1, $2, $3, $4, $5)
                """,
                workspace_id,
                content_id,
                model_id,
                prediction_type,
                prediction,
            )

    @classmethod
    async def get_prediction(
        cls,
        workspace_id: UUID,
        content_id: UUID,
        prediction_type: str,
    ) -> Optional[dict]:
        """Retrieve cached prediction."""
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT prediction, created_at
                FROM ml.predictions
                WHERE workspace_id = $1 AND content_id = $2 AND prediction_type = $3
                ORDER BY created_at DESC
                LIMIT 1
                """,
                workspace_id,
                content_id,
                prediction_type,
            )

            return dict(result) if result else None

    @classmethod
    async def update_feature_store(
        cls,
        workspace_id: UUID,
        entity_type: str,
        entity_id: UUID,
        features: dict,
    ) -> None:
        """Update computed features."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ml.feature_store (workspace_id, entity_type, entity_id, features)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (workspace_id, entity_type, entity_id)
                DO UPDATE SET features = $4, computed_at = now()
                """,
                workspace_id,
                entity_type,
                entity_id,
                features,
            )
