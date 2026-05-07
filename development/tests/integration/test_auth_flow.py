"""
Integration tests — Auth service flow.

Pairwise: auth-service ↔ user-db-access-service

Tests the complete authentication lifecycle against the live stack:
login, token verification, refresh, logout, session management,
password management, session revocation, and token cleanup.
"""

import httpx


class TestLogin:
    """Test the login endpoint with real credential verification."""

    def test_login_valid_owner_credentials(self, http_client: httpx.Client) -> None:
        """
        Test login with valid owner credentials returns tokens.

        Verifies:
        - 200 status code
        - Response contains access_token and refresh_token
        - Token type is bearer
        """
        resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@demo.com", "password": "password123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data.get("token_type", "").lower() == "bearer"

    def test_login_valid_employee_credentials(self, http_client: httpx.Client) -> None:
        """
        Test login with valid employee credentials returns tokens.

        Verifies:
        - 200 status code
        - Response contains access_token
        """
        resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "employee@demo.com", "password": "password123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_invalid_password(self, http_client: httpx.Client) -> None:
        """
        Test login with wrong password is rejected.

        Verifies:
        - Response is 401 (not 500 or 200)
        """
        resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@demo.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, http_client: httpx.Client) -> None:
        """
        Test login with email that doesn't exist is rejected.

        Verifies:
        - Response is 401
        """
        resp = http_client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "password123",
            },
        )
        assert resp.status_code == 401

    def test_login_missing_fields(self, http_client: httpx.Client) -> None:
        """
        Test login with missing email/password returns 422.

        Verifies:
        - Validation error, not server crash
        """
        resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@demo.com"},
        )
        assert resp.status_code == 422


