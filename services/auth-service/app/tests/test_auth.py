"""
Unit tests for Auth Service.

Covers token creation, decoding, refresh-token persistence,
revocation, blacklisting, and all API endpoints.

Sync functions (hashing, JWT creation) tested synchronously.
Async functions (DB persistence, revocation) tested with async fixtures.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.auth import (
    blacklist_access_token,
    cleanup_expired_tokens,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
    is_token_blacklisted,
    revoke_all_user_tokens,
    revoke_refresh_token,
    store_refresh_token,
    verify_refresh_token,
)
from app.models.auth import RefreshToken, TokenBlacklist


# ==============================================================================
# Token Hashing  (sync — no DB required)
# ==============================================================================


class TestTokenHashing:
    """Verify SHA-256 token hashing utility."""

    def test_hash_is_deterministic(self) -> None:
        token = "test-token-value"
        assert hash_token(token) == hash_token(token)

    def test_hash_differs_for_different_inputs(self) -> None:
        assert hash_token("token-a") != hash_token("token-b")

    def test_hash_length_is_64_hex_chars(self) -> None:
        assert len(hash_token("anything")) == 64


# ==============================================================================
# Access Token Creation / Decoding  (sync)
# ==============================================================================


class TestAccessToken:
    """Verify JWT access token creation and decoding."""

    def test_create_access_token_returns_three_values(self) -> None:
        token, jti, expires = create_access_token(
            user_id=1, email="a@b.com", role="owner", owner_id=1
        )
        assert isinstance(token, str)
        assert len(jti) == 32
        assert isinstance(expires, datetime)

    def test_decode_valid_token_returns_payload(self) -> None:
        token, _, _ = create_access_token(
            user_id=42, email="user@test.com", role="employee", owner_id=1
        )
        payload = decode_access_token(token)
        assert payload is not None
        assert payload.sub == "42"
        assert payload.email == "user@test.com"
        assert payload.role == "employee"
        assert payload.owner_id == 1

    def test_decode_invalid_token_returns_none(self) -> None:
        assert decode_access_token("not.a.jwt") is None

    def test_decode_expired_token_returns_none(self) -> None:
        token, _, _ = create_access_token(
            user_id=1, email="a@b.com", role="owner", owner_id=1,
            expires_delta=timedelta(seconds=-1),
        )
        assert decode_access_token(token) is None

    def test_custom_expiry_is_honoured(self) -> None:
        delta = timedelta(hours=2)
        _, _, expires = create_access_token(
            user_id=1, email="a@b.com", role="owner", owner_id=1,
            expires_delta=delta,
        )
        expected = datetime.now(timezone.utc) + delta
        # Handle comparison between aware and naive datetimes
        if expires.tzinfo is None:
            expected = expected.replace(tzinfo=None)
        assert abs((expires - expected).total_seconds()) < 5


# ==============================================================================
# Refresh Token Creation  (sync)
# ==============================================================================


class TestRefreshToken:
    """Verify opaque refresh token generation."""

    def test_creates_non_empty_string(self) -> None:
        token = create_refresh_token()
        assert isinstance(token, str) and len(token) > 0

    def test_tokens_are_unique(self) -> None:
        assert create_refresh_token() != create_refresh_token()


# ==============================================================================
# Refresh Token Persistence  (async)
# ==============================================================================


class TestRefreshTokenStorage:
    """Verify async refresh-token storage and verification."""

    async def test_store_refresh_token(
        self, db_session: AsyncSession, sample_user: dict
    ) -> None:
        raw = create_refresh_token()
        row = await store_refresh_token(
            db=db_session,
            user_id=sample_user["id"],
            owner_id=sample_user["owner_id"],
            raw_token=raw,
            device_info="unit-test",
            ip_address="127.0.0.1",
        )
        assert row.id is not None
        assert row.user_id == sample_user["id"]
        assert row.token_hash == hash_token(raw)
        assert row.is_revoked is False

    async def test_verify_valid_refresh_token(
        self, db_session: AsyncSession, stored_refresh_token: tuple
    ) -> None:
        raw_token, db_row = stored_refresh_token
        verified = await verify_refresh_token(db_session, raw_token)
        assert verified is not None
        assert verified.id == db_row.id

    async def test_verify_unknown_token_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        assert await verify_refresh_token(db_session, "does-not-exist") is None

    async def test_verify_revoked_token_returns_none(
        self, db_session: AsyncSession, stored_refresh_token: tuple
    ) -> None:
        raw_token, db_row = stored_refresh_token
        db_row.is_revoked = True
        await db_session.commit()
        assert await verify_refresh_token(db_session, raw_token) is None

    async def test_verify_expired_token_returns_none_and_revokes(
        self, db_session: AsyncSession, sample_user: dict
    ) -> None:
        raw = create_refresh_token()
        row = await store_refresh_token(
            db=db_session,
            user_id=sample_user["id"],
            owner_id=sample_user["owner_id"],
            raw_token=raw,
            expires_days=0,
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db_session.commit()

        assert await verify_refresh_token(db_session, raw) is None
        await db_session.refresh(row)
        assert row.is_revoked is True


# ==============================================================================
# Revocation  (async)
# ==============================================================================


class TestRevocation:
    """Verify single-token and bulk revocation."""

    async def test_revoke_single_token(
        self, db_session: AsyncSession, stored_refresh_token: tuple
    ) -> None:
        raw_token, _ = stored_refresh_token
        assert await revoke_refresh_token(db_session, raw_token) is True

    async def test_revoke_unknown_token_returns_false(
        self, db_session: AsyncSession
    ) -> None:
        assert await revoke_refresh_token(db_session, "nope") is False

    async def test_revoke_all_user_tokens(
        self, db_session: AsyncSession, sample_user: dict
    ) -> None:
        for _ in range(3):
            await store_refresh_token(
                db=db_session,
                user_id=sample_user["id"],
                owner_id=sample_user["owner_id"],
                raw_token=create_refresh_token(),
            )
        count = await revoke_all_user_tokens(db_session, sample_user["id"])
        assert count == 3

    async def test_revoke_all_is_idempotent(
        self, db_session: AsyncSession, sample_user: dict
    ) -> None:
        await store_refresh_token(
            db=db_session,
            user_id=sample_user["id"],
            owner_id=sample_user["owner_id"],
            raw_token=create_refresh_token(),
        )
        await revoke_all_user_tokens(db_session, sample_user["id"])
        assert await revoke_all_user_tokens(db_session, sample_user["id"]) == 0


# ==============================================================================
# Access Token Blacklist  (async, Redis mocked)
# ==============================================================================


class TestBlacklist:
    """Verify access-token blacklisting via DB (Redis is mocked out)."""

    async def test_blacklist_then_check(self, db_session: AsyncSession) -> None:
        jti = "abc123"
        await blacklist_access_token(
            db=db_session,
            jti=jti,
            user_id=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert await is_token_blacklisted(jti, db_session) is True

    async def test_non_blacklisted_jti(self, db_session: AsyncSession) -> None:
        assert await is_token_blacklisted("not-in-list", db_session) is False


# ==============================================================================
# Cleanup  (async)
# ==============================================================================


class TestCleanup:
    """Verify expired token cleanup."""

    async def test_cleanup_removes_expired_rows(
        self, db_session: AsyncSession, sample_user: dict
    ) -> None:
        raw = create_refresh_token()
        row = await store_refresh_token(
            db=db_session,
            user_id=sample_user["id"],
            owner_id=sample_user["owner_id"],
            raw_token=raw,
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await db_session.commit()

        await blacklist_access_token(
            db=db_session,
            jti="old-jti",
            user_id=sample_user["id"],
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        result = await cleanup_expired_tokens(db_session)
        assert result["refresh_tokens_deleted"] >= 1
        assert result["blacklist_entries_deleted"] >= 1

    async def test_cleanup_preserves_active_tokens(
        self, db_session: AsyncSession, stored_refresh_token: tuple
    ) -> None:
        result = await cleanup_expired_tokens(db_session)
        assert result["refresh_tokens_deleted"] == 0


# ==============================================================================
# API Endpoint Tests
# ==============================================================================


class TestHealthEndpoint:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "auth-service"


class TestVerifyEndpoint:
    async def test_verify_valid_token(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        token, _, _ = access_token_for_owner
        response = await client.post(
            "/api/v1/auth/verify", json={"access_token": token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["user_id"] == 1
        assert data["role"] == "owner"

    async def test_verify_invalid_token(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/verify",
            json={"access_token": "garbage.token.here"},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False

    async def test_verify_blacklisted_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        access_token_for_owner: tuple,
    ) -> None:
        token, jti, expires = access_token_for_owner
        await blacklist_access_token(
            db=db_session, jti=jti, user_id=1, expires_at=expires
        )
        response = await client.post(
            "/api/v1/auth/verify", json={"access_token": token}
        )
        data = response.json()
        assert data["valid"] is False
        assert "revoked" in data["message"].lower()


class TestRefreshEndpoint:
    async def test_refresh_with_valid_token(
        self, client: AsyncClient, stored_refresh_token: tuple
    ) -> None:
        raw_token, _ = stored_refresh_token
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": raw_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_with_invalid_token(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not-a-real-token"},
        )
        assert response.status_code == 401


class TestLogoutEndpoint:
    async def test_logout_revokes_refresh_token(
        self, client: AsyncClient, stored_refresh_token: tuple
    ) -> None:
        raw_token, _ = stored_refresh_token
        response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": raw_token}
        )
        assert response.status_code == 204
        # Refreshing with the same token should now fail
        refresh_resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": raw_token}
        )
        assert refresh_resp.status_code == 401

    async def test_logout_with_unknown_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": "does-not-exist"},
        )
        assert response.status_code == 401


class TestMeEndpoint:
    async def test_me_with_valid_token(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        token, _, _ = access_token_for_owner
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["user_id"] == 1

    async def test_me_without_token_returns_401(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401


class TestRevokeAllEndpoint:
    async def test_owner_can_revoke_all(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        access_token_for_owner: tuple,
        sample_user: dict,
    ) -> None:
        for _ in range(2):
            await store_refresh_token(
                db=db_session,
                user_id=sample_user["id"],
                owner_id=sample_user["owner_id"],
                raw_token=create_refresh_token(),
            )
        token, _, _ = access_token_for_owner
        response = await client.post(
            "/api/v1/auth/revoke-all",
            json={"user_id": sample_user["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["revoked_count"] >= 2

    async def test_employee_cannot_revoke_others(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        token, _, _ = access_token_for_employee
        response = await client.post(
            "/api/v1/auth/revoke-all",
            json={"user_id": 999},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ==============================================================================
# Token Security Edge Cases
# ==============================================================================


class TestTokenSecurityEdgeCases:
    """Verify resilience against manipulated/forged tokens."""

    def test_token_with_manipulated_payload_fails(self) -> None:
        token, _, _ = create_access_token(
            user_id=1, email="a@b.com", role="employee", owner_id=1
        )
        parts = token.split(".")
        if len(parts) == 3:
            modified = f"{parts[0]}.{parts[1][:-1]}X.{parts[2]}"
            assert decode_access_token(modified) is None

    def test_token_with_none_signature_fails(self) -> None:
        token, _, _ = create_access_token(
            user_id=1, email="a@b.com", role="owner", owner_id=1
        )
        parts = token.split(".")
        if len(parts) == 3:
            assert decode_access_token(f"{parts[0]}.{parts[1]}.") is None


# ==============================================================================
# Multi-Tenant Token Isolation
# ==============================================================================


class TestMultiTenantTokenIsolation:
    """Verify tokens carry correct tenant context."""

    def test_token_contains_owner_id(self) -> None:
        token, _, _ = create_access_token(
            user_id=5, email="emp@tenant1.com", role="employee", owner_id=100
        )
        payload = decode_access_token(token)
        assert payload is not None
        assert payload.owner_id == 100

    async def test_revoke_all_respects_user_boundaries(
        self, db_session: AsyncSession
    ) -> None:
        t1_raw = create_refresh_token()
        await store_refresh_token(
            db=db_session, user_id=1, owner_id=1, raw_token=t1_raw
        )
        t2_raw = create_refresh_token()
        await store_refresh_token(
            db=db_session, user_id=2, owner_id=2, raw_token=t2_raw
        )

        await revoke_all_user_tokens(db_session, user_id=1)

        assert await verify_refresh_token(db_session, t1_raw) is None
        assert await verify_refresh_token(db_session, t2_raw) is not None


# ==============================================================================
# Login Validation
# ==============================================================================


class TestLoginSecurityMeasures:
    async def test_login_with_empty_email_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "", "password": "anything123"},
        )
        assert response.status_code == 422

    async def test_login_happy_path_returns_tokens(
        self, client: AsyncClient
    ) -> None:
        """Successful login must return access + refresh tokens with correct claims."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "owner@demo.com", "password": "password123"},
        )
        assert response.status_code == 200
        data = response.json()

        # Must contain both token types
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

        # Must echo back user context
        assert data["user_id"] == 1
        assert data["role"] == "owner"
        assert data["owner_id"] == 1

        # Access token must be a valid, decodable JWT
        from jose import jwt as jose_jwt
        from common.config import settings

        payload = jose_jwt.decode(
            data["access_token"],
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        assert payload["sub"] == "1"
        assert payload["email"] == "owner@demo.com"
        assert payload["role"] == "owner"
        assert payload["owner_id"] == 1
        assert payload["token_type"] == "access"

    async def test_login_with_invalid_credentials_returns_401(
        self, client: AsyncClient, _mock_httpx_client,
    ) -> None:
        """Failed authentication must return 401."""
        from unittest.mock import MagicMock
        import httpx

        # Override the autouse mock to return authenticated=False
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"authenticated": False}

        import app.api.routes as routes_mod
        original_client = routes_mod._http_client
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        routes_mod._http_client = mock_client

        try:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "wrong@demo.com", "password": "badpassword"},
            )
            assert response.status_code == 401
            assert "Invalid" in response.json()["detail"]
        finally:
            routes_mod._http_client = original_client


