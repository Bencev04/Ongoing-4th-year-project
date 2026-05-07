"""
Frontend Service Test Configuration.

Provides pytest fixtures for testing the frontend routes and templates.
Path resolution is handled by pytest.ini (pythonpath setting), so no
manual sys.path manipulation is needed here.
"""

from collections.abc import Generator
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def sample_jobs() -> list[dict]:
    """
    Fixture providing sample job data for testing.

    Returns:
        list[dict]: List of sample job dictionaries
    """
    return [
        {
            "id": 1,
            "title": "Kitchen Renovation",
            "description": "Full kitchen remodel",
            "customer_id": 1,
            "customer_name": "John Doe",
            "owner_id": 1,
            "status": "scheduled",
            "priority": "high",
            "start_time": datetime(2024, 1, 15, 9, 0),
            "end_time": datetime(2024, 1, 15, 17, 0),
            "location": "123 Main St, Dublin",
            "eircode": "D02 XY45",
            "estimated_duration": 480,
            "notes": "Materials ordered",
            "created_at": datetime(2024, 1, 1),
            "updated_at": datetime(2024, 1, 1),
        },
        {
            "id": 2,
            "title": "Plumbing Repair",
            "description": "Fix leaking pipe",
            "customer_id": 2,
            "customer_name": "Jane Smith",
            "owner_id": 1,
            "status": "pending",
            "priority": "urgent",
            "start_time": None,
            "end_time": None,
            "location": "456 Oak Ave, Cork",
            "eircode": "T12 AB34",
            "estimated_duration": 120,
            "notes": None,
            "created_at": datetime(2024, 1, 5),
            "updated_at": datetime(2024, 1, 5),
        },
        {
            "id": 3,
            "title": "Electrical Inspection",
            "description": "Annual safety inspection",
            "customer_id": 1,
            "customer_name": "John Doe",
            "owner_id": 1,
            "status": "completed",
            "priority": "normal",
            "start_time": datetime(2024, 1, 10, 14, 0),
            "end_time": datetime(2024, 1, 10, 16, 0),
            "location": "123 Main St, Dublin",
            "eircode": "D02 XY45",
            "estimated_duration": 120,
            "notes": "All clear",
            "created_at": datetime(2024, 1, 2),
            "updated_at": datetime(2024, 1, 10),
        },
    ]


@pytest.fixture
def sample_customers() -> list[dict]:
    """
    Fixture providing sample customer data for testing.

    Returns:
        list[dict]: List of sample customer dictionaries
    """
    return [
        {
            "id": 1,
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+353 1 234 5678",
            "address": "123 Main St, Dublin",
            "eircode": "D02 XY45",
        },
        {
            "id": 2,
            "name": "Jane Smith",
            "email": "jane@example.com",
            "phone": "+353 21 987 6543",
            "address": "456 Oak Ave, Cork",
            "eircode": "T12 AB34",
        },
    ]


@pytest.fixture
def sample_employees() -> list[dict]:
    """
    Fixture providing sample employee data for testing.

    Returns:
        list[dict]: List of sample employee dictionaries
    """
    return [
        {"id": 1, "name": "Owner User", "email": "owner@crm.com", "role": "owner"},
        {"id": 2, "name": "Mike Johnson", "email": "mike@crm.com", "role": "employee"},
        {
            "id": 3,
            "name": "Sarah Williams",
            "email": "sarah@crm.com",
            "role": "employee",
        },
    ]


@pytest.fixture
def calendar_data() -> dict:
    """
    Fixture providing sample calendar data for testing.

    Returns:
        dict: Calendar data with year, month, and days
    """
    return {
        "year": 2024,
        "month": 1,
        "month_name": "January",
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "calendar_days": [
            {
                "day": day,
                "date": date(2024, 1, day) if 1 <= day <= 31 else None,
                "is_current_month": True,
                "is_today": day == 15,
                "events": [],
            }
            for day in range(1, 32)
        ],
    }


@pytest.fixture
def app() -> FastAPI:
    """
    Create a FastAPI test application instance.

    The ``_http_client`` used by the API-proxy routes is replaced with
    a mock that immediately raises ``httpx.ConnectError`` so tests
    never attempt real network calls to backend services.

    The ``service_client`` module is also patched so calendar routes
    never reach the job-bl-service.

    Returns:
        FastAPI: Test application instance
    """
    from app import service_client
    from app.main import app as main_app
    from app.routes import api_proxy

    # Build a mock that mimics httpx.AsyncClient.request() but raises
    # ConnectError instantly — same behaviour as a refused connection.
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request.side_effect = httpx.ConnectError(
        "Backend service unavailable (mocked for tests)"
    )

    # Also mock the service_client used by calendar routes.
    # Raising ConnectError makes every fetch* function return its
    # safe default (empty list / None) without network access.
    mock_sc_client = AsyncMock(spec=httpx.AsyncClient)
    mock_sc_client.get.side_effect = httpx.ConnectError(
        "job-bl-service unavailable (mocked for tests)"
    )

    # Patch module-level clients.
    original_api = api_proxy._http_client
    original_sc = service_client._http_client
    api_proxy._http_client = mock_client
    service_client._http_client = mock_sc_client
    yield main_app
    api_proxy._http_client = original_api
    service_client._http_client = original_sc


# ── Multi-day / overlapping event fixtures ─────────────────────────────


@pytest.fixture
def multi_day_job() -> dict[str, Any]:
    """A single job spanning three days (Jan 15 → Jan 17)."""
    return {
        "id": 10,
        "title": "Bathroom Refit",
        "description": "Multi-day bathroom renovation",
        "customer_id": 1,
        "owner_id": 1,
        "assigned_to": 2,
        "status": "scheduled",
        "priority": "high",
        "start_time": "2024-01-15T08:00:00",
        "end_time": "2024-01-17T18:00:00",
        "all_day": False,
        "color": "#3b82f6",
    }


@pytest.fixture
def overlapping_jobs() -> list[dict[str, Any]]:
    """Two jobs on the same day at overlapping times."""
    return [
        {
            "id": 20,
            "title": "Morning Plumbing",
            "status": "scheduled",
            "priority": "normal",
            "start_time": "2024-01-15T09:00:00",
            "end_time": "2024-01-15T12:00:00",
            "all_day": False,
            "color": None,
        },
        {
            "id": 21,
            "title": "Afternoon Electrical",
            "status": "pending",
            "priority": "urgent",
            "start_time": "2024-01-15T11:00:00",
            "end_time": "2024-01-15T15:00:00",
            "all_day": False,
            "color": "#f97316",
        },
    ]


@pytest.fixture
def calendar_api_response(
    multi_day_job: dict[str, Any],
    overlapping_jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Simulated /jobs/calendar API response for Jan 2024.

    Contains a multi-day job (spans 15→17) and two overlapping same-day
    jobs on Jan 15.  Useful for testing ``_expand_events_into_days``.
    """
    return [
        {
            "date": "2024-01-15",
            "jobs": [multi_day_job, *overlapping_jobs],
            "total_jobs": 3,
        },
    ]


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    """
    Create a test client for synchronous tests.

    Args:
        app: FastAPI application instance

    Yields:
        TestClient: Test client for making requests
    """
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def async_client(app: FastAPI) -> AsyncClient:
    """
    Create an async test client for async tests.

    Args:
        app: FastAPI application instance

    Returns:
        AsyncClient: Async test client for making requests
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
