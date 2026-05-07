"""
Cross-Tenant Isolation Integration Tests
=========================================

Validates that data belonging to one tenant (organisation) is completely
invisible and inaccessible to another tenant.

Architecture under test::

    Owner 1 (Demo CRM Ltd.)   ─┐
                                ├─ customer-bl / job-bl ─► DB
    Owner 2 (Second Tenant)   ─┘

Owner 1 creates resources, then Owner 2 verifies they are absent from
their view.  Tests also verify that a deactivated user cannot log in.

Industry-standard practices applied:
    - Explicit test isolation with try/finally cleanup
    - Docstrings on every test method
    - Descriptive assertions with failure messages
"""

import httpx
import pytest

# ==========================================================================
# Customer Isolation
# ==========================================================================


class TestCustomerIsolation:
    """
    Verify that customers created by one tenant are invisible to another.

    Pairwise: customer-bl-service ↔ customer-db-access-service
    """

    def test_tenant2_cannot_see_tenant1_customers(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Owner 1 creates a customer; Owner 2 must not see it.

        Steps:
        1. Owner 1 creates "Isolation Test Customer"
        2. Owner 2 lists their customers
        3. Verify the customer does not appear

        Verifies:
        - Owner 2's customer list does not contain the new customer
        """
        # Owner 1 creates a customer
        create_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Isolated",
                "last_name": "Customer",
                "email": "isolated@cross-tenant.example.com",
                "phone": "+353 1 000 0000",
            },
        )
        assert create_resp.status_code in (200, 201), (
            f"Create failed: {create_resp.text}"
        )
        customer = create_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        try:
            # Owner 2 lists their customers
            list_resp = http_client.get(
                "/api/v1/customers/",
                headers=owner2_headers,
            )
            assert list_resp.status_code == 200

            data = list_resp.json()
            customers = (
                data
                if isinstance(data, list)
                else (
                    data.get("data") or data.get("items") or data.get("customers", [])
                )
            )

            # None of Owner 2's customers should have this ID
            ids = [c.get("id") or c.get("customer_id") for c in customers]
            assert customer_id not in ids, (
                "Owner 2 can see Owner 1's customer — tenant isolation broken"
            )
        finally:
            # Cleanup with Owner 1
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )

    def test_tenant2_cannot_read_tenant1_customer_directly(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Owner 2 cannot fetch a specific customer created by Owner 1 via ID.

        Verifies:
        - GET /customers/{id} returns 404 or 403 for cross-tenant access
        """
        # Owner 1 creates a customer
        create_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Direct",
                "last_name": "Access",
                "email": "direct-access@cross-tenant.example.com",
                "phone": "+353 1 000 0001",
            },
        )
        customer = create_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        try:
            # Owner 2 tries direct GET
            resp = http_client.get(
                f"/api/v1/customers/{customer_id}",
                headers=owner2_headers,
            )
            assert resp.status_code in (403, 404), (
                f"Expected 403/404 but got {resp.status_code} — "
                "cross-tenant direct read should be denied"
            )
        finally:
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )


# ==========================================================================
# Job Isolation
# ==========================================================================


class TestJobIsolation:
    """
    Verify that jobs created by one tenant are invisible to another.

    Pairwise: job-bl-service ↔ job-db-access-service
    """

    def test_tenant2_cannot_see_tenant1_jobs(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Owner 1 creates a job; Owner 2's job list must not contain it.

        Verifies:
        - Owner 2's job listing does not include the job ID
        """
        # Owner 1 creates a job
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Isolated Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            # Owner 2 lists jobs
            list_resp = http_client.get(
                "/api/v1/jobs/",
                headers=owner2_headers,
            )
            assert list_resp.status_code == 200

            data = list_resp.json()
            jobs = (
                data
                if isinstance(data, list)
                else (data.get("data") or data.get("items") or data.get("jobs", []))
            )

            ids = [j.get("id") or j.get("job_id") for j in jobs]
            assert job_id not in ids, (
                "Owner 2 can see Owner 1's job — tenant isolation broken"
            )
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )

    def test_tenant2_cannot_read_tenant1_job_directly(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Owner 2 cannot fetch a specific job belonging to Owner 1.

        Verifies:
        - GET /jobs/{id} returns 404 or 403
        """
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Direct Access Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            resp = http_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=owner2_headers,
            )
            assert resp.status_code in (403, 404), (
                f"Expected 403/404 but got {resp.status_code}"
            )
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )


# ==========================================================================
# User / Employee Isolation
# ==========================================================================


