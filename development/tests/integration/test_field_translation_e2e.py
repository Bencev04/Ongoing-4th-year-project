"""
End-to-end tests for BL ↔ DB field name translation.

Verifies that BL services correctly translate between public API
field names and internal DB column names through the full stack.

Field mappings under test:
- Customer: first_name + last_name ↔ name, company ↔ company_name
- Job: assigned_to ↔ assigned_employee_id, address ↔ location
"""

from typing import Any

import httpx
import pytest


def _extract_items(data: Any) -> list[dict[str, Any]]:
    """Extract items from a list or paginated envelope response."""
    if isinstance(data, list):
        return data
    return (
        data.get("items")
        or data.get("data")
        or data.get("customers")
        or data.get("jobs")
        or []
    )


def _get_first_employee_id(
    client: httpx.Client,
    headers: dict[str, str],
) -> int | None:
    """Fetch the first employee ID from the employees list."""
    resp = client.get("/api/v1/employees/", headers=headers)
    if resp.status_code != 200:
        return None
    items = _extract_items(resp.json())
    if not items:
        return None
    return items[0].get("id") or items[0].get("employee_id")


class TestCustomerFieldTranslation:
    """Verify customer BL → DB field translation round-trips correctly."""

    def test_create_customer_with_split_names(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Create customer with first_name + last_name; GET returns same fields.

        The DB stores a single ``name`` column, but the BL layer should
        split it back into first_name / last_name in the response.
        """
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Translation",
                "last_name": "TestUser",
                "email": "translation-test@example.com",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Customer create failed: {resp.status_code} — {resp.text}"
        )
        customer = resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        try:
            # GET should return BL field names, not DB names
            get_resp = http_client.get(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )
            assert get_resp.status_code == 200
            data = get_resp.json()

            assert "first_name" in data, f"Missing first_name: {data.keys()}"
            assert "last_name" in data, f"Missing last_name: {data.keys()}"
            assert data["first_name"] == "Translation"
            assert data["last_name"] == "TestUser"
            # DB field should NOT leak through
            assert "name" not in data or data.get("name") is None, (
                f"DB field 'name' leaked into BL response: {data.get('name')}"
            )
        finally:
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )

    def test_create_customer_with_company(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Create customer with ``company``; GET returns ``company`` not ``company_name``.
        """
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Company",
                "last_name": "Test",
                "email": "company-field-test@example.com",
                "company": "Acme Corp",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Customer create failed: {resp.status_code} — {resp.text}"
        )
        customer = resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        try:
            get_resp = http_client.get(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )
            assert get_resp.status_code == 200
            data = get_resp.json()

            assert data.get("company") == "Acme Corp", (
                f"Expected company='Acme Corp', got: {data.get('company')}"
            )
            assert "company_name" not in data, (
                "DB field 'company_name' leaked into BL response"
            )
        finally:
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )

    def test_list_customers_uses_bl_field_names(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """All items in customer list should use BL field names."""
        resp = http_client.get(
            "/api/v1/customers/",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        items = _extract_items(resp.json())
        assert len(items) > 0, "No customers found for field name check"

        for item in items:
            assert "first_name" in item, (
                f"Customer list item missing 'first_name': {item.keys()}"
            )
            assert "last_name" in item, (
                f"Customer list item missing 'last_name': {item.keys()}"
            )
            # DB-internal 'name' should not appear
            assert "name" not in item or item.get("name") is None, (
                f"DB field 'name' in list item: {item.get('name')}"
            )


class TestJobFieldTranslation:
    """Verify job BL → DB field translation round-trips correctly."""

    def test_create_job_with_address(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Create job with ``address``; GET returns ``address`` not ``location``.
        """
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Address Translation Test",
                "address": "123 Main Street, Dublin",
                "status": "pending",
                "priority": "normal",
            },
        )
        assert resp.status_code in (200, 201), (
            f"Job create failed: {resp.status_code} — {resp.text}"
        )
        job = resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            get_resp = http_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )
            assert get_resp.status_code == 200
            data = get_resp.json()

            assert data.get("address") == "123 Main Street, Dublin", (
                f"Expected address='123 Main Street, Dublin', "
                f"got: {data.get('address')}"
            )
            assert "location" not in data, "DB field 'location' leaked into BL response"
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )

    def test_assign_job_uses_assigned_to(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Assign job via ``assigned_to``; GET returns ``assigned_to``, not
        ``assigned_employee_id``.
        """
        emp_id = _get_first_employee_id(http_client, owner_headers)
        if emp_id is None:
            pytest.skip("No employees available for assignment test")

        # Create a job
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Assignment Translation Test",
                "status": "pending",
                "priority": "normal",
            },
        )
        assert create_resp.status_code in (200, 201)
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            # Assign via BL field name
            assign_resp = http_client.post(
                f"/api/v1/jobs/{job_id}/assign",
                headers=owner_headers,
                json={"assigned_to": emp_id},
            )
            assert assign_resp.status_code == 200, (
                f"Assign failed: {assign_resp.status_code} — {assign_resp.text}"
            )

            # GET should return BL field name
            get_resp = http_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )
            assert get_resp.status_code == 200
            data = get_resp.json()

            assert "assigned_to" in data, f"Missing 'assigned_to': {data.keys()}"
            assert data["assigned_to"] == emp_id
            assert "assigned_employee_id" not in data, (
                "DB field 'assigned_employee_id' leaked into BL response"
            )
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )

    def test_list_jobs_uses_bl_field_names(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """All items in job list should use BL field names."""
        resp = http_client.get(
            "/api/v1/jobs/",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        items = _extract_items(resp.json())
        # Only check jobs that have these fields set
        for item in items:
            # address should appear instead of location
            if "location" in item:
                pytest.fail(
                    f"DB field 'location' in job list item: {item.get('location')}"
                )
            # assigned_to should appear instead of assigned_employee_id
            if "assigned_employee_id" in item:
                pytest.fail(
                    f"DB field 'assigned_employee_id' in job list item: "
                    f"{item.get('assigned_employee_id')}"
                )

    def test_job_detail_has_enriched_names(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Job detail should include enriched names (customer_name,
        assigned_to_name) when customer/employee are linked.
        """
        # Get a customer ID for linking
        cust_resp = http_client.get(
            "/api/v1/customers/",
            headers=owner_headers,
        )
        items = _extract_items(cust_resp.json())
        if not items:
            pytest.skip("No customers for enrichment test")
        customer_id = items[0].get("id") or items[0].get("customer_id")

        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Enrichment Test Job",
                "customer_id": customer_id,
                "status": "pending",
            },
        )
        assert create_resp.status_code in (200, 201)
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            get_resp = http_client.get(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )
            assert get_resp.status_code == 200
            data = get_resp.json()

            # customer_name should be populated when customer_id is set
            assert "customer_name" in data, (
                f"Missing 'customer_name' in job detail: {data.keys()}"
            )
            assert data["customer_name"], (
                "customer_name should not be empty when customer is linked"
            )
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )
