"""
Frontend Map Page Route Tests

Unit tests for the map view page rendering and functionality.
Tests ensure the map page loads correctly with all expected
UI elements, Google Maps integration, and Alpine.js components.
"""

from fastapi.testclient import TestClient


class TestMapPage:
    """Tests for the map page rendering."""

    def test_map_page_returns_200(self, client: TestClient) -> None:
        """
        Test that the map page loads successfully.

        Verifies:
        - HTTP 200 status code is returned
        - HTML response is properly rendered
        """
        response = client.get("/map")
        assert response.status_code == 200

    def test_map_page_contains_map_canvas(self, client: TestClient) -> None:
        """
        Test that the map page contains the map container element.

        Verifies the map-canvas div is present for Google Maps rendering.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert 'id="map-canvas"' in response.text

    def test_map_page_contains_alpine_component(self, client: TestClient) -> None:
        """
        Test that the map page includes the Alpine.js map component.

        Verifies:
        - x-data attribute is present (Alpine.js integration)
        - mapViewApp function is referenced
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "x-data" in response.text
        assert "mapViewApp()" in response.text

    def test_map_page_includes_map_page_js(self, client: TestClient) -> None:
        """
        Test that the map page includes the map-page.js script.

        Verifies the dedicated map page JavaScript file is loaded.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "map-page.js" in response.text

    def test_map_page_has_status_filter(self, client: TestClient) -> None:
        """
        Test that the map page contains a status filter dropdown.

        Verifies:
        - Status filter element is present
        - Expected status options are available
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert 'id="map-status"' in response.text
        assert "scheduled" in response.text.lower()
        assert "in_progress" in response.text.lower()
        assert "completed" in response.text.lower()

    def test_map_page_has_date_range_inputs(self, client: TestClient) -> None:
        """
        Test that the map page contains date range filter inputs.

        Verifies both start and end date inputs are present.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert 'id="map-start"' in response.text
        assert 'id="map-end"' in response.text

    def test_map_page_has_employee_filter(self, client: TestClient) -> None:
        """
        Test that the map page contains an employee filter dropdown.

        Verifies the employee filter element is present.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert 'id="map-employee"' in response.text

    def test_map_page_has_route_planning_button(self, client: TestClient) -> None:
        """
        Test that the map page has a route planning toggle button.

        Verifies the Plan Route button is present in the toolbar.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "Plan Route" in response.text


class TestMapPageRoutePanel:
    """Tests for the route planning sidebar elements."""

    def test_map_page_has_route_sidebar(self, client: TestClient) -> None:
        """
        Test that the map page contains the route planning sidebar.

        Verifies:
        - The route sidebar panel exists
        - Calculate Route button is present
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "Calculate Route" in response.text

    def test_map_page_has_optimize_button(self, client: TestClient) -> None:
        """
        Test that the route sidebar contains an Optimize Route button.

        Verifies the optimize functionality is available for route planning.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "Optimize" in response.text

    def test_map_page_has_clear_route_button(self, client: TestClient) -> None:
        """
        Test that the route sidebar contains a Clear Route button.

        Verifies users can clear the planned route.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "Clear Route" in response.text


class TestMapPageGoogleMaps:
    """Tests for Google Maps integration elements.

    Note: In the test environment ``google_maps_browser_key`` defaults to
    an empty string, so the ``{% if google_maps_key %}`` conditional in
    the template is *not* rendered.  These tests verify the *template
    source* exists by checking for the script reference inside
    ``{% block scripts %}`` which is always rendered.
    """

    def test_map_page_includes_map_page_script(self, client: TestClient) -> None:
        """
        Test that the map page always loads the map-page.js script.

        The map-page.js file is included outside the maps-key conditional
        block and should always be present regardless of API key config.
        """
        response = client.get("/map")
        assert response.status_code == 200
        assert "map-page.js" in response.text
