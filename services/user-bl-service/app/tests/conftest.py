"""
User BL Service — Test Configuration.

Provides shared pytest fixtures for testing user business logic routes.
Path resolution is handled by pytest.ini (pythonpath setting), so no
manual sys.path manipulation is needed here.
"""

import pytest
from datetime import datetime
from typing import Generator

from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import CurrentUser, get_current_user


# ==============================================================================
# Helper Factories
# ==============================================================================

def _make_owner_user() -> CurrentUser:
    """Create a mock owner user with company_id for dependency injection."""
    return CurrentUser(
        user_id=1, email="owner@test.com", role="owner",
        owner_id=1, company_id=1,
    )


def _make_employee_user() -> CurrentUser:
    """Create a mock employee user with company_id for dependency injection."""
    return CurrentUser(
        user_id=2, email="emp@test.com", role="employee",
        owner_id=1, company_id=1,
    )


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
    app.dependency_overrides[get_current_user] = lambda: _make_owner_user()
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
    app.dependency_overrides[get_current_user] = lambda: _make_employee_user()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client() -> Generator[TestClient, None, None]:
    """
    Test client with no auth override (default behaviour).

    Yields:
        TestClient: Unauthenticated sync test client.
    """
    with TestClient(app) as c:
        yield c


# ==============================================================================
# Sample Data Fixtures
# ==============================================================================

@pytest.fixture
def sample_user_response() -> dict:
    """
    Sample user response from user-db-access-service.

    Returns:
        dict: User data dictionary with all expected fields.
    """
    return {
        "id": 10,
        "email": "new@test.com",
        "first_name": "New",
        "last_name": "User",
        "phone": None,
        "role": "employee",
        "is_active": True,
        "owner_id": 1,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }


@pytest.fixture
def sample_user_list() -> dict:
    """
    Sample paginated user list from user-db-access-service.

    Returns:
        dict: Paginated response with a single owner user.
    """
    return {
        "items": [
            {
                "id": 1,
                "email": "owner@test.com",
                "first_name": "Owner",
                "last_name": "User",
                "phone": None,
                "role": "owner",
                "is_active": True,
                "owner_id": None,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        ],
        "total": 1,
        "page": 1,
        "per_page": 100,
        "pages": 1,
    }
