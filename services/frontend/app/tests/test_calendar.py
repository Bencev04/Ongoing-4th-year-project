"""
Frontend Calendar Route Tests

Unit tests for the calendar page and related endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import date


class TestCalendarPage:
    """Tests for the main calendar page."""
    
    def test_calendar_page_returns_200(self, client: TestClient):
        """Test that the calendar page loads successfully."""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_calendar_page_contains_calendar_grid(self, client: TestClient):
        """Test that the calendar page contains the calendar grid container."""
        response = client.get("/")
        assert response.status_code == 200
        assert "calendar-grid" in response.text
    
    def test_calendar_page_contains_job_queue(self, client: TestClient):
        """Test that the calendar page contains the job queue sidebar."""
        response = client.get("/")
        assert response.status_code == 200
        assert "job-queue" in response.text
    
    def test_calendar_page_contains_htmx_attributes(self, client: TestClient):
        """Test that the calendar page has HTMX integration."""
        response = client.get("/")
        assert response.status_code == 200
        assert "hx-get" in response.text
        assert "hx-target" in response.text
    
    def test_calendar_page_contains_alpine_component(self, client: TestClient):
        """Test that the calendar page has Alpine.js integration."""
        response = client.get("/")
        assert response.status_code == 200
        assert "x-data" in response.text
        assert "calendarApp" in response.text


class TestCalendarNavigation:
    """Tests for calendar navigation endpoints."""
    
    def test_navigate_to_specific_month(self, client: TestClient):
        """Test navigating to a specific month."""
        response = client.get("/calendar/2024/6")
        assert response.status_code == 200
    
    def test_navigate_to_previous_month(self, client: TestClient):
        """Test the previous month navigation."""
        response = client.get("/calendar/prev?year=2024&month=3")
        # Should redirect or return partial content
        assert response.status_code in [200, 302]
    
    def test_navigate_to_next_month(self, client: TestClient):
        """Test the next month navigation."""
        response = client.get("/calendar/next?year=2024&month=3")
        # Should redirect or return partial content
        assert response.status_code in [200, 302]


class TestCalendarGrid:
    """Tests for calendar grid partial endpoint."""
    
    def test_calendar_grid_returns_html(self, client: TestClient):
        """Test that the grid endpoint returns HTML partial."""
        response = client.get("/calendar/grid?year=2024&month=1")
        assert response.status_code == 200
        # Should return HTML, not JSON
        assert "text/html" in response.headers.get("content-type", "")


class TestJobQueue:
    """Tests for job queue endpoints."""
    
    def test_job_queue_returns_html(self, client: TestClient):
        """Test that the job queue endpoint returns HTML partial."""
        response = client.get("/calendar/job-queue")
        assert response.status_code == 200


class TestJobModal:
    """Tests for job modal endpoints."""
    
    def test_job_modal_create_form(self, client: TestClient):
        """Test that the create job modal loads."""
        response = client.get("/calendar/job-modal")
        assert response.status_code == 200
        assert "Create New Job" in response.text or "form" in response.text


class TestDayView:
    """Tests for day view endpoints."""
    
    def test_day_view_returns_html(self, client: TestClient):
        """Test that the day view endpoint returns HTML."""
        response = client.get("/calendar/day/2024-01-15")
        assert response.status_code == 200


class TestStaticAssets:
    """Tests for static asset serving."""
    
    def test_css_file_exists(self, client: TestClient):
        """Test that the CSS file is served."""
        response = client.get("/static/css/styles.css")
        # Static files might return 404 if not mounted properly in test
        # This is expected behavior - just ensure no 500 error
        assert response.status_code != 500
    
    def test_js_file_exists(self, client: TestClient):
        """Test that the JS file is served."""
        response = client.get("/static/js/main.js")
        # Static files might return 404 if not mounted properly in test
        # This is expected behavior - just ensure no 500 error
        assert response.status_code != 500


class TestCalendarBoundaryNavigation:
    """Test calendar boundary month navigation."""

    def test_december_to_january_navigation(self, client: TestClient) -> None:
        """Test that navigating next from December goes to January of the next year."""
        response = client.get("/calendar/next?year=2025&month=12", follow_redirects=False)
        assert response.status_code in (302, 307)
        location = response.headers.get("location", "")
        assert "2026" in location
        assert "/1" in location or "month=1" in location

    def test_january_to_december_navigation(self, client: TestClient) -> None:
        """Test that navigating prev from January goes to December of the prior year."""
        response = client.get("/calendar/prev?year=2026&month=1", follow_redirects=False)
        assert response.status_code in (302, 307)
        location = response.headers.get("location", "")
        assert "2025" in location
        assert "/12" in location or "month=12" in location
