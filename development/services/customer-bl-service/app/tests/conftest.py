"""
Customer BL Service — Test Configuration.

Provides shared pytest fixtures for testing customer business logic routes.
Path resolution is handled by pytest.ini (pythonpath setting), so no
manual sys.path manipulation is needed here.
"""

from collections.abc import Generator
from datetime import datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import CurrentUser, get_current_user
from app.main import app

# ==============================================================================
# Helper Factories
# ==============================================================================


def _make_owner() -> CurrentUser:
    """Create a mock owner user for dependency injection."""
    return CurrentUser(user_id=1, email="owner@test.com", role="owner", owner_id=1)


def _make_employee() -> CurrentUser:
    """Create a mock employee user for dependency injection."""
    return CurrentUser(user_id=5, email="emp@test.com", role="employee", owner_id=1)


# ==============================================================================
# Client Fixtures
# ==============================================================================


@pytest.fixture
def owner_client() -> Generator[TestClient, None, None]:
    """
    Test client authenticated as a tenant owner.

    Overrides the ``get_current_user`` dependency so every request
    is treated as coming from an owner with ``owner_id=1``.

    Yields:
        TestClient: Authenticated sync test client.
    """
    app.dependency_overrides[get_current_user] = lambda: _make_owner()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def employee_client() -> Generator[TestClient, None, None]:
    """
    Test client authenticated as an employee.

    Overrides the ``get_current_user`` dependency so every request
    is treated as coming from an employee within ``owner_id=1``.

    Yields:
        TestClient: Authenticated sync test client.
    """
    app.dependency_overrides[get_current_user] = lambda: _make_employee()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ==============================================================================
# Sample Data Fixtures
# ==============================================================================


@pytest.fixture
def sample_customer() -> dict:
    """
    Sample customer response from customer-db-access-service.

    Returns:
        dict: Customer data dictionary with all expected fields.
    """
    now = datetime.utcnow()
    return {
        "id": 10,
        "first_name": "Alice",
        "last_name": "Smith",
        "email": "alice@example.com",
        "phone": "555-1234",
        "company": "Smith Corp",
        "address": "456 Oak Ave",
        "eircode": "D04 AB12",
        "owner_id": 1,
        "is_active": True,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@pytest.fixture
def sample_note() -> dict:
    """
    Sample customer note.

    Returns:
        dict: Note data dictionary with all expected fields.
    """
    now = datetime.utcnow()
    return {
        "id": 1,
        "customer_id": 10,
        "content": "Great customer, very responsive.",
        "created_by_id": 1,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


# ==============================================================================
# Permission Mock Fixture
# ==============================================================================


@pytest.fixture(autouse=True)
def _mock_permission_http_check():
    """Mock the HTTP call that ``require_permission`` makes for non-privileged roles.

    Returns a realistic response based on employee role defaults.
    Privileged roles (owner, admin, superadmin) bypass the HTTP call entirely.
    """
    employee_defaults = frozenset(
        {
            "company.view",
            "customers.create",
            "customers.edit",
            "jobs.create",
            "jobs.edit",
            "jobs.update_status",
            "notes.create",
            "notes.edit",
        }
    )

    async def _check_permission(self, url, **kwargs):
        url_str = str(url)
        if "/api/v1/permissions/" in url_str and "/check/" in url_str:
            perm = url_str.rsplit("/check/", 1)[-1].rstrip("/")
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 200
            resp.json.return_value = {
                "user_id": 0,
                "permission": perm,
                "granted": perm in employee_defaults,
            }
            return resp
        raise httpx.ConnectError("not mocked")

    with patch.object(httpx.AsyncClient, "get", _check_permission):
        yield
