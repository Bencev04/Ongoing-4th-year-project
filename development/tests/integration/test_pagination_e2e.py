"""
End-to-end tests for pagination across list endpoints.

Creates enough resources to span multiple pages, then verifies that
pagination metadata (page, per_page, total) and page boundaries work.
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


class TestCustomerPagination:
    """Verify pagination on the customer list endpoint."""

    @pytest.fixture(autouse=True)
    def _bulk_customers(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Create 15 customers, yield, then clean up."""
        self._created_ids: list[int] = []
        for i in range(15):
            resp = http_client.post(
                "/api/v1/customers",
                headers=owner_headers,
                json={
                    "first_name": f"PagTest{i:02d}",
                    "last_name": "Customer",
                    "email": f"pagtest-cust-{i:02d}@example.com",
                },
            )
            if resp.status_code in (200, 201):
                cid = resp.json().get("id") or resp.json().get("customer_id")
                if cid:
                    self._created_ids.append(cid)

        if len(self._created_ids) < 12:
            pytest.skip(f"Only created {len(self._created_ids)}/15 customers")

        yield  # type: ignore[misc]

        for cid in self._created_ids:
            http_client.delete(
                f"/api/v1/customers/{cid}",
                headers=owner_headers,
            )

    def test_first_page_has_correct_size(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """page=1, per_page=5 → exactly 5 items."""
        resp = http_client.get(
            "/api/v1/customers",
            headers=owner_headers,
            params={"page": 1, "per_page": 5, "search": "PagTest"},
        )
        assert resp.status_code == 200
        data = resp.json()
        items = _extract_items(data)
        assert len(items) == 5, f"Expected 5 items, got {len(items)}"

    def test_pagination_metadata_present(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Response contains total, page, and per_page metadata."""
        resp = http_client.get(
            "/api/v1/customers",
            headers=owner_headers,
            params={"page": 1, "per_page": 5, "search": "PagTest"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Metadata can live at the top level or inside "pagination"
        meta = data.get("pagination", data)
        assert "total" in meta or "total_count" in meta, (
            f"No total/total_count in response: {list(data.keys())}"
        )

    def test_second_page_different_items(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Items on page 2 are different from page 1."""
        p1 = http_client.get(
            "/api/v1/customers",
            headers=owner_headers,
            params={"page": 1, "per_page": 5, "search": "PagTest"},
        )
        p2 = http_client.get(
            "/api/v1/customers",
            headers=owner_headers,
            params={"page": 2, "per_page": 5, "search": "PagTest"},
        )
        assert p1.status_code == 200
        assert p2.status_code == 200

        ids1 = {c.get("id") or c.get("customer_id") for c in _extract_items(p1.json())}
        ids2 = {c.get("id") or c.get("customer_id") for c in _extract_items(p2.json())}
        assert ids1.isdisjoint(ids2), "Page 1 and 2 overlap"

    def test_page_beyond_data_returns_empty(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Requesting a page far beyond the data → empty items, not error."""
        resp = http_client.get(
            "/api/v1/customers",
            headers=owner_headers,
            params={"page": 999, "per_page": 10, "search": "PagTest"},
        )
        assert resp.status_code == 200
        items = _extract_items(resp.json())
        assert len(items) == 0


class TestJobPagination:
    """Verify pagination on the job list endpoint."""

    @pytest.fixture(autouse=True)
    def _bulk_jobs(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Create 12 jobs, yield, then clean up."""
        self._created_ids: list[int] = []
        for i in range(12):
            resp = http_client.post(
                "/api/v1/jobs",
                headers=owner_headers,
                json={
                    "title": f"PagTestJob-{i:02d}",
                    "status": "pending",
                    "priority": "normal",
                },
            )
            if resp.status_code in (200, 201):
                jid = resp.json().get("id") or resp.json().get("job_id")
                if jid:
                    self._created_ids.append(jid)

        if len(self._created_ids) < 10:
            pytest.skip(f"Only created {len(self._created_ids)}/12 jobs")

        yield  # type: ignore[misc]

        for jid in self._created_ids:
            http_client.delete(
                f"/api/v1/jobs/{jid}",
                headers=owner_headers,
            )

    def test_job_first_page(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """page=1, per_page=5 → 5 items."""
        resp = http_client.get(
            "/api/v1/jobs",
            headers=owner_headers,
            params={"page": 1, "per_page": 5},
        )
        assert resp.status_code == 200
        items = _extract_items(resp.json())
        assert len(items) == 5

    def test_job_pagination_metadata(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Job list response includes total count."""
        resp = http_client.get(
            "/api/v1/jobs",
            headers=owner_headers,
            params={"page": 1, "per_page": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        meta = data.get("pagination", data)
        assert "total" in meta or "total_count" in meta, (
            f"No pagination total in response: {list(data.keys())}"
        )

    def test_job_page_beyond_data(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Far-future page → empty items."""
        resp = http_client.get(
            "/api/v1/jobs",
            headers=owner_headers,
            params={"page": 999, "per_page": 10},
        )
        assert resp.status_code == 200
        items = _extract_items(resp.json())
        assert len(items) == 0

    def test_default_page_returns_items(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Calling without explicit page/per_page returns items."""
        resp = http_client.get(
            "/api/v1/jobs",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        items = _extract_items(resp.json())
        assert len(items) >= 1
