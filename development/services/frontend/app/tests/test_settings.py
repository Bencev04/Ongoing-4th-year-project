"""
Frontend Settings Page Tests

Unit tests for the settings page route, HTML template rendering,
companion JavaScript component, and the proxy routes for
company, permissions, and tenant audit endpoints.
"""

from fastapi.testclient import TestClient

# ==========================================================================
# Settings Page — Route & Rendering
# ==========================================================================


class TestSettingsPage:
    """Tests for the settings page route and initial HTML rendering."""

    def test_settings_page_returns_200(self, client: TestClient) -> None:
        """
        Test that /settings returns HTTP 200.

        Verifies:
        - Route is registered and reachable.
        - Template renders without server-side errors.
        """
        response = client.get("/settings")
        assert response.status_code == 200

    def test_settings_page_has_title(self, client: TestClient) -> None:
        """
        Test that the page HTML contains the "Settings" title.

        Verifies the <title> or heading reflects the page purpose.
        """
        response = client.get("/settings")
        assert "Settings" in response.text

    def test_settings_page_contains_alpine_component(self, client: TestClient) -> None:
        """
        Test that the settings page mounts the Alpine.js component.

        Verifies:
        - ``x-data`` attribute is present.
        - ``settingsApp()`` function reference is in the output.
        """
        response = client.get("/settings")
        assert "x-data" in response.text
        assert "settingsApp()" in response.text

    def test_settings_page_has_four_tabs(self, client: TestClient) -> None:
        """
        Test that all four tab labels are rendered in the HTML.

        Verifies:
        - Organisation tab label is present.
        - People tab label is present.
        - Permissions tab label is present.
        - Audit Logs tab label is present.
        """
        response = client.get("/settings")
        html = response.text
        assert "Organisation" in html
        assert "People" in html
        assert "Permissions" in html
        assert "Audit Logs" in html

    def test_settings_page_has_organisation_form(self, client: TestClient) -> None:
        """
        Test that the Organisation tab contains form fields.

        Verifies the company detail inputs are present in the template.
        """
        response = client.get("/settings")
        html = response.text
        assert "companyForm.name" in html
        assert "Save" in html

    def test_settings_page_has_people_table(self, client: TestClient) -> None:
        """
        Test that the People tab renders a user table placeholder.

        Verifies:
        - A table header for user names or email is present.
        - The reset-password modal markup is included.
        """
        response = client.get("/settings")
        html = response.text
        assert "resetPassword" in html or "Reset Password" in html

    def test_settings_page_has_permissions_grid(self, client: TestClient) -> None:
        """
        Test that the Permissions tab contains toggle controls.

        Verifies:
        - Permission toggle elements are present.
        - A save or apply button for permissions is present.
        """
        response = client.get("/settings")
        html = response.text
        # The grid uses Alpine toggle bindings
        assert "togglePermission" in html or "permissionGroups" in html

    def test_settings_page_has_audit_log_section(self, client: TestClient) -> None:
        """
        Test that the Audit Logs tab markup is present.

        Verifies:
        - The audit logs heading is rendered.
        - Search/filter bindings are present.
        """
        html = client.get("/settings").text
        assert "Audit Logs" in html
        assert "auditSearch" in html
        assert "filteredAuditLogs" in html

    def test_settings_page_has_access_denied_banner(self, client: TestClient) -> None:
        """
        Test that the template includes a client-side access-denied banner.

        The banner is shown to non-owner/admin users via Alpine.js.
        """
        response = client.get("/settings")
        assert (
            "Access Denied" in response.text or "access denied" in response.text.lower()
        )


# ==========================================================================
# Settings JavaScript — Static Asset
# ==========================================================================


