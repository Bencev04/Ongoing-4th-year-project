"""
Test configuration and fixtures for User Service.

Uses async SQLite (aiosqlite) to accurately reflect the production
async database layer.  Each test gets a freshly created schema.
Path resolution is handled by pytest.ini (pythonpath setting).
"""

from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from common.database import Base, get_async_db
from app.main import app

# ---------------------------------------------------------------------------
# SQLite compatibility: BigInteger → INTEGER so that autoincrement works
# (PostgreSQL uses BIGSERIAL; SQLite only auto-increments INTEGER PK)
# ---------------------------------------------------------------------------

@compiles(BigInteger, "sqlite")
def _bi_as_integer(element, compiler, **kw):
    return "INTEGER"

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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh async database session with a clean schema."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingAsyncSession() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an ``AsyncClient`` backed by the in-memory test database."""
    async def _override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_db] = _override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_user_data() -> dict:
    """Provide sample user creation data."""
    return {
        "email": "test@example.com",
        "password": "testpassword123",
        "first_name": "Test",
        "last_name": "User",
        "phone": "1234567890",
        "role": "employee",
    }


@pytest.fixture()
def sample_owner_data() -> dict:
    """Provide sample owner creation data."""
    return {
        "email": "owner@example.com",
        "password": "ownerpassword123",
        "first_name": "Owner",
        "last_name": "User",
        "phone": "0987654321",
        "role": "owner",
    }


@pytest.fixture()
def sample_employee_data() -> dict:
    """Provide sample employee details data."""
    return {
        "position": "Plumber",
        "hourly_rate": 25.50,
        "skills": "plumbing,heating,gas",
        "notes": "Certified gas engineer",
    }
