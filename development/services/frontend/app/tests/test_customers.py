"""
Frontend Customer Route Tests

Unit tests for the customer page, HTMX partials, and the
customers.js Alpine component contract.

All tests use the synchronous ``TestClient`` fixture from conftest.
"""

from fastapi.testclient import TestClient

# ==============================================================================
# Main Page Tests
# ==============================================================================


class TestCustomersPage:
    """Verify the main /customers page renders correctly."""

    def test_customers_page_returns_200(self, client: TestClient) -> None:
        """GET /customers should return 200 OK."""
        response = client.get("/customers")
        assert response.status_code == 200

    def test_customers_page_has_correct_title(self, client: TestClient) -> None:
        """Page title should contain 'Customers'."""
        response = client.get("/customers")
        assert "Customers" in response.text

    def test_customers_page_contains_alpine_component(self, client: TestClient) -> None:
        """Template must mount the customersApp() Alpine component."""
        response = client.get("/customers")
        assert "customersApp()" in response.text
        assert 'x-data="customersApp()"' in response.text

    def test_customers_page_contains_search_input(self, client: TestClient) -> None:
        """The search bar should be rendered on the page."""
        response = client.get("/customers")
        assert "x-model.debounce" in response.text
        assert "placeholder=" in response.text

    def test_customers_page_contains_status_filter(self, client: TestClient) -> None:
        """An active/inactive status filter <select> should exist."""
        response = client.get("/customers")
        assert "statusFilter" in response.text
        assert "All Statuses" in response.text

    def test_customers_page_contains_add_button(self, client: TestClient) -> None:
        """An 'Add Customer' button must be present."""
        response = client.get("/customers")
        assert "Add Customer" in response.text

    def test_customers_page_contains_table(self, client: TestClient) -> None:
        """A customer table with correct column headers should render."""
        response = client.get("/customers")
        assert "<table" in response.text
        assert "Customer" in response.text
        assert "Contact" in response.text
        assert "Status" in response.text
        assert "Actions" in response.text

    def test_customers_page_contains_pagination(self, client: TestClient) -> None:
        """Pagination controls should be present."""
        response = client.get("/customers")
        assert "prevPage()" in response.text
        assert "nextPage()" in response.text

    def test_customers_page_loads_js_file(self, client: TestClient) -> None:
        """The page should reference the external customers.js script."""
        response = client.get("/customers")
        assert "/static/js/customers.js" in response.text

    def test_customers_page_contains_empty_state(self, client: TestClient) -> None:
        """An empty-state message should render when no customers exist."""
        response = client.get("/customers")
        assert "No customers found" in response.text

    def test_customers_page_contains_detail_panel(self, client: TestClient) -> None:
        """The slide-over detail panel should be in the DOM."""
        response = client.get("/customers")
        assert "Customer Details" in response.text
        assert "detailOpen" in response.text

    def test_customers_page_contains_create_edit_modal(
        self, client: TestClient
    ) -> None:
        """The create/edit modal should be present in the DOM."""
        response = client.get("/customers")
        assert "Add New Customer" in response.text
        assert "first_name" in response.text
        assert "last_name" in response.text

    def test_customers_page_contains_delete_modal(self, client: TestClient) -> None:
        """The delete confirmation modal should be in the DOM."""
        response = client.get("/customers")
        assert "Delete Customer" in response.text
        assert "deleteModalOpen" in response.text

    def test_customers_page_contains_toast(self, client: TestClient) -> None:
        """A toast notification container should exist."""
        response = client.get("/customers")
        assert "toast.show" in response.text


# ==============================================================================
# HTMX Partial Tests
# ==============================================================================


class TestCustomerCreateModal:
    """Tests for the HTMX customer create-modal partial."""

    def test_create_modal_returns_200(self, client: TestClient) -> None:
        """GET /customers/create-modal should return 200."""
        response = client.get("/customers/create-modal")
        assert response.status_code == 200

    def test_create_modal_returns_html(self, client: TestClient) -> None:
        """Response content-type should be text/html."""
        response = client.get("/customers/create-modal")
        assert "text/html" in response.headers.get("content-type", "")

    def test_create_modal_contains_form(self, client: TestClient) -> None:
        """The partial should include a <form> element."""
        response = client.get("/customers/create-modal")
        assert "<form" in response.text

    def test_create_modal_has_required_fields(self, client: TestClient) -> None:
        """First name, last name, email, phone, and address fields."""
        response = client.get("/customers/create-modal")
        assert "first_name" in response.text
        assert "last_name" in response.text
        assert "email" in response.text.lower()
        assert "phone" in response.text.lower()

    def test_create_modal_title_says_add(self, client: TestClient) -> None:
        """Modal title for create mode should say 'Add New Customer'."""
        response = client.get("/customers/create-modal")
        assert "Add New Customer" in response.text


