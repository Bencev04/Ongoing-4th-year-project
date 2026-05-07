"""
Frontend API Proxy Tests

Unit tests for the API proxy routes that forward requests to backend services.
"""

from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.routes import api_proxy


class TestJobsProxy:
    """Tests for job-related API proxy endpoints."""

    def test_get_jobs_endpoint_exists(self, client: TestClient):
        """Test that the jobs endpoint exists and routes to backend.

        The conftest mocks the HTTP client to raise ConnectError,
        so proxied routes return 503 (service unavailable).
        """
        response = client.get("/api/jobs")
        assert response.status_code == 503

    def test_create_job_endpoint_accepts_post(self, client: TestClient):
        """Test that the create job endpoint accepts POST."""
        response = client.post(
            "/api/jobs", json={"title": "Test Job", "owner_id": 1, "created_by_id": 1}
        )
        assert response.status_code == 503

    def test_update_job_endpoint_accepts_put(self, client: TestClient) -> None:
        """Test that the job detail endpoint accepts PUT for updates."""
        response = client.put("/api/jobs/501", json={"title": "Updated Job"})
        assert response.status_code == 503


class TestCustomersProxy:
    """Tests for customer-related API proxy endpoints."""

    def test_get_customers_endpoint_exists(self, client: TestClient):
        """Test that the customers endpoint exists and routes to backend."""
        response = client.get("/api/customers")
        assert response.status_code == 503


class TestUsersProxy:
    """Tests for user-related API proxy endpoints."""

    def test_get_users_endpoint_exists(self, client: TestClient):
        """Test that the users endpoint exists and routes to backend."""
        response = client.get("/api/users")
        assert response.status_code == 503


class TestEmployeesProxy:
    """Tests for employee-related API proxy endpoints."""

    def test_get_employees_endpoint_exists(self, client: TestClient):
        """Test that the employees endpoint exists and routes to backend."""
        response = client.get("/api/employees/")
        assert response.status_code == 503


class TestHealthCheck:
    """Tests for health check endpoints."""

    def test_health_endpoint(self, client: TestClient):
        """Test that the health endpoint returns OK."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_redirects_to_calendar(self, client: TestClient):
        """Test that unauthenticated root requests redirect to login."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")


class TestAuthProxy:
    """Test auth proxy route registration."""

    def test_auth_login_proxy_exists(self, client: TestClient) -> None:
        """Test that POST /api/auth/login route exists (proxy registered)."""
        response = client.post(
            "/api/auth/login", json={"email": "test@demo.com", "password": "pass"}
        )
        assert response.status_code == 503

    def test_auth_verify_proxy_exists(self, client: TestClient) -> None:
        """Test that POST /api/auth/verify route exists."""
        response = client.post("/api/auth/verify", json={"access_token": "fake"})
        assert response.status_code == 503

    def test_login_sets_http_only_cookies_and_hides_tokens(
        self,
        client: TestClient,
    ) -> None:
        """Test that login response sets cookies and does not expose token fields."""
        original_request = api_proxy._http_client.request
        api_proxy._http_client.request = AsyncMock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "access-secret",
                    "refresh_token": "refresh-secret",
                    "token_type": "bearer",
                    "expires_in": 1800,
                    "user_id": 1,
                    "role": "owner",
                },
            )
        )

        try:
            response = client.post(
                "/api/auth/login",
                json={"email": "owner@demo.com", "password": "password123"},
            )
        finally:
            api_proxy._http_client.request = original_request

        assert response.status_code == 200
        payload = response.json()
        assert "access_token" not in payload
        assert "refresh_token" not in payload
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "wp_access_token=" in set_cookie_header
        assert "wp_refresh_token=" in set_cookie_header

    def test_proxy_promotes_access_cookie_to_authorization_header(
        self,
        client: TestClient,
    ) -> None:
        """Test cookie-based auth header injection for proxied API requests."""
        captured_headers: dict[str, str] = {}

        async def _capture_request(*args, **kwargs):  # type: ignore[no-untyped-def]
            captured_headers.update(kwargs.get("headers", {}))
            return httpx.Response(200, json={"items": []})

        original_request = api_proxy._http_client.request
        api_proxy._http_client.request = AsyncMock(side_effect=_capture_request)

        try:
            client.cookies.set("wp_access_token", "cookie-token")
            response = client.get("/api/jobs")
        finally:
            api_proxy._http_client.request = original_request

        assert response.status_code == 200
        assert captured_headers.get("Authorization") == "Bearer cookie-token"


class TestNotesProxy:
    """Test notes proxy route registration."""

    def test_notes_get_route_exists(self, client: TestClient) -> None:
        """Test that GET /api/notes/1 route is registered."""
        response = client.get("/api/notes/1")
        assert response.status_code == 503


class TestAdminProxy:
    """Test admin proxy route registration."""

    def test_admin_organizations_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/admin/organizations route exists."""
        response = client.get("/api/admin/organizations")
        assert response.status_code == 503

    def test_admin_audit_logs_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/admin/audit-logs route exists."""
        response = client.get("/api/admin/audit-logs")
        assert response.status_code == 503


class TestTenantAuditProxy:
    """Test tenant audit proxy route registration."""

    def test_tenant_audit_logs_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/audit-logs route is registered."""
        response = client.get("/api/audit-logs")
        assert response.status_code == 503


class TestMapsProxy:
    """Test maps proxy route registration."""

    def test_maps_geocode_eircode_proxy_exists(self, client: TestClient) -> None:
        """Test that POST /api/maps/geocode-eircode route is registered."""
        response = client.post(
            "/api/maps/geocode-eircode",
            json={"eircode": "D02XY45"},
        )
        assert response.status_code == 503


class TestCompanyProxy:
    """Test company proxy route registration."""

    def test_get_company_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/company route is registered."""
        response = client.get("/api/company")
        assert response.status_code == 503

    def test_update_company_proxy_exists(self, client: TestClient) -> None:
        """Test that PUT /api/company route is registered."""
        response = client.put(
            "/api/company",
            json={"name": "Updated"},
        )
        assert response.status_code == 503


class TestPermissionsProxy:
    """Test permissions proxy route registration."""

    def test_get_permissions_catalog_proxy_exists(self, client: TestClient) -> None:
        """Test that GET /api/permissions/catalog route is registered."""
        response = client.get("/api/permissions/catalog")
        assert response.status_code == 503

    def test_maps_geocode_proxy_exists(self, client: TestClient) -> None:
        """Test that POST /api/maps/geocode route is registered."""
        response = client.post(
            "/api/maps/geocode",
            json={"address": "123 Main St, Dublin"},
        )
        assert response.status_code == 503
