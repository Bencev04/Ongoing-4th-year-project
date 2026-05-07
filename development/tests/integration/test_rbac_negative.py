"""
Role-Based Access Control (RBAC) Negative Integration Tests
============================================================

Systematically tests that lower-privilege roles are denied access to
operations reserved for higher-privilege roles.

Role hierarchy (from ``common/auth.py``)::

    superadmin = 100
    owner      = 80
    admin      = 60
    manager    = 40
    employee   = 20
    viewer     = 10

Each test class focuses on a specific role and asserts that it CANNOT
perform operations above its level.

Industry-standard practices applied:
    - Explicit HTTP status assertions with descriptive messages
    - Tests structured as "role X cannot do Y" for RBAC clarity
    - No cleanup needed — operations are expected to fail (no side-effects)
"""

import httpx

# ==========================================================================
# Viewer Restrictions (role=10 — lowest privilege)
# ==========================================================================


class TestViewerRestrictions:
    """
    Viewers have read-only access to their tenant's data.
    They must not be able to create, update, or delete any resource.
    """

    def test_viewer_cannot_create_customer(
        self,
        http_client: httpx.Client,
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Viewer cannot create a new customer.

        Verifies:
        - POST /customers/ returns 403
        """
        resp = http_client.post(
            "/api/v1/customers/",
            headers=viewer_headers,
            json={
                "first_name": "Should",
                "last_name": "Fail",
                "email": "viewer-create@rbac.example.com",
                "phone": "+353 0 000 0000",
            },
        )
        assert resp.status_code == 403, (
            f"Viewer created a customer (got {resp.status_code})"
        )

    def test_viewer_cannot_create_job(
        self,
        http_client: httpx.Client,
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Viewer cannot create a new job.

        Verifies:
        - POST /jobs/ returns 403
        """
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=viewer_headers,
            json={
                "title": "Viewer Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        assert resp.status_code == 403, f"Viewer created a job (got {resp.status_code})"

    def test_viewer_cannot_delete_customer(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Viewer cannot delete an existing customer.

        Steps:
        1. Owner creates a customer (setup)
        2. Viewer attempts DELETE
        3. Assert 403

        Verifies:
        - DELETE /customers/{id} returns 403 for viewer
        """
        # Setup: create with owner
        create_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Viewer",
                "last_name": "Delete",
                "email": "viewer-delete@rbac.example.com",
                "phone": "+353 0 000 0001",
            },
        )
        customer = create_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        try:
            # Viewer tries to delete
            resp = http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=viewer_headers,
            )
            assert resp.status_code == 403, (
                f"Viewer deleted a customer (got {resp.status_code})"
            )
        finally:
            # Owner cleans up
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )

    def test_viewer_cannot_create_user(
        self,
        http_client: httpx.Client,
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Viewer cannot create a new user.

        Verifies:
        - POST /users/ returns 403
        """
        resp = http_client.post(
            "/api/v1/users/",
            headers=viewer_headers,
            json={
                "email": "viewer-newuser@rbac.example.com",
                "password": "password123",
                "first_name": "Should",
                "last_name": "Fail",
                "role": "employee",
            },
        )
        assert resp.status_code == 403, (
            f"Viewer created a user (got {resp.status_code})"
        )

    def test_viewer_can_read_customers(
        self,
        http_client: httpx.Client,
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Viewer CAN read the customer list (read-only access).

        Verifies:
        - GET /customers/ returns 200
        """
        resp = http_client.get(
            "/api/v1/customers/",
            headers=viewer_headers,
        )
        assert resp.status_code == 200, (
            f"Viewer cannot even read customers (got {resp.status_code})"
        )

    def test_viewer_can_read_jobs(
        self,
        http_client: httpx.Client,
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Viewer CAN read the job list (read-only access).

        Verifies:
        - GET /jobs/ returns 200
        """
        resp = http_client.get(
            "/api/v1/jobs/",
            headers=viewer_headers,
        )
        assert resp.status_code == 200, (
            f"Viewer cannot even read jobs (got {resp.status_code})"
        )


# ==========================================================================
# Employee Restrictions (role=20)
# ==========================================================================


class TestEmployeeRestrictions:
    """
    Employees can create some resources but cannot manage users or
    perform admin-level operations.
    """

    def test_employee_cannot_deactivate_users(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Employee cannot deactivate a user (owner/admin only).

        Verifies:
        - DELETE /users/{id} returns 403
        """
        resp = http_client.delete(
            f"/api/v1/users/{owner_user_id}",
            headers=employee_headers,
        )
        assert resp.status_code == 403, (
            f"Employee deactivated a user (got {resp.status_code})"
        )

    def test_employee_cannot_invite_users(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Employee cannot invite new users (owner/admin only).

        Verifies:
        - POST /users/invite returns 403
        """
        resp = http_client.post(
            "/api/v1/users/invite",
            headers=employee_headers,
            json={
                "email": "employee-invite@rbac.example.com",
                "first_name": "Should",
                "last_name": "Fail",
                "role": "employee",
            },
        )
        assert resp.status_code == 403, (
            f"Employee invited a user (got {resp.status_code})"
        )

    def test_employee_cannot_update_company_profile(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Employee cannot update the company profile (owner only).

        Verifies:
        - PUT /company returns 403
        """
        resp = http_client.put(
            "/api/v1/company/",
            headers=employee_headers,
            json={"phone": "+353 0 000 0000"},
        )
        assert resp.status_code == 403, (
            f"Employee updated company profile (got {resp.status_code})"
        )

    def test_employee_cannot_access_admin_panel(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Employee cannot access the superadmin user listing.

        Verifies:
        - GET /admin/users returns 403
        """
        resp = http_client.get(
            "/api/v1/admin/users",
            headers=employee_headers,
        )
        assert resp.status_code == 403, (
            f"Employee accessed admin panel (got {resp.status_code})"
        )


# ==========================================================================
# Manager Restrictions (role=40)
# ==========================================================================


class TestManagerRestrictions:
    """
    Managers have operational authority but cannot manage users or
    organisation settings.
    """

    def test_manager_cannot_create_users(
        self,
        http_client: httpx.Client,
        manager_headers: dict[str, str],
    ) -> None:
        """
        Manager cannot create new users (owner/admin only).

        Verifies:
        - POST /users/ returns 403
        """
        resp = http_client.post(
            "/api/v1/users/",
            headers=manager_headers,
            json={
                "email": "manager-newuser@rbac.example.com",
                "password": "password123",
                "first_name": "Should",
                "last_name": "Fail",
                "role": "employee",
            },
        )
        assert resp.status_code == 403, (
            f"Manager created a user (got {resp.status_code})"
        )

    def test_manager_can_create_customer(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        manager_headers: dict[str, str],
    ) -> None:
        """
        Manager CAN create customers (operational permission).

        Verifies:
        - POST /customers/ returns 200 or 201
        """
        resp = http_client.post(
            "/api/v1/customers/",
            headers=manager_headers,
            json={
                "first_name": "Manager",
                "last_name": "Created",
                "email": "manager-customer@rbac.example.com",
                "phone": "+353 0 000 0002",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Manager could not create customer (got {resp.status_code})"
        )
        # Cleanup with owner
        customer = resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")
        http_client.delete(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )

    def test_manager_can_create_job(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        manager_headers: dict[str, str],
    ) -> None:
        """
        Manager CAN create jobs (operational permission).

        Verifies:
        - POST /jobs/ returns 200 or 201
        """
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=manager_headers,
            json={
                "title": "Manager Created Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Manager could not create job (got {resp.status_code})"
        )
        # Cleanup with owner
        job = resp.json()
        job_id = job.get("id") or job.get("job_id")
        http_client.delete(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )


# ==========================================================================
# Owner vs Admin boundary
# ==========================================================================


class TestOwnerAdminBoundary:
    """
    Admins (role=60) cannot perform owner-only (role=80) operations such
    as updating the company profile or accessing the superadmin panel.
    """

    def test_admin_cannot_access_superadmin_panel(
        self,
        http_client: httpx.Client,
        admin_headers: dict[str, str],
    ) -> None:
        """
        Admin cannot access the superadmin user listing.

        Verifies:
        - GET /admin/users returns 403
        """
        resp = http_client.get(
            "/api/v1/admin/users",
            headers=admin_headers,
        )
        assert resp.status_code == 403, (
            f"Admin accessed superadmin panel (got {resp.status_code})"
        )

    def test_owner_cannot_access_superadmin_panel(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Regular owner cannot access the superadmin panel.

        Verifies:
        - GET /admin/users returns 403
        """
        resp = http_client.get(
            "/api/v1/admin/users",
            headers=owner_headers,
        )
        assert resp.status_code == 403, (
            f"Owner accessed superadmin panel (got {resp.status_code})"
        )


# ==========================================================================
# Unauthenticated Access
# ==========================================================================


class TestUnauthenticatedAccess:
    """
    Requests without an Authorization header must be rejected.
    """

    def test_no_auth_customers(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        Unauthenticated request to /customers/ must fail.

        Verifies:
        - GET /customers/ returns 401 or 403
        """
        resp = http_client.get("/api/v1/customers/")
        assert resp.status_code in (401, 403)

    def test_no_auth_jobs(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        Unauthenticated request to /jobs/ must fail.

        Verifies:
        - GET /jobs/ returns 401 or 403
        """
        resp = http_client.get("/api/v1/jobs/")
        assert resp.status_code in (401, 403)

    def test_no_auth_users(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        Unauthenticated request to /users/ must fail.

        Verifies:
        - GET /users/ returns 401 or 403
        """
        resp = http_client.get("/api/v1/users/")
        assert resp.status_code in (401, 403)

    def test_no_auth_admin(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        Unauthenticated request to /admin/users must fail.

        Verifies:
        - GET /admin/users returns 401 or 403
        """
        resp = http_client.get("/api/v1/admin/users")
        assert resp.status_code in (401, 403)
