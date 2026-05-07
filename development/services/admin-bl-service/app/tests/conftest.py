"""
Test fixtures for Admin BL Service.

Provides:
- ``client`` — ``AsyncClient`` authenticated as superadmin via dependency override.
- ``owner_client`` — ``AsyncClient`` authenticated as owner (should be rejected).
- ``mock_http_client`` — patches ``service_client._http_client`` to prevent
  real HTTP calls.  By default the mock raises ``httpx.ConnectError`` so
  tests must explicitly configure responses.
- ``superadmin_token`` / ``owner_token`` — dummy token strings (auth is
  bypassed via dependency overrides, so these are just placeholders).

All fixtures are function-scoped so tests stay isolated.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_current_user
from app.main import app
from common.auth import CurrentUser

# ==============================================================================
# Mock User Factories
# ==============================================================================


def _make_superadmin_user() -> CurrentUser:
    """Create a mock superadmin user for dependency injection."""
    return CurrentUser(
        user_id=999,
        email="superadmin@system.local",
        role="superadmin",
        owner_id=None,
        company_id=None,
        organization_id=None,
    )


def _make_owner_user() -> CurrentUser:
    """Create a mock owner user (should be rejected by superadmin-only endpoints)."""
    return CurrentUser(
        user_id=1,
        email="owner@demo.com",
        role="owner",
        owner_id=1,
        company_id=1,
        organization_id=1,
    )


# ==============================================================================
# Auth Fixtures
# ==============================================================================


@pytest.fixture
def superadmin_token() -> str:
    """Dummy superadmin token (auth is bypassed via dependency override)."""
    return "test-superadmin-token"


@pytest.fixture
def owner_token() -> str:
    """Dummy owner token (auth is bypassed via dependency override)."""
    return "test-owner-token"


# ==============================================================================
# HTTP Client Mock
# ==============================================================================


@pytest.fixture(autouse=True)
def mock_http_client():
    """
    Patch the service client's HTTP client.

    Prevents real network calls.  Tests configure specific return
    values via ``mock.get.return_value``, ``mock.post.return_value``, etc.
    Default response is 503 so unhandled calls surface clearly.
    """
    mock = AsyncMock(spec=httpx.AsyncClient)
    # Default: return 503 so unhandled calls fail clearly (not silently)
    _default = httpx.Response(503, json={"detail": "Mock — no handler configured"})
    mock.get.return_value = _default
    mock.post.return_value = _default
    mock.put.return_value = _default
    mock.delete.return_value = _default

    with patch("app.service_client._http_client", mock):
        yield mock


# ==============================================================================
# Async Test Client — Superadmin (default)
# ==============================================================================


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client authenticated as superadmin.

    Overrides only ``get_current_user`` so that ``require_superadmin``
    still runs its role check (which passes for superadmin).
    """
    app.dependency_overrides[get_current_user] = lambda: _make_superadmin_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def owner_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client authenticated as owner.

    Overrides ``get_current_user`` to return an owner user.
    ``require_superadmin`` still runs and will reject with 403.
    """
    app.dependency_overrides[get_current_user] = lambda: _make_owner_user()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