# ==============================================================================
# Cleanup Endpoint Tests
# ==============================================================================


class TestCleanupEndpoint:
    """Test suite for POST /api/v1/auth/cleanup endpoint."""

    @pytest.mark.asyncio
    async def test_owner_can_trigger_cleanup(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        """
        Test that an owner can trigger token cleanup.

        Verifies:
        - Cleanup endpoint returns 200.
        - Response contains refresh_tokens_deleted and blacklist_entries_deleted.
        """
        token, _, _ = access_token_for_owner
        response = await client.post(
            "/api/v1/auth/cleanup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "refresh_tokens_deleted" in data
        assert "blacklist_entries_deleted" in data

    @pytest.mark.asyncio
    async def test_superadmin_can_trigger_cleanup(
        self, client: AsyncClient, access_token_for_superadmin: tuple
    ) -> None:
        """
        Test that a superadmin can trigger token cleanup via role hierarchy.

        Verifies:
        - Superadmin (role level 100) passes require_role("owner", "admin") check.
        - Returns 200 with cleanup counts.
        """
        token, _, _ = access_token_for_superadmin
        response = await client.post(
            "/api/v1/auth/cleanup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "refresh_tokens_deleted" in data

    @pytest.mark.asyncio
    async def test_employee_cannot_trigger_cleanup(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """
        Test that an employee is forbidden from triggering cleanup.

        Verifies:
        - Employee role (level 20) is below owner (level 80).
        - Returns 403.
        """
        token, _, _ = access_token_for_employee
        response = await client.post(
            "/api/v1/auth/cleanup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_trigger_cleanup(self, client: AsyncClient) -> None:
        """
        Test that a viewer role is forbidden from triggering cleanup.
        """
        token, _, _ = create_access_token(
            user_id=99, email="viewer@demo.com", role="viewer",
            owner_id=1, company_id=1, organization_id=None,
        )
        response = await client.post(
            "/api/v1/auth/cleanup",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cleanup_without_auth_returns_401(self, client: AsyncClient) -> None:
        """Test that cleanup requires authentication."""
        response = await client.post("/api/v1/auth/cleanup")
        assert response.status_code == 401


# ==============================================================================
# Login Edge Cases
# ==============================================================================


class TestLoginEdgeCases:
    """Test edge cases for the login endpoint."""

    @pytest.mark.asyncio
    async def test_login_with_missing_password_returns_422(
        self, client: AsyncClient
    ) -> None:
        """Test that missing password field returns 422 validation error."""
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@demo.com"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_service_unavailable_returns_503(
        self, client: AsyncClient
    ) -> None:
        """
        Test that login returns 503 when user-db-access service is down.
        """
        import httpx as _httpx
        from unittest.mock import AsyncMock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        mock_client.post.side_effect = _httpx.ConnectError("Connection refused")
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@demo.com", "password": "password123"},
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Impersonation Edge Cases
# ==============================================================================


class TestImpersonationEdgeCases:
    """Test impersonation edge cases."""

    @pytest.mark.asyncio
    async def test_impersonate_nonexistent_user_returns_404(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple,
    ) -> None:
        """Test impersonation of a user that doesn't exist returns 404."""
        from unittest.mock import AsyncMock
        from app.api import routes as routes_mod

        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"detail": "User not found"}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_superadmin
            response = await client.post(
                "/api/v1/auth/impersonate",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_user_id": 99999, "reason": "testing"},
            )
            assert response.status_code == 404
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_impersonate_service_unavailable_returns_503(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple,
    ) -> None:
        """Test impersonation returns 503 when user service is down."""
        import httpx as _httpx
        from unittest.mock import AsyncMock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        mock_client.get.side_effect = _httpx.ConnectError("Connection refused")
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_superadmin
            response = await client.post(
                "/api/v1/auth/impersonate",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_user_id": 5, "reason": "testing"},
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Revoke-All Edge Cases
# ==============================================================================


class TestRevokeAllEdgeCases:
    """Test revoke-all edge cases."""

    @pytest.mark.asyncio
    async def test_employee_can_revoke_own_sessions(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """Test that an employee can revoke their own sessions."""
        token, _, _ = access_token_for_employee
        response = await client.post(
            "/api/v1/auth/revoke-all",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": 2},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_revoke_all_without_auth_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Test that revoke-all requires authentication."""
        response = await client.post(
            "/api/v1/auth/revoke-all",
            json={"user_id": 1},
        )
        assert response.status_code == 401


# ==============================================================================
# Password Change Tests
# ==============================================================================


class TestPasswordChangeEndpoint:
    """Test password change functionality."""

    @pytest.mark.asyncio
    async def test_change_password_success(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """Test successful password change."""
        import httpx as _httpx
        from unittest.mock import AsyncMock, Mock
        from app.api import routes as routes_mod

        # Mock the HTTP calls to user-db-access-service
        mock_client = AsyncMock()
        
        # Mock authentication verification (current password correct)
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json = Mock(return_value={"authenticated": True, "user_id": 2})
        
        # Mock password update
        update_response = Mock()
        update_response.status_code = 200
        update_response.json = Mock(return_value={"id": 2, "email": "employee@demo.com"})
        
        mock_client.post.return_value = auth_response
        mock_client.put.return_value = update_response
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_employee
            response = await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "password123",
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Password changed successfully"
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_change_password_incorrect_current_password(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """Test password change with incorrect current password returns 401."""
        import httpx as _httpx
        from unittest.mock import AsyncMock, Mock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        
        # Mock authentication verification (current password incorrect)
        auth_response = Mock()
        auth_response.status_code = 200
        auth_response.json = Mock(return_value={"authenticated": False})
        mock_client.post.return_value = auth_response
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_employee
            response = await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "wrongpassword",
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 401
            data = response.json()
            assert "incorrect" in data["detail"].lower()
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_change_password_without_auth_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Test that password change requires authentication."""
        response = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "password123",
                "new_password": "newpassword456",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_change_password_service_unavailable_returns_503(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """Test password change returns 503 when user service is down."""
        import httpx as _httpx
        from unittest.mock import AsyncMock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        mock_client.post.side_effect = _httpx.ConnectError("Connection refused")
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_employee
            response = await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "password123",
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_change_password_short_password_returns_422(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """Test password change with too short password returns 422."""
        token, _, _ = access_token_for_employee
        response = await client.post(
            "/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "password123",
                "new_password": "short",  # Less than 8 characters
            },
        )
        assert response.status_code == 422


# ==============================================================================
# Password Reset Tests (Admin)
# ==============================================================================


class TestPasswordResetEndpoint:
    """Test password reset functionality for admins."""

    @pytest.mark.asyncio
    async def test_owner_can_reset_employee_password(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        """Test owner can reset password for employee in their organization."""
        import httpx as _httpx
        from unittest.mock import AsyncMock, Mock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        
        # Mock getting target user (employee in same org)
        user_response = Mock()
        user_response.status_code = 200
        user_response.json = Mock(return_value={"id": 2, "owner_id": 1, "email": "employee@demo.com"})
        
        # Mock password update
        update_response = Mock()
        update_response.status_code = 200
        update_response.json = Mock(return_value={"id": 2})
        
        mock_client.get.return_value = user_response
        mock_client.put.return_value = update_response
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_owner
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "user_id": 2,
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Password reset successfully"
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_owner_cannot_reset_password_in_other_org(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        """Test owner cannot reset password for user in different organization."""
        import httpx as _httpx
        from unittest.mock import AsyncMock, Mock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        
        # Mock getting target user (different org)
        user_response = Mock()
        user_response.status_code = 200
        user_response.json = Mock(return_value={"id": 5, "owner_id": 99, "email": "other@org.com"})
        
        mock_client.get.return_value = user_response
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_owner
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "user_id": 5,
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 403
            data = response.json()
            assert "different organization" in data["detail"].lower()
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_superadmin_can_reset_any_password(
        self, client: AsyncClient, access_token_for_superadmin: tuple
    ) -> None:
        """Test superadmin can reset password for any user."""
        import httpx as _httpx
        from unittest.mock import AsyncMock, Mock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        
        # Mock getting target user (any org)
        user_response = Mock()
        user_response.status_code = 200
        user_response.json = Mock(return_value={"id": 5, "owner_id": 99, "email": "anyuser@anyorg.com"})
        
        # Mock password update
        update_response = Mock()
        update_response.status_code = 200
        update_response.json = Mock(return_value={"id": 5})
        
        mock_client.get.return_value = user_response
        mock_client.put.return_value = update_response
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_superadmin
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "user_id": 5,
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Password reset successfully"
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_employee_cannot_reset_password(
        self, client: AsyncClient, access_token_for_employee: tuple
    ) -> None:
        """Test employee cannot reset passwords (requires admin role)."""
        token, _, _ = access_token_for_employee
        response = await client.post(
            "/api/v1/auth/reset-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": 1,
                "new_password": "newpassword456",
            },
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        """Test password reset returns 404 for nonexistent user."""
        import httpx as _httpx
        from unittest.mock import AsyncMock, Mock
        from app.api import routes as routes_mod

        mock_client = AsyncMock()
        
        # Mock user not found
        user_response = Mock()
        user_response.status_code = 404
        mock_client.get.return_value = user_response
        
        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            token, _, _ = access_token_for_owner
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "user_id": 99999,
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 404
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_reset_password_without_auth_returns_401(
        self, client: AsyncClient
    ) -> None:
        """Test that password reset requires authentication."""
        response = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "user_id": 2,
                "new_password": "newpassword456",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_password_short_password_returns_422(
        self, client: AsyncClient, access_token_for_owner: tuple
    ) -> None:
        """Test password reset with too short password returns 422."""
        token, _, _ = access_token_for_owner
        response = await client.post(
            "/api/v1/auth/reset-password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_id": 2,
                "new_password": "short",  # Less than 8 characters
            },
        )
        assert response.status_code == 422
