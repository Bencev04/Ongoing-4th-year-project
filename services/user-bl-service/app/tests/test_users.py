"""
Unit tests for User Service (Business Logic Layer).

Tests the API routes with mocked service-client calls to
user-db-access-service and auth-service.
Fixtures (owner_client, employee_client, unauthenticated_client,
sample_user_response, sample_user_list) are provided by conftest.py.
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


# ==============================================================================
# Health Check
# ==============================================================================

class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_returns_200(self, owner_client: TestClient) -> None:
        response = owner_client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "user-service"


# ==============================================================================
# List Users
# ==============================================================================

class TestListUsers:
    """Tests for GET /api/v1/users."""

    @patch("app.service_client.get_users", new_callable=AsyncMock)
    def test_list_users_returns_tenant_scoped_results(
        self, mock_get: AsyncMock, owner_client: TestClient, sample_user_list: dict,
    ) -> None:
        mock_get.return_value = sample_user_list
        response = owner_client.get("/api/v1/users")

        assert response.status_code == 200
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["owner_id"] == 1  # tenant isolation


# ==============================================================================
# Create User
# ==============================================================================

class TestCreateUser:
    """Tests for POST /api/v1/users."""

    @patch("app.service_client.create_user", new_callable=AsyncMock)
    def test_owner_can_create_user(
        self, mock_create: AsyncMock, owner_client: TestClient, sample_user_response: dict,
    ) -> None:
        mock_create.return_value = sample_user_response
        response = owner_client.post(
            "/api/v1/users",
            json={
                "email": "new@test.com",
                "password": "password123",
                "first_name": "New",
                "last_name": "User",
            },
        )
        assert response.status_code == 201
        # Verify owner_id was injected
        payload = mock_create.call_args.args[0]
        assert payload["owner_id"] == 1

    @patch("app.service_client.create_user", new_callable=AsyncMock)
    def test_employee_cannot_create_user(
        self, mock_create: AsyncMock, employee_client: TestClient,
    ) -> None:
        response = employee_client.post(
            "/api/v1/users",
            json={
                "email": "new@test.com",
                "password": "password123",
                "first_name": "New",
                "last_name": "User",
            },
        )
        assert response.status_code == 403
        mock_create.assert_not_called()


# ==============================================================================
# Get User
# ==============================================================================

class TestGetUser:
    """Tests for GET /api/v1/users/{id}."""

    @patch("app.service_client.get_user", new_callable=AsyncMock)
    def test_get_user_in_same_tenant(
        self, mock_get: AsyncMock, owner_client: TestClient, sample_user_response: dict,
    ) -> None:
        mock_get.return_value = sample_user_response
        response = owner_client.get("/api/v1/users/10")

        assert response.status_code == 200
        assert response.json()["id"] == 10

    @patch("app.service_client.get_user", new_callable=AsyncMock)
    def test_get_user_in_different_tenant_denied(
        self, mock_get: AsyncMock, owner_client: TestClient,
    ) -> None:
        mock_get.return_value = {
            **{
                "id": 99, "email": "other@test.com", "first_name": "Other",
                "last_name": "User", "role": "employee", "is_active": True,
                "owner_id": 999,  # Different tenant
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        }
        response = owner_client.get("/api/v1/users/99")
        assert response.status_code == 403


# ==============================================================================
# Update User
# ==============================================================================

class TestUpdateUser:
    """Tests for PUT /api/v1/users/{id}."""

    @patch("app.service_client.update_user", new_callable=AsyncMock)
    @patch("app.service_client.get_user", new_callable=AsyncMock)
    def test_owner_can_update_any_user(
        self, mock_get: AsyncMock, mock_update: AsyncMock,
        owner_client: TestClient, sample_user_response: dict,
    ) -> None:
        mock_get.return_value = {"id": 10, "owner_id": 1}
        mock_update.return_value = {**sample_user_response, "first_name": "Updated"}
        response = owner_client.put(
            "/api/v1/users/10",
            json={"first_name": "Updated"},
        )
        assert response.status_code == 200

    @patch("app.service_client.update_user", new_callable=AsyncMock)
    @patch("app.service_client.get_user", new_callable=AsyncMock)
    def test_employee_can_update_self(
        self, mock_get: AsyncMock, mock_update: AsyncMock,
        employee_client: TestClient, sample_user_response: dict,
    ) -> None:
        mock_get.return_value = {"id": 2, "owner_id": 1}
        mock_update.return_value = sample_user_response
        # Employee user_id is 2, updating user 2 = self
        response = employee_client.put(
            "/api/v1/users/2",
            json={"phone": "555-1234"},
        )
        assert response.status_code == 200

    @patch("app.service_client.get_user", new_callable=AsyncMock)
    def test_employee_cannot_update_other_user(
        self, mock_get: AsyncMock, employee_client: TestClient,
    ) -> None:
        mock_get.return_value = {"id": 99, "owner_id": 1}
        response = employee_client.put(
            "/api/v1/users/99",
            json={"first_name": "Hacked"},
        )
        assert response.status_code == 403


# ==============================================================================
# Delete User
# ==============================================================================

class TestDeleteUser:
    """Tests for DELETE /api/v1/users/{id}."""

    @patch("app.service_client.delete_user", new_callable=AsyncMock)
    @patch("app.service_client.get_user", new_callable=AsyncMock)
    def test_owner_can_delete_user(
        self, mock_get: AsyncMock, mock_delete: AsyncMock, owner_client: TestClient,
    ) -> None:
        mock_get.return_value = {"id": 10, "owner_id": 1}
        mock_delete.return_value = None
        response = owner_client.delete("/api/v1/users/10")
        assert response.status_code == 204

    def test_owner_cannot_delete_self(self, owner_client: TestClient) -> None:
        response = owner_client.delete("/api/v1/users/1")
        assert response.status_code == 400

    def test_employee_cannot_delete_user(self, employee_client: TestClient) -> None:
        response = employee_client.delete("/api/v1/users/10")
        assert response.status_code == 403


# ==============================================================================
# Invite Employee
# ==============================================================================

class TestInviteEmployee:
    """Tests for POST /api/v1/users/invite."""

    @patch("app.service_client.create_employee", new_callable=AsyncMock)
    @patch("app.service_client.create_user", new_callable=AsyncMock)
    def test_invite_creates_user_and_employee(
        self,
        mock_create_user: AsyncMock,
        mock_create_emp: AsyncMock,
        owner_client: TestClient,
        sample_user_response: dict,
    ) -> None:
        mock_create_user.return_value = sample_user_response
        mock_create_emp.return_value = {
            "id": 5,
            "user_id": 10,
            "position": "Plumber",
            "hourly_rate": 25.0,
            "skills": "plumbing",
            "notes": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        response = owner_client.post(
            "/api/v1/users/invite",
            json={
                "email": "new@test.com",
                "password": "password123",
                "first_name": "New",
                "last_name": "Employee",
                "position": "Plumber",
                "hourly_rate": 25.0,
                "skills": "plumbing",
            },
        )
        assert response.status_code == 201
        mock_create_user.assert_called_once()
        mock_create_emp.assert_called_once()


# ==============================================================================
# List Employees
# ==============================================================================

class TestListEmployees:
    """Tests for GET /api/v1/employees."""

    @patch("app.service_client.get_employees_by_owner", new_callable=AsyncMock)
    def test_list_employees_scoped_to_tenant(
        self, mock_get: AsyncMock, owner_client: TestClient,
    ) -> None:
        mock_get.return_value = []
        response = owner_client.get("/api/v1/employees")
        assert response.status_code == 200
        mock_get.assert_called_once()
        assert mock_get.call_args.kwargs["owner_id"] == 1


# ==============================================================================
# Company Endpoints
# ==============================================================================

class TestGetCompany:
    """Tests for GET /api/v1/company."""

    @patch("app.service_client.get_company", new_callable=AsyncMock)
    def test_get_company_returns_company_details(
        self, mock_get: AsyncMock, owner_client: TestClient,
    ) -> None:
        """Test that authenticated user can retrieve their company details."""
        mock_get.return_value = {
            "id": 1,
            "name": "Test Company",
            "email": "info@testcompany.com",
            "phone": "555-0100",
            "address": "123 Main St",
            "eircode": None,
            "logo_url": None,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = owner_client.get("/api/v1/company")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Company"
        mock_get.assert_called_once_with(1)  # company_id from CurrentUser


class TestUpdateCompany:
    """Tests for PUT /api/v1/company."""

    @patch("app.service_client.update_company", new_callable=AsyncMock)
    def test_owner_can_update_company(
        self, mock_update: AsyncMock, owner_client: TestClient,
    ) -> None:
        """Test that owner can update company details."""
        mock_update.return_value = {
            "id": 1,
            "name": "Updated Company Name",
            "email": "info@testcompany.com",
            "phone": "555-0100",
            "address": "123 Main St",
            "eircode": None,
            "logo_url": None,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = owner_client.put(
            "/api/v1/company",
            json={"name": "Updated Company Name"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Company Name"
        mock_update.assert_called_once()

    def test_employee_cannot_update_company(
        self, employee_client: TestClient,
    ) -> None:
        """Test that employees cannot update company details."""
        response = employee_client.put(
            "/api/v1/company",
            json={"name": "Hacked Company Name"},
        )
        # Should be denied due to role check
        assert response.status_code == 403
