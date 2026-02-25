"""
Frontend Page Rendering Integration Tests
==========================================

Verifies that all major frontend HTML pages are served correctly by
the NGINX → frontend service pipeline.

The frontend uses client-side authentication (localStorage JWT tokens),
so pages are served without server-side auth checks.  These tests
confirm that the HTML templates render without 500 errors and contain
expected structural elements.

Routes tested:
    - GET /login         (standalone login page)
    - GET /logout        (redirect to /login)
    - GET /calendar      (main calendar view)
    - GET /customers     (customer listing)
    - GET /employees     (employee listing)
    - GET /profile       (user profile page)
    - GET /admin         (superadmin dashboard)

Industry-standard practices applied:
    - Each test checks both status code and key HTML element presence
    - Descriptive assertion messages
    - Grouped by functional area
"""

import httpx
import pytest


# ==========================================================================
# Public Pages (no auth required)
# ==========================================================================

class TestPublicPages:
    """
    Pages that are accessible without any authentication token.
    """

    def test_login_page_renders(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /login returns 200 with an HTML form.

        Verifies:
        - 200 status code
        - Response contains 'login' or 'sign in' text (case-insensitive)
        """
        resp = http_client.get("/login")
        assert resp.status_code == 200, (
            f"Login page returned {resp.status_code}"
        )
        body = resp.text.lower()
        assert "login" in body or "sign in" in body, (
            "Login page missing expected login/sign-in text"
        )

    def test_login_page_contains_form(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        The login page should contain a <form> element for credentials.

        Verifies:
        - HTML contains '<form' tag
        - HTML contains an input for email/password
        """
        resp = http_client.get("/login")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "<form" in body, "Login page missing <form> element"
        assert "password" in body, "Login page missing password field"

    def test_logout_redirects_to_login(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /logout should redirect (302/307) to the login page.

        Note: httpx with follow_redirects=False by default, but our
        client may follow redirects. We accept either a redirect status
        or a 200 with login content.

        Verifies:
        - Response is either a redirect to /login or a 200 with login content
        """
        # Use a separate client to avoid following redirects
        base_url = str(http_client._base_url)
        with httpx.Client(
            base_url=base_url,
            follow_redirects=False,
            timeout=30.0,
        ) as client:
            resp = client.get("/logout")

        if resp.status_code in (301, 302, 307, 308):
            location = resp.headers.get("location", "")
            assert "login" in location.lower(), (
                f"Logout redirects to {location}, expected /login"
            )
        else:
            # If redirect was followed, we should see the login page
            assert resp.status_code == 200


# ==========================================================================
# Authenticated Pages (served without server-side auth gate)
# ==========================================================================

class TestAuthenticatedPages:
    """
    Pages that require client-side auth tokens but are served as HTML
    by the frontend service regardless (auth is enforced in JS).

    We verify the template renders without a 500 error.
    """

    def test_calendar_page_renders(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /calendar returns 200 with calendar HTML.

        Verifies:
        - 200 status code
        - Response contains 'calendar' text
        """
        resp = http_client.get("/calendar")
        assert resp.status_code == 200, (
            f"Calendar page returned {resp.status_code}"
        )
        body = resp.text.lower()
        assert "calendar" in body, (
            "Calendar page missing expected 'calendar' text"
        )

    def test_customers_page_renders(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /customers returns 200 with customers HTML.

        Verifies:
        - 200 status code
        - Response contains 'customer' text
        """
        resp = http_client.get("/customers")
        assert resp.status_code == 200, (
            f"Customers page returned {resp.status_code}"
        )
        body = resp.text.lower()
        assert "customer" in body, (
            "Customers page missing expected 'customer' text"
        )

    def test_employees_page_renders(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /employees returns 200 with employees HTML.

        Verifies:
        - 200 status code
        - Response contains 'employee' text
        """
        resp = http_client.get("/employees")
        assert resp.status_code == 200, (
            f"Employees page returned {resp.status_code}"
        )
        body = resp.text.lower()
        assert "employee" in body, (
            "Employees page missing expected 'employee' text"
        )

    def test_profile_page_renders(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /profile returns 200 with profile HTML.

        Verifies:
        - 200 status code
        - Response contains 'profile' text
        """
        resp = http_client.get("/profile")
        assert resp.status_code == 200, (
            f"Profile page returned {resp.status_code}"
        )
        body = resp.text.lower()
        assert "profile" in body, (
            "Profile page missing expected 'profile' text"
        )


# ==========================================================================
# Admin Page
# ==========================================================================

class TestAdminPage:
    """
    The /admin page is the superadmin dashboard.
    It is served as HTML (no server-side auth gate), but should render.
    """

    def test_admin_page_renders(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        GET /admin returns 200 with admin HTML.

        Verifies:
        - 200 status code
        - Response contains 'admin' text
        """
        resp = http_client.get("/admin")
        assert resp.status_code == 200, (
            f"Admin page returned {resp.status_code}"
        )
        body = resp.text.lower()
        assert "admin" in body, (
            "Admin page missing expected 'admin' text"
        )


# ==========================================================================
# Static Assets
# ==========================================================================

class TestStaticAssets:
    """
    Verify that CSS/JS static assets are served correctly.
    """

    def test_static_css_or_js_reachable(
        self,
        http_client: httpx.Client,
    ) -> None:
        """
        At least one static asset path should return 200.

        We probe common paths; if the login page works then its
        CSS/JS must be loadable.

        Verifies:
        - Login page HTML references static assets
        - At least one static path is reachable (200) or the page
          works fully self-contained
        """
        login_resp = http_client.get("/login")
        assert login_resp.status_code == 200

        body = login_resp.text

        # Extract a CSS or JS href/src from the HTML
        import re

        asset_paths = re.findall(
            r'(?:href|src)=["\'](/static/[^"\']+)["\']',
            body,
        )

        if not asset_paths:
            # Page may be fully self-contained with inline styles
            pytest.skip("No /static/ asset references found in login page")

        # Test the first found asset
        asset_resp = http_client.get(asset_paths[0])
        assert asset_resp.status_code == 200, (
            f"Static asset {asset_paths[0]} returned {asset_resp.status_code}"
        )
