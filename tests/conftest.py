"""Shared test fixtures for knowledge-service automated tests.

Uses real PostgreSQL with pgvector (Docker container on port 15434).
Mocks JWT auth and embedding service.
"""

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
import random

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from knowledge_service.main import app
from knowledge_service.services.auth import UserContext, get_current_user
from knowledge_service.db import pool as db_pool_module


# ---------------------------------------------------------------------------
# Mock auth
# ---------------------------------------------------------------------------

TEST_USER = UserContext(
    user_id="550e8400-e29b-41d4-a716-446655440000",
    email="test-assessor@email.com",
    role="assessor",
    name="Test Assessor",
)


async def mock_get_current_user() -> UserContext:
    return TEST_USER


app.dependency_overrides[get_current_user] = mock_get_current_user


# ---------------------------------------------------------------------------
# Mock embedding — returns random vectors instead of calling OpenAI
# ---------------------------------------------------------------------------


def _random_vector(dim: int = 1536) -> list[float]:
    return [random.uniform(-1, 1) for _ in range(dim)]


@pytest.fixture(autouse=True)
def mock_embeddings():
    """Mock embedding service so tests don't need OpenAI API key."""
    with (
        patch(
            "knowledge_service.services.embedding.embed_texts",
            new_callable=AsyncMock,
            side_effect=lambda texts: [_random_vector() for _ in texts],
        ),
        patch(
            "knowledge_service.services.embedding.embed_single",
            new_callable=AsyncMock,
            side_effect=lambda text: _random_vector(),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# DB cleanup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop_policy():
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(autouse=True)
async def reset_and_clean_db():
    """Reset DB pool and clean tables before/after each test."""
    db_pool_module._pool = None
    pool = await db_pool_module.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM enriched_chunks")
        await conn.execute("DELETE FROM policy_chunks")
        await conn.execute("DELETE FROM document_chunks")
        await conn.execute("DELETE FROM topics")
    yield
    pool = await db_pool_module.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM enriched_chunks")
        await conn.execute("DELETE FROM policy_chunks")
        await conn.execute("DELETE FROM document_chunks")
        await conn.execute("DELETE FROM topics")
    await db_pool_module.close_pool()


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
