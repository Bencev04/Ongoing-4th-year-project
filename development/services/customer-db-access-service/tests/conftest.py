"""
Test configuration and fixtures for Customer Service.

Uses async SQLite (aiosqlite) to accurately reflect the production
async database layer.  Each test function receives a freshly created
schema so tests remain fully isolated.
Path resolution is handled by pytest.ini (pythonpath setting).
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.main import app
from common.database import Base, get_async_db

# ---------------------------------------------------------------------------
# Async in-memory SQLite engine
# ---------------------------------------------------------------------------

SQLALCHEMY_DATABASE_URL: str = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingAsyncSession = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Database session fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async database session with a clean schema.

    Tables are created before yielding and dropped after the test
    completes, ensuring full isolation between tests.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingAsyncSession() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an ``AsyncClient`` backed by the in-memory test database.

    Overrides the production ``get_async_db`` dependency so that all
    requests use the test session.  ``ASGITransport`` does **not**
    trigger lifespan events, so no real PostgreSQL connection is made.
    """

    async def _override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_db] = _override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_customer_data() -> dict:
    """Provide sample customer creation data."""
    return {
        "owner_id": 1,
        "name": "John Smith",
        "email": "john.smith@example.com",
        "phone": "0871234567",
        "address": "123 Main Street, Dublin",
        "eircode": "D02 XY45",
        "company_name": "Smith & Co.",
    }


@pytest.fixture()
def sample_note_data() -> dict:
    """Provide sample note creation data."""
    return {
        "content": "Customer prefers morning appointments",
        "created_by_id": 1,
    }
