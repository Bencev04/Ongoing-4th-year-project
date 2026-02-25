"""
Test configuration and fixtures for Job Service.

Uses async SQLite (aiosqlite) to accurately reflect the production
async database layer.  Each test gets a freshly created schema.
Path resolution is handled by pytest.ini (pythonpath setting).
"""

from datetime import datetime, timedelta
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from common.database import Base, get_async_db
from app.main import app

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
def sample_job_data() -> dict:
    """Provide sample scheduled job creation data."""
    start = datetime.utcnow() + timedelta(days=1)
    return {
        "owner_id": 1,
        "created_by_id": 1,
        "title": "Kitchen Renovation",
        "description": "Full kitchen renovation including cabinets and plumbing",
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=4)).isoformat(),
        "all_day": False,
        "status": "scheduled",
        "priority": "normal",
        "assigned_employee_id": 1,
        "customer_id": 1,
        "location": "123 Main Street, Dublin",
        "eircode": "D02 XY45",
        "estimated_duration": 240,
        "notes": "Customer prefers morning work",
        "color": "#3B82F6",
    }


@pytest.fixture()
def sample_unscheduled_job_data() -> dict:
    """Provide sample unscheduled (pending) job data."""
    return {
        "owner_id": 1,
        "created_by_id": 1,
        "title": "Emergency Repair",
        "description": "Urgent plumbing repair needed",
        "status": "pending",
        "priority": "urgent",
        "customer_id": 1,
        "location": "456 Oak Avenue, Dublin",
    }
