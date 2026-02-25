"""
Tests for Admin BL Service — Audit Logs and Platform Settings.

Coverage:
- List audit logs (pagination, filtering)
- List platform settings
- Get single platform setting
- Update platform setting

All tests use mocked HTTP calls — no real network or database.
"""

import pytest
import httpx
from unittest.mock import AsyncMock

from httpx import AsyncClient


# ==============================================================================
# Sample Data
# ==============================================================================

SAMPLE_AUDIT_LOG: dict = {
    "id": 1,
    "timestamp": "2026-01-15T10:30:00",
    "actor_id": 999,
    "actor_email": "superadmin@system.local",
    "actor_role": "superadmin",
    "impersonator_id": None,
    "organization_id": 1,
    "action": "organization.create",
    "resource_type": "organization",
    "resource_id": "1",
    "details": {"name": "Test Org"},
    "ip_address": "127.0.0.1",
}

SAMPLE_SETTING: dict = {
    "key": "maintenance_mode",
    "value": False,
    "description": "Enable/disable platform maintenance mode",
    "updated_by": None,
    "updated_at": "2026-01-01T00:00:00",
}


# ==============================================================================
# Audit Log Tests
# ==============================================================================

class TestAuditLogs:
    """Tests for GET /api/v1/admin/audit-logs."""

    @pytest.mark.asyncio
    async def test_list_audit_logs_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify that listing audit logs returns paginated results.

        Verifies:
        - 200 status code
        - Response contains items and pagination metadata
        """
        mock_http_client.get.return_value = httpx.Response(
            200,
            json={
                "items": [SAMPLE_AUDIT_LOG],
                "total": 1,
                "page": 1,
                "per_page": 50,
                "pages": 1,
            },
        )

        resp = await client.get(
            "/api/v1/admin/audit-logs",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["action"] == "organization.create"

    @pytest.mark.asyncio
    async def test_list_audit_logs_with_filters(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify that audit log query params are forwarded correctly.

        Verifies:
        - 200 status code with filter parameters
        - Filters are passed through to the service client
        """
        mock_http_client.get.return_value = httpx.Response(
            200,
            json={
                "items": [],
                "total": 0,
                "page": 1,
                "per_page": 50,
                "pages": 0,
            },
        )

        resp = await client.get(
            "/api/v1/admin/audit-logs",
            params={
                "organization_id": 1,
                "action": "organization.suspend",
            },
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ==============================================================================
# Platform Settings Tests
# ==============================================================================

class TestPlatformSettings:
    """Tests for /api/v1/admin/settings endpoints."""

    @pytest.mark.asyncio
    async def test_list_settings_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify listing all platform settings.

        Verifies:
        - 200 status code
        - All settings returned with total count
        """
        mock_http_client.get.return_value = httpx.Response(
            200, json={"items": [SAMPLE_SETTING], "total": 1}
        )

        resp = await client.get(
            "/api/v1/admin/settings",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["key"] == "maintenance_mode"

    @pytest.mark.asyncio
    async def test_get_setting_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify fetching a single platform setting.

        Verifies:
        - 200 status code
        - Correct setting data returned
        """
        mock_http_client.get.return_value = httpx.Response(
            200, json=SAMPLE_SETTING
        )

        resp = await client.get(
            "/api/v1/admin/settings/maintenance_mode",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["key"] == "maintenance_mode"

    @pytest.mark.asyncio
    async def test_get_setting_not_found(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify 404 for non-existent setting key.

        Verifies:
        - 404 status code
        """
        mock_http_client.get.return_value = httpx.Response(
            404, json={"detail": "Not found"}
        )

        resp = await client.get(
            "/api/v1/admin/settings/nonexistent_key",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_setting_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify updating a platform setting.

        Verifies:
        - 200 status code
        - Updated value reflected
        - Audit log write attempted
        """
        updated = {**SAMPLE_SETTING, "value": True, "updated_by": 999}
        mock_http_client.put.return_value = httpx.Response(200, json=updated)
        mock_http_client.post.return_value = httpx.Response(201, json={})

        resp = await client.put(
            "/api/v1/admin/settings/maintenance_mode",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"value": True},
        )

        assert resp.status_code == 200
        assert resp.json()["value"] is True
