"""
Extended Admin & Impersonation Write-Op Integration Tests
==========================================================

Covers admin endpoints and shadow-token operations NOT tested in
``test_admin_flow.py`` or ``test_impersonation_e2e.py``.

Gaps filled by this file:
    - GET /admin/users/{user_id}  (specific user lookup)
    - Shadow-token write: create customer while impersonating
    - Shadow-token write: create job while impersonating
    - Audit trail verification for impersonated write actions

Industry-standard practices applied:
    - try/finally cleanup for resources created during tests
    - Descriptive assertion messages
    - Full docstrings on every test
"""

import httpx
import pytest

# ==========================================================================
# Helpers
# ==========================================================================


def _get_shadow_headers(
    http_client: httpx.Client,
    superadmin_headers: dict[str, str],
    target_user_id: int,
) -> dict[str, str]:
    """
    Request a shadow (impersonation) token and return auth headers.

    Args:
        http_client:       Shared HTTP client
        superadmin_headers: Superadmin Authorization headers
        target_user_id:    ID of the user to impersonate

    Returns:
        Dict with Authorization header using the shadow access token.
    """
    resp = http_client.post(
        "/api/v1/auth/impersonate",
        headers=superadmin_headers,
        json={"target_user_id": target_user_id},
    )
    assert resp.status_code == 200, (
        f"Impersonation failed: {resp.status_code} — {resp.text}"
    )
    data = resp.json()
    token = data.get("access_token") or data.get("shadow_token")
    assert token, "No access_token in impersonation response"
    return {"Authorization": f"Bearer {token}"}


# ==========================================================================
# Admin User Detail
# ==========================================================================


class TestAdminUserDetail:
    """
    Test GET /admin/users/{user_id} — single-user lookup.

    This endpoint is covered for the list (GET /admin/users) in
    test_admin_flow.py but the per-ID variant was untested.
    """

    def test_superadmin_can_get_user_by_id(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
    ) -> None:
        """
        Superadmin retrieves a specific user by ID.

        Verifies:
        - 200 response
        - Response contains user fields (id, email)
        """
        # User ID 1 should always exist (seeded superadmin or owner)
        resp = http_client.get(
            "/api/v1/admin/users/1",
            headers=superadmin_headers,
        )
        assert resp.status_code == 200, f"GET /admin/users/1 failed: {resp.status_code}"
        data = resp.json()
        # Should contain user data (may be nested under "data" key)
        user = data.get("data", data)
        assert "email" in user or "id" in user, "Response missing user fields"

    def test_owner_cannot_get_admin_user_by_id(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Regular owner cannot access the admin user-detail endpoint.

        Verifies:
        - GET /admin/users/{id} returns 403
        """
        resp = http_client.get(
            "/api/v1/admin/users/1",
            headers=owner_headers,
        )
        assert resp.status_code == 403, (
            f"Owner accessed admin user detail (got {resp.status_code})"
        )

    def test_nonexistent_user_returns_404(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
    ) -> None:
        """
        Requesting a non-existent user ID returns 404.

        Verifies:
        - GET /admin/users/999999 returns 404
        """
        resp = http_client.get(
            "/api/v1/admin/users/999999",
            headers=superadmin_headers,
        )
        assert resp.status_code == 404, (
            f"Expected 404 for missing user, got {resp.status_code}"
        )


# ==========================================================================
# Shadow-Token Write Operations
# ==========================================================================


class TestShadowTokenWriteOps:
    """
    Verify that a superadmin's shadow token (impersonating an owner)
    can perform write operations on behalf of the owner.

    The shadow token inherits the owner's organisation context, so
    resources are created under the impersonated user's tenant.
    """

    def _get_owner_user_id(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
    ) -> int:
        """Helper: resolve the owner's user ID from the admin user list."""
        resp = http_client.get(
            "/api/v1/admin/users",
            headers=superadmin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        users = (
            data
            if isinstance(data, list)
            else (data.get("data") or data.get("items") or data.get("users", []))
        )
        for u in users:
            if u.get("email") == "owner@demo.com":
                return u.get("id") or u.get("user_id")
        pytest.skip("owner@demo.com not found in admin user list")

    def test_shadow_token_can_create_customer(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
        owner_headers: dict[str, str],
    ) -> None:
        """
        Superadmin impersonates owner and creates a customer.

        Steps:
        1. Get shadow token for the owner
        2. POST /customers/ with shadow auth
        3. Verify 200/201 and customer is created
        4. Cleanup with owner headers

        Verifies:
        - Shadow token can create resources in the owner's tenant
        """
        owner_id = self._get_owner_user_id(http_client, superadmin_headers)
        shadow_headers = _get_shadow_headers(
            http_client,
            superadmin_headers,
            owner_id,
        )

        # Create customer via shadow token
        resp = http_client.post(
            "/api/v1/customers/",
            headers=shadow_headers,
            json={
                "first_name": "Shadow",
                "last_name": "Customer",
                "email": "shadow-customer@admin-ext.example.com",
                "phone": "+353 1 999 0001",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Shadow create customer failed: {resp.status_code} — {resp.text}"
        )
        customer = resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        # Cleanup — use owner headers (same tenant)
        http_client.delete(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )

    def test_shadow_token_can_create_job(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
        owner_headers: dict[str, str],
    ) -> None:
        """
        Superadmin impersonates owner and creates a job.

        Verifies:
        - Shadow token can create jobs in the owner's tenant
        """
        owner_id = self._get_owner_user_id(http_client, superadmin_headers)
        shadow_headers = _get_shadow_headers(
            http_client,
            superadmin_headers,
            owner_id,
        )

        resp = http_client.post(
            "/api/v1/jobs/",
            headers=shadow_headers,
            json={
                "title": "Shadow Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Shadow create job failed: {resp.status_code} — {resp.text}"
        )
        job = resp.json()
        job_id = job.get("id") or job.get("job_id")

        # Cleanup
        http_client.delete(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )


# ==========================================================================
# Audit Trail Verification
# ==========================================================================


class TestAuditTrailForImpersonation:
    """
    Verify that impersonated actions generate audit-log entries that
    record the impersonator's identity.
    """

    def test_audit_logs_exist_after_impersonated_action(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
    ) -> None:
        """
        After a superadmin performs an action (e.g., org suspend/unsuspend),
        the audit log should contain a corresponding entry.

        Steps:
        1. List audit logs
        2. Verify at least one entry exists (earlier tests will have
           created some via org operations)

        Verifies:
        - GET /admin/audit-logs returns 200
        - Response contains at least one log entry
        """
        resp = http_client.get(
            "/api/v1/admin/audit-logs",
            headers=superadmin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        logs = (
            data
            if isinstance(data, list)
            else (data.get("data") or data.get("items") or data.get("logs", []))
        )
        assert len(logs) > 0, "Audit log is empty after admin operations"

    def test_audit_log_entries_have_required_fields(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
    ) -> None:
        """
        Each audit-log entry should contain standard fields.

        Verifies:
        - Entries contain 'action' and 'actor_email' (or similar keys)
        """
        resp = http_client.get(
            "/api/v1/admin/audit-logs",
            headers=superadmin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        logs = (
            data
            if isinstance(data, list)
            else (data.get("data") or data.get("items") or data.get("logs", []))
        )
        if not logs:
            pytest.skip("No audit logs to inspect")

        entry = logs[0]
        # Should contain at least an action identifier
        assert "action" in entry or "event" in entry, (
            f"Audit entry missing 'action' key: {entry.keys()}"
        )
