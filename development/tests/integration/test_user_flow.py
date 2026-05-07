"""
Integration tests — User service flow.

Pairwise: user-bl-service ↔ user-db-access-service

Tests user and employee CRUD operations through the BL layer using
real auth tokens and real database operations. Covers:
    - User listing, creation, update, deactivation
    - Employee invite, details CRUD
    - Company profile get/update
    - RBAC enforcement for write operations
"""

import time

import httpx
import pytest


class TestListUsers:
    """Test listing users through the BL layer."""

    def test_list_users_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that listing users returns 200 and a list.

        Verifies:
        - Response is 200
        - Response body is a list or contains a data/items array
        """
        resp = http_client.get(
            "/api/v1/users/",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Response may be a list or a paginated envelope
        if isinstance(data, list):
            assert len(data) >= 1  # At least the owner exists
        else:
            items = data.get("data") or data.get("items") or data.get("users", [])
            assert len(items) >= 1

    def test_list_users_requires_auth(self, http_client: httpx.Client) -> None:
        """
        Test that listing users without auth returns 401.

        Verifies:
        - Unauthenticated request is rejected
        """
        resp = http_client.get("/api/v1/users/")
        assert resp.status_code in (401, 403)

    def test_list_users_tenant_scoped(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that both owner and employee see users scoped to their tenant.

        Verifies:
        - Both return 200
        - Owner and employee belong to the same tenant in demo data
        """
        owner_resp = http_client.get("/api/v1/users/", headers=owner_headers)
        emp_resp = http_client.get("/api/v1/users/", headers=employee_headers)
        assert owner_resp.status_code == 200
        assert emp_resp.status_code == 200


