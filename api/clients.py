"""Async clients for all data stores with retry + timeout."""
import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
from redis import asyncio as aioredis
from minio import Minio
from minio.error import S3Error
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from config import settings

logger = logging.getLogger(__name__)


class PostgreSQLPool:
    """Wrapper around asyncpg connection pool."""

    _pool: asyncpg.Pool | None = None

    @classmethod
    async def init(cls) -> None:
        """Initialize the pool."""
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                database=settings.db_name,
                min_size=settings.db_pool_min,
                max_size=settings.db_pool_max,
                timeout=10,
                command_timeout=30,
            )
            logger.info("PostgreSQL pool initialized")

    @classmethod
    async def close(cls) -> None:
        """Close the pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("PostgreSQL pool closed")

    @classmethod
    @asynccontextmanager
    async def acquire(cls):
        """Acquire a connection from the pool."""
        if not cls._pool:
            raise RuntimeError("Pool not initialized")
        async with cls._pool.acquire() as conn:
            yield conn


class RedisClient:
    """Wrapper around aioredis."""

    _redis: aioredis.Redis | None = None

    @classmethod
    async def init(cls) -> None:
        """Initialize Redis connection."""
        if cls._redis is None:
            cls._redis = await aioredis.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            logger.info("Redis client initialized")

    @classmethod
    async def close(cls) -> None:
        """Close Redis connection."""
        if cls._redis:
            await cls._redis.close()
            cls._redis = None
            logger.info("Redis client closed")

    @classmethod
    async def get(cls, key: str) -> str | None:
        """Get a value from Redis."""
        if not cls._redis:
            raise RuntimeError("Redis not initialized")
        return await cls._redis.get(key)

    @classmethod
    async def set(cls, key: str, value: str, ex: int | None = None) -> None:
        """Set a value in Redis."""
        if not cls._redis:
            raise RuntimeError("Redis not initialized")
        await cls._redis.set(key, value, ex=ex)

    @classmethod
    async def delete(cls, *keys: str) -> int:
        """Delete keys from Redis."""
        if not cls._redis:
            raise RuntimeError("Redis not initialized")
        return await cls._redis.delete(*keys)

    @classmethod
    async def lpush(cls, key: str, *values: str) -> int:
        """Push values to a list."""
        if not cls._redis:
            raise RuntimeError("Redis not initialized")
        return await cls._redis.lpush(key, *values)

    @classmethod
    async def lpop(cls, key: str) -> str | None:
        """Pop from a list."""
        if not cls._redis:
            raise RuntimeError("Redis not initialized")
        return await cls._redis.lpop(key)


class MinIOClient:
    """Wrapper around Minio S3 client."""

    _client: Minio | None = None

    @classmethod
    def init(cls) -> None:
        """Initialize MinIO client."""
        if cls._client is None:
            cls._client = Minio(
                f"{settings.minio_host}:{settings.minio_port}",
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=False,
            )
            logger.info("MinIO client initialized")

    @classmethod
    def put_object(cls, bucket: str, key: str, data: bytes) -> None:
        """Put an object to MinIO."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        try:
            cls._client.put_object(bucket, key, data=data, length=len(data))
        except S3Error as e:
            logger.error(f"MinIO put error: {e}")
            raise

    @classmethod
    def get_object(cls, bucket: str, key: str) -> bytes:
        """Get an object from MinIO."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        try:
            response = cls._client.get_object(bucket, key)
            return response.read()
        except S3Error as e:
            logger.error(f"MinIO get error: {e}")
            raise

    @classmethod
    def bucket_exists(cls, bucket: str) -> bool:
        """Check if a bucket exists."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        return cls._client.bucket_exists(bucket)

    @classmethod
    def make_bucket(cls, bucket: str) -> None:
        """Create a bucket."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        try:
            if not cls.bucket_exists(bucket):
                cls._client.make_bucket(bucket)
                logger.info(f"MinIO bucket created: {bucket}")
        except S3Error as e:
            logger.error(f"MinIO bucket create error: {e}")
            raise

    @classmethod
    def put_file(cls, bucket: str, key: str, file_path: str, content_type: str) -> None:
        """Upload a file from disk (streamed) to MinIO."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        try:
            cls._client.fput_object(bucket, key, file_path, content_type=content_type)
        except S3Error as e:
            logger.error(f"MinIO put_file error: {e}")
            raise

    @classmethod
    def remove_object(cls, bucket: str, key: str) -> None:
        """Delete an object from MinIO (no error if it is already gone)."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        try:
            cls._client.remove_object(bucket, key)
        except S3Error as e:
            logger.error(f"MinIO remove error: {e}")
            raise

    @classmethod
    def presigned_get(cls, bucket: str, key: str, expires_seconds: int = 3600) -> str:
        """Time-limited GET URL for direct playback/download."""
        if not cls._client:
            raise RuntimeError("MinIO not initialized")
        from datetime import timedelta

        return cls._client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=expires_seconds)
        )


class QdrantClient:
    """Wrapper around Qdrant async client."""

    _client: AsyncQdrantClient | None = None

    @classmethod
    async def init(cls) -> None:
        """Initialize Qdrant client."""
        if cls._client is None:
            cls._client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=10,
            )
            logger.info("Qdrant client initialized")

    @classmethod
    async def close(cls) -> None:
        """Close Qdrant client."""
        if cls._client:
            await cls._client.close()
            cls._client = None
            logger.info("Qdrant client closed")

    @classmethod
    async def search(cls, collection_name: str, vector: list[float], limit: int = 10):
        """Search for similar vectors."""
        if not cls._client:
            raise RuntimeError("Qdrant not initialized")
        return await cls._client.search(
            collection_name=collection_name, query_vector=vector, limit=limit
        )

    @classmethod
    async def upsert(cls, collection_name: str, points: list) -> None:
        """Upsert points to a collection."""
        if not cls._client:
            raise RuntimeError("Qdrant not initialized")
        await cls._client.upsert(collection_name=collection_name, points=points)


class OllamaClient:
    """Wrapper around Ollama API."""

    _base_url: str = f"http://{settings.ollama_host}:{settings.ollama_port}"

    @classmethod
    async def generate(cls, model: str, prompt: str, stream: bool = False) -> str:
        """Generate text using Ollama."""
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{cls._base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": stream},
            )
            resp.raise_for_status()
            return resp.json()["response"]

    @classmethod
    async def embed(cls, model: str, text: str) -> list[float]:
        """Generate embeddings using Ollama."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{cls._base_url}/api/embeddings",
                json={"model": model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
