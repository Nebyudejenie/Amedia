"""Health check endpoints."""
from fastapi import APIRouter

from clients import PostgreSQLPool, RedisClient, QdrantClient

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
async def health_check():
    """System health check: all stores must respond."""
    status_map = {"status": "ok", "checks": {}}

    # PostgreSQL
    try:
        async with PostgreSQLPool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        status_map["checks"]["postgresql"] = "ok"
    except Exception as e:
        status_map["checks"]["postgresql"] = f"error: {str(e)}"
        status_map["status"] = "degraded"

    # Redis
    try:
        await RedisClient.set("health-check", "1", ex=10)
        status_map["checks"]["redis"] = "ok"
    except Exception as e:
        status_map["checks"]["redis"] = f"error: {str(e)}"
        status_map["status"] = "degraded"

    # Qdrant
    try:
        # Just check the client is responsive by checking if it can list collections
        await QdrantClient._client.get_collections()
        status_map["checks"]["qdrant"] = "ok"
    except Exception as e:
        status_map["checks"]["qdrant"] = f"error: {str(e)}"
        status_map["status"] = "degraded"

    return status_map
