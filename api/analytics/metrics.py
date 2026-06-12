"""Metrics Service for custom KPI calculations."""
import logging
from uuid import UUID
from datetime import date, datetime, timedelta
from typing import Optional

from clients import PostgreSQLPool, RedisClient

logger = logging.getLogger(__name__)


class MetricsService:
    """Calculate and cache custom metrics."""

    @classmethod
    async def create_metric(
        cls,
        workspace_id: UUID,
        name: str,
        definition: str,
        metric_type: str,
        dimension: Optional[str] = None,
    ) -> UUID:
        """Create custom metric definition."""
        async with PostgreSQLPool.acquire() as conn:
            metric_id = await conn.fetchval(
                """
                INSERT INTO analytics.custom_metrics
                    (workspace_id, name, definition, metric_type, dimension)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                workspace_id,
                name,
                definition,
                metric_type,
                dimension,
            )
            return metric_id

    @classmethod
    async def calculate_metric(
        cls,
        workspace_id: UUID,
        metric_id: UUID,
        start_date: date,
        end_date: date,
        dimension: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> dict:
        """
        Calculate metric value with caching.

        Returns:
            {
                "metric_name": "engagement_rate",
                "value": 0.18,
                "dimension": "daily",
                "data_points": [...],
                "trend": "up|down|stable",
                "computed_at": "2026-06-11T14:30:00Z"
            }
        """
        # Check Redis cache
        cache_key = f"analytics:metric:{metric_id}:{dimension}:{start_date}:{end_date}"
        cached = await RedisClient.get(cache_key)

        if cached:
            import json
            return json.loads(cached)

        async with PostgreSQLPool.acquire() as conn:
            # Get metric definition
            metric = await conn.fetchrow(
                "SELECT name, definition, metric_type FROM analytics.custom_metrics WHERE id = $1",
                metric_id,
            )

            if not metric:
                return {"error": "Metric not found"}

            # Execute calculation (simplified)
            if metric["metric_type"] == "count":
                value = await cls._calculate_count(conn, metric["definition"], start_date, end_date)
            elif metric["metric_type"] == "avg":
                value = await cls._calculate_avg(conn, metric["definition"], start_date, end_date)
            elif metric["metric_type"] == "sum":
                value = await cls._calculate_sum(conn, metric["definition"], start_date, end_date)
            elif metric["metric_type"] == "ratio":
                value = await cls._calculate_ratio(conn, metric["definition"], start_date, end_date)
            else:
                value = 0

            # Get trend
            prev_start = start_date - timedelta(days=(end_date - start_date).days)
            prev_value = await cls._calculate_avg(conn, metric["definition"], prev_start, start_date)
            trend = "up" if value > prev_value else "down" if value < prev_value else "stable"

            result = {
                "metric_name": metric["name"],
                "value": value,
                "dimension": dimension,
                "data_points": await cls._get_daily_data_points(conn, metric_id, start_date, end_date),
                "trend": trend,
                "computed_at": datetime.utcnow().isoformat(),
            }

            # Cache for 1 hour
            import json
            await RedisClient.set(cache_key, json.dumps(result, default=str), ex=3600)

            return result

    @classmethod
    async def _calculate_count(
        cls, conn, definition: str, start_date: date, end_date: date
    ) -> int:
        """Count aggregation."""
        # Simplified - execute parameterized query
        result = await conn.fetchval(
            f"SELECT COUNT(*) FROM {definition} WHERE created_at >= $1 AND created_at < $2",
            start_date,
            end_date + timedelta(days=1),
        )
        return result or 0

    @classmethod
    async def _calculate_avg(cls, conn, definition: str, start_date: date, end_date: date) -> float:
        """Average aggregation."""
        result = await conn.fetchval(
            f"SELECT AVG(value) FROM {definition} WHERE created_at >= $1 AND created_at < $2",
            start_date,
            end_date + timedelta(days=1),
        )
        return float(result) if result else 0.0

    @classmethod
    async def _calculate_sum(cls, conn, definition: str, start_date: date, end_date: date) -> float:
        """Sum aggregation."""
        result = await conn.fetchval(
            f"SELECT SUM(value) FROM {definition} WHERE created_at >= $1 AND created_at < $2",
            start_date,
            end_date + timedelta(days=1),
        )
        return float(result) if result else 0.0

    @classmethod
    async def _calculate_ratio(cls, conn, definition: str, start_date: date, end_date: date) -> float:
        """Ratio calculation (numerator/denominator from definition)."""
        parts = definition.split("/")
        if len(parts) != 2:
            return 0.0

        numerator = await conn.fetchval(
            f"SELECT COUNT(*) FROM {parts[0]} WHERE created_at >= $1 AND created_at < $2",
            start_date,
            end_date + timedelta(days=1),
        )

        denominator = await conn.fetchval(
            f"SELECT COUNT(*) FROM {parts[1]} WHERE created_at >= $1 AND created_at < $2",
            start_date,
            end_date + timedelta(days=1),
        )

        if denominator and denominator > 0:
            return numerator / denominator
        return 0.0

    @classmethod
    async def _get_daily_data_points(
        cls, conn, metric_id: UUID, start_date: date, end_date: date
    ) -> list[dict]:
        """Get daily breakdown of metric."""
        rows = await conn.fetch(
            """
            SELECT dimension_value, value, computed_at
            FROM analytics.metric_snapshots
            WHERE metric_id = $1 AND computed_at::date >= $2 AND computed_at::date <= $3
            ORDER BY computed_at
            """,
            metric_id,
            start_date,
            end_date,
        )

        return [
            {"date": str(r["computed_at"].date()), "value": r["value"]}
            for r in rows
        ]

    @classmethod
    async def delete_metric(cls, workspace_id: UUID, metric_id: UUID) -> None:
        """Delete metric definition."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                "DELETE FROM analytics.custom_metrics WHERE id = $1 AND workspace_id = $2",
                metric_id,
                workspace_id,
            )
