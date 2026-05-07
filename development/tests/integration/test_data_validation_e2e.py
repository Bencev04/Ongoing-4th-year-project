"""
End-to-end tests for input validation through the full stack.

Verifies that invalid payloads are rejected with the correct
HTTP status codes (422 for validation, 404 for missing, 409 for
conflict) rather than silently accepted or causing 500 errors.
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


class TestCustomerValidation:
    """Verify customer input validation at the BL layer."""

    def test_invalid_email_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Customer with malformed email → 422."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Test",
                "last_name": "Invalid",
                "email": "not-an-email",
            },
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid email, got {resp.status_code}"
        )

    def test_missing_first_name_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Customer without required first_name → 422."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={"last_name": "OnlyLast"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing first_name, got {resp.status_code}"
        )

    def test_missing_last_name_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Customer without required last_name → 422."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={"first_name": "OnlyFirst"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing last_name, got {resp.status_code}"
        )

    def test_empty_first_name_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Customer with empty first_name → 422 (min_length=1)."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={"first_name": "", "last_name": "Valid"},
        )
        assert resp.status_code == 422

    def test_oversized_name_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Customer with name longer than 100 chars → 422 (max_length=100)."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "A" * 101,
                "last_name": "Valid",
            },
        )
        assert resp.status_code == 422


class TestJobValidation:
    """Verify job input validation at the BL layer."""

    def test_missing_title_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Job without required title → 422."""
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={"status": "pending", "priority": "normal"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for missing title, got {resp.status_code}"
        )

    def test_empty_title_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Job with empty title → 422 (min_length=1)."""
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={"title": "", "status": "pending"},
        )
        assert resp.status_code == 422

    def test_oversized_title_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Job with title > 200 chars → 422 (max_length=200)."""
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={"title": "T" * 201, "status": "pending"},
        )
        assert resp.status_code == 422

    def test_invalid_status_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Job with invalid status string → rejected (422 at BL or 500/400 at DB).

        Valid statuses: pending, scheduled, in_progress, completed, cancelled.
        """
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Invalid Status Test",
                "status": "nonexistent_status",
                "priority": "normal",
            },
        )
        # Should not succeed (2xx) — any client error is acceptable
        assert resp.status_code >= 400, (
            f"Invalid status should be rejected, got {resp.status_code}"
        )
        assert resp.status_code != 500, (
            "Invalid status should not cause a 500 internal server error"
        )

    def test_invalid_priority_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Job with invalid priority string → rejected.

        Valid priorities: low, normal, high, urgent.
        """
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Invalid Priority Test",
                "status": "pending",
                "priority": "super_ultra_mega",
            },
        )
        assert resp.status_code >= 400, (
            f"Invalid priority should be rejected, got {resp.status_code}"
        )
        assert resp.status_code != 500, (
            "Invalid priority should not cause a 500 internal server error"
        )

    def test_negative_duration_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Job with negative estimated_duration → 422 (ge=0)."""
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Negative Duration",
                "status": "pending",
                "estimated_duration": -5,
            },
        )
        assert resp.status_code == 422


class TestResourceNotFound:
    """Verify that requests for nonexistent resources return 404."""

    def test_nonexistent_customer_returns_404(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """GET /customers/999999 → 404."""
        resp = http_client.get(
            "/api/v1/customers/999999",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_nonexistent_job_returns_404(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """GET /jobs/999999 → 404."""
        resp = http_client.get(
            "/api/v1/jobs/999999",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_nonexistent_employee_returns_404(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """GET /employees/999999 → 404."""
        resp = http_client.get(
            "/api/v1/employees/999999",
            headers=owner_headers,
        )
        assert resp.status_code == 404

    def test_invalid_id_format_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """GET /jobs/abc → 422 or 404 (not 500)."""
        resp = http_client.get(
            "/api/v1/jobs/abc",
            headers=owner_headers,
        )
        assert resp.status_code in (404, 422), (
            f"Invalid ID format should be 404/422, got {resp.status_code}"
        )


class TestCrossResourceValidation:
    """Verify validation that spans multiple resources."""

    def test_job_with_other_tenant_customer_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Creating a job referencing a customer from another tenant
        → 403 or 404 (not 200).
        """
        # Create a customer under owner2
        cust_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner2_headers,
            json={
                "first_name": "Other",
                "last_name": "Tenant",
                "email": "other-tenant-val@example.com",
            },
        )
        if cust_resp.status_code not in (200, 201):
            pytest.skip("Could not create cross-tenant customer")
        cust = cust_resp.json()
        cust_id = cust.get("id") or cust.get("customer_id")

        try:
            # Owner1 tries to create a job referencing owner2's customer
            resp = http_client.post(
                "/api/v1/jobs/",
                headers=owner_headers,
                json={
                    "title": "Cross Tenant Customer Ref",
                    "customer_id": cust_id,
                    "status": "pending",
                },
            )
            assert resp.status_code in (400, 403, 404, 422), (
                f"Cross-tenant customer ref should be rejected, got {resp.status_code}"
            )
        finally:
            http_client.delete(
                f"/api/v1/customers/{cust_id}",
                headers=owner2_headers,
            )

    def test_empty_request_body_rejected(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """POST /jobs/ with empty body → 422."""
        resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={},
        )
        assert resp.status_code == 422
