"""Configuration from environment variables."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Arada API configuration."""

    # API
    api_title: str = "Arada Intelligence OS"
    api_version: str = "0.1.0"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Database (PostgreSQL)
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = "arada"
    db_password: str
    db_name: str = "arada"
    db_pool_min: int = 5
    db_pool_max: int = 20

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # MinIO
    minio_host: str = "127.0.0.1"
    minio_port: int = 9000
    minio_access_key: str = "arada"
    minio_secret_key: str
    minio_bucket_prefix: str = "arada"

    # Qdrant
    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333

    # Ollama
    ollama_host: str = "127.0.0.1"
    ollama_port: int = 11434

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Rate limiting
    rate_limit_calls: int = 100
    rate_limit_period_seconds: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()  # type: ignore
