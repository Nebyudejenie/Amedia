"""Pytest configuration and shared fixtures."""
import asyncio
import os
from uuid import UUID, uuid4
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from api.main import app
from api.clients import PostgreSQLPool, RedisClient
from api.config import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_connection():
    """Get database connection."""
    await PostgreSQLPool.init()
    async with PostgreSQLPool.acquire() as conn:
        yield conn
    await PostgreSQLPool.close()


@pytest_asyncio.fixture
async def redis_client():
    """Get Redis client."""
    await RedisClient.init()
    yield RedisClient
    await RedisClient.close()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


# ============================================================================
# Test Data Factories
# ============================================================================


class WorkspaceFactory:
    """Factory for test workspaces."""

    @staticmethod
    def create_data() -> dict:
        """Create workspace test data."""
        return {
            "id": uuid4(),
            "name": f"Test Workspace {uuid4()}",
            "plan": "creator",
            "owner_id": uuid4(),
            "created_at": datetime.utcnow(),
        }


class UserFactory:
    """Factory for test users."""

    @staticmethod
    def create_data(workspace_id: UUID | None = None) -> dict:
        """Create user test data."""
        return {
            "id": uuid4(),
            "workspace_id": workspace_id or uuid4(),
            "email": f"test_{uuid4()}@example.com",
            "name": f"Test User {uuid4()}",
            "role": "editor",
            "password_hash": "hashed_password",
            "created_at": datetime.utcnow(),
        }


class ContentFactory:
    """Factory for test content items."""

    @staticmethod
    def create_data(workspace_id: UUID | None = None) -> dict:
        """Create content test data."""
        return {
            "id": uuid4(),
            "workspace_id": workspace_id or uuid4(),
            "source_id": uuid4(),
            "title": f"Test Content {uuid4()}",
            "description": "Test content description",
            "content_type": "article",
            "url": "https://example.com/article",
            "raw_content": "Raw content text",
            "created_at": datetime.utcnow(),
        }


class JobFactory:
    """Factory for test jobs."""

    @staticmethod
    def create_data(workspace_id: UUID | None = None) -> dict:
        """Create job test data."""
        return {
            "id": uuid4(),
            "workspace_id": workspace_id or uuid4(),
            "user_id": uuid4(),
            "job_type": "brief",
            "status": "pending",
            "payload": {"content_id": str(uuid4())},
            "created_at": datetime.utcnow(),
        }


class WebhookSubscriptionFactory:
    """Factory for test webhook subscriptions."""

    @staticmethod
    def create_data(workspace_id: UUID | None = None) -> dict:
        """Create webhook subscription test data."""
        return {
            "id": uuid4(),
            "workspace_id": workspace_id or uuid4(),
            "user_id": uuid4(),
            "url": "https://webhook.example.com/events",
            "events": ["content.ingested", "job.completed"],
            "secret": "test_secret_key",
            "headers": {"Authorization": "Bearer token"},
            "active": True,
            "created_at": datetime.utcnow(),
        }


class MLModelFactory:
    """Factory for test ML models."""

    @staticmethod
    def create_data(workspace_id: UUID | None = None) -> dict:
        """Create ML model test data."""
        return {
            "id": uuid4(),
            "workspace_id": workspace_id or uuid4(),
            "name": f"test_model_{uuid4()}",
            "type": "sentiment",
            "model_key": "huggingface:distilbert-base-uncased-finetuned-sst-2-english",
            "version": 1,
            "status": "active",
            "config": {"threshold": 0.5},
            "metrics": {"accuracy": 0.92},
            "created_at": datetime.utcnow(),
        }


# ============================================================================
# Auth Fixtures
# ============================================================================


@pytest.fixture
def auth_headers(client):
    """Get authorization headers for tests."""
    # Create test token (would normally call auth endpoint)
    test_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"
    return {"Authorization": f"Bearer {test_token}"}


@pytest.fixture
def workspace_id():
    """Get test workspace ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Get test user ID."""
    return uuid4()


# ============================================================================
# Helper Functions
# ============================================================================


async def insert_workspace(conn, workspace_id: UUID | None = None) -> UUID:
    """Insert test workspace and return ID."""
    ws_id = workspace_id or uuid4()

    await conn.execute(
        """
        INSERT INTO auth.workspaces (id, name, plan, owner_id)
        VALUES ($1, $2, $3, $4)
        """,
        ws_id,
        "Test Workspace",
        "creator",
        uuid4(),
    )

    return ws_id


async def insert_user(conn, workspace_id: UUID, user_id: UUID | None = None) -> UUID:
    """Insert test user and return ID."""
    uid = user_id or uuid4()

    await conn.execute(
        """
        INSERT INTO auth.users (id, workspace_id, email, name, role, password_hash)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        uid,
        workspace_id,
        f"test_{uid}@example.com",
        "Test User",
        "editor",
        "hashed_password",
    )

    return uid


async def insert_content(
    conn, workspace_id: UUID, content_id: UUID | None = None
) -> UUID:
    """Insert test content and return ID."""
    cid = content_id or uuid4()
    source_id = uuid4()

    await conn.execute(
        """
        INSERT INTO content.sources (id, workspace_id, source_type, url)
        VALUES ($1, $2, $3, $4)
        """,
        source_id,
        workspace_id,
        "rss",
        "https://example.com/feed",
    )

    await conn.execute(
        """
        INSERT INTO content.normalized_items
            (id, workspace_id, source_id, title, description, content_type, url)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        cid,
        workspace_id,
        source_id,
        "Test Content",
        "Test description",
        "article",
        "https://example.com/article",
    )

    return cid


@pytest.fixture
async def test_workspace(db_connection):
    """Create test workspace."""
    workspace_id = uuid4()
    await insert_workspace(db_connection, workspace_id)
    return workspace_id


@pytest.fixture
async def test_user(db_connection, test_workspace):
    """Create test user."""
    user_id = uuid4()
    await insert_user(db_connection, test_workspace, user_id)
    return user_id


@pytest.fixture
async def test_content(db_connection, test_workspace):
    """Create test content."""
    content_id = uuid4()
    await insert_content(db_connection, test_workspace, content_id)
    return content_id
