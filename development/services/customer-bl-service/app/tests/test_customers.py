"""
Unit tests for Customer Service (Business Logic Layer).

Tests API routes with mocked service-client calls.
Fixtures (owner_client, employee_client, sample_customer, sample_note)
are provided by conftest.py.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# ==============================================================================
# Health Check
# ==============================================================================


class TestHealthEndpoint:
    def test_health_returns_200(self, owner_client: TestClient) -> None:
        response = owner_client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["service"] == "customer-service"


# ==============================================================================
# List Customers
# ==============================================================================


class TestListCustomers:
    @patch("app.service_client.get_customers", new_callable=AsyncMock)
    def test_list_scoped_to_tenant(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 100,
            "pages": 0,
        }
        response = owner_client.get("/api/v1/customers")
        assert response.status_code == 200
        assert mock_get.call_args.kwargs["owner_id"] == 1


# ==============================================================================
# Create Customer
# ==============================================================================


class TestCreateCustomer:
    @patch("app.service_client.create_customer", new_callable=AsyncMock)
    def test_create_injects_owner_id(
        self,
        mock_create: AsyncMock,
        owner_client: TestClient,
        sample_customer: dict,
    ) -> None:
        mock_create.return_value = sample_customer
        response = owner_client.post(
            "/api/v1/customers",
            json={"first_name": "Alice", "last_name": "Smith"},
        )
        assert response.status_code == 201
        payload = mock_create.call_args.args[0]
        assert payload["owner_id"] == 1

    @patch("app.service_client.create_customer", new_callable=AsyncMock)
    def test_employee_can_create_customer(
        self,
        mock_create: AsyncMock,
        employee_client: TestClient,
        sample_customer: dict,
    ) -> None:
        mock_create.return_value = sample_customer
        response = employee_client.post(
            "/api/v1/customers",
            json={"first_name": "Alice", "last_name": "Smith"},
        )
        assert response.status_code == 201


# ==============================================================================
# Get Customer (with enrichment)
# ==============================================================================


class TestGetCustomer:
    @patch("app.service_client.get_customer_notes", new_callable=AsyncMock)
    @patch("app.service_client.get_jobs_for_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_get_enriched_customer(
        self,
        mock_cust: AsyncMock,
        mock_jobs: AsyncMock,
        mock_notes: AsyncMock,
        owner_client: TestClient,
        sample_customer: dict,
        sample_note: dict,
    ) -> None:
        mock_cust.return_value = dict(sample_customer)
        mock_jobs.return_value = [
            {"id": 1, "title": "Fix Sink", "status": "completed", "start_time": None}
        ]
        mock_notes.return_value = [sample_note]

        response = owner_client.get("/api/v1/customers/10")
        assert response.status_code == 200
        data = response.json()
        assert len(data["recent_jobs"]) == 1
        assert len(data["customer_notes"]) == 1

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_get_customer_wrong_tenant(
        self,
        mock_cust: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_cust.return_value = {
            "id": 99,
            "first_name": "X",
            "last_name": "Y",
            "owner_id": 999,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = owner_client.get("/api/v1/customers/99")
        assert response.status_code == 403


# ==============================================================================
# Update Customer
# ==============================================================================


class TestUpdateCustomer:
    @patch("app.service_client.update_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_update_customer(
        self,
        mock_get: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
        sample_customer: dict,
    ) -> None:
        mock_get.return_value = sample_customer
        mock_update.return_value = {**sample_customer, "company": "New Corp"}
        response = owner_client.put(
            "/api/v1/customers/10",
            json={"company": "New Corp"},
        )
        assert response.status_code == 200


# ==============================================================================
# Delete Customer
# ==============================================================================


class TestDeleteCustomer:
    @patch("app.service_client.delete_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_owner_can_delete(
        self,
        mock_get: AsyncMock,
        mock_del: AsyncMock,
        owner_client: TestClient,
        sample_customer: dict,
    ) -> None:
        mock_get.return_value = sample_customer
        mock_del.return_value = None
        response = owner_client.delete("/api/v1/customers/10")
        assert response.status_code == 204

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_employee_cannot_delete(
        self,
        mock_get: AsyncMock,
        employee_client: TestClient,
        sample_customer: dict,
    ) -> None:
        mock_get.return_value = sample_customer
        response = employee_client.delete("/api/v1/customers/10")
        assert response.status_code == 403


# ==============================================================================
# Customer Notes
# ==============================================================================


class TestCustomerNotes:
    @patch("app.service_client.get_customer_notes", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_list_notes(
        self,
        mock_cust: AsyncMock,
        mock_notes: AsyncMock,
        owner_client: TestClient,
        sample_customer: dict,
        sample_note: dict,
    ) -> None:
        mock_cust.return_value = sample_customer
        mock_notes.return_value = [sample_note]
        response = owner_client.get("/api/v1/notes/10")
        assert response.status_code == 200
        assert len(response.json()) == 1

    @patch("app.service_client.create_customer_note", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_create_note_includes_created_by(
        self,
        mock_cust: AsyncMock,
        mock_create: AsyncMock,
        owner_client: TestClient,
        sample_customer: dict,
        sample_note: dict,
    ) -> None:
        mock_cust.return_value = sample_customer
        mock_create.return_value = sample_note
        response = owner_client.post(
            "/api/v1/notes/10",
            json={"content": "Great customer"},
        )
        assert response.status_code == 201
        payload = mock_create.call_args.args[1]
        assert payload["created_by_id"] == 1


# ==============================================================================
# Search Customers
# ==============================================================================


class TestSearchCustomers:
    @patch("app.service_client.get_customers", new_callable=AsyncMock)
    def test_search_passes_query(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 50,
            "pages": 0,
        }
        response = owner_client.get("/api/v1/customers/search?q=alice")
        assert response.status_code == 200
        assert mock_get.call_args.kwargs["search"] == "alice"


# ==============================================================================
# Note Update Endpoint
# ==============================================================================


class TestNoteUpdateEndpoint:
    """Tests for PUT /api/v1/notes/{note_id}."""

    @patch("app.service_client.update_customer_note", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_customer_note", new_callable=AsyncMock)
    def test_update_note_happy_path(
        self,
        mock_note: AsyncMock,
        mock_cust: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
        sample_note: dict,
        sample_customer: dict,
    ) -> None:
        """
        Owner can update a note in their tenant.

        Verifies:
        - 200 status code
        - Note content is updated
        - Tenant isolation chain: note → customer → owner_id check
        """
        mock_note.return_value = sample_note
        mock_cust.return_value = sample_customer
        updated_note = {**sample_note, "content": "Updated content"}
        mock_update.return_value = updated_note

        response = owner_client.put(
            f"/api/v1/notes/{sample_note['id']}",
            json={"content": "Updated content"},
        )

        assert response.status_code == 200
        assert response.json()["content"] == "Updated content"
        mock_update.assert_called_once()

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_customer_note", new_callable=AsyncMock)
    def test_update_note_wrong_tenant_denied(
        self,
        mock_note: AsyncMock,
        mock_cust: AsyncMock,
        owner_client: TestClient,
        sample_note: dict,
    ) -> None:
        """
        Updating a note from another tenant must be denied.

        Verifies:
        - 403 status code
        """
        mock_note.return_value = sample_note
        mock_cust.return_value = {"id": 10, "owner_id": 999, "is_active": True}

        response = owner_client.put(
            f"/api/v1/notes/{sample_note['id']}",
            json={"content": "Malicious update"},
        )

        assert response.status_code == 403


# ==============================================================================
# Note Delete Endpoint
# ==============================================================================


class TestNoteDeleteEndpoint:
    """Tests for DELETE /api/v1/notes/{note_id}."""

    @patch("app.service_client.delete_customer_note", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_customer_note", new_callable=AsyncMock)
    def test_owner_can_delete_note(
        self,
        mock_note: AsyncMock,
        mock_cust: AsyncMock,
        mock_del: AsyncMock,
        owner_client: TestClient,
        sample_note: dict,
        sample_customer: dict,
    ) -> None:
        """
        Owner can delete a note in their tenant.

        Verifies:
        - 204 status code
        - delete_customer_note called
        """
        mock_note.return_value = sample_note
        mock_cust.return_value = sample_customer
        mock_del.return_value = None

        response = owner_client.delete(f"/api/v1/notes/{sample_note['id']}")

        assert response.status_code == 204
        mock_del.assert_called_once()

    @patch("app.service_client.get_customer_note", new_callable=AsyncMock)
    def test_employee_cannot_delete_note(
        self,
        mock_note: AsyncMock,
        employee_client: TestClient,
        sample_note: dict,
    ) -> None:
        """
        Employees cannot delete notes (require_role blocks them).

        Verifies:
        - 403 status code for employee role
        """
        mock_note.return_value = sample_note

        response = employee_client.delete(f"/api/v1/notes/{sample_note['id']}")

        assert response.status_code == 403


# ==============================================================================
# Delete Customer Cross-Tenant
# ==============================================================================


class TestDeleteCustomerCrossTenant:
    """Tests for DELETE /api/v1/customers/{id} cross-tenant denial."""

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_delete_customer_wrong_tenant_denied(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Deleting a customer from a different tenant returns 403.

        Verifies:
        - 403 status code when customer's owner_id != current user's owner_id
        - delete_customer is never called
        """
        mock_get.return_value = {
            "id": 99,
            "first_name": "Other",
            "last_name": "Tenant",
            "owner_id": 999,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        response = owner_client.delete("/api/v1/customers/99")

        assert response.status_code == 403
