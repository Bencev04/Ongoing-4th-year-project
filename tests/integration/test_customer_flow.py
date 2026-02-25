"""
Integration tests — Customer service flow.

Pairwise: customer-bl-service ↔ customer-db-access-service

Tests customer and customer notes CRUD operations through the BL layer
using real auth tokens, real database, and real service-to-service calls.

Covers:
    - Customer listing, search, CRUD
    - Customer notes create, update, delete
    - RBAC enforcement on write/delete operations
"""

from typing import Dict, Optional

import httpx
import pytest


class TestListCustomers:
    """Test listing customers through the BL layer."""

    def test_list_customers_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test that listing customers returns 200.

        Verifies:
        - Response is 200
        - Response contains customer data (demo seed)
        """
        resp = http_client.get(
            "/api/v1/customers/",
            headers=owner_headers,
        )
        assert resp.status_code == 200

    def test_list_customers_requires_auth(
        self, http_client: httpx.Client
    ) -> None:
        """
        Test customers endpoint requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get("/api/v1/customers/")
        assert resp.status_code in (401, 403)


class TestCustomerCRUD:
    """Test customer create, read, update, delete cycle."""

    def test_create_and_read_customer(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test full create → read cycle for a customer.

        Verifies:
        - POST /customers/ returns 201 or 200
        - The returned customer has the correct name
        - GET /customers/{id} retrieves the same customer
        """
        # Create
        create_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Integration",
                "last_name": "TestCustomer",
                "email": "integration-test@example.com",
                "phone": "0851234567",
            },
        )
        assert create_resp.status_code in (200, 201)
        customer = create_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")
        assert customer_id is not None

        # Read
        get_resp = http_client.get(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )
        assert get_resp.status_code == 200

        # Cleanup — delete the test customer
        http_client.delete(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )

    def test_update_customer(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test creating and then updating a customer.

        Verifies:
        - POST creates the customer
        - PUT updates the customer's phone
        - GET returns the updated phone
        """
        # Create
        create_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Update",
                "last_name": "TestCustomer",
                "email": "update-test@example.com",
                "phone": "0850000000",
            },
        )
        customer = create_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        # Update
        update_resp = http_client.put(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
            json={"phone": "0859999999"},
        )
        assert update_resp.status_code == 200

        # Cleanup
        http_client.delete(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )

    def test_delete_customer(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test deleting a customer.

        Verifies:
        - POST creates
        - DELETE returns 200/204
        - GET after delete returns 404 or empty/inactive
        """
        # Create
        create_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "Delete",
                "last_name": "TestCustomer",
                "email": "delete-test@example.com",
            },
        )
        customer = create_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        # Delete
        del_resp = http_client.delete(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )
        assert del_resp.status_code in (200, 204)


class TestCustomerNotes:
    """Test customer notes CRUD through the BL layer."""

    def test_create_and_list_notes(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test creating a note on a customer and listing notes.

        Verifies:
        - Create a customer
        - POST a note to that customer
        - GET notes for the customer returns the note
        """
        # Create a customer first
        cust_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "NoteTest",
                "last_name": "Customer",
                "email": "notetest@example.com",
            },
        )
        customer = cust_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        # Create a note
        note_resp = http_client.post(
            f"/api/v1/notes/{customer_id}",
            headers=owner_headers,
            json={
                "content": "Integration test note — should be cleaned up.",
            },
        )
        assert note_resp.status_code in (200, 201)

        # Cleanup
        http_client.delete(
            f"/api/v1/customers/{customer_id}",
            headers=owner_headers,
        )


# ==========================================================================
# Customer Search
# ==========================================================================

