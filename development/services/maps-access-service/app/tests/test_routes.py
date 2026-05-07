"""
Tests for maps-access-service API routes.

Covers all geocoding endpoints, health check, and graceful
degradation when the Google Maps API key is not configured or
the external API returns errors.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient

# ==============================================================================
# Health Check
# ==============================================================================


class TestHealthCheck:
    """Health endpoint tests."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Health endpoint returns 200 with service info."""
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "maps-access-service"


# ==============================================================================
# Geocode Endpoint
# ==============================================================================


class TestGeocodeEndpoint:
    """Tests for POST /api/v1/maps/geocode."""

    @pytest.mark.asyncio
    async def test_geocode_success(
        self,
        client: AsyncClient,
        mock_google_geocode_success: dict,
    ) -> None:
        """Geocode returns lat/lng and formatted address."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_google_geocode_success
        mock_resp.raise_for_status.return_value = None

        with (
            patch(
                "app.services.google_maps.settings",
            ) as mock_settings,
            patch("httpx.AsyncClient.get", return_value=mock_resp),
        ):
            mock_settings.google_maps_server_key = "test-key"
            mock_settings.redis_url = "redis://localhost:6379/0"

            resp = await client.post(
                "/api/v1/maps/geocode",
                json={"address": "Dublin, Ireland"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["latitude"] == 53.3498
        assert data["result"]["longitude"] == -6.2603
        assert data["result"]["formatted_address"] == "Dublin, Ireland"
        assert data["result"]["eircode"] == "D02 XY45"

    @pytest.mark.asyncio
    async def test_geocode_no_results(
        self,
        client: AsyncClient,
        mock_google_geocode_no_results: dict,
    ) -> None:
        """Geocode returns error when no results found."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_google_geocode_no_results
        mock_resp.raise_for_status.return_value = None

        with (
            patch(
                "app.services.google_maps.settings",
            ) as mock_settings,
            patch("httpx.AsyncClient.get", return_value=mock_resp),
        ):
            mock_settings.google_maps_server_key = "test-key"
            mock_settings.redis_url = "redis://localhost:6379/0"

            resp = await client.post(
                "/api/v1/maps/geocode",
                json={"address": "nonexistent place xyz123"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["result"] is None

    @pytest.mark.asyncio
    async def test_geocode_no_api_key(self, client: AsyncClient) -> None:
        """Geocode returns unavailable when API key is empty."""
        with patch("app.services.google_maps.settings") as mock_settings:
            mock_settings.google_maps_server_key = ""

            resp = await client.post(
                "/api/v1/maps/geocode",
                json={"address": "Dublin, Ireland"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_geocode_api_failure(self, client: AsyncClient) -> None:
        """Geocode returns error when Google API call fails."""
        with (
            patch("app.services.google_maps.settings") as mock_settings,
            patch(
                "httpx.AsyncClient.get",
                side_effect=httpx.ConnectError("Connection failed"),
            ),
        ):
            mock_settings.google_maps_server_key = "test-key"
            mock_settings.redis_url = "redis://localhost:6379/0"

            resp = await client.post(
                "/api/v1/maps/geocode",
                json={"address": "Dublin, Ireland"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_geocode_empty_address(self, client: AsyncClient) -> None:
        """Geocode rejects empty address with 422."""
        resp = await client.post(
            "/api/v1/maps/geocode",
            json={"address": ""},
        )
        assert resp.status_code == 422


# ==============================================================================
# Reverse Geocode Endpoint
# ==============================================================================


class TestReverseGeocodeEndpoint:
    """Tests for POST /api/v1/maps/reverse-geocode."""

    @pytest.mark.asyncio
    async def test_reverse_geocode_success(
        self,
        client: AsyncClient,
        mock_google_geocode_success: dict,
    ) -> None:
        """Reverse geocode returns address for valid coordinates."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_google_geocode_success
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.services.google_maps.settings") as mock_settings,
            patch("httpx.AsyncClient.get", return_value=mock_resp),
        ):
            mock_settings.google_maps_server_key = "test-key"
            mock_settings.redis_url = "redis://localhost:6379/0"

            resp = await client.post(
                "/api/v1/maps/reverse-geocode",
                json={"latitude": 53.3498, "longitude": -6.2603},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["formatted_address"] == "Dublin, Ireland"

    @pytest.mark.asyncio
    async def test_reverse_geocode_no_api_key(self, client: AsyncClient) -> None:
        """Reverse geocode returns unavailable when key missing."""
        with patch("app.services.google_maps.settings") as mock_settings:
            mock_settings.google_maps_server_key = ""

            resp = await client.post(
                "/api/v1/maps/reverse-geocode",
                json={"latitude": 53.3498, "longitude": -6.2603},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False

    @pytest.mark.asyncio
    async def test_reverse_geocode_invalid_coords(self, client: AsyncClient) -> None:
        """Reverse geocode rejects out-of-range coordinates."""
        resp = await client.post(
            "/api/v1/maps/reverse-geocode",
            json={"latitude": 200, "longitude": -6.2603},
        )
        assert resp.status_code == 422


# ==============================================================================
# Eircode Geocode Endpoint
# ==============================================================================


class TestEircodeGeocodeEndpoint:
    """Tests for POST /api/v1/maps/geocode-eircode."""

    @pytest.mark.asyncio
    async def test_eircode_geocode_success(
        self,
        client: AsyncClient,
        mock_google_geocode_success: dict,
    ) -> None:
        """Eircode geocode returns lat/lng and address."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_google_geocode_success
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.services.google_maps.settings") as mock_settings,
            patch("httpx.AsyncClient.get", return_value=mock_resp),
        ):
            mock_settings.google_maps_server_key = "test-key"
            mock_settings.redis_url = "redis://localhost:6379/0"

            resp = await client.post(
                "/api/v1/maps/geocode-eircode",
                json={"eircode": "D02 XY45"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["result"]["latitude"] == 53.3498

    @pytest.mark.asyncio
    async def test_eircode_geocode_no_api_key(self, client: AsyncClient) -> None:
        """Eircode geocode returns unavailable when key missing."""
        with patch("app.services.google_maps.settings") as mock_settings:
            mock_settings.google_maps_server_key = ""

            resp = await client.post(
                "/api/v1/maps/geocode-eircode",
                json={"eircode": "D02 XY45"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False

    @pytest.mark.asyncio
    async def test_eircode_geocode_empty(self, client: AsyncClient) -> None:
        """Eircode geocode rejects empty eircode."""
        resp = await client.post(
            "/api/v1/maps/geocode-eircode",
            json={"eircode": ""},
        )
        assert resp.status_code == 422
