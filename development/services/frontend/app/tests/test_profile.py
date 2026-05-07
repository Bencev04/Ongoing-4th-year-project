"""
Tests for the profile page route.

Verifies that the profile page renders correctly with password change form.
"""

from fastapi.testclient import TestClient


class TestProfilePage:
    """Tests for GET /profile."""

    def test_profile_page_returns_200(self, client: TestClient) -> None:
        """Profile page loads successfully.

        Verifies:
        - HTTP 200 status code
        """
        response = client.get("/profile")
        assert response.status_code == 200

    def test_profile_page_contains_title(self, client: TestClient) -> None:
        """Profile page contains expected heading.

        Verifies:
        - Page contains "Profile" text
        """
        response = client.get("/profile")
        assert "Profile" in response.text

    def test_profile_page_uses_authfetch(self, client: TestClient) -> None:
        """Profile page uses authFetch for API calls.

        Verifies:
        - JavaScript uses authFetch() instead of plain fetch()
        """
        response = client.get("/profile")
        assert "authFetch" in response.text
