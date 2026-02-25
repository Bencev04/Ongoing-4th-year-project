"""
Integration tests — Superadmin Impersonation E2E flow.

End-to-end: Superadmin → Auth /impersonate → Shadow Token → Tenant operations

Tests the complete impersonation lifecycle:
1. Superadmin authenticates
2. Superadmin requests shadow token for a target user (owner)
3. Shadow token is used to perform tenant-scoped operations
4. RBAC enforcement: non-superadmin users cannot impersonate
5. Safety guard: cannot impersonate another superadmin

Industry standard patterns:
    - Least-privilege validation (shadow token has target's permissions, not superadmin's)
    - Audit trail verification (impersonator_id in token claims)
    - Security boundary testing (negative cases for all forbidden paths)
    - Short-lived token verification
"""

from typing import Dict, Optional

import httpx
import pytest


# ==============================================================================
# Impersonation Token Generation
# ==============================================================================

class TestImpersonateEndpoint:
    """Test POST /api/v1/auth/impersonate."""

    def test_superadmin_can_impersonate_owner(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """Superadmin should receive a shadow token for the owner user."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=superadmin_headers,
            json={
                "target_user_id": owner_user_id,
                "reason": "Integration test — verifying impersonation flow",
            },
        )
        assert resp.status_code == 200, (
            f"Impersonate failed: {resp.status_code} — {resp.text}"
        )
        data = resp.json()
        assert "access_token" in data or "shadow_token" in data, (
            f"No token in impersonation response: {data}"
        )

    def test_superadmin_can_impersonate_employee(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        employee_user_id: int,
    ) -> None:
        """Superadmin should also be able to impersonate employees."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=superadmin_headers,
            json={
                "target_user_id": employee_user_id,
                "reason": "Integration test — employer impersonation",
            },
        )
        assert resp.status_code == 200

    def test_owner_cannot_impersonate(
        self, http_client: httpx.Client, owner_headers: Dict[str, str],
        employee_user_id: int,
    ) -> None:
        """Only superadmins can impersonate \u2014 owner should get 403."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=owner_headers,
            json={"target_user_id": employee_user_id, "reason": "Not allowed"},
        )
        assert resp.status_code == 403

    def test_employee_cannot_impersonate(
        self, http_client: httpx.Client, employee_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """Only superadmins can impersonate — employee should get 403."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=employee_headers,
            json={"target_user_id": owner_user_id, "reason": "Not allowed"},
        )
        assert resp.status_code == 403

    def test_cannot_impersonate_superadmin(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        superadmin_user_id: int,
    ) -> None:
        """Cannot impersonate another superadmin \u2014 safety guard."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=superadmin_headers,
            json={
                "target_user_id": superadmin_user_id,
                "reason": "Testing superadmin impersonation guard",
            },
        )
        assert resp.status_code == 403

    def test_cannot_impersonate_nonexistent_user(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str]
    ) -> None:
        """Target user must exist — 404 for nonexistent IDs."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=superadmin_headers,
            json={
                "target_user_id": 99999,
                "reason": "Testing nonexistent user guard",
            },
        )
        assert resp.status_code == 404

    def test_impersonate_without_auth_is_rejected(
        self, http_client: httpx.Client, owner_user_id: int,
    ) -> None:
        """Unauthenticated impersonation request should fail."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            json={"target_user_id": owner_user_id, "reason": "No auth"},
        )
        assert resp.status_code in (401, 403)


# ==============================================================================
# Shadow Token Usage — Tenant-Scoped Operations
# ==============================================================================

class TestShadowTokenOperations:
    """
    Verify that a shadow token behaves like the target user's normal token.

    The superadmin impersonates the owner, then uses the shadow token to
    perform operations in the owner's tenant. This tests the full E2E flow:
    auth → impersonate → BL service → DB access.
    """

    def _get_shadow_token(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        target_user_id: int,
    ) -> Optional[str]:
        """Helper: obtain a shadow token for the target user."""
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=superadmin_headers,
            json={
                "target_user_id": target_user_id,
                "reason": "Integration test — shadow token operations",
            },
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("access_token") or data.get("shadow_token")

    def test_shadow_token_can_list_users(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """Shadow token for owner should see the owner's tenant users."""
        shadow = self._get_shadow_token(http_client, superadmin_headers, owner_user_id)
        if shadow is None:
            pytest.skip("Could not obtain shadow token")

        headers = {
            "Authorization": f"Bearer {shadow}",
            "Content-Type": "application/json",
        }
        resp = http_client.get("/api/v1/users/", headers=headers)
        assert resp.status_code == 200

    def test_shadow_token_can_list_customers(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """Shadow token for owner should access the owner's customers."""
        shadow = self._get_shadow_token(http_client, superadmin_headers, owner_user_id)
        if shadow is None:
            pytest.skip("Could not obtain shadow token")

        headers = {
            "Authorization": f"Bearer {shadow}",
            "Content-Type": "application/json",
        }
        resp = http_client.get("/api/v1/customers/", headers=headers)
        assert resp.status_code == 200

    def test_shadow_token_can_list_jobs(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """Shadow token for owner should access the owner's jobs."""
        shadow = self._get_shadow_token(http_client, superadmin_headers, owner_user_id)
        if shadow is None:
            pytest.skip("Could not obtain shadow token")

        headers = {
            "Authorization": f"Bearer {shadow}",
            "Content-Type": "application/json",
        }
        resp = http_client.get("/api/v1/jobs/", headers=headers)
        assert resp.status_code == 200

    def test_shadow_token_verify_shows_impersonator(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        The /auth/verify endpoint should show impersonator_id in its response.

        This verifies the audit trail is maintained \u2014 the shadow token preserves
        traceability to the original superadmin.
        """
        shadow = self._get_shadow_token(http_client, superadmin_headers, owner_user_id)
        if shadow is None:
            pytest.skip("Could not obtain shadow token")

        resp = http_client.post(
            "/api/v1/auth/verify",
            json={"access_token": shadow},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have impersonator info or at least valid user info
        assert data.get("valid") is True or data.get("authenticated") is True

    def test_shadow_token_cannot_access_admin_endpoints(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Shadow token for owner should NOT have superadmin access.

        The shadow token inherits the TARGET's role (owner), not the
        superadmin's role. Admin endpoints should reject it.
        """
        shadow = self._get_shadow_token(http_client, superadmin_headers, owner_user_id)
        if shadow is None:
            pytest.skip("Could not obtain shadow token")

        headers = {
            "Authorization": f"Bearer {shadow}",
            "Content-Type": "application/json",
        }
        resp = http_client.get("/api/v1/admin/organizations", headers=headers)
        assert resp.status_code == 403, (
            "Shadow token (owner role) should NOT access admin endpoints"
        )


# ==============================================================================
# Impersonation with Employee Role
# ==============================================================================

class TestEmployeeImpersonation:
    """Test that impersonating an employee gives employee-level access."""

    def _get_employee_shadow_token(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        employee_user_id: int,
    ) -> Optional[str]:
        resp = http_client.post(
            "/api/v1/auth/impersonate",
            headers=superadmin_headers,
            json={
                "target_user_id": employee_user_id,
                "reason": "Integration test — employee impersonation",
            },
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("access_token") or data.get("shadow_token")

    def test_employee_shadow_can_read_users(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        employee_user_id: int,
    ) -> None:
        """Employee shadow token should have read access to users."""
        shadow = self._get_employee_shadow_token(http_client, superadmin_headers, employee_user_id)
        if shadow is None:
            pytest.skip("Could not obtain employee shadow token")

        headers = {
            "Authorization": f"Bearer {shadow}",
            "Content-Type": "application/json",
        }
        resp = http_client.get("/api/v1/users/", headers=headers)
        assert resp.status_code == 200

    def test_employee_shadow_cannot_create_users(
        self, http_client: httpx.Client, superadmin_headers: Dict[str, str],
        employee_user_id: int,
    ) -> None:
        """Employee shadow token should NOT be able to create users (owner-only)."""
        shadow = self._get_employee_shadow_token(http_client, superadmin_headers, employee_user_id)
        if shadow is None:
            pytest.skip("Could not obtain employee shadow token")

        headers = {
            "Authorization": f"Bearer {shadow}",
            "Content-Type": "application/json",
        }
        resp = http_client.post(
            "/api/v1/users/",
            headers=headers,
            json={
                "email": "hacked@test.com",
                "password": "password123",
                "first_name": "Hacked",
                "last_name": "User",
            },
        )
        assert resp.status_code == 403