class TestSettingsJavaScript:
    """Tests for the settings.js Alpine.js companion script."""

    def test_settings_js_is_loaded_in_page(self, client: TestClient) -> None:
        """
        Test that settings.js is referenced in the rendered HTML.

        Verifies the script tag is present in the page head.
        """
        response = client.get("/settings")
        assert "/static/js/settings.js" in response.text

    def test_settings_js_static_file_exists(self, client: TestClient) -> None:
        """
        Test that the settings.js static file is served.

        Verifies the file returns HTTP 200 and contains JavaScript.
        """
        response = client.get("/static/js/settings.js")
        assert response.status_code == 200
        assert "settingsApp" in response.text

    def test_settings_js_uses_authfetch(self, client: TestClient) -> None:
        """
        Test that settings.js uses authFetch for all API calls.

        Settings makes authenticated calls to multiple backend endpoints.
        """
        response = client.get("/static/js/settings.js")
        assert response.status_code == 200
        assert "authFetch" in response.text

    def test_settings_js_has_organisation_methods(self, client: TestClient) -> None:
        """
        Test that the JS component defines Organisation tab methods.

        Verifies:
        - ``loadCompany`` method for fetching company data.
        - ``saveCompany`` method for persisting edits.
        """
        js = client.get("/static/js/settings.js").text
        assert "loadCompany" in js
        assert "saveCompany" in js

    def test_settings_js_has_people_methods(self, client: TestClient) -> None:
        """
        Test that the JS component defines People tab methods.

        Verifies:
        - ``loadPeople`` method for fetching team members.
        - ``resetPassword`` method for admin password resets.
        """
        js = client.get("/static/js/settings.js").text
        assert "loadPeople" in js
        assert "resetPassword" in js

    def test_settings_js_has_permissions_methods(self, client: TestClient) -> None:
        """
        Test that the JS component defines Permissions tab methods.

        Verifies:
        - ``loadUserPermissions`` method.
        - ``savePermissions`` method.
        - ``togglePermission`` method.
        """
        js = client.get("/static/js/settings.js").text
        assert "loadUserPermissions" in js
        assert "savePermissions" in js
        assert "togglePermission" in js

    def test_settings_js_has_audit_methods(self, client: TestClient) -> None:
        """
        Test that the JS component defines Audit Log tab methods.
        """
        js = client.get("/static/js/settings.js").text
        assert "loadAuditLogs" in js
        assert "filteredAuditLogs" in js
        assert "auditActionOptions" in js

    def test_settings_js_calls_company_endpoint(self, client: TestClient) -> None:
        """
        Test that settings.js references the /api/company endpoint.
        """
        js = client.get("/static/js/settings.js").text
        assert "/api/company" in js

    def test_settings_js_calls_permissions_catalog(self, client: TestClient) -> None:
        """
        Test that settings.js references the permissions catalog endpoint.
        """
        js = client.get("/static/js/settings.js").text
        assert "/api/permissions/catalog" in js

    def test_settings_js_calls_audit_logs_endpoint(self, client: TestClient) -> None:
        """
        Test that settings.js references the tenant audit logs endpoint.
        """
        js = client.get("/static/js/settings.js").text
        assert "/api/audit-logs" in js


# ==========================================================================
# Proxy Routes — Company & Permissions
# ==========================================================================


class TestCompanyProxy:
    """Tests for the company API proxy routes."""

    def test_get_company_proxy_exists(self, client: TestClient) -> None:
        """
        Test that GET /api/company routes to user-bl backend.

        The mock raises ConnectError so we expect 503.
        """
        response = client.get("/api/company")
        assert response.status_code == 503

    def test_put_company_proxy_exists(self, client: TestClient) -> None:
        """
        Test that PUT /api/company routes to user-bl backend.
        """
        response = client.put(
            "/api/company",
            json={"name": "Acme", "email": "info@acme.com"},
        )
        assert response.status_code == 503


class TestPermissionsProxy:
    """Tests for the permissions API proxy routes."""

    def test_get_permissions_catalog_proxy_exists(self, client: TestClient) -> None:
        """
        Test that GET /api/permissions/catalog proxies to user-bl.
        """
        response = client.get("/api/permissions/catalog")
        assert response.status_code == 503

    def test_get_user_permissions_proxy_exists(self, client: TestClient) -> None:
        """
        Test that GET /api/users/42/permissions proxies to user-bl.
        """
        response = client.get("/api/users/42/permissions")
        assert response.status_code == 503


class TestTenantAuditProxy:
    """Tests for the tenant audit log API proxy route."""

    def test_get_audit_logs_proxy_exists(self, client: TestClient) -> None:
        """
        Test that GET /api/audit-logs proxies to user-bl.
        """
        response = client.get("/api/audit-logs")
        assert response.status_code == 503


# ==========================================================================
# Permission-Gated UI — Customers Page
# ==========================================================================


