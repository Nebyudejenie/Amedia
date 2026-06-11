"""Attribution Service for multi-touch credit assignment."""
import logging
from uuid import UUID
from typing import Optional

from api.clients import PostgreSQLPool

logger = logging.getLogger(__name__)


class AttributionService:
    """Multi-touch attribution modeling."""

    MODELS = {
        "first_touch": "First interaction gets 100% credit",
        "last_touch": "Last interaction gets 100% credit",
        "linear": "Equal credit to all interactions",
        "time_decay": "Later interactions get more credit",
        "custom": "Custom weights per interaction type",
    }

    @classmethod
    async def calculate_attribution(
        cls,
        workspace_id: UUID,
        conversion_id: UUID,
        touch_points: list[dict],
        model: str = "linear",
    ) -> dict:
        """
        Calculate attribution for a conversion.

        Touch points format:
        [
            {"event": "content.ingested", "source_id": "...", "timestamp": "2026-06-01T10:00:00"},
            {"event": "job.completed", "source_id": "...", "timestamp": "2026-06-02T14:30:00"},
            ...
        ]

        Models:
        - first_touch: first interaction gets 100%
        - last_touch: last interaction gets 100%
        - linear: equal credit to all
        - time_decay: exponential weight toward end
        - custom: custom defined weights
        """
        if model not in cls.MODELS:
            raise ValueError(f"Unknown attribution model: {model}")

        if not touch_points:
            return {
                "model": model,
                "touch_points": [],
                "total_credit": 0,
            }

        # Calculate credits
        if model == "first_touch":
            credits = cls._first_touch(touch_points)
        elif model == "last_touch":
            credits = cls._last_touch(touch_points)
        elif model == "linear":
            credits = cls._linear(touch_points)
        elif model == "time_decay":
            credits = cls._time_decay(touch_points)
        else:
            credits = cls._linear(touch_points)

        # Normalize to 1.0
        total = sum(c["credit"] for c in credits)
        if total > 0:
            for c in credits:
                c["credit"] /= total

        # Store in database
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO analytics.attribution
                    (workspace_id, conversion_id, touch_points, model)
                VALUES ($1, $2, $3, $4)
                """,
                workspace_id,
                conversion_id,
                credits,
                model,
            )

        return {
            "model": model,
            "touch_points": credits,
            "total_credit": sum(c["credit"] for c in credits),
        }

    @classmethod
    def _first_touch(cls, touch_points: list[dict]) -> list[dict]:
        """First touch attribution."""
        result = []
        for i, tp in enumerate(touch_points):
            result.append({
                **tp,
                "credit": 1.0 if i == 0 else 0.0,
            })
        return result

    @classmethod
    def _last_touch(cls, touch_points: list[dict]) -> list[dict]:
        """Last touch attribution."""
        result = []
        for i, tp in enumerate(touch_points):
            result.append({
                **tp,
                "credit": 1.0 if i == len(touch_points) - 1 else 0.0,
            })
        return result

    @classmethod
    def _linear(cls, touch_points: list[dict]) -> list[dict]:
        """Linear attribution (equal credit)."""
        credit = 1.0 / len(touch_points) if touch_points else 0
        result = []
        for tp in touch_points:
            result.append({
                **tp,
                "credit": credit,
            })
        return result

    @classmethod
    def _time_decay(cls, touch_points: list[dict]) -> list[dict]:
        """Time decay attribution (exponential toward end)."""
        n = len(touch_points)
        if n == 0:
            return []

        # Exponential weights: 2^i
        weights = [2.0 ** i for i in range(n)]
        total_weight = sum(weights)

        result = []
        for i, tp in enumerate(touch_points):
            result.append({
                **tp,
                "credit": weights[i] / total_weight,
            })
        return result

    @classmethod
    async def get_attribution(
        cls,
        workspace_id: UUID,
        conversion_id: UUID,
    ) -> Optional[dict]:
        """Get attribution for conversion."""
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT model, touch_points
                FROM analytics.attribution
                WHERE workspace_id = $1 AND conversion_id = $2
                ORDER BY created_at DESC LIMIT 1
                """,
                workspace_id,
                conversion_id,
            )

            if result:
                return dict(result)
            return None

    @classmethod
    async def compare_models(
        cls,
        workspace_id: UUID,
        conversion_id: UUID,
    ) -> dict:
        """Compare all attribution models for single conversion."""
        results = {}

        async with PostgreSQLPool.acquire() as conn:
            for model_name in cls.MODELS:
                result = await conn.fetchrow(
                    """
                    SELECT touch_points
                    FROM analytics.attribution
                    WHERE workspace_id = $1 AND conversion_id = $2 AND model = $3
                    """,
                    workspace_id,
                    conversion_id,
                    model_name,
                )

                if result:
                    results[model_name] = {
                        "description": cls.MODELS[model_name],
                        "touch_points": result["touch_points"],
                    }

        return results
