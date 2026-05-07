"""
Unit tests for User BL Service — service_client module.

Tests the HTTP client layer that communicates with user-db-access-service.
Every async function is tested for:
    1. Cache miss → successful HTTP call → cache set
    2. Cache hit → return cached data (no HTTP call)
    3. Downstream error codes (404, 409, 4xx) → appropriate HTTPException
    4. Connection error → 503 HTTPException

Industry standard: 100% branch coverage on the client adapter layer.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data: dict = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = '{"detail": "error"}'
    return resp


# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------
_SC = "app.service_client"
_CLIENT = f"{_SC}._client"
_CACHE_GET = f"{_SC}.cache_get"
_CACHE_SET = f"{_SC}.cache_set"
_CACHE_DEL = f"{_SC}.cache_delete"
_CACHE_DEL_P = f"{_SC}.cache_delete_pattern"


# ==============================================================================
# get_users
# ==============================================================================


class TestGetUsers:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_miss_makes_http_call(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_users

        payload = {"items": [], "total": 0}
        mock_get.return_value = _mock_response(200, payload)
        result = await get_users(skip=0, limit=10, owner_id=1)
        assert result == payload
        mock_get.assert_called_once()
        mock_cs.assert_called_once()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value={"items": [], "total": 0})
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit_skips_http(self, mock_get, mock_cg):
        from app.service_client import get_users

        result = await get_users(skip=0, limit=10, owner_id=1)
        assert result == {"items": [], "total": 0}
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error_raises_503(self, mock_get, mock_cg):
        from app.service_client import get_users

        with pytest.raises(HTTPException) as exc_info:
            await get_users(skip=0, limit=10)
        assert exc_info.value.status_code == 503


# ==============================================================================
# get_user
# ==============================================================================


class TestGetUser:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_user

        user_data = {"id": 1, "email": "test@test.com"}
        mock_get.return_value = _mock_response(200, user_data)
        result = await get_user(1)
        assert result == user_data

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value={"id": 1})
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_user

        result = await get_user(1)
        assert result == {"id": 1}
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_404_raises(self, mock_get, mock_cg):
        from app.service_client import get_user

        mock_get.return_value = _mock_response(404)
        with pytest.raises(HTTPException) as exc_info:
            await get_user(999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_user

        with pytest.raises(HTTPException) as exc_info:
            await get_user(1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# create_user
# ==============================================================================


class TestCreateUser:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.post", new_callable=AsyncMock)
    async def test_success(self, mock_post, mock_cdp):
        from app.service_client import create_user

        user_data = {"id": 10, "email": "new@test.com"}
        mock_post.return_value = _mock_response(200, user_data)
        result = await create_user({"email": "new@test.com", "password": "pass"})
        assert result == user_data
        mock_cdp.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{_CLIENT}.post", new_callable=AsyncMock)
    async def test_409_conflict(self, mock_post):
        from app.service_client import create_user

        mock_post.return_value = _mock_response(409, {"detail": "Email exists"})
        with pytest.raises(HTTPException) as exc_info:
            await create_user({"email": "dup@test.com"})
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_post):
        from app.service_client import create_user

        with pytest.raises(HTTPException) as exc_info:
            await create_user({"email": "new@test.com"})
        assert exc_info.value.status_code == 503


# ==============================================================================
# update_user
# ==============================================================================


class TestUpdateUser:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.put", new_callable=AsyncMock)
    async def test_success(self, mock_put, mock_cd, mock_cdp):
        from app.service_client import update_user

        updated = {"id": 1, "first_name": "Updated"}
        mock_put.return_value = _mock_response(200, updated)
        result = await update_user(1, {"first_name": "Updated"})
        assert result == updated
        mock_cd.assert_called_once()
        mock_cdp.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.put", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error(self, mock_put):
        from app.service_client import update_user

        with pytest.raises(HTTPException) as exc_info:
            await update_user(1, {"first_name": "X"})
        assert exc_info.value.status_code == 503


# ==============================================================================
# delete_user
# ==============================================================================


class TestDeleteUser:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.delete", new_callable=AsyncMock)
    async def test_success(self, mock_del, mock_cd, mock_cdp):
        from app.service_client import delete_user

        mock_del.return_value = _mock_response(200)
        await delete_user(1)
        mock_cd.assert_called_once()
        mock_cdp.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{_CLIENT}.delete", new_callable=AsyncMock)
    async def test_404_raises(self, mock_del):
        from app.service_client import delete_user

        mock_del.return_value = _mock_response(404)
        with pytest.raises(HTTPException) as exc_info:
            await delete_user(999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.delete",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_del):
        from app.service_client import delete_user

        with pytest.raises(HTTPException) as exc_info:
            await delete_user(1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# get_employees_by_owner
# ==============================================================================


class TestGetEmployeesByOwner:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_employees_by_owner

        employees = {
            "items": [{"id": 1, "user_id": 2}],
            "total": 1,
            "page": 1,
            "per_page": 100,
            "pages": 1,
        }
        mock_get.return_value = _mock_response(200, employees)
        result = await get_employees_by_owner(owner_id=1)
        assert result == employees

    @pytest.mark.asyncio
    @patch(
        _CACHE_GET,
        new_callable=AsyncMock,
        return_value={
            "items": [{"id": 1}],
            "total": 1,
            "page": 1,
            "per_page": 100,
            "pages": 1,
        },
    )
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_employees_by_owner

        result = await get_employees_by_owner(owner_id=1)
        assert result == {
            "items": [{"id": 1}],
            "total": 1,
            "page": 1,
            "per_page": 100,
            "pages": 1,
        }
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_employees_by_owner

        with pytest.raises(HTTPException) as exc_info:
            await get_employees_by_owner(owner_id=1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# create_employee / update_employee / get_employee
# ==============================================================================


class TestCreateEmployee:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.post", new_callable=AsyncMock)
    async def test_success(self, mock_post, mock_cdp):
        from app.service_client import create_employee

        emp = {"id": 5, "user_id": 10}
        mock_post.return_value = _mock_response(200, emp)
        result = await create_employee({"user_id": 10, "position": "Dev"})
        assert result == emp

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error(self, mock_post):
        from app.service_client import create_employee

        with pytest.raises(HTTPException) as exc_info:
            await create_employee({"user_id": 10})
        assert exc_info.value.status_code == 503


class TestUpdateEmployee:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.put", new_callable=AsyncMock)
    async def test_success(self, mock_put, mock_cdp):
        from app.service_client import update_employee

        emp = {"id": 5, "position": "Senior Dev"}
        mock_put.return_value = _mock_response(200, emp)
        result = await update_employee(5, {"position": "Senior Dev"})
        assert result == emp

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.put", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error(self, mock_put):
        from app.service_client import update_employee

        with pytest.raises(HTTPException) as exc_info:
            await update_employee(5, {"position": "X"})
        assert exc_info.value.status_code == 503


class TestGetEmployee:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_employee

        emp = {"id": 5, "user_id": 2}
        mock_get.return_value = _mock_response(200, emp)
        result = await get_employee(5)
        assert result == emp

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_404(self, mock_get, mock_cg):
        from app.service_client import get_employee

        mock_get.return_value = _mock_response(404)
        with pytest.raises(HTTPException) as exc_info:
            await get_employee(999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value={"id": 5})
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_employee

        result = await get_employee(5)
        assert result == {"id": 5}
        mock_get.assert_not_called()


# ==============================================================================
# get_company / update_company
# ==============================================================================


class TestGetCompany:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_company

        company = {"id": 1, "name": "Test Co"}
        mock_get.return_value = _mock_response(200, company)
        result = await get_company(1)
        assert result == company

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_company

        with pytest.raises(HTTPException) as exc_info:
            await get_company(1)
        assert exc_info.value.status_code == 503


class TestUpdateCompany:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.put", new_callable=AsyncMock)
    async def test_success(self, mock_put, mock_cd):
        from app.service_client import update_company

        company = {"id": 1, "name": "Updated Co"}
        mock_put.return_value = _mock_response(200, company)
        result = await update_company(1, {"name": "Updated Co"})
        assert result == company

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.put", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    )
    async def test_connect_error(self, mock_put):
        from app.service_client import update_company

        with pytest.raises(HTTPException) as exc_info:
            await update_company(1, {"name": "X"})
        assert exc_info.value.status_code == 503


# ==============================================================================
# _handle_response edge cases
# ==============================================================================


class TestHandleResponse:
    @pytest.mark.asyncio
    async def test_generic_4xx_raises(self):
        from app.service_client import _handle_response

        with pytest.raises(HTTPException) as exc_info:
            await _handle_response(_mock_response(422))
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_200_returns_json(self):
        from app.service_client import _handle_response

        result = await _handle_response(_mock_response(200, {"ok": True}))
        assert result == {"ok": True}
