"""
Unit tests for User BL Service — permission management endpoints
and require_permission enforcement.

Tests the permission-related API routes with mocked service-client calls.
Fixtures (owner_client, employee_client) are from conftest.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------
_SC = "app.service_client"
_CLIENT = f"{_SC}._client"
_CACHE_GET = f"{_SC}.cache_get"
_CACHE_SET = f"{_SC}.cache_set"
_CACHE_DEL = f"{_SC}.cache_delete"


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = '{"detail": "error"}'
    return resp


# ==============================================================================
# GET /permissions/catalog
# ==============================================================================


class TestGetPermissionCatalog:
    """Tests for GET /api/v1/permissions/catalog."""

    @patch(f"{_SC}.get_permission_catalog", new_callable=AsyncMock)
    def test_owner_can_get_catalog(
        self,
        mock_catalog: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        catalog_data = {
            "permissions": ["jobs.create", "jobs.delete"],
            "role_defaults": {"employee": ["jobs.create"]},
        }
        mock_catalog.return_value = catalog_data
        resp = owner_client.get("/api/v1/permissions/catalog")
        assert resp.status_code == 200
        assert resp.json() == catalog_data
        mock_catalog.assert_called_once()

    @patch(f"{_SC}.get_permission_catalog", new_callable=AsyncMock)
    def test_employee_can_get_catalog(
        self,
        mock_catalog: AsyncMock,
        employee_client: TestClient,
    ) -> None:
        """Catalog is public to authenticated users (no role gate)."""
        mock_catalog.return_value = {"permissions": [], "role_defaults": {}}
        resp = employee_client.get("/api/v1/permissions/catalog")
        assert resp.status_code == 200


# ==============================================================================
# GET /users/{user_id}/permissions
# ==============================================================================


class TestGetUserPermissions:
    """Tests for GET /api/v1/users/{user_id}/permissions."""

    @patch(f"{_SC}.get_user_permissions", new_callable=AsyncMock)
    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_owner_can_view_user_permissions(
        self,
        mock_get_user: AsyncMock,
        mock_get_perms: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get_user.return_value = {"id": 5, "owner_id": 1}
        mock_get_perms.return_value = {
            "user_id": 5,
            "owner_id": 1,
            "permissions": {"jobs.create": True},
        }
        resp = owner_client.get("/api/v1/users/5/permissions")
        assert resp.status_code == 200
        mock_get_perms.assert_called_once_with(1, 5)

    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_employee_cannot_view_permissions(
        self,
        mock_get_user: AsyncMock,
        employee_client: TestClient,
    ) -> None:
        """Endpoint requires owner/admin role — employee gets 403."""
        resp = employee_client.get("/api/v1/users/5/permissions")
        assert resp.status_code == 403

    @patch(f"{_SC}.get_user_permissions", new_callable=AsyncMock)
    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_denies_cross_tenant_access(
        self,
        mock_get_user: AsyncMock,
        mock_get_perms: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """Owner cannot view permissions of a user in another tenant."""
        mock_get_user.return_value = {"id": 99, "owner_id": 999}
        resp = owner_client.get("/api/v1/users/99/permissions")
        assert resp.status_code == 403
        mock_get_perms.assert_not_called()


# ==============================================================================
# PUT /users/{user_id}/permissions
# ==============================================================================


class TestUpdateUserPermissions:
    """Tests for PUT /api/v1/users/{user_id}/permissions."""

    @patch(f"{_SC}.update_user_permissions", new_callable=AsyncMock)
    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_owner_can_update_permissions(
        self,
        mock_get_user: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get_user.return_value = {"id": 5, "owner_id": 1}
        mock_update.return_value = {
            "user_id": 5,
            "owner_id": 1,
            "permissions": {"jobs.create": False},
        }
        resp = owner_client.put(
            "/api/v1/users/5/permissions",
            json={"permissions": {"jobs.create": False}},
        )
        assert resp.status_code == 200
        mock_update.assert_called_once_with(1, 5, {"jobs.create": False})

    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_employee_cannot_update_permissions(
        self,
        mock_get_user: AsyncMock,
        employee_client: TestClient,
    ) -> None:
        resp = employee_client.put(
            "/api/v1/users/5/permissions",
            json={"permissions": {"jobs.create": True}},
        )
        assert resp.status_code == 403

    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_cannot_modify_own_permissions(
        self,
        mock_get_user: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """Owner cannot modify their own permissions (user_id == current user)."""
        mock_get_user.return_value = {"id": 1, "owner_id": 1}
        resp = owner_client.put(
            "/api/v1/users/1/permissions",
            json={"permissions": {"jobs.create": True}},
        )
        assert resp.status_code == 400
        assert "own permissions" in resp.json()["detail"].lower()

    @patch(f"{_SC}.update_user_permissions", new_callable=AsyncMock)
    @patch(f"{_SC}.get_user", new_callable=AsyncMock)
    def test_denies_cross_tenant_update(
        self,
        mock_get_user: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get_user.return_value = {"id": 99, "owner_id": 999}
        resp = owner_client.put(
            "/api/v1/users/99/permissions",
            json={"permissions": {"jobs.create": True}},
        )
        assert resp.status_code == 403
        mock_update.assert_not_called()


# ==============================================================================
# GET /audit-logs
# ==============================================================================


class TestGetTenantAuditLogs:
    """Tests for GET /api/v1/audit-logs."""

    @patch(f"{_SC}.get_audit_logs", new_callable=AsyncMock)
    def test_owner_can_view_tenant_audit_logs(
        self,
        mock_get_logs: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get_logs.return_value = {
            "items": [
                {
                    "id": 1,
                    "timestamp": "2026-03-11T10:30:00Z",
                    "actor_id": 1,
                    "actor_email": "owner@test.com",
                    "actor_role": "owner",
                    "impersonator_id": None,
                    "organization_id": 1,
                    "action": "job.create",
                    "resource_type": "job",
                    "resource_id": "42",
                    "details": {"title": "Boiler Service"},
                    "ip_address": "127.0.0.1",
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 50,
            "pages": 1,
        }

        resp = owner_client.get("/api/v1/audit-logs")

        assert resp.status_code == 200
        mock_get_logs.assert_called_once_with(
            organization_id=1,
            page=1,
            per_page=50,
            actor_id=None,
            action=None,
            resource_type=None,
            search=None,
            date_from=None,
            date_to=None,
        )

    def test_employee_cannot_view_tenant_audit_logs(
        self,
        employee_client: TestClient,
    ) -> None:
        """Endpoint requires owner/admin role."""
        resp = employee_client.get("/api/v1/audit-logs")
        assert resp.status_code == 403


# ==============================================================================
# Service Client: Permission Functions
# ==============================================================================


class TestServiceClientGetPermissionCatalog:
    """Tests for service_client.get_permission_catalog."""

    @pytest.mark.asyncio
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_returns_catalog(self, mock_get: AsyncMock) -> None:
        from app.service_client import get_permission_catalog

        payload = {"permissions": ["jobs.create"], "role_defaults": {}}
        mock_get.return_value = _mock_response(200, payload)
        result = await get_permission_catalog()
        assert result == payload

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error_raises_503(self, mock_get: AsyncMock) -> None:
        from fastapi import HTTPException

        from app.service_client import get_permission_catalog

        with pytest.raises(HTTPException) as exc:
            await get_permission_catalog()
        assert exc.value.status_code == 503


class TestServiceClientGetUserPermissions:
    """Tests for service_client.get_user_permissions."""

    @pytest.mark.asyncio
    @patch(_CACHE_SET, new_callable=AsyncMock)
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_miss_makes_http_call(
        self, mock_get: AsyncMock, mock_cg: AsyncMock, mock_cs: AsyncMock
    ) -> None:
        from app.service_client import get_user_permissions

        payload = {"user_id": 5, "owner_id": 1, "permissions": {}}
        mock_get.return_value = _mock_response(200, payload)
        result = await get_user_permissions(1, 5)
        assert result == payload
        mock_get.assert_called_once()
        mock_cs.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        _CACHE_GET,
        new_callable=AsyncMock,
        return_value={"user_id": 5, "owner_id": 1, "permissions": {}},
    )
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_cache_hit_skips_http(
        self, mock_get: AsyncMock, mock_cg: AsyncMock
    ) -> None:
        from app.service_client import get_user_permissions

        result = await get_user_permissions(1, 5)
        assert result["user_id"] == 5
        mock_get.assert_not_called()

    @pytest.mark.asyncio
    @patch(_CACHE_GET, new_callable=AsyncMock, return_value=None)
    @patch(
        f"{_CLIENT}.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error_raises_503(
        self, mock_get: AsyncMock, mock_cg: AsyncMock
    ) -> None:
        from fastapi import HTTPException

        from app.service_client import get_user_permissions

        with pytest.raises(HTTPException) as exc:
            await get_user_permissions(1, 5)
        assert exc.value.status_code == 503


class TestServiceClientUpdateUserPermissions:
    """Tests for service_client.update_user_permissions."""

    @pytest.mark.asyncio
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.put", new_callable=AsyncMock)
    async def test_sends_put_and_invalidates_cache(
        self, mock_put: AsyncMock, mock_cd: AsyncMock
    ) -> None:
        from app.service_client import update_user_permissions

        payload = {"user_id": 5, "owner_id": 1, "permissions": {"jobs.create": True}}
        mock_put.return_value = _mock_response(200, payload)
        result = await update_user_permissions(1, 5, {"jobs.create": True})
        assert result == payload
        mock_put.assert_called_once()
        mock_cd.assert_called_once()

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.put",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error_raises_503(self, mock_put: AsyncMock) -> None:
        from fastapi import HTTPException

        from app.service_client import update_user_permissions

        with pytest.raises(HTTPException) as exc:
            await update_user_permissions(1, 5, {"jobs.create": True})
        assert exc.value.status_code == 503


class TestServiceClientSeedUserPermissions:
    """Tests for service_client.seed_user_permissions."""

    @pytest.mark.asyncio
    @patch(_CACHE_DEL, new_callable=AsyncMock)
    @patch(f"{_CLIENT}.post", new_callable=AsyncMock)
    async def test_sends_post_with_role(
        self, mock_post: AsyncMock, mock_cd: AsyncMock
    ) -> None:
        from app.service_client import seed_user_permissions

        payload = {"user_id": 5, "owner_id": 1, "permissions": {}}
        mock_post.return_value = _mock_response(200, payload)
        result = await seed_user_permissions(1, 5, "employee")
        assert result == payload
        mock_post.assert_called_once()
        # Verify role was passed as query param
        call_kwargs = mock_post.call_args
        assert "role" in str(call_kwargs)
        mock_cd.assert_called_once()


class TestServiceClientGetAuditLogs:
    """Tests for service_client.get_audit_logs."""

    @pytest.mark.asyncio
    @patch(f"{_CLIENT}.get", new_callable=AsyncMock)
    async def test_calls_db_access_with_filters(self, mock_get: AsyncMock) -> None:
        from app.service_client import get_audit_logs

        payload = {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 100,
            "pages": 0,
        }
        mock_get.return_value = _mock_response(200, payload)

        result = await get_audit_logs(
            organization_id=1,
            page=2,
            per_page=50,
            actor_id=7,
            action="job.create",
            resource_type="job",
        )

        assert result == payload
        assert mock_get.call_args.kwargs["params"] == {
            "page": 2,
            "per_page": 50,
            "organization_id": 1,
            "actor_id": 7,
            "action": "job.create",
            "resource_type": "job",
        }

    @pytest.mark.asyncio
    @patch(
        f"{_CLIENT}.get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("down"),
    )
    async def test_connect_error_raises_503(self, mock_get: AsyncMock) -> None:
        from fastapi import HTTPException

        from app.service_client import get_audit_logs

        with pytest.raises(HTTPException) as exc:
            await get_audit_logs(organization_id=1)
        assert exc.value.status_code == 503
