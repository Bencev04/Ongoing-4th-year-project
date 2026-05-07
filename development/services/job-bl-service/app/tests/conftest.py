"""
Job BL Service — Test Configuration.

Provides shared pytest fixtures for testing job business logic routes.
Path resolution is handled by pytest.ini (pythonpath setting), so no
manual sys.path manipulation is needed here.
"""

from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import CurrentUser, get_current_user
from app.main import app

# ==============================================================================
# Permission Check HTTP Mock (autouse)
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
def sample_job() -> dict:
    """
    Sample job response from job-db-access-service.

    Returns:
        dict: Job data dictionary with all expected fields.
    """
    now = datetime.utcnow()
    return {
        "id": 1,
        "title": "Fix Sink",
        "description": "Leaky sink repair",
        "customer_id": 10,
        "owner_id": 1,
        "assigned_to": 5,
        "status": "scheduled",
        "priority": "medium",
        "start_time": now.isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "estimated_duration": 120,
        "address": "123 Main St",
        "notes": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


@pytest.fixture
def sample_customer() -> dict:
    """
    Sample customer data for job-related lookups.

    Returns:
        dict: Minimal customer data with name and owner_id.
    """
    return {
        "id": 10,
        "name": "Alice Smith",
        "email": "alice@example.com",
        "owner_id": 1,
    }