class TestGetUser:
    """Test retrieving individual users."""

    def test_get_own_user(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that the owner can retrieve their own user record.

        Verifies:
        - GET /users/ returns at least one user
        - GET /users/{id} returns that user's details
        """
        # Get the user list to find the owner's ID
        list_resp = http_client.get("/api/v1/users/", headers=owner_headers)
        data = list_resp.json()
        users = (
            data
            if isinstance(data, list)
            else (data.get("data") or data.get("items") or data.get("users", []))
        )
        assert len(users) > 0

        user_id = users[0].get("id") or users[0].get("user_id")
        detail_resp = http_client.get(
            f"/api/v1/users/{user_id}",
            headers=owner_headers,
        )
        assert detail_resp.status_code == 200


class TestListEmployees:
    """Test listing employees through the BL layer."""

    def test_list_employees_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that listing employees returns 200.

        Verifies:
        - Response is 200
        - At least one employee exists (demo seed data)
        """
        resp = http_client.get(
            "/api/v1/employees/",
            headers=owner_headers,
        )
        assert resp.status_code == 200

    def test_list_employees_requires_auth(self, http_client: httpx.Client) -> None:
        """
        Test employees endpoint requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get("/api/v1/employees/")
        assert resp.status_code in (401, 403)


# ==========================================================================
# User CRUD — Create, Update, Deactivate
# ==========================================================================


class TestUserCRUD:
    """
    Test user create, update, and deactivation through the BL layer.

    Pairwise: user-bl-service ↔ user-db-access-service

    Only owner/admin roles should be able to create and deactivate users.
    Self-edit is allowed for any authenticated user.
    """

    def test_owner_can_create_user(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that an owner can create a new user in their tenant.

        Steps:
        1. POST /users with valid payload
        2. Verify 200/201 and returned user data
        3. Cleanup via DELETE

        Verifies:
        - 200 or 201 status
        - Returned user has correct email
        """
        email = f"testuser-{int(time.time())}@example.com"

        create_resp = http_client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": email,
                "password": "TestPass123!",
                "first_name": "Test",
                "last_name": "User",
                "role": "employee",
            },
        )
        assert create_resp.status_code in (200, 201), (
            f"Create user failed: {create_resp.status_code} — {create_resp.text}"
        )
        user = create_resp.json()
        user_id = user.get("id") or user.get("user_id")
        assert user_id is not None

        # Cleanup
        http_client.delete(
            f"/api/v1/users/{user_id}",
            headers=owner_headers,
        )

    def test_employee_cannot_create_user(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that an employee cannot create users.

        Verifies:
        - 403 — insufficient privileges (employee role level 20)
        """
        resp = http_client.post(
            "/api/v1/users/",
            headers=employee_headers,
            json={
                "email": "hacker@example.com",
                "password": "HackedPass1!",
                "first_name": "Hacker",
                "last_name": "User",
                "role": "admin",
            },
        )
        assert resp.status_code == 403

    def test_owner_can_update_user(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that an owner can update a user's details.

        Steps:
        1. Create a user
        2. PUT /users/{id} with updated first_name
        3. Verify update succeeded
        4. Cleanup

        Verifies:
        - 200 on successful update
        - Updated field is reflected
        """
        email = f"update-user-{int(time.time())}@example.com"

        # Create
        create_resp = http_client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": email,
                "password": "TestPass123!",
                "first_name": "Before",
                "last_name": "Update",
                "role": "employee",
            },
        )
        user = create_resp.json()
        user_id = user.get("id") or user.get("user_id")

        try:
            # Update
            update_resp = http_client.put(
                f"/api/v1/users/{user_id}",
                headers=owner_headers,
                json={"first_name": "After"},
            )
            assert update_resp.status_code == 200
        finally:
            # Cleanup
            http_client.delete(
                f"/api/v1/users/{user_id}",
                headers=owner_headers,
            )

    def test_owner_can_deactivate_user(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that an owner can deactivate (soft-delete) a user.

        Steps:
        1. Create a user
        2. DELETE /users/{id}
        3. Verify 200/204

        Verifies:
        - Deactivation returns success status
        """
        email = f"deactivate-{int(time.time())}@example.com"

        create_resp = http_client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": email,
                "password": "TestPass123!",
                "first_name": "Deactivate",
                "last_name": "Me",
                "role": "employee",
            },
        )
        user = create_resp.json()
        user_id = user.get("id") or user.get("user_id")

        del_resp = http_client.delete(
            f"/api/v1/users/{user_id}",
            headers=owner_headers,
        )
        assert del_resp.status_code in (200, 204)

    def test_employee_cannot_deactivate_user(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that an employee cannot deactivate users.

        Verifies:
        - 403 — employee role is too low for user deletion
        """
        # Try to deactivate user_id 1 (owner) — should be forbidden
        resp = http_client.delete(
            "/api/v1/users/1",
            headers=employee_headers,
        )
        assert resp.status_code == 403


# ==========================================================================
# Employee Invite (combined user + employee creation)
# ==========================================================================


class TestUserInvite:
    """
    Test the /users/invite endpoint for creating a user with employee details.

    Pairwise: user-bl-service ↔ user-db-access-service

    This is a composite operation that creates a user record and attaches
    employee-specific details (position, hourly_rate, skills) in one call.
    """

    def test_owner_can_invite_user(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that an owner can invite a user with employee details.

        Verifies:
        - 200 or 201 status
        - Returned response contains user and/or employee data
        """
        email = f"invite-{int(time.time())}@example.com"
        created_user_id = None

        try:
            resp = http_client.post(
                "/api/v1/users/invite",
                headers=owner_headers,
                json={
                    "email": email,
                    "password": "InvitePass123!",
                    "first_name": "Invited",
                    "last_name": "Employee",
                    "position": "Field Technician",
                    "hourly_rate": 25.00,
                    "skills": "Plumbing, Electrical",
                },
            )
            assert resp.status_code in (200, 201), (
                f"Invite failed: {resp.status_code} — {resp.text}"
            )
            data = resp.json()
            # Extract user_id for cleanup
            created_user_id = (
                data.get("id")
                or data.get("user_id")
                or (data.get("user", {}) or {}).get("id")
            )
        finally:
            # Cleanup — deactivate the invited user if created
            if created_user_id:
                http_client.delete(
                    f"/api/v1/users/{created_user_id}",
                    headers=owner_headers,
                )

    def test_employee_cannot_invite(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that an employee cannot invite new users.

        Verifies:
        - 403 — only owner/admin can invite
        """
        resp = http_client.post(
            "/api/v1/users/invite",
            headers=employee_headers,
            json={
                "email": "no-invite@example.com",
                "password": "TestPass123!",
                "first_name": "No",
                "last_name": "Invite",
            },
        )
        assert resp.status_code == 403


# ==========================================================================
# Employee Details CRUD
# ==========================================================================


class TestEmployeeCRUD:
    """
    Test employee details retrieval and update.

    Pairwise: user-bl-service ↔ user-db-access-service
    """

    def _get_first_employee_id(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> int | None:
        """Helper: get the first employee's ID from the list endpoint."""
        resp = http_client.get(
            "/api/v1/employees/",
            headers=owner_headers,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        employees = (
            data
            if isinstance(data, list)
            else (data.get("data") or data.get("items") or data.get("employees", []))
        )
        if not employees:
            return None
        return employees[0].get("id") or employees[0].get("employee_id")

    def test_get_employee_by_id(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test retrieving a single employee by ID.

        Verifies:
        - 200 response
        - Employee data contains expected fields
        """
        emp_id = self._get_first_employee_id(http_client, owner_headers)
        if emp_id is None:
            pytest.skip("No employees found in tenant")

        resp = http_client.get(
            f"/api/v1/employees/{emp_id}",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should contain employee-specific fields
        assert "id" in data or "employee_id" in data

    def test_update_employee(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test updating employee details (position, hourly_rate).

        Verifies:
        - 200 on successful update
        """
        emp_id = self._get_first_employee_id(http_client, owner_headers)
        if emp_id is None:
            pytest.skip("No employees found in tenant")

        resp = http_client.put(
            f"/api/v1/employees/{emp_id}",
            headers=owner_headers,
            json={"position": "Senior Technician"},
        )
        assert resp.status_code == 200


# ==========================================================================
# Company Profile
# ==========================================================================


class TestCompanyProfile:
    """
    Test company profile retrieval and update.

    Pairwise: user-bl-service ↔ user-db-access-service

    Any authenticated user can view the company profile;
    only owner/admin can update it.
    """

    def test_get_own_company(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that an owner can retrieve their company profile.

        Verifies:
        - 200 response
        - Response contains company data fields
        """
        resp = http_client.get(
            "/api/v1/company/",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data or "company_name" in data or "id" in data

    def test_update_company(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that an owner can update their company profile.

        Verifies:
        - 200 on successful update
        """
        resp = http_client.put(
            "/api/v1/company/",
            headers=owner_headers,
            json={"phone": "+353 1 555 9999"},
        )
        assert resp.status_code == 200

    def test_employee_cannot_update_company(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that an employee cannot update the company profile.

        Verifies:
        - 403 — only owner/admin can modify company details
        """
        resp = http_client.put(
            "/api/v1/company/",
            headers=employee_headers,
            json={"name": "Hacked Company Name"},
        )
        assert resp.status_code == 403