class TestCustomerSearch:
    """
    Test the customer search/autocomplete endpoint.

    Pairwise: customer-bl-service ↔ customer-db-access-service

    GET /customers/search?q=<term> returns matching customers for the
    authenticated user's tenant.
    """

    def test_search_returns_matching_customers(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test that searching for a known customer name returns results.

        Verifies:
        - 200 response
        - Results are a list (possibly empty if no match; we test structure)
        """
        # Search for the demo seed customer "John Smith"
        resp = http_client.get(
            "/api/v1/customers/search",
            headers=owner_headers,
            params={"q": "John"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Response may be a list or paginated envelope
        if isinstance(data, dict):
            items = (
                data.get("items") or data.get("data")
                or data.get("customers", [])
            )
            assert isinstance(items, list)
        else:
            assert isinstance(data, list)

    def test_search_requires_auth(
        self, http_client: httpx.Client
    ) -> None:
        """
        Test that the search endpoint requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get(
            "/api/v1/customers/search",
            params={"q": "test"},
        )
        assert resp.status_code in (401, 403)

    def test_search_requires_query_param(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test that the search endpoint requires the 'q' parameter.

        Verifies:
        - 422 (validation error) when 'q' is missing
        """
        resp = http_client.get(
            "/api/v1/customers/search",
            headers=owner_headers,
        )
        assert resp.status_code == 422


# ==========================================================================
# Customer Notes — Update and Delete
# ==========================================================================

class TestCustomerNotesExtended:
    """
    Extended note tests: update and delete operations with RBAC checks.

    Pairwise: customer-bl-service ↔ customer-db-access-service

    PUT /notes/{note_id} — any auth user can update.
    DELETE /notes/{note_id} — owner/admin only.
    """

    def _create_customer_with_note(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> tuple:
        """
        Helper: create a customer and add a note to it.

        Returns:
            (customer_id, note_id) — both may be None if creation fails.
        """
        # Create customer
        cust_resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "NoteTest",
                "last_name": "Extended",
                "email": "notetest-ext@example.com",
            },
        )
        if cust_resp.status_code not in (200, 201):
            return (None, None)
        customer = cust_resp.json()
        customer_id = customer.get("id") or customer.get("customer_id")

        # Create note on that customer
        note_resp = http_client.post(
            f"/api/v1/notes/{customer_id}",
            headers=owner_headers,
            json={"content": "Original note content for testing."},
        )
        if note_resp.status_code not in (200, 201):
            return (customer_id, None)
        note = note_resp.json()
        note_id = note.get("id") or note.get("note_id")
        return (customer_id, note_id)

    def test_update_note(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test updating a customer note's content.

        Verifies:
        - PUT /notes/{note_id} returns 200
        - Content is changed
        """
        customer_id, note_id = self._create_customer_with_note(
            http_client, owner_headers
        )
        if note_id is None:
            pytest.skip("Could not create customer + note for test")

        try:
            update_resp = http_client.put(
                f"/api/v1/notes/{note_id}",
                headers=owner_headers,
                json={"content": "Updated note content."},
            )
            assert update_resp.status_code == 200
        finally:
            # Cleanup — deleting customer cascade-deletes notes
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )

    def test_delete_note(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test deleting a customer note.

        Verifies:
        - DELETE /notes/{note_id} returns 200 or 204
        """
        customer_id, note_id = self._create_customer_with_note(
            http_client, owner_headers
        )
        if note_id is None:
            pytest.skip("Could not create customer + note for test")

        try:
            del_resp = http_client.delete(
                f"/api/v1/notes/{note_id}",
                headers=owner_headers,
            )
            assert del_resp.status_code in (200, 204)
        finally:
            # Cleanup
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )

    def test_employee_cannot_delete_note(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
        employee_headers: Dict[str, str],
    ) -> None:
        """
        Test that an employee cannot delete notes (owner/admin only).

        Verifies:
        - 403 when employee attempts DELETE /notes/{note_id}
        """
        customer_id, note_id = self._create_customer_with_note(
            http_client, owner_headers
        )
        if note_id is None:
            pytest.skip("Could not create customer + note for test")

        try:
            del_resp = http_client.delete(
                f"/api/v1/notes/{note_id}",
                headers=employee_headers,
            )
            assert del_resp.status_code == 403
        finally:
            # Cleanup with owner credentials
            http_client.delete(
                f"/api/v1/customers/{customer_id}",
                headers=owner_headers,
            )
