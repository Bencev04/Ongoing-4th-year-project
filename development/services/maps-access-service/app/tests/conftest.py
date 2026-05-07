"""
Pytest configuration and fixtures for maps-access-service tests.
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client wired to the FastAPI app.

    Yields:
        AsyncClient bound to the test ASGI transport.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _mock_redis() -> None:
    """Disable Redis for all tests (same pattern as other services)."""
    with patch(
        "app.services.google_maps.get_redis",
        new_callable=AsyncMock,
        return_value=None,
    ):
        yield


@pytest.fixture
def mock_google_geocode_success() -> dict:
    """Sample successful Google Geocoding API response.

    Returns:
        Dict matching the Google Geocoding API JSON structure.
    """
    return {
        "status": "OK",
        "results": [
            {
                "geometry": {
                    "location": {
                        "lat": 53.3498,
                        "lng": -6.2603,
                    }
                },
                "formatted_address": "Dublin, Ireland",
                "address_components": [
                    {
                        "long_name": "D02 XY45",
                        "short_name": "D02 XY45",
                        "types": ["postal_code"],
                    },
                    {
                        "long_name": "Dublin",
                        "short_name": "Dublin",
                        "types": ["locality", "political"],
                    },
                ],
            }
        ],
    }


@pytest.fixture
def mock_google_geocode_no_results() -> dict:
    """Sample Google Geocoding API response with no results.

    Returns:
        Dict matching the Google Geocoding API JSON structure.
    """
    return {
        "status": "ZERO_RESULTS",
        "results": [],
    }
