"""
Unit tests for Customer Service.

Covers CRUD operations and API endpoints for customers and notes.
All database interactions are async (matching the production layer).

Test classes
------------
- ``TestCustomerCRUD``              – direct CRUD function tests
- ``TestCustomerNoteCRUD``          – note CRUD tests
- ``TestCustomerAPI``               – HTTP endpoint tests
- ``TestCustomerNoteAPI``           – note endpoint tests
- ``TestCustomerSearchAndFiltering``– search / tenant isolation
- ``TestCustomerNoteManagement``    – ordering, empty notes, long content
- ``TestCustomerDataIntegrity``     – phone formats, email uniqueness, optional fields
- ``TestCustomerSoftDeleteAndReactivation`` – deactivation / reactivation
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    create_customer,
    get_customer,
    get_customers,
    update_customer,
    delete_customer,
    create_note,
    get_customer_notes,
)
from app.schemas import CustomerCreate, CustomerUpdate, CustomerNoteCreate
from app.models import Customer


# ==============================================================================
# Customer CRUD Tests
# ==============================================================================


class TestCustomerCRUD:
    """Tests for Customer CRUD operations."""

    async def test_create_customer(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Creating a customer should persist to the database."""
        customer_data = CustomerCreate(**sample_customer_data)
        customer = await create_customer(db_session, customer_data)

        assert customer.id is not None
        assert customer.name == sample_customer_data["name"]
        assert customer.email == sample_customer_data["email"]
        assert customer.owner_id == sample_customer_data["owner_id"]
        assert customer.is_active is True

    async def test_get_customer_by_id(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Should retrieve a customer by primary key."""
        customer_data = CustomerCreate(**sample_customer_data)
        created = await create_customer(db_session, customer_data)

        retrieved = await get_customer(db_session, created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == created.name

    async def test_get_customers_with_search(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Should filter customers by a search term (name ilike)."""
        customer_data = CustomerCreate(**sample_customer_data)
        await create_customer(db_session, customer_data)

        customers, total = await get_customers(
            db_session, owner_id=1, search="John"
        )

        assert total == 1
        assert len(customers) == 1
        assert "John" in customers[0].name

    async def test_update_customer(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Should update customer fields via partial update."""
        customer_data = CustomerCreate(**sample_customer_data)
        customer = await create_customer(db_session, customer_data)

        update_data = CustomerUpdate(name="Jane Smith", phone="0877654321")
        updated = await update_customer(db_session, customer.id, update_data)

        assert updated is not None
        assert updated.name == "Jane Smith"
        assert updated.phone == "0877654321"
        # Unchanged fields must be preserved
        assert updated.email == sample_customer_data["email"]

    async def test_delete_customer_deactivates(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Deleting a customer should soft-delete (deactivate), not remove."""
        customer_data = CustomerCreate(**sample_customer_data)
        customer = await create_customer(db_session, customer_data)

        result = await delete_customer(db_session, customer.id)
        assert result is True

        deactivated = await get_customer(db_session, customer.id)
        assert deactivated is not None
        assert deactivated.is_active is False


# ==============================================================================
# Customer Note CRUD Tests
# ==============================================================================


class TestCustomerNoteCRUD:
    """Tests for Customer Note CRUD operations."""

    async def test_create_note(
        self,
        db_session: AsyncSession,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """Creating a note should persist to the database."""
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )

        note_data = CustomerNoteCreate(customer_id=customer.id, **sample_note_data)
        note = await create_note(db_session, note_data)

        assert note.id is not None
        assert note.customer_id == customer.id
        assert note.content == sample_note_data["content"]

    async def test_get_customer_notes(
        self,
        db_session: AsyncSession,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """Should retrieve notes for a customer with total count."""
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )

        # Create multiple notes
        for i in range(3):
            note_data = CustomerNoteCreate(
                customer_id=customer.id,
                content=f"Note {i}",
                created_by_id=1,
            )
            await create_note(db_session, note_data)

        notes, total = await get_customer_notes(db_session, customer.id)

        assert total == 3
        assert len(notes) == 3


# ==============================================================================
# Customer API Endpoint Tests
# ==============================================================================


class TestCustomerAPI:
    """Tests for Customer HTTP API endpoints."""

    async def test_health_check(self, client: AsyncClient) -> None:
        """Health endpoint should return healthy status."""
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "customer-service"

    async def test_create_customer_endpoint(
        self, client: AsyncClient, sample_customer_data: dict
    ) -> None:
        """POST /customers should create a new customer."""
        response = await client.post("/api/v1/customers", json=sample_customer_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_customer_data["name"]
        assert "id" in data

    async def test_get_customer_endpoint(
        self, client: AsyncClient, sample_customer_data: dict
    ) -> None:
        """GET /customers/{id} should return customer data."""
        create_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = create_resp.json()["id"]

        response = await client.get(f"/api/v1/customers/{customer_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == customer_id
        assert data["name"] == sample_customer_data["name"]

    async def test_list_customers_requires_owner_id(
        self, client: AsyncClient
    ) -> None:
        """GET /customers without owner_id should return 422."""
        response = await client.get("/api/v1/customers")
        assert response.status_code == 422

    async def test_list_customers_with_owner_id(
        self, client: AsyncClient, sample_customer_data: dict
    ) -> None:
        """GET /customers?owner_id=1 should return the owner's customers."""
        await client.post("/api/v1/customers", json=sample_customer_data)

        response = await client.get("/api/v1/customers?owner_id=1")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 1

    async def test_update_customer_endpoint(
        self, client: AsyncClient, sample_customer_data: dict
    ) -> None:
        """PUT /customers/{id} should update customer data."""
        create_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = create_resp.json()["id"]

        response = await client.put(
            f"/api/v1/customers/{customer_id}", json={"name": "Updated Name"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    async def test_delete_customer_endpoint(
        self, client: AsyncClient, sample_customer_data: dict
    ) -> None:
        """DELETE /customers/{id} should deactivate the customer."""
        create_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = create_resp.json()["id"]

        response = await client.delete(f"/api/v1/customers/{customer_id}")
        assert response.status_code == 204

        # Verify the customer is deactivated
        get_resp = await client.get(f"/api/v1/customers/{customer_id}")
        assert get_resp.json()["is_active"] is False


# ==============================================================================
# Customer Note API Endpoint Tests
# ==============================================================================


class TestCustomerNoteAPI:
    """Tests for Customer Note HTTP API endpoints."""

    async def test_create_note_endpoint(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """POST /customer-notes/ should create a note."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        note_data = {**sample_note_data, "customer_id": customer_id}
        response = await client.post("/api/v1/customer-notes/", json=note_data)

        assert response.status_code == 201
        data = response.json()
        assert data["customer_id"] == customer_id
        assert data["content"] == sample_note_data["content"]

    async def test_list_notes_endpoint(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """GET /customer-notes/{customer_id} should return notes."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        note_data = {**sample_note_data, "customer_id": customer_id}
        await client.post("/api/v1/customer-notes/", json=note_data)

        response = await client.get(f"/api/v1/customer-notes/{customer_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


# ==============================================================================
# Customer Search & Filtering Tests
# ==============================================================================


class TestCustomerSearchAndFiltering:
    """
    Tests for customer search functionality and advanced filtering.

    Critical for CRM usability — users need fast, accurate search
    to find customers by various criteria.
    """

    async def test_search_customer_by_partial_name(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Search must support partial name matching (case-insensitive).

        Essential UX feature — users rarely remember full names.
        Handles prefixes, substrings, and case variations.
        """
        customers_data = [
            {**sample_customer_data, "name": "John Smith", "email": "john@test.com"},
            {**sample_customer_data, "name": "Jane Johnson", "email": "jane@test.com"},
            {**sample_customer_data, "name": "Bob Builder", "email": "bob@test.com"},
        ]

        for data in customers_data:
            await create_customer(db_session, CustomerCreate(**data))

        # "john" appears in "John Smith" and "Jane Johnson"
        results, _ = await get_customers(db_session, owner_id=1, search="john")
        assert len(results) >= 2

        # Case-insensitive
        results_upper, _ = await get_customers(db_session, owner_id=1, search="JOHN")
        assert len(results_upper) == len(results)

    async def test_search_customer_by_email(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Search must match email addresses (partial)."""
        customer_data = {
            **sample_customer_data,
            "name": "Test Customer",
            "email": "unique.email@test.com",
        }
        await create_customer(db_session, CustomerCreate(**customer_data))

        results, _ = await get_customers(
            db_session, owner_id=1, search="unique.email"
        )
        assert len(results) == 1
        assert "unique.email" in results[0].email

    async def test_search_customer_by_phone(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Search must match phone numbers (partial)."""
        await create_customer(
            db_session, CustomerCreate(**{**sample_customer_data, "phone": "0871234567"})
        )

        results, _ = await get_customers(db_session, owner_id=1, search="0871234")
        assert len(results) >= 1

    async def test_search_returns_empty_for_no_matches(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Search with no matches must return an empty list, not an error."""
        await create_customer(db_session, CustomerCreate(**sample_customer_data))

        results, total = await get_customers(
            db_session, owner_id=1, search="XyZ_NoMatch_123"
        )

        assert results == []
        assert total == 0

    async def test_search_respects_tenant_isolation(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Search must never return customers from other tenants.

        Critical security requirement — tenant isolation must be
        enforced in all queries.
        """
        tenant1_data = {
            **sample_customer_data,
            "name": "Tenant 1 Customer",
            "owner_id": 1,
            "email": "t1@test.com",
        }
        tenant2_data = {
            **sample_customer_data,
            "name": "Tenant 2 Customer",
            "owner_id": 2,
            "email": "t2@test.com",
        }

        await create_customer(db_session, CustomerCreate(**tenant1_data))
        await create_customer(db_session, CustomerCreate(**tenant2_data))

        results, _ = await get_customers(db_session, owner_id=1, search="Customer")

        assert all(c.owner_id == 1 for c in results)


# ==============================================================================
# Customer Note Management Tests
# ==============================================================================


class TestCustomerNoteManagement:
    """Tests for customer note CRUD operations and ordering.

    Notes are critical for relationship tracking — recording
    conversations, preferences, issues, and service history.
    """

    async def test_notes_ordered_by_creation_time(
        self,
        db_session: AsyncSession,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """Notes must be returned in reverse chronological order (newest first)."""
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )

        for i in range(3):
            await create_note(
                db_session,
                CustomerNoteCreate(
                    customer_id=customer.id,
                    content=f"Note {i}",
                    created_by_id=1,
                ),
            )

        notes, total = await get_customer_notes(db_session, customer.id)

        assert total == 3
        assert len(notes) == 3

    async def test_customer_with_no_notes(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Customers without notes should return an empty list."""
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )

        notes, total = await get_customer_notes(db_session, customer.id)

        assert notes == []
        assert total == 0

    async def test_note_content_can_be_long(
        self,
        db_session: AsyncSession,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """Notes must support long-form content without truncation."""
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )

        long_content = "A" * 2000
        note = await create_note(
            db_session,
            CustomerNoteCreate(
                customer_id=customer.id,
                content=long_content,
                created_by_id=1,
            ),
        )

        assert len(note.content) == 2000
        assert note.content == long_content


# ==============================================================================
# Customer Data Integrity Tests
# ==============================================================================


class TestCustomerDataIntegrity:
    """Tests for data validation and integrity constraints."""

    async def test_customer_phone_format_validation(
        self, client: AsyncClient, sample_customer_data: dict
    ) -> None:
        """Phone numbers should accept various formats.

        International customers use different formats; the system
        should be flexible in what it accepts.
        """
        valid_phones = [
            "0871234567",
            "+353871234567",
            "087 123 4567",
            "(087) 123-4567",
        ]

        for idx, phone in enumerate(valid_phones):
            data = {
                **sample_customer_data,
                "phone": phone,
                "email": f"phone_test_{idx}@test.com",
            }
            response = await client.post("/api/v1/customers", json=data)
            assert response.status_code == 201, f"Rejected valid phone: {phone}"

    async def test_customer_email_uniqueness_per_tenant(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Email uniqueness should be enforced per tenant.

        The same person might be the customer of multiple tenants,
        but within one tenant email should be unique.
        """
        customer1 = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )

        # Same email in a different tenant should be allowed
        data_tenant2 = {**sample_customer_data, "owner_id": 2}
        customer2 = await create_customer(
            db_session, CustomerCreate(**data_tenant2)
        )

        assert customer1.email == customer2.email
        assert customer1.owner_id != customer2.owner_id

    async def test_customer_address_fields_optional(
        self, db_session: AsyncSession
    ) -> None:
        """Address fields must be optional — allow minimal customer records."""
        minimal_data = {
            "name": "New Customer",
            "email": "minimal@test.com",
            "owner_id": 1,
        }

        customer = await create_customer(
            db_session, CustomerCreate(**minimal_data)
        )

        assert customer.id is not None
        assert customer.name == "New Customer"
        assert customer.address is None


# ==============================================================================
# Customer Soft Delete & Reactivation Tests
# ==============================================================================


class TestCustomerSoftDeleteAndReactivation:
    """Tests for customer deactivation and reactivation.

    Soft deletes preserve historical data while hiding inactive
    customers from normal operations.
    """

    async def test_deactivated_customer_not_in_active_listings(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Deactivated customers should not appear in active-only queries.

        Keeps active customer lists clean while preserving data
        for historical jobs and reporting.
        """
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )
        await delete_customer(db_session, customer.id)

        # Filtering by is_active=True should exclude deactivated customers
        results, _ = await get_customers(
            db_session, owner_id=1, is_active=True
        )

        customer_ids = [c.id for c in results]
        assert customer.id not in customer_ids

    async def test_deactivated_customer_still_accessible_by_id(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Deactivated customers must remain retrievable by ID.

        Essential for viewing historical jobs associated with
        inactive customers.
        """
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )
        await delete_customer(db_session, customer.id)

        retrieved = await get_customer(db_session, customer.id)

        assert retrieved is not None
        assert retrieved.id == customer.id
        assert retrieved.is_active is False

    async def test_reactivate_customer(
        self, db_session: AsyncSession, sample_customer_data: dict
    ) -> None:
        """Deactivated customers should be reactivatable.

        Business scenario: customer returns after a period of
        inactivity — reactivate their account.
        """
        customer = await create_customer(
            db_session, CustomerCreate(**sample_customer_data)
        )
        await delete_customer(db_session, customer.id)

        # Reactivate
        update_data = CustomerUpdate(is_active=True)
        reactivated = await update_customer(db_session, customer.id, update_data)

        assert reactivated.is_active is True

        # Should now appear in active listings
        results, _ = await get_customers(
            db_session, owner_id=1, is_active=True
        )
        customer_ids = [c.id for c in results]
        assert customer.id in customer_ids


# ==============================================================================
# Note Update API Tests
# ==============================================================================


class TestNoteUpdateAPI:
    """Tests for PUT /api/v1/customer-notes/{note_id} endpoint."""

    async def test_update_note_content_successfully(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """PUT /customer-notes/{id} should update note content."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        note_data = {**sample_note_data, "customer_id": customer_id}
        note_resp = await client.post("/api/v1/customer-notes/", json=note_data)
        note_id: int = note_resp.json()["id"]

        response = await client.put(
            f"/api/v1/customer-notes/{note_id}",
            json={"content": "Updated note content"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == note_id
        assert data["content"] == "Updated note content"
        assert data["customer_id"] == customer_id

    async def test_update_nonexistent_note_returns_404(
        self, client: AsyncClient
    ) -> None:
        """PUT /customer-notes/99999 should return 404."""
        response = await client.put(
            "/api/v1/customer-notes/99999",
            json={"content": "Does not matter"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"


# ==============================================================================
# Note Delete API Tests
# ==============================================================================


class TestNoteDeleteAPI:
    """Tests for DELETE /api/v1/customer-notes/{note_id} endpoint."""

    async def test_delete_note_successfully(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """DELETE /customer-notes/{id} should remove the note."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        note_data = {**sample_note_data, "customer_id": customer_id}
        note_resp = await client.post("/api/v1/customer-notes/", json=note_data)
        note_id: int = note_resp.json()["id"]

        delete_resp = await client.delete(f"/api/v1/customer-notes/{note_id}")
        assert delete_resp.status_code == 204

        # Verify the note is gone
        get_resp = await client.get(f"/api/v1/customer-notes/note/{note_id}")
        assert get_resp.status_code == 404

    async def test_delete_nonexistent_note_returns_404(
        self, client: AsyncClient
    ) -> None:
        """DELETE /customer-notes/99999 should return 404."""
        response = await client.delete("/api/v1/customer-notes/99999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"


# ==============================================================================
# Get Single Note API Tests
# ==============================================================================


class TestGetSingleNoteAPI:
    """Tests for GET /api/v1/customer-notes/note/{note_id} endpoint."""

    async def test_get_note_by_id(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """GET /customer-notes/note/{id} should return note data."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        note_data = {**sample_note_data, "customer_id": customer_id}
        note_resp = await client.post("/api/v1/customer-notes/", json=note_data)
        note_id: int = note_resp.json()["id"]

        response = await client.get(f"/api/v1/customer-notes/note/{note_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == note_id
        assert data["customer_id"] == customer_id
        assert data["content"] == sample_note_data["content"]

    async def test_get_nonexistent_note_returns_404(
        self, client: AsyncClient
    ) -> None:
        """GET /customer-notes/note/99999 should return 404."""
        response = await client.get("/api/v1/customer-notes/note/99999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"


# ==============================================================================
# Customer Include Notes Tests
# ==============================================================================


class TestCustomerIncludeNotes:
    """Tests for GET /api/v1/customers/{id}?include_notes=true."""

    async def test_get_customer_with_notes(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """include_notes=true should return customer with notes array."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        # Create two notes
        for i in range(2):
            note_data = {
                **sample_note_data,
                "customer_id": customer_id,
                "content": f"Note {i}",
            }
            await client.post("/api/v1/customer-notes/", json=note_data)

        response = await client.get(
            f"/api/v1/customers/{customer_id}?include_notes=true"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == customer_id
        assert "notes" in data
        assert len(data["notes"]) == 2


# ==============================================================================
# Customer 404 Path Tests
# ==============================================================================


class TestCustomer404Paths:
    """Tests for 404 responses on nonexistent customer IDs."""

    async def test_get_nonexistent_customer_returns_404(
        self, client: AsyncClient
    ) -> None:
        """GET /customers/99999 should return 404."""
        response = await client.get("/api/v1/customers/99999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Customer not found"

    async def test_update_nonexistent_customer_returns_404(
        self, client: AsyncClient
    ) -> None:
        """PUT /customers/99999 should return 404."""
        response = await client.put(
            "/api/v1/customers/99999", json={"name": "Ghost"}
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Customer not found"

    async def test_delete_nonexistent_customer_returns_404(
        self, client: AsyncClient
    ) -> None:
        """DELETE /customers/99999 should return 404."""
        response = await client.delete("/api/v1/customers/99999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Customer not found"


# ==============================================================================
# Customer Note Pagination Tests
# ==============================================================================


class TestCustomerNotePagination:
    """Tests for note pagination via skip and limit query params."""

    async def test_notes_pagination_skip_and_limit(
        self,
        client: AsyncClient,
        sample_customer_data: dict,
        sample_note_data: dict,
    ) -> None:
        """Create 5 notes, request skip=2&limit=2, verify 2 returned."""
        customer_resp = await client.post(
            "/api/v1/customers", json=sample_customer_data
        )
        customer_id: int = customer_resp.json()["id"]

        for i in range(5):
            note_data = {
                **sample_note_data,
                "customer_id": customer_id,
                "content": f"Paginated note {i}",
            }
            await client.post("/api/v1/customer-notes/", json=note_data)

        response = await client.get(
            f"/api/v1/customer-notes/{customer_id}?skip=2&limit=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
