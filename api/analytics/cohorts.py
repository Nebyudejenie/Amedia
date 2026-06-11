"""Cohort Analysis Service."""
import logging
from uuid import UUID
from typing import Optional

from api.clients import PostgreSQLPool

logger = logging.getLogger(__name__)


class CohortService:
    """Create and analyze user cohorts."""

    @classmethod
    async def create_cohort(
        cls,
        workspace_id: UUID,
        name: str,
        criteria: dict,
    ) -> UUID:
        """
        Create cohort based on criteria.

        Criteria example:
        {
            "engagement_rate": {">": 0.1},
            "source_type": {"in": ["rss", "telegram"]},
            "created_after": "2026-05-01"
        }
        """
        async with PostgreSQLPool.acquire() as conn:
            # Build SQL WHERE clause from criteria
            members = await cls._find_members(conn, workspace_id, criteria)

            cohort_id = await conn.fetchval(
                """
                INSERT INTO analytics.cohorts
                    (workspace_id, name, definition, members)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                workspace_id,
                name,
                criteria,
                members,
            )

            return cohort_id

    @classmethod
    async def _find_members(
        cls, conn, workspace_id: UUID, criteria: dict
    ) -> list[str]:
        """Find users matching cohort criteria."""
        # Simplified: query user table with basic filters
        query = "SELECT id FROM auth.users WHERE workspace_id = $1"
        params = [workspace_id]

        # Example: filter by created_after
        if "created_after" in criteria:
            query += f" AND created_at >= ${len(params) + 1}"
            params.append(criteria["created_after"])

        rows = await conn.fetch(query, *params)
        return [str(r["id"]) for r in rows]

    @classmethod
    async def get_cohort(cls, workspace_id: UUID, cohort_id: UUID) -> dict:
        """Get cohort details."""
        async with PostgreSQLPool.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT id, name, definition, members, created_at
                FROM analytics.cohorts
                WHERE id = $1 AND workspace_id = $2
                """,
                cohort_id,
                workspace_id,
            )

            if result:
                return dict(result)
            return None

    @classmethod
    async def list_cohorts(cls, workspace_id: UUID) -> list[dict]:
        """List all cohorts."""
        async with PostgreSQLPool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, array_length(members, 1) as size, created_at
                FROM analytics.cohorts
                WHERE workspace_id = $1
                ORDER BY created_at DESC
                """,
                workspace_id,
            )

            return [dict(r) for r in rows]

    @classmethod
    async def compare_cohorts(
        cls,
        workspace_id: UUID,
        cohort_ids: list[UUID],
        metric_names: list[str],
    ) -> dict:
        """
        Compare multiple cohorts across metrics.

        Returns:
            {
                "cohorts": [
                    {
                        "cohort_id": "...",
                        "name": "power-users",
                        "size": 150,
                        "metrics": {
                            "avg_engagement": 0.45,
                            "churn_rate": 0.05
                        }
                    },
                    ...
                ],
                "comparison": {
                    "avg_engagement": {
                        "highest_cohort": "...",
                        "value": 0.45
                    }
                }
            }
        """
        async with PostgreSQLPool.acquire() as conn:
            cohort_data = []

            for cohort_id in cohort_ids:
                cohort = await conn.fetchrow(
                    "SELECT name, members FROM analytics.cohorts WHERE id = $1",
                    cohort_id,
                )

                if not cohort:
                    continue

                metrics = {}
                for metric_name in metric_names:
                    value = await conn.fetchval(
                        """
                        SELECT value FROM analytics.cohort_metrics
                        WHERE cohort_id = $1 AND metric_name = $2
                        ORDER BY computed_at DESC LIMIT 1
                        """,
                        cohort_id,
                        metric_name,
                    )
                    metrics[metric_name] = value or 0

                cohort_data.append({
                    "cohort_id": cohort_id,
                    "name": cohort["name"],
                    "size": len(cohort["members"]) if cohort["members"] else 0,
                    "metrics": metrics,
                })

            # Find highest values for each metric
            comparison = {}
            for metric_name in metric_names:
                values = [c["metrics"].get(metric_name, 0) for c in cohort_data]
                if values:
                    max_value = max(values)
                    max_cohort = cohort_data[values.index(max_value)]

                    comparison[metric_name] = {
                        "highest_cohort": max_cohort["name"],
                        "value": max_value,
                    }

            return {
                "cohorts": cohort_data,
                "comparison": comparison,
            }

    @classmethod
    async def update_cohort(
        cls,
        workspace_id: UUID,
        cohort_id: UUID,
        name: Optional[str] = None,
        criteria: Optional[dict] = None,
    ) -> None:
        """Update cohort definition."""
        async with PostgreSQLPool.acquire() as conn:
            updates = []
            params = [cohort_id, workspace_id]

            if name:
                updates.append(f"name = ${len(params) + 1}")
                params.append(name)

            if criteria:
                updates.append(f"definition = ${len(params) + 1}")
                params.append(criteria)
                members = await cls._find_members(conn, workspace_id, criteria)
                updates.append(f"members = ${len(params) + 1}")
                params.append(members)

            if updates:
                query = f"""
                    UPDATE analytics.cohorts
                    SET {", ".join(updates)}
                    WHERE id = $1 AND workspace_id = $2
                """
                await conn.execute(query, *params)

    @classmethod
    async def delete_cohort(cls, workspace_id: UUID, cohort_id: UUID) -> None:
        """Delete cohort."""
        async with PostgreSQLPool.acquire() as conn:
            await conn.execute(
                "DELETE FROM analytics.cohorts WHERE id = $1 AND workspace_id = $2",
                cohort_id,
                workspace_id,
            )
