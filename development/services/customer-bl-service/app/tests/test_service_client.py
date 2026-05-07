"""
Unit tests for Customer BL Service — service_client module.

Tests the HTTP client layer that communicates with customer-db-access-service
and job-db-access-service. Covers cache hit/miss, error codes, connection
errors, and field translation helpers.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException


def _mock_response(status_code: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = '{"detail": "error"}'
    return resp


_SC = "app.service_client"
_CUST_CLIENT = f"{_SC}._customer_client"
_JOB_CLIENT = f"{_SC}._job_client"
_CACHE_GET = f"{_SC}.cache_get"
_CACHE_SET = f"{_SC}.cache_set"
_CACHE_DEL = f"{_SC}.cache_delete"
_CACHE_DEL_P = f"{_SC}.cache_delete_pattern"
_MAPS_CLIENT = f"{_SC}._maps_client"


# ==============================================================================
# Field Translation Tests
# ==============================================================================


class TestFieldTranslation:
    def test_to_db_payload_combines_names(self):
        from app.service_client import _to_db_payload

        result = _to_db_payload(
            {"first_name": "Alice", "last_name": "Smith", "email": "a@b.com"}
        )
        assert result["name"] == "Alice Smith"
        assert result["email"] == "a@b.com"
        assert "first_name" not in result

    def test_to_db_payload_company_rename(self):
        from app.service_client import _to_db_payload

        result = _to_db_payload({"company": "Acme Corp"})
        assert result["company_name"] == "Acme Corp"
        assert "company" not in result

    def test_from_db_response_splits_name(self):
        from app.service_client import _from_db_response

        result = _from_db_response({"name": "Alice Smith", "company_name": "Acme"})
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Smith"
        assert result["company"] == "Acme"

    def test_from_db_response_single_name(self):
        from app.service_client import _from_db_response

        result = _from_db_response({"name": "Alice"})
        assert result["first_name"] == "Alice"
        assert result["last_name"] == ""


# ==============================================================================
# get_customers
# ==============================================================================


class TestGetCustomers:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_miss(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_customers

        data = {"items": [], "total": 0}
        mock_get.return_value = _mock_response(200, data)
        result = await get_customers(skip=0, limit=10, owner_id=1)
        assert result == data
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value={"items": []})
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_customers

        result = await get_customers(skip=0, limit=10, owner_id=1)
        assert result == {"items": []}
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CUST_CLIENT}.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_customers

        with pytest.raises(HTTPException) as exc_info:
            await get_customers(skip=0, limit=10)
        assert exc_info.value.status_code == 503


# ==============================================================================
# get_customer
# ==============================================================================


class TestGetCustomer:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_customer

        cust = {"id": 1, "name": "Alice Smith", "company_name": "Acme"}
        mock_get.return_value = _mock_response(200, cust)
        result = await get_customer(1)
        # _from_db_response translates name→first_name/last_name, company_name→company
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Smith"
        assert result["company"] == "Acme"

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_404(self, mock_get, mock_cg):
        from app.service_client import get_customer

        mock_get.return_value = _mock_response(404)
        with pytest.raises(HTTPException) as exc_info:
            await get_customer(999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CUST_CLIENT}.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_customer

        with pytest.raises(HTTPException) as exc_info:
            await get_customer(1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# create_customer
# ==============================================================================


class TestCreateCustomer:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_CUST_CLIENT}.post", new_callable=AsyncMock)
    async def test_success(self, mock_post, mock_cdp):
        from app.service_client import create_customer

        cust = {"id": 10, "name": "New Customer", "company_name": None}
        mock_post.return_value = _mock_response(200, cust)
        result = await create_customer({"first_name": "New", "last_name": "Customer"})
        assert result["id"] == 10
        assert result["first_name"] == "New"
        assert result["last_name"] == "Customer"

    @pytest.mark.asyncio
    @patch(f"{_CUST_CLIENT}.post", new_callable=AsyncMock)
    async def test_409_conflict(self, mock_post):
        from app.service_client import create_customer

        mock_post.return_value = _mock_response(409, {"detail": "duplicate"})
        with pytest.raises(HTTPException) as exc_info:
            await create_customer({"email": "dup@test.com"})
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    @patch(
        f"{_CUST_CLIENT}.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_post):
        from app.service_client import create_customer

        with pytest.raises(HTTPException) as exc_info:
            await create_customer({"email": "new@test.com"})
        assert exc_info.value.status_code == 503


# ==============================================================================
# update_customer / delete_customer
# ==============================================================================


class TestUpdateCustomer:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CUST_CLIENT}.put", new_callable=AsyncMock)
    async def test_success(self, mock_put, mock_cd, mock_cdp):
        from app.service_client import update_customer

        updated = {"id": 1, "name": "Updated Name", "company_name": None}
        mock_put.return_value = _mock_response(200, updated)
        result = await update_customer(1, {"first_name": "Updated"})
        assert result["id"] == 1
        assert result["first_name"] == "Updated"
        assert result["last_name"] == "Name"

    @pytest.mark.asyncio
    @patch(
        f"{_CUST_CLIENT}.put",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_put):
        from app.service_client import update_customer

        with pytest.raises(HTTPException) as exc_info:
            await update_customer(1, {"first_name": "X"})
        assert exc_info.value.status_code == 503


class TestDeleteCustomer:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CUST_CLIENT}.delete", new_callable=AsyncMock)
    async def test_success(self, mock_del, mock_cd, mock_cdp):
        from app.service_client import delete_customer

        mock_del.return_value = _mock_response(200)
        await delete_customer(1)
        mock_cd.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        f"{_CUST_CLIENT}.delete",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_del):
        from app.service_client import delete_customer

        with pytest.raises(HTTPException) as exc_info:
            await delete_customer(1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# Customer Notes
# ==============================================================================


class TestGetCustomerNotes:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_customer_notes

        notes = [{"id": 1, "content": "Note 1"}]
        mock_get.return_value = _mock_response(200, notes)
        result = await get_customer_notes(10)
        assert result == notes

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=[{"id": 1}])
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_customer_notes

        result = await get_customer_notes(10)
        assert result == [{"id": 1}]
        mock_get.assert_not_called()


class TestCreateCustomerNote:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_CUST_CLIENT}.post", new_callable=AsyncMock)
    async def test_success(self, mock_post, mock_cdp):
        from app.service_client import create_customer_note

        note = {"id": 1, "content": "New note"}
        mock_post.return_value = _mock_response(200, note)
        result = await create_customer_note(10, {"content": "New note"})
        assert result == note

    @pytest.mark.asyncio
    @patch(
        f"{_CUST_CLIENT}.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_post):
        from app.service_client import create_customer_note

        with pytest.raises(HTTPException) as exc_info:
            await create_customer_note(10, {"content": "Note"})
        assert exc_info.value.status_code == 503


class TestDeleteCustomerNote:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_CUST_CLIENT}.delete", new_callable=AsyncMock)
    async def test_success(self, mock_del, mock_cdp):
        from app.service_client import delete_customer_note

        mock_del.return_value = _mock_response(200)
        await delete_customer_note(1)


# ==============================================================================
# Cross-Service: get_jobs_for_customer
# ==============================================================================


class TestGetJobsForCustomer:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_jobs_for_customer

        jobs = [{"id": 1, "title": "Fix sink"}]
        mock_get.return_value = _mock_response(200, jobs)
        result = await get_jobs_for_customer(10, owner_id=1)
        assert result == jobs

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_JOB_CLIENT}.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_graceful_degradation(self, mock_get, mock_cg):
        from app.service_client import get_jobs_for_customer

        # Should gracefully degrade (return empty list) or raise
        try:
            result = await get_jobs_for_customer(10, owner_id=1)
            assert result == [] or result is None
        except HTTPException as e:
            assert e.status_code == 503


# ==============================================================================
# _handle edge cases
# ==============================================================================


class TestHandleResponse:
    @pytest.mark.asyncio
    async def test_generic_4xx(self):
        from app.service_client import _handle

        with pytest.raises(HTTPException) as exc_info:
            await _handle(_mock_response(422))
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_success(self):
        from app.service_client import _handle

        result = await _handle(_mock_response(200, {"ok": True}))
        assert result == {"ok": True}


# ==============================================================================
# _maybe_geocode tests
# ==============================================================================


class TestMaybeGeocode:
    """Tests for the non-blocking geocoding helper."""

    @pytest.mark.asyncio
    async def test_skips_when_coords_present(self) -> None:
        """Geocoding is skipped when latitude and longitude are already set."""
        from app.service_client import _maybe_geocode

        payload = {"address": "123 Main St", "latitude": 53.35, "longitude": -6.26}
        result = await _maybe_geocode(payload)
        assert result["latitude"] == 53.35
        assert result["longitude"] == -6.26

    @pytest.mark.asyncio
    async def test_skips_when_no_address_or_eircode(self) -> None:
        """Geocoding is skipped when neither address nor eircode is provided."""
        from app.service_client import _maybe_geocode

        payload = {"first_name": "John", "last_name": "Doe"}
        result = await _maybe_geocode(payload)
        assert "latitude" not in result
        assert "longitude" not in result

    @pytest.mark.asyncio
    @patch(f"{_MAPS_CLIENT}.post", new_callable=AsyncMock)
    async def test_geocode_by_address(self, mock_post: AsyncMock) -> None:
        """Address triggers /geocode and enriches the payload."""
        from app.service_client import _maybe_geocode

        mock_post.return_value = _mock_response(
            200, {"results": [{"latitude": 53.35, "longitude": -6.26}]}
        )
        payload = {"address": "123 Main St, Dublin"}
        result = await _maybe_geocode(payload)
        assert result["latitude"] == 53.35
        assert result["longitude"] == -6.26
        mock_post.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{_MAPS_CLIENT}.post", new_callable=AsyncMock)
    async def test_geocode_by_eircode(self, mock_post: AsyncMock) -> None:
        """Eircode triggers /geocode-eircode (takes priority over address)."""
        from app.service_client import _maybe_geocode

        mock_post.return_value = _mock_response(
            200, {"results": [{"latitude": 53.34, "longitude": -6.27}]}
        )
        payload = {"address": "123 Main St", "eircode": "D02 XY45"}
        result = await _maybe_geocode(payload)
        assert result["latitude"] == 53.34
        assert result["longitude"] == -6.27
        call_url = mock_post.call_args[0][0]
        assert "eircode" in call_url

    @pytest.mark.asyncio
    @patch(f"{_MAPS_CLIENT}.post", new_callable=AsyncMock)
    async def test_no_results_returns_payload_unchanged(
        self, mock_post: AsyncMock
    ) -> None:
        """Empty results from maps service leaves payload without coords."""
        from app.service_client import _maybe_geocode

        mock_post.return_value = _mock_response(200, {"results": []})
        payload = {"address": "Nonexistent Place"}
        result = await _maybe_geocode(payload)
        assert "latitude" not in result
        assert "longitude" not in result

    @pytest.mark.asyncio
    @patch(f"{_MAPS_CLIENT}.post", new_callable=AsyncMock)
    async def test_non_200_returns_payload_unchanged(
        self, mock_post: AsyncMock
    ) -> None:
        """Non-200 response from maps service leaves payload without coords."""
        from app.service_client import _maybe_geocode

        mock_post.return_value = _mock_response(500)
        payload = {"address": "123 Main St"}
        result = await _maybe_geocode(payload)
        assert "latitude" not in result
        assert "longitude" not in result

    @pytest.mark.asyncio
    @patch(
        f"{_MAPS_CLIENT}.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("maps service unavailable"),
    )
    async def test_connect_error_returns_payload_unchanged(
        self, mock_post: AsyncMock
    ) -> None:
        """ConnectError from maps service is swallowed — non-blocking."""
        from app.service_client import _maybe_geocode

        payload = {"address": "123 Main St"}
        result = await _maybe_geocode(payload)
        assert "latitude" not in result
        assert "longitude" not in result
