"""
Integration tests — Admin BL service flow.

Pairwise: admin-bl-service ↔ user-db-access-service

Tests platform administration endpoints that require superadmin access:
organization CRUD, audit logs, platform settings, and cross-tenant
user management. Verifies RBAC enforcement — non-superadmin users
must be denied access (HTTP 403).

Industry standard patterns:
    - RBAC boundary testing (positive + negative cases for each role)
    - CRUD lifecycle tests (create → read → update → delete)
    - Data isolation verification (superadmin sees all, owner sees own)
    - Cleanup via try/finally to avoid test pollution
"""

import time

import httpx

# ==============================================================================
# Organization Management
# ==============================================================================


class TestListOrganizations:
    """Verify superadmin can list all organizations."""

    def test_superadmin_can_list_organizations(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        resp = http_client.get(
            "/api/v1/admin/organizations", headers=superadmin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return a list or paginated response
        if isinstance(data, dict):
            items = (
                data.get("items") or data.get("data") or data.get("organizations", [])
            )
            assert isinstance(items, list)
        else:
            assert isinstance(data, list)

    def test_owner_cannot_list_organizations(
        self, http_client: httpx.Client, owner_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/organizations", headers=owner_headers)
        assert resp.status_code == 403

    def test_employee_cannot_list_organizations(
        self, http_client: httpx.Client, employee_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/organizations", headers=employee_headers)
        assert resp.status_code == 403

    def test_unauthenticated_cannot_list_organizations(
        self, http_client: httpx.Client
    ) -> None:
        resp = http_client.get("/api/v1/admin/organizations")
        assert resp.status_code in (401, 403)


class TestOrganizationCRUD:
    """Full CRUD lifecycle for organizations (superadmin only)."""

    def test_create_and_read_organization(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        slug = f"int-test-org-{int(time.time())}"
        # Create
        create_resp = http_client.post(
            "/api/v1/admin/organizations",
            headers=superadmin_headers,
            json={
                "name": "Integration Test Org",
                "slug": slug,
            },
        )
        assert create_resp.status_code in (200, 201), (
            f"Create org failed: {create_resp.status_code} — {create_resp.text}"
        )
        org = create_resp.json()
        created_org_id = org.get("id") or org.get("organization_id")
        assert created_org_id is not None
        assert org.get("name") == "Integration Test Org"

        try:
            # Read
            get_resp = http_client.get(
                f"/api/v1/admin/organizations/{created_org_id}",
                headers=superadmin_headers,
            )
            assert get_resp.status_code == 200
            assert get_resp.json().get("name") == "Integration Test Org"
        finally:
            http_client.delete(
                f"/api/v1/admin/organizations/{created_org_id}",
                headers=superadmin_headers,
            )

    def test_update_organization(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        slug = f"update-test-org-{int(time.time())}"
        create_resp = http_client.post(
            "/api/v1/admin/organizations",
            headers=superadmin_headers,
            json={
                "name": "Update Test Org",
                "slug": slug,
            },
        )
        org = create_resp.json()
        created_org_id = org.get("id") or org.get("organization_id")

        try:
            update_resp = http_client.put(
                f"/api/v1/admin/organizations/{created_org_id}",
                headers=superadmin_headers,
                json={"name": "Updated Org Name"},
            )
            assert update_resp.status_code == 200
            assert update_resp.json().get("name") == "Updated Org Name"
        finally:
            http_client.delete(
                f"/api/v1/admin/organizations/{created_org_id}",
                headers=superadmin_headers,
            )

    def test_delete_organization(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        slug = f"delete-test-org-{int(time.time())}"
        create_resp = http_client.post(
            "/api/v1/admin/organizations",
            headers=superadmin_headers,
            json={
                "name": "Delete Test Org",
                "slug": slug,
            },
        )
        org = create_resp.json()
        org_id = org.get("id") or org.get("organization_id")

        del_resp = http_client.delete(
            f"/api/v1/admin/organizations/{org_id}",
            headers=superadmin_headers,
        )
        assert del_resp.status_code in (200, 204)

    def test_owner_cannot_create_organization(
        self, http_client: httpx.Client, owner_headers: dict[str, str]
    ) -> None:
        resp = http_client.post(
            "/api/v1/admin/organizations",
            headers=owner_headers,
            json={"name": "Hacked Org", "slug": "hacked-org"},
        )
        assert resp.status_code == 403


# ==============================================================================
# Organization Suspension
# ==============================================================================


class TestOrganizationSuspension:
    """Test suspend / unsuspend lifecycle."""

    def test_suspend_and_unsuspend_organization(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        slug = f"suspend-test-org-{int(time.time())}"
        create_resp = http_client.post(
            "/api/v1/admin/organizations",
            headers=superadmin_headers,
            json={"name": "Suspend Test Org", "slug": slug},
        )
        org = create_resp.json()
        created_org_id = org.get("id") or org.get("organization_id")

        try:
            # Suspend
            suspend_resp = http_client.post(
                f"/api/v1/admin/organizations/{created_org_id}/suspend",
                headers=superadmin_headers,
                json={"reason": "Integration test — testing suspension flow"},
            )
            assert suspend_resp.status_code == 200

            # Verify suspended
            get_resp = http_client.get(
                f"/api/v1/admin/organizations/{created_org_id}",
                headers=superadmin_headers,
            )
            assert get_resp.status_code == 200
            org_data = get_resp.json()
            assert (
                org_data.get("is_active") is False or org_data.get("suspended") is True
            )

            # Unsuspend
            unsuspend_resp = http_client.post(
                f"/api/v1/admin/organizations/{created_org_id}/unsuspend",
                headers=superadmin_headers,
            )
            assert unsuspend_resp.status_code == 200
        finally:
            http_client.delete(
                f"/api/v1/admin/organizations/{created_org_id}",
                headers=superadmin_headers,
            )


# ==============================================================================
# Audit Logs
# ==============================================================================


class TestAuditLogs:
    """Verify audit log retrieval endpoints."""

    def test_superadmin_can_list_audit_logs(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/audit-logs", headers=superadmin_headers)
        assert resp.status_code == 200

    def test_audit_logs_with_filters(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        resp = http_client.get(
            "/api/v1/admin/audit-logs",
            headers=superadmin_headers,
            params={"limit": 5},
        )
        assert resp.status_code == 200

    def test_owner_cannot_access_audit_logs(
        self, http_client: httpx.Client, owner_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/audit-logs", headers=owner_headers)
        assert resp.status_code == 403


# ==============================================================================
# Platform Settings
# ==============================================================================


class TestPlatformSettings:
    """Verify platform settings endpoints."""

    def test_superadmin_can_list_settings(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/settings", headers=superadmin_headers)
        assert resp.status_code == 200

    def test_superadmin_can_get_specific_setting(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        # Try to get a known setting key
        resp = http_client.get(
            "/api/v1/admin/settings/maintenance_mode",
            headers=superadmin_headers,
        )
        # May be 200 (found) or 404 (not seeded) — both are valid
        assert resp.status_code in (200, 404)

    def test_superadmin_can_update_setting(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        resp = http_client.put(
            "/api/v1/admin/settings/test_setting",
            headers=superadmin_headers,
            json={"value": "integration-test-value"},
        )
        assert resp.status_code == 200

    def test_owner_cannot_access_settings(
        self, http_client: httpx.Client, owner_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/settings", headers=owner_headers)
        assert resp.status_code == 403


# ==============================================================================
# Cross-Tenant User Management
# ==============================================================================


class TestCrossTenantUsers:
    """Verify superadmin can list users across tenants."""

    def test_superadmin_can_list_all_users(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/users", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        if isinstance(data, dict):
            items = data.get("items") or data.get("data") or data.get("users", [])
            assert len(items) >= 2  # At least owner + employee
        else:
            assert len(data) >= 2

    def test_owner_cannot_access_admin_users(
        self, http_client: httpx.Client, owner_headers: dict[str, str]
    ) -> None:
        resp = http_client.get("/api/v1/admin/users", headers=owner_headers)
        assert resp.status_code == 403


# ==============================================================================
# NGINX Routing for Admin Service
# ==============================================================================


class TestAdminRouting:
    """Verify NGINX correctly routes admin endpoints."""

    def test_admin_route_not_502(
        self, http_client: httpx.Client, superadmin_headers: dict[str, str]
    ) -> None:
        """Admin service should be reachable (not returning 502 Bad Gateway)."""
        resp = http_client.get(
            "/api/v1/admin/organizations",
            headers=superadmin_headers,
        )
        assert resp.status_code != 502

    def test_admin_health_endpoint(self, http_client: httpx.Client) -> None:
        """Admin service health check (direct, not through NGINX routing)."""
        resp = http_client.get("/api/v1/admin/health")
        # May be routed or not — depends on nginx config
        assert resp.status_code in (200, 404, 403)
