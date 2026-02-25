"""
Unit tests for User Service.

Covers CRUD operations and API endpoints for users and employees,
including password hashing, role assignment, and lifecycle management.

All database interactions are async (matching the production layer).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    create_user,
    get_user,
    get_user_by_email,
    update_user,
    delete_user,
    create_employee,
    get_employee_by_user_id,
    verify_password,
    get_password_hash,
)
from app.schemas import UserCreate, UserUpdate, EmployeeCreate
from app.models import User, UserRole


# ==============================================================================
# Password Hashing Tests  (sync — no DB required)
# ==============================================================================


class TestPasswordHashing:
    """Verify password hashing utilities."""

    def test_password_hash_creates_different_hash(self) -> None:
        password = "testpassword123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert len(hashed) > 0

    def test_password_verification_succeeds_with_correct_password(self) -> None:
        password = "testpassword123"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_password_verification_fails_with_wrong_password(self) -> None:
        hashed = get_password_hash("testpassword123")
        assert verify_password("wrongpassword", hashed) is False


# ==============================================================================
# User CRUD Tests
# ==============================================================================


class TestUserCRUD:
    """Tests for async User CRUD operations."""

    async def test_create_user(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        assert user.id is not None
        assert user.email == sample_user_data["email"]
        assert user.first_name == sample_user_data["first_name"]
        assert user.role == UserRole.EMPLOYEE
        assert user.is_active is True

    async def test_get_user_by_id(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        created = await create_user(db_session, UserCreate(**sample_user_data))
        retrieved = await get_user(db_session, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    async def test_get_user_by_email(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        created = await create_user(db_session, UserCreate(**sample_user_data))
        retrieved = await get_user_by_email(db_session, sample_user_data["email"])
        assert retrieved is not None
        assert retrieved.id == created.id

    async def test_get_nonexistent_user_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        assert await get_user(db_session, 99999) is None

    async def test_update_user(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        updated = await update_user(
            db_session, user.id, UserUpdate(first_name="Updated", phone="5555555555")
        )
        assert updated is not None
        assert updated.first_name == "Updated"
        assert updated.phone == "5555555555"
        assert updated.last_name == sample_user_data["last_name"]

    async def test_delete_user_deactivates(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        result = await delete_user(db_session, user.id)
        assert result is True
        deactivated = await get_user(db_session, user.id)
        assert deactivated is not None
        assert deactivated.is_active is False


# ==============================================================================
# Employee CRUD Tests
# ==============================================================================


class TestEmployeeCRUD:
    """Tests for async Employee CRUD operations."""

    async def test_create_employee(
        self,
        db_session: AsyncSession,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        owner = await create_user(db_session, UserCreate(**sample_owner_data))
        user_data = {**sample_user_data, "owner_id": owner.id}
        user = await create_user(db_session, UserCreate(**user_data))
        emp = await create_employee(
            db_session, EmployeeCreate(user_id=user.id, owner_id=owner.id, **sample_employee_data)
        )
        assert emp.id is not None
        assert emp.user_id == user.id
        assert emp.position == sample_employee_data["position"]

    async def test_get_employee_by_user_id(
        self,
        db_session: AsyncSession,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        owner = await create_user(db_session, UserCreate(**sample_owner_data))
        user_data = {**sample_user_data, "owner_id": owner.id}
        user = await create_user(db_session, UserCreate(**user_data))
        created = await create_employee(
            db_session, EmployeeCreate(user_id=user.id, owner_id=owner.id, **sample_employee_data)
        )
        retrieved = await get_employee_by_user_id(db_session, user.id)
        assert retrieved is not None
        assert retrieved.id == created.id


# ==============================================================================
# User API Endpoint Tests
# ==============================================================================


class TestUserAPI:
    """Tests for User HTTP API endpoints."""

    async def test_health_check(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "user-service"

    async def test_create_user_endpoint(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        response = await client.post("/api/v1/users", json=sample_user_data)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == sample_user_data["email"]
        assert "id" in data
        assert "password" not in data

    async def test_create_duplicate_user_fails(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        await client.post("/api/v1/users", json=sample_user_data)
        response = await client.post("/api/v1/users", json=sample_user_data)
        assert response.status_code == 409

    async def test_get_user_endpoint(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/users", json=sample_user_data)
        user_id: int = create_resp.json()["id"]
        response = await client.get(f"/api/v1/users/{user_id}")
        assert response.status_code == 200
        assert response.json()["id"] == user_id

    async def test_get_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/users/99999")
        assert response.status_code == 404

    async def test_update_user_endpoint(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/users", json=sample_user_data)
        user_id: int = create_resp.json()["id"]
        response = await client.put(
            f"/api/v1/users/{user_id}", json={"first_name": "UpdatedName"}
        )
        assert response.status_code == 200
        assert response.json()["first_name"] == "UpdatedName"

    async def test_delete_user_endpoint(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/users", json=sample_user_data)
        user_id: int = create_resp.json()["id"]
        response = await client.delete(f"/api/v1/users/{user_id}")
        assert response.status_code == 204
        get_resp = await client.get(f"/api/v1/users/{user_id}")
        assert get_resp.json()["is_active"] is False

    async def test_list_users_endpoint(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        await client.post("/api/v1/users", json=sample_user_data)
        response = await client.get("/api/v1/users")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1


# ==============================================================================
# Employee API Endpoint Tests
# ==============================================================================


class TestEmployeeAPI:
    """Tests for Employee HTTP API endpoints."""

    async def test_create_employee_endpoint(
        self,
        client: AsyncClient,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id: int = owner_resp.json()["id"]
        user_resp = await client.post("/api/v1/users", json={**sample_user_data, "owner_id": owner_id})
        user_id: int = user_resp.json()["id"]
        response = await client.post(
            "/api/v1/employees",
            json={**sample_employee_data, "user_id": user_id, "owner_id": owner_id},
        )
        assert response.status_code == 201
        assert response.json()["user_id"] == user_id

    async def test_get_employee_endpoint(
        self,
        client: AsyncClient,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id: int = owner_resp.json()["id"]
        user_resp = await client.post("/api/v1/users", json={**sample_user_data, "owner_id": owner_id})
        user_id: int = user_resp.json()["id"]
        emp_resp = await client.post(
            "/api/v1/employees",
            json={**sample_employee_data, "user_id": user_id, "owner_id": owner_id},
        )
        emp_id: int = emp_resp.json()["id"]
        response = await client.get(f"/api/v1/employees/{emp_id}")
        assert response.status_code == 200
        assert response.json()["id"] == emp_id


# ==============================================================================
# Email Validation Tests
# ==============================================================================


class TestEmailValidationAndDuplicates:
    """Tests for email format validation."""

    async def test_invalid_email_format_rejected(
        self, client: AsyncClient
    ) -> None:
        invalid_emails = [
            "notanemail",
            "@nodomain.com",
            "user@",
            "user @domain.com",
            "",
        ]
        for email in invalid_emails:
            response = await client.post(
                "/api/v1/users",
                json={
                    "email": email,
                    "password": "password123",
                    "first_name": "Test",
                    "last_name": "User",
                    "role": "employee",
                    "owner_id": 1,
                },
            )
            assert response.status_code == 422, f"Accepted invalid email: {email}"


# ==============================================================================
# User Roles & Permissions Tests
# ==============================================================================


class TestUserRolesAndPermissions:
    """Tests for role assignment and validation."""

    async def test_create_owner_without_owner_id(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        owner_data = {**sample_user_data, "role": "owner", "owner_id": None}
        user = await create_user(db_session, UserCreate(**owner_data))
        assert user.role == UserRole.OWNER
        assert user.owner_id is None

    async def test_user_role_cannot_be_invalid(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/users",
            json={
                "email": "test@test.com",
                "password": "password123",
                "first_name": "Test",
                "last_name": "User",
                "role": "hacker",
                "owner_id": 1,
            },
        )
        assert response.status_code == 422


# ==============================================================================
# User Lifecycle Management Tests
# ==============================================================================


class TestUserLifecycleManagement:
    """Tests for user activation/deactivation lifecycle."""

    async def test_newly_created_user_is_active(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        assert user.is_active is True

    async def test_deactivated_user_retrieval(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        await delete_user(db_session, user.id)
        retrieved = await get_user(db_session, user.id)
        assert retrieved is not None
        assert retrieved.is_active is False

    async def test_reactivate_deactivated_user(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        await delete_user(db_session, user.id)
        reactivated = await update_user(
            db_session, user.id, UserUpdate(is_active=True)
        )
        assert reactivated.is_active is True


# ==============================================================================
# Employee–User Relationship Tests
# ==============================================================================


class TestEmployeeUserRelationship:
    """Tests for Employee ↔ User integrity constraints."""

    async def test_employee_cannot_exist_without_user(
        self, client: AsyncClient, sample_employee_data: dict
    ) -> None:
        response = await client.post(
            "/api/v1/employees",
            json={**sample_employee_data, "user_id": 99999, "owner_id": 99999},
        )
        assert response.status_code == 404

    async def test_one_user_can_have_only_one_employee_record(
        self,
        client: AsyncClient,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id: int = owner_resp.json()["id"]
        user_resp = await client.post("/api/v1/users", json={**sample_user_data, "owner_id": owner_id})
        user_id: int = user_resp.json()["id"]
        emp_data = {**sample_employee_data, "user_id": user_id, "owner_id": owner_id}
        resp1 = await client.post("/api/v1/employees", json=emp_data)
        assert resp1.status_code == 201
        resp2 = await client.post("/api/v1/employees", json=emp_data)
        assert resp2.status_code == 409

    async def test_employee_data_is_optional_for_users(
        self, db_session: AsyncSession, sample_user_data: dict
    ) -> None:
        user = await create_user(db_session, UserCreate(**sample_user_data))
        emp = await get_employee_by_user_id(db_session, user.id)
        assert emp is None


# ==============================================================================
# User Query & Pagination Tests
# ==============================================================================


class TestUserQueryAndPagination:
    """Tests for listing, filtering, and pagination."""

    async def test_list_users_with_pagination(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        for i in range(5):
            await client.post(
                "/api/v1/users",
                json={**sample_user_data, "email": f"user{i}@test.com"},
            )
        response = await client.get("/api/v1/users?skip=0&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 3
        assert data["total"] >= 5

    async def test_list_users_by_owner_id(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        await client.post(
            "/api/v1/users",
            json={**sample_user_data, "owner_id": 1, "email": "u1@test.com"},
        )
        await client.post(
            "/api/v1/users",
            json={**sample_user_data, "owner_id": 2, "email": "u2@test.com"},
        )
        response = await client.get("/api/v1/users?owner_id=1")
        assert response.status_code == 200
        for user in response.json()["items"]:
            assert user["owner_id"] == 1

    async def test_list_users_with_role_filter(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        await client.post(
            "/api/v1/users",
            json={**sample_user_data, "role": "employee", "email": "emp@test.com"},
        )
        await client.post(
            "/api/v1/users",
            json={**sample_user_data, "role": "admin", "email": "admin@test.com"},
        )
        response = await client.get("/api/v1/users?role=employee")
        assert response.status_code == 200
        for user in response.json()["items"]:
            assert user["role"] == "employee"


# ==============================================================================
# Company CRUD Tests
# ==============================================================================


class TestCompanyCRUD:
    """Tests for async Company CRUD operations."""

    async def test_create_company(self, db_session: AsyncSession) -> None:
        """Test creating a company via CRUD layer."""
        from app.crud import create_company
        from app.schemas import CompanyCreate

        company = await create_company(
            db_session,
            CompanyCreate(name="Acme Plumbing", phone="0851234567", email="info@acme.ie"),
        )
        assert company.id is not None
        assert company.name == "Acme Plumbing"
        assert company.phone == "0851234567"
        assert company.is_active is True

    async def test_get_company(self, db_session: AsyncSession) -> None:
        """Test retrieving a company by ID via CRUD layer."""
        from app.crud import create_company, get_company
        from app.schemas import CompanyCreate

        created = await create_company(
            db_session, CompanyCreate(name="Test Co")
        )
        retrieved = await get_company(db_session, created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Test Co"

    async def test_get_nonexistent_company_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        """Test that fetching a non-existent company returns None."""
        from app.crud import get_company

        assert await get_company(db_session, 99999) is None

    async def test_update_company(self, db_session: AsyncSession) -> None:
        """Test updating company fields via CRUD layer."""
        from app.crud import create_company, update_company
        from app.schemas import CompanyCreate, CompanyUpdate

        company = await create_company(
            db_session, CompanyCreate(name="Old Name", phone="111")
        )
        updated = await update_company(
            db_session, company.id, CompanyUpdate(name="New Name", phone="222")
        )
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.phone == "222"

    async def test_update_nonexistent_company_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        """Test that updating a non-existent company returns None."""
        from app.crud import update_company
        from app.schemas import CompanyUpdate

        assert await update_company(db_session, 99999, CompanyUpdate(name="X")) is None


# ==============================================================================
# Company API Tests
# ==============================================================================


class TestCompanyAPI:
    """Tests for Company HTTP API endpoints."""

    async def test_create_company_endpoint(self, client: AsyncClient) -> None:
        """Test POST /api/v1/companies creates a company."""
        response = await client.post(
            "/api/v1/companies",
            json={"name": "API Plumbing Ltd", "phone": "0861234567"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "API Plumbing Ltd"
        assert "id" in data
        assert data["is_active"] is True

    async def test_get_company_endpoint(self, client: AsyncClient) -> None:
        """Test GET /api/v1/companies/{id} returns the company."""
        create_resp = await client.post(
            "/api/v1/companies", json={"name": "Get Me Ltd"}
        )
        company_id: int = create_resp.json()["id"]
        response = await client.get(f"/api/v1/companies/{company_id}")
        assert response.status_code == 200
        assert response.json()["id"] == company_id
        assert response.json()["name"] == "Get Me Ltd"

    async def test_get_nonexistent_company_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/companies/{id} returns 404 for missing company."""
        response = await client.get("/api/v1/companies/99999")
        assert response.status_code == 404

    async def test_update_company_endpoint(self, client: AsyncClient) -> None:
        """Test PUT /api/v1/companies/{id} updates company fields."""
        create_resp = await client.post(
            "/api/v1/companies", json={"name": "Before Update"}
        )
        company_id: int = create_resp.json()["id"]
        response = await client.put(
            f"/api/v1/companies/{company_id}",
            json={"name": "After Update", "eircode": "D01AB12"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "After Update"
        assert response.json()["eircode"] == "D01AB12"

    async def test_update_nonexistent_company_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test PUT /api/v1/companies/{id} returns 404 for missing company."""
        response = await client.put(
            "/api/v1/companies/99999", json={"name": "Nope"}
        )
        assert response.status_code == 404


# ==============================================================================
# Internal Authentication Tests
# ==============================================================================


class TestInternalAuthentication:
    """Tests for POST /api/v1/internal/authenticate (service-to-service)."""

    async def test_authenticate_correct_credentials(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        """Test that correct email + password returns authenticated=true."""
        await client.post("/api/v1/users", json=sample_user_data)
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["email"] == sample_user_data["email"]
        assert data["user_id"] is not None
        assert data["role"] == sample_user_data["role"]

    async def test_authenticate_wrong_password(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        """Test that wrong password returns authenticated=false."""
        await client.post("/api/v1/users", json=sample_user_data)
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={
                "email": sample_user_data["email"],
                "password": "completelyWrongPassword!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user_id"] is None

    async def test_authenticate_nonexistent_email(
        self, client: AsyncClient
    ) -> None:
        """Test that a non-existent email returns authenticated=false."""
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={"email": "nobody@nowhere.com", "password": "irrelevant"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False

    async def test_authenticate_deactivated_user(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        """Test that a deactivated user cannot authenticate."""
        create_resp = await client.post("/api/v1/users", json=sample_user_data)
        user_id: int = create_resp.json()["id"]
        await client.delete(f"/api/v1/users/{user_id}")
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={
                "email": sample_user_data["email"],
                "password": sample_user_data["password"],
            },
        )
        assert response.status_code == 200
        assert response.json()["authenticated"] is False


# ==============================================================================
# User API 404 Path Tests
# ==============================================================================


class TestUserAPI404Paths:
    """Tests for 404 responses on nonexistent user resources."""

    async def test_get_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/users/{id} returns 404 for missing user."""
        response = await client.get("/api/v1/users/99999")
        assert response.status_code == 404

    async def test_put_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test PUT /api/v1/users/{id} returns 404 for missing user."""
        response = await client.put(
            "/api/v1/users/99999", json={"first_name": "Ghost"}
        )
        assert response.status_code == 404

    async def test_delete_nonexistent_user_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test DELETE /api/v1/users/{id} returns 404 for missing user."""
        response = await client.delete("/api/v1/users/99999")
        assert response.status_code == 404

    async def test_get_nonexistent_employee_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/employees/{id} returns 404 for missing employee."""
        response = await client.get("/api/v1/employees/99999")
        assert response.status_code == 404

    async def test_put_nonexistent_employee_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test PUT /api/v1/employees/{id} returns 404 for missing employee."""
        response = await client.put(
            "/api/v1/employees/99999", json={"position": "Ghost"}
        )
        assert response.status_code == 404


# ==============================================================================
# Organization API Tests
# ==============================================================================


class TestOrganizationAPI:
    """Tests for Organization HTTP API endpoints."""

    async def test_create_organization(self, client: AsyncClient) -> None:
        """Test POST /api/v1/organizations creates an organization."""
        response = await client.post(
            "/api/v1/organizations",
            json={
                "name": "Test Org",
                "slug": "test-org",
                "billing_email": "billing@testorg.com",
                "billing_plan": "starter",
                "max_users": 10,
                "max_customers": 100,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Org"
        assert data["slug"] == "test-org"
        assert data["billing_plan"] == "starter"
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_organization_duplicate_slug_fails(
        self, client: AsyncClient
    ) -> None:
        """Test that creating two orgs with the same slug returns 409."""
        payload = {"name": "Org One", "slug": "dupe-slug"}
        await client.post("/api/v1/organizations", json=payload)
        response = await client.post(
            "/api/v1/organizations", json={"name": "Org Two", "slug": "dupe-slug"}
        )
        assert response.status_code == 409

    async def test_list_organizations(self, client: AsyncClient) -> None:
        """Test GET /api/v1/organizations returns a paginated list."""
        await client.post(
            "/api/v1/organizations",
            json={"name": "List Org", "slug": "list-org"},
        )
        response = await client.get("/api/v1/organizations")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_get_organization_by_id(self, client: AsyncClient) -> None:
        """Test GET /api/v1/organizations/{id} returns the organization."""
        create_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Get Org", "slug": "get-org"},
        )
        org_id: int = create_resp.json()["id"]
        response = await client.get(f"/api/v1/organizations/{org_id}")
        assert response.status_code == 200
        assert response.json()["id"] == org_id
        assert response.json()["name"] == "Get Org"

    async def test_get_nonexistent_organization_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/organizations/{id} returns 404 for missing org."""
        response = await client.get("/api/v1/organizations/99999")
        assert response.status_code == 404

    async def test_update_organization(self, client: AsyncClient) -> None:
        """Test PUT /api/v1/organizations/{id} updates organization fields."""
        create_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Before", "slug": "update-org"},
        )
        org_id: int = create_resp.json()["id"]
        response = await client.put(
            f"/api/v1/organizations/{org_id}",
            json={"name": "After", "billing_plan": "professional"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "After"
        assert response.json()["billing_plan"] == "professional"

    async def test_update_nonexistent_organization_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test PUT /api/v1/organizations/{id} returns 404 for missing org."""
        response = await client.put(
            "/api/v1/organizations/99999", json={"name": "Nope"}
        )
        assert response.status_code == 404

    async def test_suspend_organization(self, client: AsyncClient) -> None:
        """Test POST /api/v1/organizations/{id}/suspend deactivates the org."""
        create_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Suspend Me", "slug": "suspend-org"},
        )
        org_id: int = create_resp.json()["id"]
        response = await client.post(
            f"/api/v1/organizations/{org_id}/suspend?reason=non-payment"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False
        assert data["suspended_reason"] == "non-payment"
        assert data["suspended_at"] is not None

    async def test_suspend_nonexistent_organization_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test POST /api/v1/organizations/{id}/suspend returns 404."""
        response = await client.post("/api/v1/organizations/99999/suspend")
        assert response.status_code == 404

    async def test_unsuspend_organization(self, client: AsyncClient) -> None:
        """Test POST /api/v1/organizations/{id}/unsuspend reactivates the org."""
        create_resp = await client.post(
            "/api/v1/organizations",
            json={"name": "Unsuspend Me", "slug": "unsuspend-org"},
        )
        org_id: int = create_resp.json()["id"]
        await client.post(f"/api/v1/organizations/{org_id}/suspend")
        response = await client.post(
            f"/api/v1/organizations/{org_id}/unsuspend"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True
        assert data["suspended_at"] is None
        assert data["suspended_reason"] is None

    async def test_unsuspend_nonexistent_organization_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test POST /api/v1/organizations/{id}/unsuspend returns 404."""
        response = await client.post("/api/v1/organizations/99999/unsuspend")
        assert response.status_code == 404


# ==============================================================================
# Audit Log API Tests
# ==============================================================================


class TestAuditLogAPI:
    """Tests for Audit Log HTTP API endpoints."""

    async def test_create_audit_log(self, client: AsyncClient) -> None:
        """Test POST /api/v1/audit-logs creates an entry."""
        response = await client.post(
            "/api/v1/audit-logs",
            json={
                "actor_id": 1,
                "actor_email": "admin@test.com",
                "actor_role": "superadmin",
                "action": "org.create",
                "resource_type": "organization",
                "resource_id": "42",
                "details": {"name": "New Org"},
                "ip_address": "127.0.0.1",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["action"] == "org.create"
        assert data["actor_id"] == 1
        assert data["resource_type"] == "organization"
        assert "id" in data
        assert "timestamp" in data

    async def test_list_audit_logs(self, client: AsyncClient) -> None:
        """Test GET /api/v1/audit-logs returns a paginated list."""
        await client.post(
            "/api/v1/audit-logs",
            json={"actor_id": 1, "action": "test.action"},
        )
        response = await client.get("/api/v1/audit-logs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1
        assert data["items"][0]["action"] == "test.action"

    async def test_list_audit_logs_filter_by_action(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/audit-logs?action=... filters results."""
        await client.post(
            "/api/v1/audit-logs",
            json={"actor_id": 1, "action": "org.suspend"},
        )
        await client.post(
            "/api/v1/audit-logs",
            json={"actor_id": 1, "action": "org.create"},
        )
        response = await client.get("/api/v1/audit-logs?action=org.suspend")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["action"] == "org.suspend"

    async def test_list_audit_logs_empty(self, client: AsyncClient) -> None:
        """Test GET /api/v1/audit-logs returns empty list when no logs."""
        response = await client.get("/api/v1/audit-logs")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0


# ==============================================================================
# Platform Settings API Tests
# ==============================================================================


class TestPlatformSettingsAPI:
    """Tests for Platform Settings HTTP API endpoints."""

    async def test_list_platform_settings_empty(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/platform-settings returns empty list initially."""
        response = await client.get("/api/v1/platform-settings")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_upsert_creates_new_setting(
        self, client: AsyncClient
    ) -> None:
        """Test PUT /api/v1/platform-settings/{key} creates a new setting."""
        response = await client.put(
            "/api/v1/platform-settings/maintenance_mode",
            json={"value": {"enabled": False}, "description": "Toggle maintenance"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "maintenance_mode"
        assert data["value"] == {"enabled": False}
        assert data["description"] == "Toggle maintenance"

    async def test_upsert_updates_existing_setting(
        self, client: AsyncClient
    ) -> None:
        """Test PUT /api/v1/platform-settings/{key} updates existing value."""
        await client.put(
            "/api/v1/platform-settings/rate_limit",
            json={"value": {"max_rps": 100}},
        )
        response = await client.put(
            "/api/v1/platform-settings/rate_limit",
            json={"value": {"max_rps": 200}},
        )
        assert response.status_code == 200
        assert response.json()["value"] == {"max_rps": 200}

    async def test_get_platform_setting_by_key(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/platform-settings/{key} returns the setting."""
        await client.put(
            "/api/v1/platform-settings/feature_flag",
            json={"value": {"dark_mode": True}},
        )
        response = await client.get("/api/v1/platform-settings/feature_flag")
        assert response.status_code == 200
        assert response.json()["key"] == "feature_flag"
        assert response.json()["value"] == {"dark_mode": True}

    async def test_get_nonexistent_platform_setting_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/platform-settings/{key} returns 404 for missing key."""
        response = await client.get("/api/v1/platform-settings/does_not_exist")
        assert response.status_code == 404

    async def test_list_platform_settings_after_creation(
        self, client: AsyncClient
    ) -> None:
        """Test GET /api/v1/platform-settings returns all created settings."""
        await client.put(
            "/api/v1/platform-settings/setting_a",
            json={"value": {"a": 1}},
        )
        await client.put(
            "/api/v1/platform-settings/setting_b",
            json={"value": {"b": 2}},
        )
        response = await client.get("/api/v1/platform-settings")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        keys = [s["key"] for s in data["items"]]
        assert "setting_a" in keys
        assert "setting_b" in keys


# ==============================================================================
# Additional Route Coverage Tests
# ==============================================================================


class TestUserListPagePerPage:
    """Tests for page/per_page pagination style on GET /api/v1/users."""

    async def test_page_per_page_pagination(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        """Test page/per_page overrides skip/limit."""
        for i in range(5):
            await client.post(
                "/api/v1/users",
                json={**sample_user_data, "email": f"page{i}@test.com"},
            )
        response = await client.get("/api/v1/users?page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["page"] == 1
        assert data["per_page"] == 2
        assert data["pages"] >= 1

    async def test_page_two(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        """Test navigating to page 2."""
        for i in range(4):
            await client.post(
                "/api/v1/users",
                json={**sample_user_data, "email": f"pg2_{i}@test.com"},
            )
        response = await client.get("/api/v1/users?page=2&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2

    async def test_filter_is_active(
        self, client: AsyncClient, sample_user_data: dict
    ) -> None:
        """Test is_active filter on user list."""
        resp = await client.post(
            "/api/v1/users",
            json={**sample_user_data, "email": "active_filter@test.com"},
        )
        user_id = resp.json()["id"]
        await client.delete(f"/api/v1/users/{user_id}")  # deactivate
        response = await client.get("/api/v1/users?is_active=false")
        assert response.status_code == 200
        for user in response.json()["items"]:
            assert user["is_active"] is False


class TestEmployeeUpdateEndpoint:
    """Tests for PUT /api/v1/employees/{id} endpoint."""

    async def test_update_employee_position(
        self,
        client: AsyncClient,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        """Test updating employee position via API."""
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id = owner_resp.json()["id"]
        user_resp = await client.post(
            "/api/v1/users",
            json={**sample_user_data, "owner_id": owner_id},
        )
        user_id = user_resp.json()["id"]
        emp_resp = await client.post(
            "/api/v1/employees",
            json={**sample_employee_data, "user_id": user_id, "owner_id": owner_id},
        )
        emp_id = emp_resp.json()["id"]
        response = await client.put(
            f"/api/v1/employees/{emp_id}",
            json={"position": "Senior Plumber"},
        )
        assert response.status_code == 200
        assert response.json()["position"] == "Senior Plumber"


class TestEmployeesByOwnerEndpoint:
    """Tests for GET /api/v1/users/{user_id}/employees endpoint."""

    async def test_list_employees_by_owner(
        self,
        client: AsyncClient,
        sample_owner_data: dict,
        sample_user_data: dict,
        sample_employee_data: dict,
    ) -> None:
        """Test listing employees under a specific owner."""
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id = owner_resp.json()["id"]
        user_resp = await client.post(
            "/api/v1/users",
            json={**sample_user_data, "owner_id": owner_id},
        )
        user_id = user_resp.json()["id"]
        await client.post(
            "/api/v1/employees",
            json={**sample_employee_data, "user_id": user_id, "owner_id": owner_id},
        )
        response = await client.get(f"/api/v1/users/{owner_id}/employees")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["owner_id"] == owner_id

    async def test_list_employees_empty_owner(
        self, client: AsyncClient, sample_owner_data: dict
    ) -> None:
        """Test listing employees for owner with no employees returns empty."""
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id = owner_resp.json()["id"]
        response = await client.get(f"/api/v1/users/{owner_id}/employees")
        assert response.status_code == 200
        assert response.json() == []


class TestInternalAuthEdgeCases:
    """Test additional paths in /internal/authenticate endpoint."""

    async def test_authenticate_owner_returns_self_as_owner_id(
        self, client: AsyncClient
    ) -> None:
        """Owner users have owner_id = their own id."""
        owner_data = {
            "email": "owner_auth@test.com",
            "password": "Str0ng!Pass",
            "first_name": "Own",
            "last_name": "Er",
            "role": "owner",
        }
        await client.post("/api/v1/users", json=owner_data)
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={"email": "owner_auth@test.com", "password": "Str0ng!Pass"},
        )
        data = response.json()
        assert data["authenticated"] is True
        assert data["owner_id"] == data["user_id"]

    async def test_authenticate_employee_returns_actual_owner_id(
        self,
        client: AsyncClient,
        sample_owner_data: dict,
        sample_employee_data: dict,
    ) -> None:
        """Employee users have owner_id = their employer's id."""
        owner_resp = await client.post("/api/v1/users", json=sample_owner_data)
        owner_id = owner_resp.json()["id"]
        emp_user_data = {
            "email": "emp_auth@test.com",
            "password": "Str0ng!Pass",
            "first_name": "Emp",
            "last_name": "Loyee",
            "role": "employee",
            "owner_id": owner_id,
        }
        await client.post("/api/v1/users", json=emp_user_data)
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={"email": "emp_auth@test.com", "password": "Str0ng!Pass"},
        )
        data = response.json()
        assert data["authenticated"] is True
        assert data["owner_id"] == owner_id

    async def test_authenticate_superadmin_returns_none_owner_id(
        self, client: AsyncClient
    ) -> None:
        """Superadmin users have owner_id = None."""
        sa_data = {
            "email": "sa_auth@test.com",
            "password": "Super!Admin1",
            "first_name": "Super",
            "last_name": "Admin",
            "role": "superadmin",
        }
        await client.post("/api/v1/users", json=sa_data)
        response = await client.post(
            "/api/v1/internal/authenticate",
            json={"email": "sa_auth@test.com", "password": "Super!Admin1"},
        )
        data = response.json()
        assert data["authenticated"] is True
        assert data["owner_id"] is None


class TestCompanyAPI404:
    """Tests for company 404 paths."""

    async def test_get_nonexistent_company_returns_404(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/companies/99999")
        assert response.status_code == 404

    async def test_update_nonexistent_company_returns_404(
        self, client: AsyncClient
    ) -> None:
        response = await client.put(
            "/api/v1/companies/99999", json={"name": "NoCompany"}
        )
        assert response.status_code == 404


class TestAuditLogPagination:
    """Tests for audit log pagination params."""

    async def test_audit_logs_pagination(self, client: AsyncClient) -> None:
        """Test page/per_page on audit logs."""
        for i in range(5):
            await client.post(
                "/api/v1/audit-logs",
                json={"actor_id": 1, "action": f"test.action.{i}"},
            )
        response = await client.get("/api/v1/audit-logs?page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["total"] >= 5

    async def test_audit_logs_filter_by_actor_id(
        self, client: AsyncClient
    ) -> None:
        """Test actor_id filter on audit logs."""
        await client.post(
            "/api/v1/audit-logs",
            json={"actor_id": 42, "action": "user42.action"},
        )
        await client.post(
            "/api/v1/audit-logs",
            json={"actor_id": 99, "action": "user99.action"},
        )
        response = await client.get("/api/v1/audit-logs?actor_id=42")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["actor_id"] == 42


class TestOrganizationPagination:
    """Tests for organization list pagination."""

    async def test_organization_list_page_per_page(
        self, client: AsyncClient
    ) -> None:
        """Test page/per_page on organization list."""
        for i in range(3):
            await client.post(
                "/api/v1/organizations",
                json={"name": f"PgOrg{i}", "slug": f"pg-org-{i}"},
            )
        response = await client.get("/api/v1/organizations?page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["total"] >= 3
