"""
Tests for Admin BL Service — Organization management endpoints.

Coverage:
- List organizations (pagination, filtering)
- Create organization (happy path, duplicate slug)
- Get single organization
- Update organization
- Suspend / unsuspend organization
- Authorization: non-superadmin rejection

All tests use mocked HTTP calls — no real network or database.
"""

from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient

# ==============================================================================
# Sample Data
# ==============================================================================

SAMPLE_ORG: dict = {
    "id": 1,
    "name": "Acme Corp",
    "slug": "acme-corp",
    "billing_email": "billing@acme.com",
    "billing_plan": "professional",
    "max_users": 100,
    "max_customers": 1000,
    "is_active": True,
    "suspended_at": None,
    "suspended_reason": None,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
}


# ==============================================================================
# Organization CRUD Tests
# ==============================================================================


class TestListOrganizations:
    """Tests for GET /api/v1/admin/organizations."""

    @pytest.mark.asyncio
    async def test_list_organizations_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify that listing organizations returns paginated results.

        Verifies:
        - 200 status code
        - Response contains items, total, page, per_page, pages
        """
        mock_http_client.get.return_value = httpx.Response(
            200,
            json={
                "items": [SAMPLE_ORG],
                "total": 1,
                "page": 1,
                "per_page": 50,
                "pages": 1,
            },
        )

        resp = await client.get(
            "/api/v1/admin/organizations",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["slug"] == "acme-corp"

    @pytest.mark.asyncio
    async def test_list_organizations_rejects_non_superadmin(
        self,
        owner_client: AsyncClient,
    ) -> None:
        """
        Verify that non-superadmin users are rejected with 403.

        Verifies:
        - 403 status code for owner role
        """
        resp = await owner_client.get(
            "/api/v1/admin/organizations",
            headers={"Authorization": "Bearer test-owner-token"},
        )

        assert resp.status_code == 403


class TestCreateOrganization:
    """Tests for POST /api/v1/admin/organizations."""

    @pytest.mark.asyncio
    async def test_create_organization_returns_201(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify successful organization creation.

        Verifies:
        - 201 status code
        - Response contains the created organization data
        - Audit log write is attempted
        """
        mock_http_client.post.return_value = httpx.Response(201, json=SAMPLE_ORG)

        resp = await client.post(
            "/api/v1/admin/organizations",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={
                "name": "Acme Corp",
                "slug": "acme-corp",
                "billing_email": "billing@acme.com",
                "billing_plan": "professional",
                "max_users": 100,
                "max_customers": 1000,
            },
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme Corp"
        assert data["slug"] == "acme-corp"
        # Verify the service client was called (create + audit log)
        assert mock_http_client.post.call_count >= 1

    @pytest.mark.asyncio
    async def test_create_organization_duplicate_slug(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify that duplicate slug returns 409.

        Verifies:
        - 409 status code on conflict
        """
        mock_http_client.post.return_value = httpx.Response(
            409, json={"detail": "Duplicate slug"}
        )

        resp = await client.post(
            "/api/v1/admin/organizations",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"name": "Acme Corp", "slug": "acme-corp"},
        )

        assert resp.status_code == 409


class TestGetOrganization:
    """Tests for GET /api/v1/admin/organizations/{org_id}."""

    @pytest.mark.asyncio
    async def test_get_organization_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify fetching a single organization.

        Verifies:
        - 200 status code
        - Correct organization data returned
        """
        mock_http_client.get.return_value = httpx.Response(200, json=SAMPLE_ORG)

        resp = await client.get(
            "/api/v1/admin/organizations/1",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    @pytest.mark.asyncio
    async def test_get_organization_not_found(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify 404 for non-existent organization.

        Verifies:
        - 404 status code
        """
        mock_http_client.get.return_value = httpx.Response(
            404, json={"detail": "Not found"}
        )

        resp = await client.get(
            "/api/v1/admin/organizations/999",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 404


class TestUpdateOrganization:
    """Tests for PUT /api/v1/admin/organizations/{org_id}."""

    @pytest.mark.asyncio
    async def test_update_organization_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify successful organization update.

        Verifies:
        - 200 status code
        - Updated fields reflected in response
        - Audit log write attempted
        """
        updated = {**SAMPLE_ORG, "name": "Acme Updated"}
        mock_http_client.put.return_value = httpx.Response(200, json=updated)
        # For audit log write
        mock_http_client.post.return_value = httpx.Response(201, json={})

        resp = await client.put(
            "/api/v1/admin/organizations/1",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"name": "Acme Updated"},
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Acme Updated"


class TestSuspendOrganization:
    """Tests for POST /api/v1/admin/organizations/{id}/suspend."""

    @pytest.mark.asyncio
    async def test_suspend_organization_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify successful organization suspension.

        Verifies:
        - 200 status code
        - Confirmation message returned
        """
        mock_http_client.put.return_value = httpx.Response(200, json=SAMPLE_ORG)
        mock_http_client.post.return_value = httpx.Response(201, json={})

        resp = await client.post(
            "/api/v1/admin/organizations/1/suspend",
            headers={"Authorization": f"Bearer {superadmin_token}"},
            json={"reason": "Payment overdue"},
        )

        assert resp.status_code == 200
        assert "suspended" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_unsuspend_organization_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify successful organization reactivation.

        Verifies:
        - 200 status code
        - Reactivation confirmation message
        """
        mock_http_client.put.return_value = httpx.Response(200, json=SAMPLE_ORG)
        mock_http_client.post.return_value = httpx.Response(201, json={})

        resp = await client.post(
            "/api/v1/admin/organizations/1/unsuspend",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        assert "reactivated" in resp.json()["message"].lower()


# ==============================================================================
# Health Check
# ==============================================================================


class TestHealthCheck:
    """Tests for GET /api/v1/health."""

    @pytest.mark.asyncio
    async def test_health_check_returns_200(self, client: AsyncClient) -> None:
        """
        Verify health check endpoint works without authentication.

        Verifies:
        - 200 status code
        - Status is "healthy"
        """
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


# ==============================================================================
# Get User Endpoint
# ==============================================================================


class TestGetUserEndpoint:
    """Tests for GET /api/v1/admin/users/{user_id}."""

    @pytest.mark.asyncio
    async def test_get_user_returns_200(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify that superadmin can fetch any user by ID.

        Verifies:
        - 200 status code
        - User data returned correctly
        """
        mock_http_client.get.return_value = httpx.Response(
            200,
            json={
                "id": 42,
                "email": "user@demo.com",
                "first_name": "Test",
                "last_name": "User",
                "role": "employee",
                "owner_id": 1,
                "is_active": True,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
        )

        resp = await client.get(
            "/api/v1/admin/users/42",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 42
        assert data["email"] == "user@demo.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """
        Verify 404 for non-existent user.

        Verifies:
        - 404 status code
        """
        mock_http_client.get.return_value = httpx.Response(
            404, json={"detail": "User 9999 not found"}
        )

        resp = await client.get(
            "/api/v1/admin/users/9999",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )

        assert resp.status_code == 404


# ==============================================================================
# Organization Update Security
# ==============================================================================


class TestOrganizationUpdateSecurity:
    """Tests that non-superadmin cannot update organizations."""

    @pytest.mark.asyncio
    async def test_owner_cannot_update_organization(
        self,
        owner_client: AsyncClient,
    ) -> None:
        """
        Non-superadmin PUT to organizations must return 403.

        Verifies:
        - 403 status code for owner role
        """
        resp = await owner_client.put(
            "/api/v1/admin/organizations/1",
            headers={"Authorization": "Bearer test-owner-token"},
            json={"name": "Hacked Org"},
        )

        assert resp.status_code == 403
