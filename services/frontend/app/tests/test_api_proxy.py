"""
Frontend API Proxy Tests

Unit tests for the API proxy routes that forward requests to backend services.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


class TestJobsProxy:
    """Tests for job-related API proxy endpoints."""
    
    def test_get_jobs_endpoint_exists(self, client: TestClient):
        """Test that the jobs endpoint exists and routes to backend."""
        response = client.get("/api/jobs")
        # Without a live backend the proxy returns 503; key check is it's not 404
        assert response.status_code != 404
    
    def test_create_job_endpoint_accepts_post(self, client: TestClient):
        """Test that the create job endpoint accepts POST."""
        response = client.post(
            "/api/jobs",
            json={
                "title": "Test Job",
                "owner_id": 1,
                "created_by_id": 1
            }
        )
        # Will likely fail without backend, but should accept the request
        assert response.status_code != 405  # Method not allowed


class TestCustomersProxy:
    """Tests for customer-related API proxy endpoints."""
    
    def test_get_customers_endpoint_exists(self, client: TestClient):
        """Test that the customers endpoint exists and routes to backend."""
        response = client.get("/api/customers")
        assert response.status_code != 404


class TestUsersProxy:
    """Tests for user-related API proxy endpoints."""
    
    def test_get_users_endpoint_exists(self, client: TestClient):
        """Test that the users endpoint exists and routes to backend."""
        response = client.get("/api/users")
        assert response.status_code != 404


class TestEmployeesProxy:
    """Tests for employee-related API proxy endpoints."""
    
    def test_get_employees_endpoint_exists(self, client: TestClient):
        """Test that the employees endpoint exists and routes to backend."""
        response = client.get("/api/employees/")
        assert response.status_code != 404


class TestHealthCheck:
    """Tests for health check endpoints."""
    
    def test_health_endpoint(self, client: TestClient):
        """Test that the health endpoint returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
    
    def test_root_redirects_to_calendar(self, client: TestClient):
        """Test that root path shows calendar."""
        response = client.get("/")
        assert response.status_code == 200


class TestAuthProxy:
    """Test auth proxy route registration."""

    def test_auth_login_proxy_exists(self, client: TestClient) -> None:
        """Test that POST /api/auth/login route exists (proxy registered)."""
        response = client.post("/api/auth/login", json={"email": "test@demo.com", "password": "pass"})
        assert response.status_code != 404
        assert response.status_code != 405

    def test_auth_verify_proxy_exists(self, client: TestClient) -> None:
        """Test that POST /api/auth/verify route exists."""
        response = client.post("/api/auth/verify", json={"access_token": "fake"})
        assert response.status_code != 404
        assert response.status_code != 405


class TestNotesProxy:
    """Test notes proxy route registration."""

    def test_notes_get_route_exists(self, client: TestClient) -> None:
        """Test that GET /api/notes/1 route is registered."""
        response = client.get("/api/notes/1")
        assert response.status_code != 404
        assert response.status_code != 405


class TestAdminProxy:
    """Test admin proxy route registration."""

    def test_admin_organizations_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/admin/organizations route exists."""
        response = client.get("/api/admin/organizations")
        assert response.status_code != 404
        assert response.status_code != 405

    def test_admin_audit_logs_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/admin/audit-logs route exists."""
        response = client.get("/api/admin/audit-logs")
        assert response.status_code != 404
        assert response.status_code != 405