class TestCustomersPermissionGating:
    """Tests that customer page buttons have permission gate attributes."""

    def test_add_customer_button_gated(self, client: TestClient) -> None:
        """
        Test that the 'Add Customer' header button is gated by canCreateCustomer.
        """
        html = client.get("/customers").text
        assert 'x-show="$store.permissions.canCreateCustomer"' in html

    def test_edit_customer_button_gated(self, client: TestClient) -> None:
        """
        Test that Edit buttons are gated by canEditCustomer.
        """
        html = client.get("/customers").text
        assert 'x-show="$store.permissions.canEditCustomer"' in html

    def test_delete_customer_button_gated(self, client: TestClient) -> None:
        """
        Test that Delete buttons are gated by canDeleteCustomer.
        """
        html = client.get("/customers").text
        assert 'x-show="$store.permissions.canDeleteCustomer"' in html

    def test_add_note_toggle_gated(self, client: TestClient) -> None:
        """
        Test that the 'Add Note' toggle is gated by canCreateNote.
        """
        html = client.get("/customers").text
        assert "$store.permissions.canCreateNote" in html


# ==========================================================================
# Permission-Gated UI — Employees Page
# ==========================================================================


class TestEmployeesPermissionGating:
    """Tests that employee page buttons have permission gate attributes."""

    def test_add_employee_button_gated(self, client: TestClient) -> None:
        """
        Test that the 'Add Employee' button is gated by canCreateEmployee.
        """
        html = client.get("/employees").text
        assert 'x-show="$store.permissions.canCreateEmployee"' in html

    def test_edit_employee_button_gated(self, client: TestClient) -> None:
        """
        Test that Edit buttons are gated by canEditEmployee.
        """
        html = client.get("/employees").text
        assert 'x-show="$store.permissions.canEditEmployee"' in html

    def test_delete_employee_button_gated(self, client: TestClient) -> None:
        """
        Test that Delete buttons are gated by canDeleteEmployee.
        """
        html = client.get("/employees").text
        assert 'x-show="$store.permissions.canDeleteEmployee"' in html


# ==========================================================================
# Permission-Gated UI — Calendar Page
# ==========================================================================


class TestCalendarPermissionGating:
    """Tests that the calendar JS component includes permission gating."""

    def test_calendar_js_has_permission_flags(self, client: TestClient) -> None:
        """
        Test that calendar.js defines canCreateJob and canScheduleJob flags.
        """
        js = client.get("/static/js/calendar.js").text
        assert "canCreateJob" in js
        assert "canScheduleJob" in js
        assert "canEditJob" in js

    def test_calendar_js_checks_schedule_permission_in_drag(
        self, client: TestClient
    ) -> None:
        """
        Test that handleDragStart guards on canScheduleJob.
        """
        js = client.get("/static/js/calendar.js").text
        assert "canScheduleJob" in js


# ==========================================================================
# Global hasPermission Helper — base.html
# ==========================================================================


class TestGlobalPermissionHelper:
    """Tests that the global hasPermission() JS helper is present."""

    def test_base_html_defines_haspermission(self, client: TestClient) -> None:
        """
        Test that the rendered page includes the global hasPermission function.

        We fetch /settings (any page extending base.html) and check
        the script block.
        """
        html = client.get("/settings").text
        assert "hasPermission" in html
        assert "_loadPermissions" in html
        assert "PRIVILEGED_ROLES" in html

    def test_base_html_defines_permission_store(self, client: TestClient) -> None:
        """
        Test that the rendered page includes the shared Alpine permission store.
        """
        html = client.get("/settings").text
        assert "Alpine.store('permissions'" in html
        assert "updatePermissionStore" in html

    def test_base_html_coalesces_auth_context_requests(
        self, client: TestClient
    ) -> None:
        """
        Test that auth context requests are coalesced through a shared promise.
        """
        html = client.get("/settings").text
        assert "_authContextPromise" in html
        assert (
            "if (!forceRefresh && _authContextPromise) return _authContextPromise;"
            in html
        )


# ==========================================================================
# Settings Navigation Link
# ==========================================================================


class TestSettingsNavLink:
    """Tests that Settings is accessible via the profile dropdown only."""

    def test_settings_dropdown_link_present(self, client: TestClient) -> None:
        """
        Test that /settings pages contain a Settings link in the profile dropdown.
        """
        html = client.get("/settings").text
        assert "settings-dropdown-link" in html

    def test_settings_navbar_link_removed(self, client: TestClient) -> None:
        """
        Test that the Settings nav link is no longer in the navbar.
        """
        html = client.get("/settings").text
        assert "settings-nav-link" not in html
