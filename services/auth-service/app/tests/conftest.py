"""
Test configuration and fixtures for Auth Service.

Uses async SQLite (aiosqlite) for database tests and patches Redis
to ensure tests run without external dependencies.
Path resolution is handled by pytest.ini (pythonpath setting).
"""

from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
from app.crud.auth import (
    create_access_token,
    create_refresh_token,
    store_refresh_token,
)
from app.models.auth import RefreshToken

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
# Auto-patch Redis for ALL tests (no real Redis needed)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_redis():
    """Patch ``get_redis`` so every Redis call raises immediately.

    The auth CRUD code catches Redis exceptions and falls back to
    the Postgres (SQLite in tests) blacklist table, so this is safe.
    """
    with patch(
        "app.crud.auth.get_redis",
        new_callable=AsyncMock,
        side_effect=Exception("Redis unavailable in tests"),
    ):
        yield


@pytest.fixture(autouse=True)
def _mock_httpx_client():
    """Patch the module-level ``_http_client`` in routes to avoid
    real network calls (auth → user-db-access-service).

    Returns a 200 with minimal user data for any GET/POST attempt.
    """
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "authenticated": True,
        "user_id": 1,
        "email": "owner@demo.com",
        "role": "owner",
        "owner_id": 1,
        "id": 1,
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response

    with patch("app.api.routes._http_client", mock_client):
        yield


# ---------------------------------------------------------------------------
# Database session
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


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

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
def sample_user() -> dict:
    """Sample owner user data."""
    return {
        "id": 1,
        "email": "owner@demo.com",
        "role": "owner",
        "owner_id": 1,
    }


@pytest.fixture()
def sample_employee() -> dict:
    """Sample employee user data."""
    return {
        "id": 2,
        "email": "employee@demo.com",
        "role": "employee",
        "owner_id": 1,
    }


@pytest.fixture()
def sample_superadmin() -> dict:
    """Sample superadmin user data (no tenant)."""
    return {
        "id": 999,
        "email": "superadmin@system.local",
        "role": "superadmin",
        "owner_id": None,
    }


# ---------------------------------------------------------------------------
# Token fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def access_token_for_owner(sample_user: dict) -> tuple[str, str, datetime]:
    """Create a valid access token for the sample owner."""
    return create_access_token(
        user_id=sample_user["id"],
        email=sample_user["email"],
        role=sample_user["role"],
        owner_id=sample_user["owner_id"],
    )


@pytest.fixture()
def access_token_for_employee(sample_employee: dict) -> tuple[str, str, datetime]:
    """Create a valid access token for the sample employee."""
    return create_access_token(
        user_id=sample_employee["id"],
        email=sample_employee["email"],
        role=sample_employee["role"],
        owner_id=sample_employee["owner_id"],
    )


@pytest.fixture()
def access_token_for_superadmin(sample_superadmin: dict) -> tuple[str, str, datetime]:
    """Create a valid access token for the sample superadmin."""
    return create_access_token(
        user_id=sample_superadmin["id"],
        email=sample_superadmin["email"],
        role=sample_superadmin["role"],
        owner_id=sample_superadmin["owner_id"],
    )


@pytest.fixture()
async def stored_refresh_token(
    db_session: AsyncSession,
    sample_user: dict,
) -> tuple[str, RefreshToken]:
    """Store a refresh token in the DB and return (raw_token, db_row)."""
    raw: str = create_refresh_token()
    row: RefreshToken = await store_refresh_token(
        db=db_session,
        user_id=sample_user["id"],
        owner_id=sample_user["owner_id"],
        raw_token=raw,
        device_info="pytest",
        ip_address="127.0.0.1",
    )
    return raw, row