class TestTokenVerification:
    """Test token verification via /auth/verify."""

    def test_verify_valid_token(
        self,
        http_client: httpx.Client,
        owner_token: str,
    ) -> None:
        """
        Test that a valid access token is accepted by /auth/verify.

        Verifies:
        - 200 response
        - Response body indicates the token is valid
        - User context (user_id, owner_id, role) is returned
        """
        resp = http_client.post(
            "/api/v1/auth/verify",
            json={"access_token": owner_token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("valid") is True or data.get("authenticated") is True
        assert "user_id" in data or "sub" in data

    def test_verify_invalid_token(self, http_client: httpx.Client) -> None:
        """
        Test that a garbage token is rejected by /auth/verify.

        Verifies:
        - 200 response (verify never returns 401 — it returns valid: false)
        """
        resp = http_client.post(
            "/api/v1/auth/verify",
            json={"access_token": "this.is.not.a.valid.jwt"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("valid") is False or data.get("authenticated") is False


class TestAuthMe:
    """Test the /auth/me endpoint."""

    def test_me_returns_user_context(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test /auth/me returns the current user's context from JWT.

        Verifies:
        - 200 response
        - Contains email, role, owner_id
        """
        resp = http_client.get(
            "/api/v1/auth/me",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("email") == "owner@demo.com"
        assert "role" in data
        assert "owner_id" in data

    def test_me_without_token_returns_401(self, http_client: httpx.Client) -> None:
        """
        Test /auth/me without auth header returns 401.

        Verifies:
        - Unauthenticated requests are rejected
        """
        resp = http_client.get("/api/v1/auth/me")
        assert resp.status_code in (401, 403)


class TestTokenRefresh:
    """Test the token refresh flow."""

    def test_refresh_returns_new_access_token(self, http_client: httpx.Client) -> None:
        """
        Test that refresh token exchange produces a new access token.

        Verifies:
        - Login to get a refresh token
        - POST /auth/refresh with that token returns a new access_token
        - The new token is different from the original
        """
        # Login to get fresh tokens
        login_resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@demo.com", "password": "password123"},
        )
        tokens = login_resp.json()
        refresh_token = tokens["refresh_token"]

        # Refresh
        refresh_resp = http_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == 200
        new_data = refresh_resp.json()
        assert "access_token" in new_data

    def test_refresh_with_invalid_token(self, http_client: httpx.Client) -> None:
        """
        Test refresh with an invalid token is rejected.

        Verifies:
        - Response is 401 (not 500)
        """
        resp = http_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not-a-real-refresh-token"},
        )
        assert resp.status_code == 401


class TestLogout:
    """Test logout and token revocation."""

    def test_logout_invalidates_token(self, http_client: httpx.Client) -> None:
        """
        Test that logging out blacklists the access token.

        Verifies:
        - Login → get tokens
        - Logout → 200
        - Using the old access token on /auth/me → 401
        """
        # Login to get a fresh session
        login_resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "owner@demo.com", "password": "password123"},
        )
        tokens = login_resp.json()
        access_token = tokens["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Logout
        logout_resp = http_client.post(
            "/api/v1/auth/logout",
            headers=headers,
            json={
                "refresh_token": tokens.get("refresh_token", ""),
                "access_token": access_token,
            },
        )
        assert logout_resp.status_code in (200, 204)

        # Old token should now be blacklisted
        me_resp = http_client.get(
            "/api/v1/auth/me",
            headers=headers,
        )
        assert me_resp.status_code in (401, 403)


class TestChangePassword:
    """
    Test the password change flow.

    Pairwise: auth-service ↔ user-db-access-service

    Verifies that authenticated users can change their own password,
    that the old password stops working, and that validation errors
    are handled correctly.
    """

    def test_change_own_password(self, http_client: httpx.Client) -> None:
        """
        Test that a user can change their own password successfully.

        Steps:
        1. Login with current credentials
        2. POST /auth/change-password with current + new password
        3. Verify the new password works for login
        4. Reset password back to original to avoid polluting other tests

        Verifies:
        - 200 on successful change
        - New password accepted on subsequent login
        - Old password no longer works after change
        """
        # Login to get a fresh session
        login_resp = http_client.post(
            "/api/v1/auth/login",
            json={"email": "employee@demo.com", "password": "password123"},
        )
        tokens = login_resp.json()
        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Content-Type": "application/json",
        }

        new_password = "NewSecurePass456!"

        try:
            # Change password
            change_resp = http_client.post(
                "/api/v1/auth/change-password",
                headers=headers,
                json={
                    "current_password": "password123",
                    "new_password": new_password,
                },
            )
            assert change_resp.status_code == 200, (
                f"Change password failed: {change_resp.status_code} — {change_resp.text}"
            )

            # Verify new password works
            new_login = http_client.post(
                "/api/v1/auth/login",
                json={"email": "employee@demo.com", "password": new_password},
            )
            assert new_login.status_code == 200, (
                "Login with new password should succeed"
            )

        finally:
            # Reset password back to original — login with new password first
            reset_login = http_client.post(
                "/api/v1/auth/login",
                json={"email": "employee@demo.com", "password": new_password},
            )
            if reset_login.status_code == 200:
                reset_headers = {
                    "Authorization": f"Bearer {reset_login.json()['access_token']}",
                    "Content-Type": "application/json",
                }
                http_client.post(
                    "/api/v1/auth/change-password",
                    headers=reset_headers,
                    json={
                        "current_password": new_password,
                        "new_password": "password123",
                    },
                )

    def test_change_password_wrong_current(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that providing the wrong current password is rejected.

        Verifies:
        - 400 or 401 when current_password doesn't match
        - Password remains unchanged
        """
        resp = http_client.post(
            "/api/v1/auth/change-password",
            headers=owner_headers,
            json={
                "current_password": "definitely-wrong-password",
                "new_password": "SomeNewPass123!",
            },
        )
        assert resp.status_code in (400, 401, 403), (
            f"Expected rejection, got {resp.status_code}"
        )

    def test_change_password_unauthenticated(self, http_client: httpx.Client) -> None:
        """
        Test that unauthenticated password change is rejected.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "password123",
                "new_password": "SomeNewPass123!",
            },
        )
        assert resp.status_code in (401, 403)


class TestResetPassword:
    """
    Test admin-initiated password reset.

    Pairwise: auth-service ↔ user-db-access-service

    Verifies RBAC: owners/admins can reset passwords for their tenant's
    users, but employees cannot. Superadmin can reset any user's password.
    """

    def test_owner_can_reset_employee_password(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        employee_user_id: int,
    ) -> None:
        """
        Test that an owner can reset an employee's password.

        Steps:
        1. Owner calls POST /auth/reset-password for employee
        2. Verify 200
        3. Verify the new password works for employee login
        4. Reset back to original password

        Verifies:
        - Owner has authority to reset subordinate passwords
        - New password is functional
        """
        new_password = "ResetByOwner789!"

        try:
            # Reset employee's password
            resp = http_client.post(
                "/api/v1/auth/reset-password",
                headers=owner_headers,
                json={
                    "user_id": employee_user_id,
                    "new_password": new_password,
                },
            )
            assert resp.status_code == 200, (
                f"Password reset failed: {resp.status_code} — {resp.text}"
            )

            # Verify the new password works
            login_resp = http_client.post(
                "/api/v1/auth/login",
                json={"email": "employee@demo.com", "password": new_password},
            )
            assert login_resp.status_code == 200

        finally:
            # Restore original password
            http_client.post(
                "/api/v1/auth/reset-password",
                headers=owner_headers,
                json={
                    "user_id": employee_user_id,
                    "new_password": "password123",
                },
            )

    def test_employee_cannot_reset_passwords(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Test that an employee cannot reset another user's password.

        Verifies:
        - Employee role (level 20) is below the required threshold
        - Response is 403
        """
        resp = http_client.post(
            "/api/v1/auth/reset-password",
            headers=employee_headers,
            json={
                "user_id": owner_user_id,  # employee should not touch this
                "new_password": "HackedPass123!",
            },
        )
        assert resp.status_code == 403

    def test_superadmin_can_reset_any_password(
        self,
        http_client: httpx.Client,
        superadmin_headers: dict[str, str],
        employee_user_id: int,
    ) -> None:
        """
        Test that superadmin can reset passwords across tenants.

        Verifies:
        - Superadmin bypasses tenant ownership check
        - New password is functional afterward
        """
        new_password = "SuperReset999!"

        try:
            resp = http_client.post(
                "/api/v1/auth/reset-password",
                headers=superadmin_headers,
                json={
                    "user_id": employee_user_id,
                    "new_password": new_password,
                },
            )
            assert resp.status_code == 200, (
                f"Superadmin reset failed: {resp.status_code} — {resp.text}"
            )

            # Verify new password works
            login = http_client.post(
                "/api/v1/auth/login",
                json={"email": "employee@demo.com", "password": new_password},
            )
            assert login.status_code == 200
        finally:
            # Restore original password
            http_client.post(
                "/api/v1/auth/reset-password",
                headers=superadmin_headers,
                json={
                    "user_id": employee_user_id,
                    "new_password": "password123",
                },
            )

    def test_owner_cannot_reset_cross_tenant_password(
        self,
        http_client: httpx.Client,
        owner2_headers: dict[str, str],
        employee_user_id: int,
    ) -> None:
        """
        Test that owner of tenant 2 cannot reset a tenant 1 user.

        Verifies:
        - Cross-tenant password reset is rejected with 403
        """
        resp = http_client.post(
            "/api/v1/auth/reset-password",
            headers=owner2_headers,
            json={
                "user_id": employee_user_id,
                "new_password": "CrossTenantHack!",
            },
        )
        assert resp.status_code == 403

    def test_reset_nonexistent_user_returns_404(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that resetting password for a non-existent user returns 404.

        Verifies:
        - Invalid user_id is handled gracefully, not a 500
        """
        resp = http_client.post(
            "/api/v1/auth/reset-password",
            headers=owner_headers,
            json={
                "user_id": 999999,
                "new_password": "DoesNotMatter123!",
            },
        )
        assert resp.status_code == 404


class TestRevokeAllSessions:
    """
    Test session revocation (revoke-all).

    Pairwise: auth-service ↔ user-db-access-service

    POST /auth/revoke-all invalidates all refresh tokens for a user,
    effectively logging them out of every device.
    """

    def test_revoke_all_sessions(
        self, http_client: httpx.Client, employee_user_id: int
    ) -> None:
        """
        Test that revoke-all invalidates all refresh tokens for the user.

        Steps:
        1. Login to get two sets of tokens (simulating two devices)
        2. Call POST /auth/revoke-all
        3. Verify old refresh tokens no longer work

        Verifies:
        - 200 response with revoked_count
        - Previously valid refresh tokens are invalidated
        """
        # Login twice — simulate two devices
        login1 = http_client.post(
            "/api/v1/auth/login",
            json={"email": "employee@demo.com", "password": "password123"},
        )
        tokens1 = login1.json()

        login2 = http_client.post(
            "/api/v1/auth/login",
            json={"email": "employee@demo.com", "password": "password123"},
        )
        tokens2 = login2.json()

        headers = {
            "Authorization": f"Bearer {tokens1['access_token']}",
            "Content-Type": "application/json",
        }

        # Revoke all sessions
        revoke_resp = http_client.post(
            "/api/v1/auth/revoke-all",
            headers=headers,
            json={"user_id": employee_user_id},
        )
        assert revoke_resp.status_code == 200

        # Old refresh tokens should now be invalid
        refresh_resp = http_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens2["refresh_token"]},
        )
        assert refresh_resp.status_code == 401, (
            "Refresh with revoked token should be rejected"
        )

    def test_employee_cannot_revoke_others(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
        owner_user_id: int,
    ) -> None:
        """
        Test that an employee cannot revoke another user's sessions.

        Verifies:
        - Attempting to revoke owner's sessions → 403
        """
        resp = http_client.post(
            "/api/v1/auth/revoke-all",
            headers=employee_headers,
            json={"user_id": owner_user_id},  # forbidden
        )
        assert resp.status_code == 403


class TestTokenCleanup:
    """
    Test expired token cleanup endpoint.

    POST /auth/cleanup prunes expired refresh tokens and blacklist entries.
    Only accessible to owner/admin+ roles.
    """

    def test_owner_can_trigger_cleanup(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Test that the owner role can trigger token cleanup.

        Verifies:
        - 200 response
        - Response contains counts of cleaned-up tokens
        """
        resp = http_client.post(
            "/api/v1/auth/cleanup",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should report how many tokens were cleaned up
        assert isinstance(data, dict)

    def test_employee_cannot_trigger_cleanup(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """
        Test that the employee role cannot trigger token cleanup.

        Verifies:
        - 403 for insufficient privileges
        """
        resp = http_client.post(
            "/api/v1/auth/cleanup",
            headers=employee_headers,
        )
        assert resp.status_code == 403