class TestCustomerEditModal:
    """Tests for the HTMX customer edit-modal partial."""

    def test_edit_modal_returns_200(self, client: TestClient) -> None:
        """GET /customers/edit-modal/1 should return 200."""
        response = client.get("/customers/edit-modal/1")
        assert response.status_code == 200

    def test_edit_modal_title_says_edit(self, client: TestClient) -> None:
        """Modal title for edit mode should say 'Edit Customer'."""
        response = client.get("/customers/edit-modal/1")
        assert "Edit Customer" in response.text

    def test_edit_modal_contains_form(self, client: TestClient) -> None:
        """The partial should include a <form> element."""
        response = client.get("/customers/edit-modal/1")
        assert "<form" in response.text

    def test_edit_modal_has_update_button(self, client: TestClient) -> None:
        """The submit button should say 'Update'."""
        response = client.get("/customers/edit-modal/1")
        assert "Update" in response.text


class TestCustomerDetailPanel:
    """Tests for the HTMX customer detail partial."""

    def test_detail_panel_returns_200(self, client: TestClient) -> None:
        """GET /customers/detail/1 should return 200."""
        response = client.get("/customers/detail/1")
        assert response.status_code == 200

    def test_detail_panel_returns_html(self, client: TestClient) -> None:
        """Content-type should be text/html."""
        response = client.get("/customers/detail/1")
        assert "text/html" in response.headers.get("content-type", "")

    def test_detail_panel_contains_contact_fields(self, client: TestClient) -> None:
        """Panel should reference email, phone, and address labels."""
        response = client.get("/customers/detail/1")
        assert "Email" in response.text
        assert "Phone" in response.text
        assert "Address" in response.text

    def test_detail_panel_has_recent_jobs_section(self, client: TestClient) -> None:
        """Panel should include a 'Recent Jobs' section."""
        response = client.get("/customers/detail/1")
        assert "Recent Jobs" in response.text


class TestCustomerDeleteConfirm:
    """Tests for the HTMX delete-confirmation partial."""

    def test_delete_confirm_returns_200(self, client: TestClient) -> None:
        """GET /customers/delete-confirm/1 should return 200."""
        response = client.get("/customers/delete-confirm/1")
        assert response.status_code == 200

    def test_delete_confirm_contains_warning(self, client: TestClient) -> None:
        """Dialog should include a warning message."""
        response = client.get("/customers/delete-confirm/1")
        assert "Delete Customer" in response.text
        assert "Are you sure" in response.text

    def test_delete_confirm_has_cancel_button(self, client: TestClient) -> None:
        """A Cancel button must be present."""
        response = client.get("/customers/delete-confirm/1")
        assert "Cancel" in response.text

    def test_delete_confirm_has_delete_button(self, client: TestClient) -> None:
        """A Delete action button must be present."""
        response = client.get("/customers/delete-confirm/1")
        # Count occurrences — header + button
        assert response.text.count("Delete") >= 2


# ==============================================================================
# Navigation Tests
# ==============================================================================


class TestCustomersNavigation:
    """Verify navbar integration."""

    def test_navbar_has_customers_link(self, client: TestClient) -> None:
        """The main navbar should contain a link to /customers."""
        response = client.get("/calendar")
        assert 'href="/customers"' in response.text

    def test_customers_page_extends_base(self, client: TestClient) -> None:
        """Page should extend base.html (includes nav and footer)."""
        response = client.get("/customers")
        # base.html renders the <nav> with 'Workflow Platform'
        assert "Workflow Platform" in response.text

    def test_redirect_root_does_not_go_to_customers(self, client: TestClient) -> None:
        """Root / should redirect to /login, not /customers."""
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]


# ==============================================================================
# Static Asset Tests
# ==============================================================================


class TestCustomerStaticAssets:
    """Verify that the customers.js static file is accessible."""

    def test_customers_js_is_served(self, client: TestClient) -> None:
        """GET /static/js/customers.js should not return 500."""
        response = client.get("/static/js/customers.js")
        assert response.status_code == 200

    def test_customers_js_contains_alpine_function(self, client: TestClient) -> None:
        """The JS file should export the customersApp function."""
        response = client.get("/static/js/customers.js")
        assert "function customersApp()" in response.text

    def test_customers_js_has_crud_methods(self, client: TestClient) -> None:
        """JS should define loadCustomers, saveCustomer, deleteCustomer."""
        response = client.get("/static/js/customers.js")
        text = response.text
        assert "loadCustomers" in text
        assert "saveCustomer" in text
        assert "deleteCustomer" in text

    def test_customers_js_has_pagination(self, client: TestClient) -> None:
        """JS should include pagination helpers."""
        response = client.get("/static/js/customers.js")
        assert "prevPage" in response.text
        assert "nextPage" in response.text
        assert "goToPage" in response.text

    def test_customers_js_has_search(self, client: TestClient) -> None:
        """JS should include the debounced search method."""
        response = client.get("/static/js/customers.js")
        assert "debouncedSearch" in response.text

    def test_customers_js_has_note_methods(self, client: TestClient) -> None:
        """JS should include the addNote method for customer notes."""
        response = client.get("/static/js/customers.js")
        assert "addNote" in response.text

    def test_customers_js_uses_auth_fetch(self, client: TestClient) -> None:
        """JS should use authFetch for authenticated API calls."""
        response = client.get("/static/js/customers.js")
        assert "authFetch" in response.text
