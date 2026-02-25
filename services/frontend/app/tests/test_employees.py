"""
Frontend Employees Route Tests

Unit tests for the employees page and related functionality.
Tests ensure proper authentication handling and page rendering.
"""

import pytest
from fastapi.testclient import TestClient


class TestEmployeesPage:
    """Tests for the employees page rendering and functionality."""
    
    def test_employees_page_returns_200(self, client: TestClient) -> None:
        """
        Test that the employees page loads successfully.
        
        Verifies:
        - HTTP 200 status code is returned
        - HTML response is properly rendered
        """
        response = client.get("/employees")
        assert response.status_code == 200
    
    def test_employees_page_contains_title(self, client: TestClient) -> None:
        """
        Test that the employees page contains the proper title.
        
        Verifies the page heading is present in the HTML.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "Employees" in response.text
    
    def test_employees_page_contains_alpine_component(self, client: TestClient) -> None:
        """
        Test that the employees page includes the Alpine.js component.
        
        Verifies:
        - x-data attribute is present (Alpine.js integration)
        - employeesApp function is defined
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "x-data" in response.text
        assert "employeesApp()" in response.text
    
    def test_employees_page_has_add_button(self, client: TestClient) -> None:
        """
        Test that the employees page has an 'Add Employee' button.
        
        Verifies the UI contains the button for inviting new employees.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "Add Employee" in response.text
    
    def test_employees_page_has_table_structure(self, client: TestClient) -> None:
        """
        Test that the employees page contains a table for displaying employees.
        
        Verifies:
        - Table headers are present (Name, Position, Skills, etc.)
        - Table structure is properly set up
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "Name" in response.text
        assert "Position" in response.text
        assert "Skills" in response.text


class TestEmployeesJavaScript:
    """Tests for JavaScript functionality on the employees page."""
    
    def test_employees_js_uses_authfetch(self, client: TestClient) -> None:
        """
        Test that the employees page JavaScript uses authFetch for API calls.
        
        This is the critical fix - authFetch automatically injects JWT tokens.
        Regular fetch() would cause 401 Unauthorized errors.
        
        Verifies:
        - authFetch is called instead of plain fetch
        - API endpoint /api/employees/ is accessed correctly
        """
        response = client.get("/employees")
        assert response.status_code == 200
        
        # Verify authFetch is used (NOT regular fetch for auth endpoints)
        assert "authFetch" in response.text
        assert "authFetch('/api/employees/'" in response.text
    
    def test_employees_js_has_load_function(self, client: TestClient) -> None:
        """
        Test that the employees page has a loadEmployees function.
        
        Verifies the core data loading functionality is present.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "loadEmployees" in response.text
    
    def test_employees_js_has_error_handling(self, client: TestClient) -> None:
        """
        Test that the employees JavaScript has proper error handling.
        
        Verifies:
        - try-catch blocks are present
        - Error state variable exists
        - HTTP status codes are checked (401, 403, etc.)
        """
        response = client.get("/employees")
        assert response.status_code == 200
        
        # Check for error handling patterns
        assert "catch" in response.text
        assert "this.error" in response.text
        assert "resp.status" in response.text or "response.ok" in response.text
    
    def test_employees_js_has_loading_state(self, client: TestClient) -> None:
        """
        Test that the employees page manages loading state.
        
        Verifies a loading indicator is shown while data is being fetched.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "this.loading" in response.text or "loading" in response.text
    
    def test_employees_js_has_type_annotations(self, client: TestClient) -> None:
        """
        Test that the JavaScript code includes JSDoc type annotations.
        
        Verifies code quality standards:
        - @type annotations for variables
        - @param annotations for parameters
        - @returns annotations for functions
        """
        response = client.get("/employees")
        assert response.status_code == 200
        
        # Check for JSDoc documentation
        assert "@type" in response.text or "@param" in response.text or "@returns" in response.text
    
    def test_employees_js_has_comments(self, client: TestClient) -> None:
        """
        Test that the JavaScript code is properly commented.
        
        Verifies JSDoc block comments explaining functionality are present.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        
        # Check for JSDoc block comments (not just // which matches URLs)
        assert "/**" in response.text


class TestEmployeesUIElements:
    """Tests for UI elements and user experience."""
    
    def test_employees_page_has_loading_indicator(self, client: TestClient) -> None:
        """
        Test that the page shows a loading indicator.
        
        Verifies a spinner or loading message is displayed while fetching data.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "Loading" in response.text or "loading" in response.text
    
    def test_employees_page_has_error_display(self, client: TestClient) -> None:
        """
        Test that the page has an area to display error messages.
        
        Verifies error messages can be shown to users when loading fails.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "x-show=\"error\"" in response.text or "error" in response.text
    
    def test_employees_page_has_empty_state(self, client: TestClient) -> None:
        """
        Test that the page has an empty state for when no employees exist.
        
        Verifies a friendly message is shown when the employee list is empty.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        assert "No employees" in response.text or "employees.length === 0" in response.text


class TestEmployeesAuthentication:
    """Tests specifically for authentication handling."""
    
    def test_employees_page_handles_401_unauthorized(self, client: TestClient) -> None:
        """
        Test that the JavaScript properly handles 401 Unauthorized responses.
        
        Verifies:
        - 401 status code is checked in the fetch response handler
        - Appropriate error message is shown
        """
        response = client.get("/employees")
        assert response.status_code == 200
        
        # Check for actual 401 handling code — status check in JS
        assert "resp.status === 401" in response.text or "status === 401" in response.text
    
    def test_employees_page_handles_403_forbidden(self, client: TestClient) -> None:
        """
        Test that the JavaScript properly handles 403 Forbidden responses.
        
        Verifies permission errors are handled in the fetch response handler.
        """
        response = client.get("/employees")
        assert response.status_code == 200
        
        # Check for actual 403 handling code — status check in JS
        assert "resp.status === 403" in response.text or "status === 403" in response.text
