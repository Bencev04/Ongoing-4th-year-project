"""
Integration tests — GDPR compliance flow.

Tests GDPR-specific endpoints through the BL layer using real auth
tokens and real database operations.

Covers:
    - Privacy consent status retrieval
    - User data export (self-service + admin)
    - User anonymization scheduling and cancellation
    - Customer data export
    - Customer anonymization
    - RBAC enforcement on GDPR endpoints
    - Cross-tenant isolation on admin GDPR operations
"""

import httpx


class TestPrivacyConsentStatus:
    """Test the consent-status endpoint for authenticated users."""

    def test_consent_status_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that consent-status returns 200 with expected fields.

        Verifies:
        - 200 status code
        - Response contains privacy_consent_at, privacy_consent_version,
          anonymize_scheduled_at keys
        """
        resp = http_client.get(
            "/api/v1/users/me/consent-status",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "privacy_consent_at" in data
        assert "privacy_consent_version" in data
        assert "anonymize_scheduled_at" in data

    def test_consent_status_requires_auth(self, http_client: httpx.Client) -> None:
        """
        Test that consent-status requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get("/api/v1/users/me/consent-status")
        assert resp.status_code in (401, 403)

    def test_consent_status_all_roles(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        employee_headers: dict[str, str],
        admin_headers: dict[str, str],
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Test that all authenticated roles can access consent status.

        Verifies:
        - 200 for owner, employee, admin, viewer
        """
        for headers in (owner_headers, employee_headers, admin_headers, viewer_headers):
            resp = http_client.get(
                "/api/v1/users/me/consent-status",
                headers=headers,
            )
            assert resp.status_code == 200


class TestUserDataExportSelf:
    """Test self-service user data export (GDPR Art. 15/20)."""

    def test_export_own_data_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that a user can export their own data.

        Verifies:
        - 200 status code
        - Response contains a 'profile' key with user data
        """
        resp = http_client.get(
            "/api/v1/users/me/export",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data

    def test_export_own_data_contains_expected_sections(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that the export contains expected data sections.

        Verifies:
        - Profile section with email and role
        """
        resp = http_client.get(
            "/api/v1/users/me/export",
            headers=employee_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        profile = data.get("profile", {})
        assert "email" in profile
        assert "role" in profile

    def test_export_requires_auth(self, http_client: httpx.Client) -> None:
        """
        Test that data export requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get("/api/v1/users/me/export")
        assert resp.status_code in (401, 403)


class TestUserDataExportAdmin:
    """Test admin-initiated user data export."""

    def test_admin_export_user_data(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        employee_user_id: int,
    ) -> None:
        """
        Test that an owner can export another user's data.

        Verifies:
        - 200 status code
        - Response contains profile data
        """
        resp = http_client.get(
            f"/api/v1/users/{employee_user_id}/export",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data

    def test_employee_cannot_export_other_user(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Test that a non-admin cannot export another user's data.

        Verifies:
        - 403 for employee trying to export owner data
        """
        resp = http_client.get(
            f"/api/v1/users/{owner_user_id}/export",
            headers=employee_headers,
        )
        assert resp.status_code == 403

    def test_cross_tenant_export_denied(
        self,
        http_client: httpx.Client,
        owner2_headers: dict[str, str],
        employee_user_id: int,
    ) -> None:
        """
        Test that a different-tenant owner cannot export user data.

        Verifies:
        - 403 for cross-tenant access
        """
        resp = http_client.get(
            f"/api/v1/users/{employee_user_id}/export",
            headers=owner2_headers,
        )
        assert resp.status_code == 403


class TestUserAnonymizationSchedule:
    """Test user self-service anonymization scheduling and cancellation."""

    def test_schedule_and_cancel_anonymization(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test the full schedule → cancel cycle for account deletion.

        Verifies:
        - POST schedule returns 200 with anonymize_scheduled_at
        - POST cancel returns 200 and clears the schedule
        - Final consent-status shows no pending anonymization
        """
        # Schedule
        schedule_resp = http_client.post(
            "/api/v1/users/me/anonymize/schedule",
            headers=employee_headers,
        )
        assert schedule_resp.status_code == 200
        schedule_data = schedule_resp.json()
        assert schedule_data.get("anonymize_scheduled_at") is not None

        # Verify consent-status reflects the scheduling
        status_resp = http_client.get(
            "/api/v1/users/me/consent-status",
            headers=employee_headers,
        )
        assert status_resp.status_code == 200
        assert status_resp.json().get("anonymize_scheduled_at") is not None

        # Cancel
        cancel_resp = http_client.post(
            "/api/v1/users/me/anonymize/cancel",
            headers=employee_headers,
        )
        assert cancel_resp.status_code == 200

        # Verify consent-status reflects the cancellation
        status_after = http_client.get(
            "/api/v1/users/me/consent-status",
            headers=employee_headers,
        )
        assert status_after.status_code == 200
        assert status_after.json().get("anonymize_scheduled_at") is None

    def test_cancel_without_schedule_is_safe(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that cancelling a non-existent schedule doesn't fail.

        Verifies:
        - POST cancel returns 200 even with nothing scheduled
        """
        resp = http_client.post(
            "/api/v1/users/me/anonymize/cancel",
            headers=owner_headers,
        )
        assert resp.status_code == 200


class TestAdminUserAnonymize:
    """Test admin-initiated immediate user anonymization."""

    def test_admin_anonymize_requires_owner_role(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Test that employee cannot anonymize another user.

        Verifies:
        - 403 for employee
        """
        resp = http_client.post(
            f"/api/v1/users/{owner_user_id}/anonymize",
            headers=employee_headers,
        )
        assert resp.status_code == 403

    def test_cross_tenant_anonymize_denied(
        self,
        http_client: httpx.Client,
        owner2_headers: dict[str, str],
        employee_user_id: int,
    ) -> None:
        """
        Test that a different-tenant owner cannot anonymize a user.

        Verifies:
        - 403 for cross-tenant access
        """
        resp = http_client.post(
            f"/api/v1/users/{employee_user_id}/anonymize",
            headers=owner2_headers,
        )
        assert resp.status_code == 403


class TestCustomerDataExport:
    """Test customer data export through the BL layer."""

    def _create_test_customer(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> int:
        """Create a disposable customer and return its ID."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "GDPR",
                "last_name": "ExportTest",
                "email": "gdpr-export-test@example.com",
                "phone": "0851111111",
            },
        )
        assert resp.status_code in (200, 201)
        return resp.json().get("id") or resp.json().get("customer_id")

    def test_export_customer_data(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test exporting a customer's data.

        Verifies:
        - 200 status code
        - Response contains profile data with first_name
        """
        cid = self._create_test_customer(http_client, owner_headers)
        try:
            resp = http_client.get(
                f"/api/v1/customers/{cid}/export",
                headers=owner_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "profile" in data
            assert data["profile"].get("first_name") == "GDPR"
        finally:
            # Cleanup
            http_client.delete(
                f"/api/v1/customers/{cid}",
                headers=owner_headers,
            )

    def test_export_requires_auth(self, http_client: httpx.Client) -> None:
        """
        Test that customer export requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get("/api/v1/customers/99999/export")
        assert resp.status_code in (401, 403)

    def test_cross_tenant_export_denied(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Test that a different-tenant owner cannot export customer data.

        Verifies:
        - 403 for cross-tenant access
        """
        cid = self._create_test_customer(http_client, owner_headers)
        try:
            resp = http_client.get(
                f"/api/v1/customers/{cid}/export",
                headers=owner2_headers,
            )
            assert resp.status_code == 403
        finally:
            http_client.delete(
                f"/api/v1/customers/{cid}",
                headers=owner_headers,
            )


class TestCustomerAnonymize:
    """Test customer anonymization through the BL layer."""

    def _create_test_customer(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> int:
        """Create a disposable customer and return its ID."""
        resp = http_client.post(
            "/api/v1/customers/",
            headers=owner_headers,
            json={
                "first_name": "GDPR",
                "last_name": "AnonymizeTest",
                "email": "gdpr-anonymize-test@example.com",
                "phone": "0852222222",
            },
        )
        assert resp.status_code in (200, 201)
        return resp.json().get("id") or resp.json().get("customer_id")

    def test_anonymize_customer(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test anonymizing a customer's personal data.

        Verifies:
        - POST anonymize returns 200
        - After anonymization, GET shows redacted PII
        """
        cid = self._create_test_customer(http_client, owner_headers)

        # Anonymize
        anon_resp = http_client.post(
            f"/api/v1/customers/{cid}/anonymize",
            headers=owner_headers,
        )
        assert anon_resp.status_code == 200

        # Verify anonymization — read the customer back
        get_resp = http_client.get(
            f"/api/v1/customers/{cid}",
            headers=owner_headers,
        )
        if get_resp.status_code == 200:
            customer = get_resp.json()
            # PII should be replaced with anonymized placeholders
            assert customer.get("first_name") != "GDPR"
            assert customer.get("email") != "gdpr-anonymize-test@example.com"

    def test_anonymize_requires_delete_permission(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        viewer_headers: dict[str, str],
    ) -> None:
        """
        Test that viewer cannot anonymize a customer (requires customers.delete).

        Verifies:
        - 403 for viewer
        """
        cid = self._create_test_customer(http_client, owner_headers)
        try:
            resp = http_client.post(
                f"/api/v1/customers/{cid}/anonymize",
                headers=viewer_headers,
            )
            assert resp.status_code == 403
        finally:
            http_client.delete(
                f"/api/v1/customers/{cid}",
                headers=owner_headers,
            )

    def test_cross_tenant_anonymize_denied(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Test that a different-tenant owner cannot anonymize a customer.

        Verifies:
        - 403 for cross-tenant access
        """
        cid = self._create_test_customer(http_client, owner_headers)
        try:
            resp = http_client.post(
                f"/api/v1/customers/{cid}/anonymize",
                headers=owner2_headers,
            )
            assert resp.status_code == 403
        finally:
            http_client.delete(
                f"/api/v1/customers/{cid}",
                headers=owner_headers,
            )


class TestPrivacyConsentUpdate:
    """Test recording privacy consent via user update."""

    def test_record_privacy_consent(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Test recording privacy consent via PUT user update.

        Verifies:
        - PUT returns 200
        - Consent status reflects the recorded consent
        """
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()

        resp = http_client.put(
            f"/api/v1/users/{owner_user_id}",
            headers=owner_headers,
            json={
                "privacy_consent_at": now,
                "privacy_consent_version": "1.0",
            },
        )
        assert resp.status_code == 200

        # Verify via consent-status
        status_resp = http_client.get(
            "/api/v1/users/me/consent-status",
            headers=owner_headers,
        )
        assert status_resp.status_code == 200
        consent = status_resp.json()
        assert consent.get("privacy_consent_at") is not None
        assert consent.get("privacy_consent_version") == "1.0"
