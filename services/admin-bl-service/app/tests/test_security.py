"""
Security tests for Admin BL Service.

Covers:
- Superadmin-only access enforcement
- Role escalation prevention
- Cross-tenant user access
- Request validation on organization operations

All endpoints require the ``superadmin`` role — these tests verify
that non-superadmin tokens are properly rejected.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import AsyncClient


# ==========================================================================
# Role Enforcement — Non-Superadmin Rejection
# ==========================================================================


class TestRoleEnforcement:
    """All admin endpoints must reject non-superadmin tokens."""

    @pytest.mark.asyncio
    async def test_owner_cannot_list_organizations(
        self, owner_client: AsyncClient,
    ) -> None:
        """Owner role must not access the organizations listing."""
        resp = await owner_client.get(
            "/api/v1/admin/organizations",
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_cannot_create_organization(
        self, owner_client: AsyncClient,
    ) -> None:
        """Owner role must not create organizations."""
        resp = await owner_client.post(
            "/api/v1/admin/organizations",
            json={"name": "Evil Corp", "slug": "evil-corp"},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_cannot_suspend_organization(
        self, owner_client: AsyncClient,
    ) -> None:
        """Owner role must not be able to suspend organizations."""
        resp = await owner_client.post(
            "/api/v1/admin/organizations/1/suspend",
            json={"reason": "testing"},
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_cannot_access_audit_logs(
        self, owner_client: AsyncClient,
    ) -> None:
        """Owner role must not access audit logs."""
        resp = await owner_client.get(
            "/api/v1/admin/audit-logs",
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_cannot_access_settings(
        self, owner_client: AsyncClient,
    ) -> None:
        """Owner role must not access platform settings."""
        resp = await owner_client.get(
            "/api/v1/admin/settings",
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_cannot_list_users_cross_tenant(
        self, owner_client: AsyncClient,
    ) -> None:
        """Owner role must not access cross-tenant user listing."""
        resp = await owner_client.get(
            "/api/v1/admin/users",
            headers={"Authorization": "Bearer test-owner-token"},
        )
        assert resp.status_code == 403


# ==========================================================================
# Superadmin Access — Positive Tests
# ==========================================================================


class TestSuperadminAccess:
    """Verify superadmin can access all endpoints (when backend responds)."""

    @pytest.mark.asyncio
    async def test_superadmin_can_list_organizations(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """Superadmin should successfully list organizations."""
        mock_http_client.get.return_value = httpx.Response(
            200,
            json={
                "items": [{
                    "id": 1, "name": "Acme", "slug": "acme",
                    "is_active": True, "billing_email": None,
                    "billing_plan": "free", "max_users": 50,
                    "max_customers": 500, "suspended_at": None,
                    "suspended_reason": None,
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                }],
                "total": 1, "page": 1, "per_page": 50, "pages": 1,
            },
        )
        resp = await client.get(
            "/api/v1/admin/organizations",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_superadmin_can_create_organization(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """Superadmin should be able to create a new organization."""
        created_org = {
            "id": 2,
            "name": "NewCo",
            "slug": "newco",
            "is_active": True,
            "billing_plan": "free",
            "billing_email": None,
            "max_users": 50,
            "max_customers": 500,
            "suspended_at": None,
            "suspended_reason": None,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        mock_http_client.post.return_value = httpx.Response(201, json=created_org)
        resp = await client.post(
            "/api/v1/admin/organizations",
            json={"name": "NewCo", "slug": "newco"},
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_superadmin_can_list_users(
        self,
        client: AsyncClient,
        superadmin_token: str,
        mock_http_client: AsyncMock,
    ) -> None:
        """Superadmin should be able to list users across tenants."""
        mock_http_client.get.return_value = httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": 1, "email": "owner@demo.com", "role": "owner",
                        "first_name": "Owner", "last_name": "User",
                        "is_active": True,
                        "created_at": "2026-01-01T00:00:00",
                        "updated_at": "2026-01-01T00:00:00",
                    },
                ],
                "total": 1, "page": 1, "per_page": 50, "pages": 1,
            },
        )
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert resp.status_code == 200


# ==========================================================================
# Input Validation
# ==========================================================================


class TestInputValidation:
    """Verify request body validation on admin endpoints."""

    @pytest.mark.asyncio
    async def test_create_org_requires_name(
        self,
        client: AsyncClient,
        superadmin_token: str,
    ) -> None:
        """Organization creation without ``name`` should fail validation."""
        resp = await client.post(
            "/api/v1/admin/organizations",
            json={"slug": "no-name-org"},
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_org_requires_slug(
        self,
        client: AsyncClient,
        superadmin_token: str,
    ) -> None:
        """Organization creation without ``slug`` should fail validation."""
        resp = await client.post(
            "/api/v1/admin/organizations",
            json={"name": "No Slug Org"},
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_suspend_requires_reason(
        self,
        client: AsyncClient,
        superadmin_token: str,
    ) -> None:
        """Suspend endpoint without ``reason`` should fail validation."""
        resp = await client.post(
            "/api/v1/admin/organizations/1/suspend",
            json={},
            headers={"Authorization": f"Bearer {superadmin_token}"},
        )
        assert resp.status_code == 422
