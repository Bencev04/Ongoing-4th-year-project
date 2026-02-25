"""
Unit tests for Job BL Service — service_client module.

Tests the HTTP client layer that communicates with job-db-access-service,
customer-db-access-service, and user-db-access-service.
Covers cache hit/miss, error codes, connection errors, and field
translation helpers.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
import httpx


def _mock_response(status_code: int = 200, json_data=None) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = '{"detail": "error"}'
    return resp


_SC = "app.service_client"
_JOB_CLIENT = f"{_SC}._job_client"
_CUST_CLIENT = f"{_SC}._customer_client"
_USER_CLIENT = f"{_SC}._user_client"
_CACHE_GET = f"{_SC}.cache_get"
_CACHE_SET = f"{_SC}.cache_set"
_CACHE_DEL = f"{_SC}.cache_delete"
_CACHE_DEL_P = f"{_SC}.cache_delete_pattern"


# ==============================================================================
# Field Translation Tests
# ==============================================================================

class TestFieldTranslation:
    def test_to_db_payload(self):
        from app.service_client import _to_db_payload
        result = _to_db_payload({"title": "Fix sink", "customer_id": 10})
        assert "title" in result

    def test_from_db_response(self):
        from app.service_client import _from_db_response
        result = _from_db_response({"id": 1, "title": "Fix sink"})
        assert result["id"] == 1

    def test_from_db_response_list(self):
        from app.service_client import _from_db_response_list
        result = _from_db_response_list([{"id": 1}, {"id": 2}])
        assert len(result) == 2


# ==============================================================================
# get_jobs
# ==============================================================================

class TestGetJobs:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_miss(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_jobs
        data = {"items": [], "total": 0}
        mock_get.return_value = _mock_response(200, data)
        result = await get_jobs(skip=0, limit=10, owner_id=1)
        assert result == data
        mock_get.assert_called_once()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value={"items": []})
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_jobs
        result = await get_jobs(skip=0, limit=10, owner_id=1)
        assert result == {"items": []}
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_jobs
        with pytest.raises(HTTPException) as exc_info:
            await get_jobs(skip=0, limit=10)
        assert exc_info.value.status_code == 503


# ==============================================================================
# get_job
# ==============================================================================

class TestGetJob:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_job
        job = {"id": 1, "title": "Fix sink"}
        mock_get.return_value = _mock_response(200, job)
        result = await get_job(1)
        assert result["title"] == "Fix sink"

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_404(self, mock_get, mock_cg):
        from app.service_client import get_job
        mock_get.return_value = _mock_response(404)
        with pytest.raises(HTTPException) as exc_info:
            await get_job(999)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_job
        with pytest.raises(HTTPException) as exc_info:
            await get_job(1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# create_job
# ==============================================================================

class TestCreateJob:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(f"{_JOB_CLIENT}.post", new_callable=AsyncMock)
    async def test_success(self, mock_post, mock_cdp):
        from app.service_client import create_job
        job = {"id": 10, "title": "New Job"}
        mock_post.return_value = _mock_response(200, job)
        result = await create_job({"title": "New Job", "status": "pending"})
        assert result == job

    @pytest.mark.asyncio
    @patch(f"{_JOB_CLIENT}.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_post):
        from app.service_client import create_job
        with pytest.raises(HTTPException) as exc_info:
            await create_job({"title": "New Job"})
        assert exc_info.value.status_code == 503


# ==============================================================================
# update_job / delete_job
# ==============================================================================

class TestUpdateJob:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_JOB_CLIENT}.put", new_callable=AsyncMock)
    async def test_success(self, mock_put, mock_cd, mock_cdp):
        from app.service_client import update_job
        updated = {"id": 1, "title": "Updated Job"}
        mock_put.return_value = _mock_response(200, updated)
        result = await update_job(1, {"title": "Updated Job"})
        assert result == updated

    @pytest.mark.asyncio
    @patch(f"{_JOB_CLIENT}.put", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_put):
        from app.service_client import update_job
        with pytest.raises(HTTPException) as exc_info:
            await update_job(1, {"title": "X"})
        assert exc_info.value.status_code == 503


class TestDeleteJob:
    @pytest.mark.asyncio
    @patch(_CACHE_DEL_P, new_callable=AsyncMock)
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_JOB_CLIENT}.delete", new_callable=AsyncMock)
    async def test_success(self, mock_del, mock_cd, mock_cdp):
        from app.service_client import delete_job
        mock_del.return_value = _mock_response(200)
        await delete_job(1)
        mock_cd.assert_called_once()

    @pytest.mark.asyncio
    @patch(f"{_JOB_CLIENT}.delete", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_del):
        from app.service_client import delete_job
        with pytest.raises(HTTPException) as exc_info:
            await delete_job(1)
        assert exc_info.value.status_code == 503


# ==============================================================================
# Calendar & Queue
# ==============================================================================

class TestCalendarJobs:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_calendar_jobs
        from datetime import date as dt_date
        resp_data = {"events": [{"id": 1}], "start_date": "2026-02-01", "end_date": "2026-02-28", "total": 1}
        mock_get.return_value = _mock_response(200, resp_data)
        result = await get_calendar_jobs(
            owner_id=1, start_date=dt_date(2026, 2, 1), end_date=dt_date(2026, 2, 28)
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_calendar_jobs
        from datetime import date as dt_date
        with pytest.raises(HTTPException) as exc_info:
            await get_calendar_jobs(owner_id=1, start_date=dt_date(2026, 2, 1), end_date=dt_date(2026, 2, 28))
        assert exc_info.value.status_code == 503


class TestJobsByAssigneeAndDate:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_jobs_by_assignee_and_date
        from datetime import date as dt_date
        resp_data = {"items": [{"id": 1, "assigned_employee_id": 5}], "total": 1}
        mock_get.return_value = _mock_response(200, resp_data)
        result = await get_jobs_by_assignee_and_date(
            assigned_to=5, target_date=dt_date(2026, 3, 15), owner_id=1
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=[{"id": 1}])
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_jobs_by_assignee_and_date
        from datetime import date as dt_date
        result = await get_jobs_by_assignee_and_date(
            assigned_to=5, target_date=dt_date(2026, 3, 15), owner_id=1
        )
        assert result == [{"id": 1}]
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_jobs_by_assignee_and_date
        from datetime import date as dt_date
        with pytest.raises(HTTPException) as exc_info:
            await get_jobs_by_assignee_and_date(
                assigned_to=5, target_date=dt_date(2026, 3, 15), owner_id=1
            )
        assert exc_info.value.status_code == 503


class TestUnscheduledJobs:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_unscheduled_jobs
        jobs = [{"id": 2, "status": "pending"}]
        mock_get.return_value = _mock_response(200, jobs)
        result = await get_unscheduled_jobs(owner_id=1)
        assert result == jobs

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=[{"id": 2}])
    @patch(f"{_JOB_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit(self, mock_get, mock_cg):
        from app.service_client import get_unscheduled_jobs
        result = await get_unscheduled_jobs(owner_id=1)
        assert result == [{"id": 2}]
        mock_get.assert_not_called()


# ==============================================================================
# Cross-Service: get_customer / get_user
# ==============================================================================

class TestCrossServiceGetCustomer:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_customer
        cust = {"id": 10, "name": "Alice"}
        mock_get.return_value = _mock_response(200, cust)
        result = await get_customer(10)
        assert result["name"] == "Alice"

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CUST_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_customer
        # Cross-service calls may gracefully degrade
        try:
            result = await get_customer(10)
            assert result is None or result == {}
        except HTTPException as e:
            assert e.status_code == 503


class TestCrossServiceGetUser:
    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_USER_CLIENT}.get", new_callable=AsyncMock)
    async def test_success(self, mock_get, mock_cg, mock_cs):
        from app.service_client import get_user
        user = {"id": 5, "email": "user@test.com"}
        mock_get.return_value = _mock_response(200, user)
        result = await get_user(5)
        assert result["email"] == "user@test.com"

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_USER_CLIENT}.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down"))
    async def test_connect_error(self, mock_get, mock_cg):
        from app.service_client import get_user
        try:
            result = await get_user(5)
            assert result is None or result == {}
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
