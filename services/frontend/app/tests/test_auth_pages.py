"""
Test suite for frontend authentication page routes.

Covers login page rendering, logout redirect behavior,
and admin portal page accessibility.
"""

import pytest
from fastapi.testclient import TestClient


class TestLoginPage:
    """Test suite for the /login page."""

    def test_login_page_returns_200(self, client: TestClient) -> None:
        """Test that login page renders successfully."""
        response = client.get("/login", follow_redirects=False)
        assert response.status_code == 200

    def test_login_page_contains_form(self, client: TestClient) -> None:
        """Test that login page includes email and password fields."""
        response = client.get("/login")
        assert "email" in response.text.lower()
        assert "password" in response.text.lower()

    def test_login_page_contains_submit_button(self, client: TestClient) -> None:
        """Test that login page has a login/submit button."""
        response = client.get("/login")
        text_lower = response.text.lower()
        assert "login" in text_lower or "sign in" in text_lower or "submit" in text_lower

    def test_login_page_accepts_next_param(self, client: TestClient) -> None:
        """Test that login page accepts ?next= query parameter."""
        response = client.get("/login?next=/employees")
        assert response.status_code == 200


class TestLogoutRoute:
    """Test suite for the /logout route."""

    def test_logout_redirects_to_login(self, client: TestClient) -> None:
        """Test that /logout redirects (302) to /login."""
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/login" in response.headers.get("location", "")


class TestAdminPage:
    """Test suite for the /admin page."""

    def test_admin_page_returns_200(self, client: TestClient) -> None:
        """Test that admin page renders."""
        response = client.get("/admin")
        assert response.status_code == 200

    def test_admin_page_contains_alpine_component(self, client: TestClient) -> None:
        """Test that admin page includes the Alpine.js adminApp component."""
        response = client.get("/admin")
        assert "adminApp()" in response.text

    def test_admin_page_has_organization_tab(self, client: TestClient) -> None:
        """Test that admin page has Organizations tab."""
        response = client.get("/admin")
        assert "Organizations" in response.text

    def test_admin_page_has_audit_logs_tab(self, client: TestClient) -> None:
        """Test that admin page has Audit Logs tab."""
        response = client.get("/admin")
        assert "Audit Logs" in response.text

    def test_admin_page_has_impersonation_feature(self, client: TestClient) -> None:
        """Test that admin page includes impersonation functionality."""
        response = client.get("/admin")
        assert "impersonate" in response.text.lower()
