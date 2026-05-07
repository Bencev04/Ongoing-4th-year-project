"""
Test suite for frontend authentication page routes.

Covers login page rendering, logout redirect behavior,
and admin portal page accessibility.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestRootRoute:
    """Test suite for the bare root route."""

    def test_root_redirects_unauthenticated_to_login(self, client: TestClient) -> None:
        """Test that unauthenticated users are sent to /login."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")

    @patch(
        "app.service_client.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "owner", "owner_id": 1},
    )
    def test_root_redirects_authenticated_user_to_calendar(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that authenticated non-superadmins are sent to /calendar."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/calendar" in response.headers.get("location", "")

    @patch(
        "app.service_client.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "superadmin"},
    )
    def test_root_redirects_superadmin_to_admin(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that superadmins are sent to /admin."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/admin" in response.headers.get("location", "")


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
        assert (
            "login" in text_lower or "sign in" in text_lower or "submit" in text_lower
        )

    def test_login_page_accepts_next_param(self, client: TestClient) -> None:
        """Test that login page accepts ?next= query parameter."""
        response = client.get("/login?next=/employees")
        assert response.status_code == 200

    def test_login_page_does_not_store_tokens_in_local_storage(
        self,
        client: TestClient,
    ) -> None:
        """Test that login script no longer persists token secrets in localStorage."""
        response = client.get("/login")
        assert "localStorage.setItem('access_token'" not in response.text
        assert "localStorage.setItem('refresh_token'" not in response.text


class TestLogoutRoute:
    """Test suite for the /logout route."""

    def test_logout_redirects_to_login(self, client: TestClient) -> None:
        """Test that POST /logout redirects (302) to /login."""
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert "/login" in response.headers.get("location", "")

    def test_logout_clears_auth_cookies(self, client: TestClient) -> None:
        """Test that POST /logout emits auth-cookie deletion headers."""
        response = client.post("/logout", follow_redirects=False)
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "wp_access_token=" in set_cookie_header
        assert "wp_refresh_token=" in set_cookie_header


class TestAdminPage:
    """Test suite for the /admin page."""

    def test_admin_page_redirects_unauthenticated_to_login(
        self, client: TestClient
    ) -> None:
        """Test that unauthenticated users are redirected to /login."""
        response = client.get("/admin", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers.get("location", "")

    @patch(
        "app.routes.admin.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "owner", "owner_id": 1},
    )
    def test_admin_page_redirects_non_superadmin(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that non-superadmin users are redirected to /calendar."""
        response = client.get("/admin", follow_redirects=False)
        assert response.status_code == 302
        assert "/calendar" in response.headers.get("location", "")

    @patch(
        "app.routes.admin.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "superadmin"},
    )
    def test_admin_page_returns_200(self, _mock: AsyncMock, client: TestClient) -> None:
        """Test that admin page renders for superadmin."""
        response = client.get("/admin")
        assert response.status_code == 200

    @patch(
        "app.routes.admin.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "superadmin"},
    )
    def test_admin_page_contains_alpine_component(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that admin page includes the Alpine.js adminApp component."""
        response = client.get("/admin")
        assert "adminApp()" in response.text

    @patch(
        "app.routes.admin.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "superadmin"},
    )
    def test_admin_page_has_organization_tab(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that admin page has Organizations tab."""
        response = client.get("/admin")
        assert "Organizations" in response.text

    @patch(
        "app.routes.admin.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "superadmin"},
    )
    def test_admin_page_has_audit_logs_tab(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that admin page has Audit Logs tab."""
        response = client.get("/admin")
        assert "Audit Logs" in response.text

    @patch(
        "app.routes.admin.get_current_user",
        new_callable=AsyncMock,
        return_value={"role": "superadmin"},
    )
    def test_admin_page_has_impersonation_feature(
        self, _mock: AsyncMock, client: TestClient
    ) -> None:
        """Test that admin page includes impersonation functionality."""
        response = client.get("/admin")
        assert "impersonate" in response.text.lower()