class TestUserIsolation:
    """
    Verify that users/employees of one tenant are invisible to another.
    """

    def test_tenant2_cannot_see_tenant1_employees(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Owner 2's employee list must not include Owner 1's employees.

        Verifies:
        - No email addresses from Owner 1 appear in Owner 2's employee list
        """
        # Get Owner 1 employees
        t1_resp = http_client.get(
            "/api/v1/employees/",
            headers=owner_headers,
        )
        assert t1_resp.status_code == 200
        t1_data = t1_resp.json()
        t1_employees = (
            t1_data
            if isinstance(t1_data, list)
            else (
                t1_data.get("data")
                or t1_data.get("items")
                or t1_data.get("employees", [])
            )
        )
        t1_emails = {e.get("email") for e in t1_employees if e.get("email")}

        # Get Owner 2 employees
        t2_resp = http_client.get(
            "/api/v1/employees/",
            headers=owner2_headers,
        )
        assert t2_resp.status_code == 200
        t2_data = t2_resp.json()
        t2_employees = (
            t2_data
            if isinstance(t2_data, list)
            else (
                t2_data.get("data")
                or t2_data.get("items")
                or t2_data.get("employees", [])
            )
        )
        t2_emails = {e.get("email") for e in t2_employees if e.get("email")}

        # No overlap expected
        overlap = t1_emails & t2_emails
        assert not overlap, f"Cross-tenant employee leakage detected: {overlap}"


# ==========================================================================
# Note Isolation
# ==========================================================================


class TestNoteIsolation:
    """
    Verify that customer notes from one tenant are inaccessible to another.
    """

    def test_tenant2_cannot_read_tenant1_notes(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        A note created on Owner 1's customer must be inaccessible to Owner 2.

        Steps:
        1. Owner 1 creates a customer and a note
        2. Owner 2 attempts to read the note
        3. Verify 403 or 404

        Verifies:
        - Cross-tenant note access is denied
        """
        # Owner 1 creates a customer
        cust_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Note",
                "last_name": "Isolation",
                "email": "note-isolation@cross-tenant.example.com",
                "phone": "+353 1 000 0002",
            },
        )
        customer = cust_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        # Add a note
        note_resp = http_client.post(
            f"/api/v1/customers/{customer_id}/notes",
            headers=owner_headers,
            json={"content": "Confidential tenant 1 note"},
        )
        note = note_resp.json()
        note_id = note.get("id") or note.get("note_id")

        try:
            # Owner 2 tries to read notes for that customer
            resp = http_client.get(
                f"/api/v1/customers/{customer_id}/notes",
                headers=owner2_headers,
            )
            # Should be denied or return empty
            if resp.status_code == 200:
                data = resp.json()
                notes = (
                    data
                    if isinstance(data, list)
                    else (
                        data.get("data") or data.get("items") or data.get("notes", [])
                    )
                )
                assert len(notes) == 0, (
                    "Owner 2 can see Owner 1's notes — isolation broken"
                )
            else:
                assert resp.status_code in (403, 404)
        finally:
            # Cleanup
            if note_id:
                http_client.delete(
                    f"/api/v1/notes/{note_id}",
                    headers=owner_headers,
                )
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )


# ==========================================================================
# Deactivated User
# ==========================================================================


class TestDeactivatedUser:
    """
    Verify that a deactivated user cannot authenticate.
    """

    def test_deactivated_user_cannot_login(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        After deactivation, a user's credentials must be rejected at login.

        Steps:
        1. Owner creates a new user
        2. Owner deactivates the user
        3. Attempt login with deactivated credentials
        4. Verify login fails

        Verifies:
        - Login returns 401 or 403 for deactivated accounts
        """
        import time

        unique = int(time.time())
        email = f"deactivate-{unique}@example.com"
        password = "password123"

        # Create a user
        create_resp = http_client.post(
            "/api/v1/users/",
            headers=owner_headers,
            json={
                "email": email,
                "password": password,
                "first_name": "Deactivate",
                "last_name": "Test",
                "role": "employee",
            },
        )
        if create_resp.status_code not in (200, 201):
            pytest.skip(f"Cannot create user: {create_resp.text}")

        user = create_resp.json()
        user_id = user.get("id") or user.get("user_id")

        # Deactivate the user (DELETE performs soft-delete / sets is_active=False)
        deact_resp = http_client.delete(
            f"/api/v1/users/{user_id}",
            headers=owner_headers,
        )
        assert deact_resp.status_code in (200, 204), (
            f"Deactivate failed: {deact_resp.text}"
        )

        # Attempt login
        login_resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert login_resp.status_code in (401, 403), (
            f"Deactivated user was able to login: {login_resp.status_code}"
        )
