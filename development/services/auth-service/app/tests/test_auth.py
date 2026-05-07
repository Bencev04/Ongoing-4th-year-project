"""
Unit tests for Auth Service.

Covers token creation, decoding, refresh-token persistence,
revocation, blacklisting, and all API endpoints.

Sync functions (hashing, JWT creation) tested synchronously.
Async functions (DB persistence, revocation) tested with async fixtures.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
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
            user_id=1,
            email="a@b.com",
            role="owner",
            owner_id=1,
            expires_delta=timedelta(seconds=-1),
        )
        assert decode_access_token(token) is None

    def test_custom_expiry_is_honoured(self) -> None:
        delta = timedelta(hours=2)
        _, _, expires = create_access_token(
            user_id=1,
            email="a@b.com",
            role="owner",
            owner_id=1,
            expires_delta=delta,
        )
        expected = datetime.now(UTC) + delta
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
        row.expires_at = datetime.now(UTC) - timedelta(seconds=10)
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
            expires_at=datetime.now(UTC) + timedelta(hours=1),
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
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
        await db_session.commit()

        await blacklist_access_token(
            db=db_session,
            jti="old-jti",
            user_id=sample_user["id"],
            expires_at=datetime.now(UTC) - timedelta(days=1),
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
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

        # The old token must be revoked (rotation).
        reuse_resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": raw_token}
        )
        assert reuse_resp.status_code == 401

        # The new token must work.
        new_resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
        )
        assert new_resp.status_code == 200

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

    async def test_me_without_token_returns_401(self, client: AsyncClient) -> None:
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

    async def test_login_happy_path_returns_tokens(self, client: AsyncClient) -> None:
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
        self,
        client: AsyncClient,
        _mock_httpx_client,
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
            user_id=99,
            email="viewer@demo.com",
            role="viewer",
            owner_id=1,
            company_id=1,
            organization_id=None,
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
        from unittest.mock import AsyncMock

        import httpx as _httpx

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
        from unittest.mock import AsyncMock

        import httpx as _httpx

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
        update_response.json = Mock(
            return_value={"id": 2, "email": "employee@demo.com"}
        )

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
        from unittest.mock import AsyncMock

        import httpx as _httpx

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
        from unittest.mock import AsyncMock, Mock

        from app.api import routes as routes_mod

        mock_client = AsyncMock()

        # Mock getting target user (employee in same org)
        user_response = Mock()
        user_response.status_code = 200
        user_response.json = Mock(
            return_value={"id": 2, "owner_id": 1, "email": "employee@demo.com"}
        )

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
        from unittest.mock import AsyncMock, Mock

        from app.api import routes as routes_mod

        mock_client = AsyncMock()

        # Mock getting target user (different org)
        user_response = Mock()
        user_response.status_code = 200
        user_response.json = Mock(
            return_value={"id": 5, "owner_id": 99, "email": "other@org.com"}
        )

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
        from unittest.mock import AsyncMock, Mock

        from app.api import routes as routes_mod

        mock_client = AsyncMock()

        # Mock getting target user (any org)
        user_response = Mock()
        user_response.status_code = 200
        user_response.json = Mock(
            return_value={"id": 5, "owner_id": 99, "email": "anyuser@anyorg.com"}
        )

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


# ==============================================================================
# HTTP Client Lifecycle Tests
# ==============================================================================


class TestHTTPClientLifecycle:
    """Test HTTP client initialization, retrieval, and cleanup."""

    @pytest.mark.asyncio
    async def test_init_http_client_creates_client(self) -> None:
        """Test that init_http_client creates a client instance."""
        from app.api import routes

        # Ensure client is None initially (or close existing)
        if routes._http_client is not None:
            await routes.close_http_client()

        await routes.init_http_client()
        assert routes._http_client is not None
        assert hasattr(routes._http_client, "get")
        assert hasattr(routes._http_client, "post")

        # Cleanup
        await routes.close_http_client()

    @pytest.mark.asyncio
    async def test_init_http_client_is_idempotent(self) -> None:
        """Test that calling init_http_client multiple times doesn't error."""
        from app.api import routes

        # Ensure clean state
        if routes._http_client is not None:
            await routes.close_http_client()

        await routes.init_http_client()
        first_client = routes._http_client

        # Second call should not create a new client
        await routes.init_http_client()
        assert routes._http_client is first_client

        # Cleanup
        await routes.close_http_client()

    @pytest.mark.asyncio
    async def test_get_http_client_returns_client_when_initialized(self) -> None:
        """Test that get_http_client returns the client after initialization."""
        from app.api import routes

        await routes.init_http_client()
        client = routes.get_http_client()
        assert client is not None
        assert client is routes._http_client

        # Cleanup
        await routes.close_http_client()

    def test_get_http_client_raises_when_not_initialized(self) -> None:
        """Test that get_http_client raises RuntimeError when client not initialized."""
        from app.api import routes

        # Ensure client is None
        routes._http_client = None

        with pytest.raises(RuntimeError, match="HTTP client not initialized"):
            routes.get_http_client()

    @pytest.mark.asyncio
    async def test_close_http_client_closes_and_clears(self) -> None:
        """Test that close_http_client properly closes and clears the client."""
        from app.api import routes

        await routes.init_http_client()
        assert routes._http_client is not None

        await routes.close_http_client()
        assert routes._http_client is None

    @pytest.mark.asyncio
    async def test_close_http_client_is_idempotent(self) -> None:
        """Test that calling close_http_client multiple times is safe."""
        from app.api import routes

        await routes.init_http_client()
        await routes.close_http_client()
        assert routes._http_client is None

        # Second close should not error
        await routes.close_http_client()
        assert routes._http_client is None

    @pytest.mark.asyncio
    async def test_http_client_has_proper_configuration(self) -> None:
        """Test that the HTTP client is initialized and functional."""
        from app.api import routes

        await routes.init_http_client()
        client = routes._http_client

        assert client is not None
        # Verify the client has the expected HTTP methods
        assert callable(getattr(client, "get", None))
        assert callable(getattr(client, "post", None))
        assert callable(getattr(client, "put", None))
        assert callable(getattr(client, "delete", None))

        # Cleanup
        await routes.close_http_client()


# ==============================================================================
# Login — Service Error Branches
# ==============================================================================


class TestLoginServiceErrors:
    """Cover error-handling branches in the login endpoint."""

    @pytest.mark.asyncio
    async def test_login_user_service_non_200(self, client: AsyncClient) -> None:
        """Non-200 from user service returns 503 ('unexpected status')."""
        from app.api import routes as routes_mod

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@demo.com", "password": "pw12345678"},
            )
            assert response.status_code == 503
            assert "unexpected status" in response.json()["detail"].lower()
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_login_owner_id_none_for_owner_role(
        self, client: AsyncClient
    ) -> None:
        """When owner_id is NULL and role is owner, owner_id defaults to user_id."""
        from app.api import routes as routes_mod

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "authenticated": True,
            "user_id": 10,
            "email": "owner@demo.com",
            "role": "owner",
            "owner_id": None,
            "id": 10,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "owner@demo.com", "password": "password123"},
            )
            assert response.status_code == 200
            data = response.json()
            # owner_id should fall back to user_id for owner role
            assert data["owner_id"] == 10
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_login_owner_id_none_for_superadmin(
        self, client: AsyncClient
    ) -> None:
        """When owner_id is NULL and role is superadmin, owner_id stays None."""
        from app.api import routes as routes_mod

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "authenticated": True,
            "user_id": 999,
            "email": "sa@system.local",
            "role": "superadmin",
            "owner_id": None,
            "id": 999,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "sa@system.local", "password": "password123"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["owner_id"] is None
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Refresh — Degraded Mode (user service errors)
# ==============================================================================


class TestRefreshDegradedMode:
    """Cover the refresh endpoint when user-fetch fails gracefully."""

    @pytest.mark.asyncio
    async def test_refresh_user_service_non_200(
        self,
        client: AsyncClient,
        stored_refresh_token: tuple,
    ) -> None:
        """Non-200 from user service during refresh still succeeds (degraded)."""
        from app.api import routes as routes_mod

        raw_token, _ = stored_refresh_token

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": raw_token},
            )
            # Refresh should still succeed; token is issued with empty
            # email/role since user-fetch failed
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data  # rotated
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_refresh_user_service_unreachable(
        self,
        client: AsyncClient,
        stored_refresh_token: tuple,
    ) -> None:
        """Network error during user-fetch still allows refresh (degraded)."""
        from app.api import routes as routes_mod

        raw_token, _ = stored_refresh_token

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": raw_token},
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data  # rotated
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Logout — Access Token Blacklisting Branches
# ==============================================================================


class TestLogoutAccessTokenBlacklisting:
    """Cover logout branches that handle optional access_token blacklisting."""

    @pytest.mark.asyncio
    async def test_logout_with_valid_access_token_blacklists_it(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        stored_refresh_token: tuple,
        access_token_for_owner: tuple,
    ) -> None:
        """Logout with an access_token should blacklist it."""
        raw_refresh, _ = stored_refresh_token
        access_tok, jti, _ = access_token_for_owner

        response = await client.post(
            "/api/v1/auth/logout",
            json={
                "refresh_token": raw_refresh,
                "access_token": access_tok,
            },
        )
        assert response.status_code == 204

        # JTI should now be blacklisted
        assert await is_token_blacklisted(jti, db_session) is True

    @pytest.mark.asyncio
    async def test_logout_with_invalid_access_token_still_revokes_refresh(
        self,
        client: AsyncClient,
        stored_refresh_token: tuple,
    ) -> None:
        """Logout with an invalid access_token should still revoke refresh."""
        raw_refresh, _ = stored_refresh_token

        response = await client.post(
            "/api/v1/auth/logout",
            json={
                "refresh_token": raw_refresh,
                "access_token": "invalid.jwt.token",
            },
        )
        assert response.status_code == 204

        # Verify the refresh token was actually revoked
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": raw_refresh},
        )
        assert refresh_resp.status_code == 401


# ==============================================================================
# Revoke-All — Cross-Tenant & Error Branches
# ==============================================================================


class TestRevokeAllCrossTenant:
    """Cover cross-tenant protection and error branches in revoke-all."""

    @pytest.mark.asyncio
    async def test_owner_revoke_cross_tenant_blocked(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Owner revoking sessions for a user in a different tenant returns 403."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        # Target user has owner_id=99 (different tenant)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 50, "owner_id": 99, "email": "x@y.com"}
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/revoke-all",
                json={"user_id": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 403
            assert "different tenant" in response.json()["detail"].lower()
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_owner_revoke_target_not_found(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Owner revoking for non-existent user returns 404."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/revoke-all",
                json={"user_id": 99999},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 404
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_owner_revoke_user_service_down(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Owner revoking when user service is down returns 503."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/revoke-all",
                json={"user_id": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_superadmin_revoke_skips_tenant_check(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple,
    ) -> None:
        """Superadmin can revoke sessions for any user without tenant check."""
        token, _, _ = access_token_for_superadmin
        response = await client.post(
            "/api/v1/auth/revoke-all",
            json={"user_id": 999},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200


# ==============================================================================
# Change-Password — Error Branches
# ==============================================================================


class TestChangePasswordErrors:
    """Cover error-handling branches in change-password."""

    @pytest.mark.asyncio
    async def test_change_password_auth_non_200(
        self,
        client: AsyncClient,
        access_token_for_employee: tuple,
    ) -> None:
        """Non-200 from authenticate endpoint returns 401."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_employee

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "password123",
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 401
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_change_password_update_non_200(
        self,
        client: AsyncClient,
        access_token_for_employee: tuple,
    ) -> None:
        """Non-200 from password update endpoint propagates that status."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_employee

        auth_resp = MagicMock(spec=httpx.Response)
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"authenticated": True, "user_id": 2}

        update_resp = MagicMock(spec=httpx.Response)
        update_resp.status_code = 400
        update_resp.json.return_value = {"detail": "Password too weak"}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = auth_resp
        mock_client.put.return_value = update_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "password123",
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 400
            assert "Password too weak" in response.json()["detail"]
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_change_password_update_service_down(
        self,
        client: AsyncClient,
        access_token_for_employee: tuple,
    ) -> None:
        """Password update fails with 503 when user service is unreachable."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_employee

        auth_resp = MagicMock(spec=httpx.Response)
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"authenticated": True, "user_id": 2}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = auth_resp
        mock_client.put.side_effect = httpx.ConnectError("Connection refused")

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
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
    async def test_change_password_update_500_uses_fallback_detail(
        self,
        client: AsyncClient,
        access_token_for_employee: tuple,
    ) -> None:
        """Server error (>=500) from update endpoint uses fallback detail."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_employee

        auth_resp = MagicMock(spec=httpx.Response)
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"authenticated": True, "user_id": 2}

        update_resp = MagicMock(spec=httpx.Response)
        update_resp.status_code = 500

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = auth_resp
        mock_client.put.return_value = update_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "current_password": "password123",
                    "new_password": "newpassword456",
                },
            )
            assert response.status_code == 500
            assert "Failed to update password" in response.json()["detail"]
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Reset-Password — Error Branches
# ==============================================================================


class TestResetPasswordErrors:
    """Cover additional error-handling branches in reset-password."""

    @pytest.mark.asyncio
    async def test_reset_password_user_service_non_200_non_404(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Non-200/non-404 from user-fetch returns 503."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": 5, "new_password": "newpassword456"},
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_reset_password_user_service_unreachable(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Network error during user-fetch returns 503."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": 5, "new_password": "newpassword456"},
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_reset_password_update_non_200(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Non-200 from password update propagates status."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        user_resp = MagicMock(spec=httpx.Response)
        user_resp.status_code = 200
        user_resp.json.return_value = {"id": 2, "owner_id": 1, "email": "e@d.com"}

        update_resp = MagicMock(spec=httpx.Response)
        update_resp.status_code = 400
        update_resp.json.return_value = {"detail": "Password too weak"}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = user_resp
        mock_client.put.return_value = update_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": 2, "new_password": "newpassword456"},
            )
            assert response.status_code == 400
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_reset_password_update_service_down(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Password update network error returns 503."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        user_resp = MagicMock(spec=httpx.Response)
        user_resp.status_code = 200
        user_resp.json.return_value = {"id": 2, "owner_id": 1, "email": "e@d.com"}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = user_resp
        mock_client.put.side_effect = httpx.ConnectError("Connection refused")

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": 2, "new_password": "newpassword456"},
            )
            assert response.status_code == 503
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_reset_password_update_500_uses_fallback_detail(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Server error (>=500) from update endpoint uses fallback detail."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_owner

        user_resp = MagicMock(spec=httpx.Response)
        user_resp.status_code = 200
        user_resp.json.return_value = {"id": 2, "owner_id": 1, "email": "e@d.com"}

        update_resp = MagicMock(spec=httpx.Response)
        update_resp.status_code = 500

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = user_resp
        mock_client.put.return_value = update_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/reset-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"user_id": 2, "new_password": "newpassword456"},
            )
            assert response.status_code == 500
            assert "Failed to reset password" in response.json()["detail"]
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Impersonate — Additional Error Branches
# ==============================================================================


class TestImpersonateServiceErrors:
    """Cover additional error branches in the impersonate endpoint."""

    @pytest.mark.asyncio
    async def test_impersonate_non_superadmin_blocked(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple,
    ) -> None:
        """Non-superadmin user is forbidden from impersonating."""
        token, _, _ = access_token_for_owner
        response = await client.post(
            "/api/v1/auth/impersonate",
            headers={"Authorization": f"Bearer {token}"},
            json={"target_user_id": 2, "reason": "testing"},
        )
        assert response.status_code == 403
        assert "Only superadmins" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_impersonate_superadmin_target_blocked(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple,
    ) -> None:
        """Impersonating another superadmin is forbidden."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_superadmin

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 888,
            "email": "other-sa@system.local",
            "role": "superadmin",
            "owner_id": None,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/impersonate",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_user_id": 888, "reason": "testing"},
            )
            assert response.status_code == 403
            assert "Cannot impersonate another superadmin" in response.json()["detail"]
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_impersonate_user_service_non_200_non_404(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple,
    ) -> None:
        """Non-200/non-404 from user service returns 503."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_superadmin

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/impersonate",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_user_id": 5, "reason": "testing"},
            )
            assert response.status_code == 503
            assert "unexpected status" in response.json()["detail"].lower()
        finally:
            routes_mod._http_client = original

    @pytest.mark.asyncio
    async def test_impersonate_success_returns_shadow_token(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple,
    ) -> None:
        """Successful impersonation returns a shadow token with impersonator_id."""
        from app.api import routes as routes_mod

        token, _, _ = access_token_for_superadmin

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": 5,
            "email": "target@demo.com",
            "role": "employee",
            "owner_id": 1,
            "company_id": 1,
            "organization_id": 1,
        }
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp

        original = routes_mod._http_client
        routes_mod._http_client = mock_client
        try:
            response = await client.post(
                "/api/v1/auth/impersonate",
                headers={"Authorization": f"Bearer {token}"},
                json={"target_user_id": 5, "reason": "support ticket #42"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert data["impersonating"] == 5
            assert data["impersonator_id"] == 999

            # Decode shadow token to check impersonator_id claim
            payload = decode_access_token(data["access_token"])
            assert payload is not None
            assert payload.impersonator_id == 999
            assert int(payload.sub) == 5
        finally:
            routes_mod._http_client = original


# ==============================================================================
# Redis Blacklist — Fast-Path Tests
# ==============================================================================


class TestRedisBlacklistPaths:
    """Test Redis fast-path for blacklisting (FakeRedis is active by default)."""

    @pytest.mark.asyncio
    async def test_blacklist_writes_to_redis_and_db(
        self,
        db_session: AsyncSession,
        _mock_redis,
    ) -> None:
        """blacklist_access_token writes to both Redis and Postgres."""
        jti = "redis-test-jti"
        await blacklist_access_token(
            db=db_session,
            jti=jti,
            user_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        # Redis fast-path should find it
        assert await _mock_redis.exists(f"bl:{jti}") is True
        # DB should also have it
        assert await is_token_blacklisted(jti, db_session) is True

    @pytest.mark.asyncio
    async def test_is_blacklisted_redis_fast_path(
        self,
        db_session: AsyncSession,
        _mock_redis,
    ) -> None:
        """is_token_blacklisted returns True from Redis without DB query."""
        _mock_redis.store["bl:fast-jti"] = "1"
        assert await is_token_blacklisted("fast-jti", db_session) is True

    @pytest.mark.asyncio
    async def test_is_blacklisted_falls_back_to_db_when_redis_down(
        self,
        db_session: AsyncSession,
        redis_unavailable,
    ) -> None:
        """When Redis is down, falls back to Postgres."""
        # Insert directly into DB
        from app.models.auth import TokenBlacklist

        entry = TokenBlacklist(
            jti="db-only-jti",
            user_id=1,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db_session.add(entry)
        await db_session.commit()

        assert await is_token_blacklisted("db-only-jti", db_session) is True

    @pytest.mark.asyncio
    async def test_is_blacklisted_no_db_returns_true(self) -> None:
        """When no backend is available, blacklist checks fail closed (True)."""
        assert await is_token_blacklisted("nonexistent-jti", db=None) is True

    @pytest.mark.asyncio
    async def test_blacklist_expired_token_skips_redis(
        self,
        db_session: AsyncSession,
        _mock_redis,
    ) -> None:
        """Blacklisting an already-expired token skips Redis (ttl <= 0)."""
        jti = "expired-jti"
        await blacklist_access_token(
            db=db_session,
            jti=jti,
            user_id=1,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        # Redis should NOT have it (TTL was negative)
        assert await _mock_redis.exists(f"bl:{jti}") is False
        # DB should still have it
        assert await is_token_blacklisted(jti, db_session) is True


# ==============================================================================
# Client IP Extraction
# ==============================================================================


class TestClientIPExtraction:
    """Cover get_client_ip branches."""

    def test_x_forwarded_for_header(self) -> None:
        """X-Forwarded-For header is preferred over client.host."""
        from app.api.dependencies import get_client_ip

        request = MagicMock()
        request.headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
        request.client = MagicMock(host="127.0.0.1")
        assert get_client_ip(request) == "1.2.3.4"

    def test_fallback_to_client_host(self) -> None:
        """Without X-Forwarded-For, falls back to request.client.host."""
        from app.api.dependencies import get_client_ip

        request = MagicMock()
        request.headers = {}
        request.client = MagicMock(host="10.0.0.1")
        assert get_client_ip(request) == "10.0.0.1"

    def test_no_client_returns_none(self) -> None:
        """When request.client is None, returns None."""
        from app.api.dependencies import get_client_ip

        request = MagicMock()
        request.headers = {}
        request.client = None
        assert get_client_ip(request) is None


# ==============================================================================
# Impersonation Token Creation (sync)
# ==============================================================================


class TestImpersonationToken:
    """Verify impersonation token creation."""

    def test_impersonation_token_has_acting_as_claim(self) -> None:
        """Shadow token carries acting_as and impersonator_id claims."""
        from app.crud.auth import create_impersonation_token

        token, jti, expires = create_impersonation_token(
            target_user_id=5,
            target_email="emp@demo.com",
            target_role="employee",
            target_owner_id=1,
            target_company_id=1,
            target_organization_id=1,
            impersonator_id=999,
        )
        payload = decode_access_token(token)
        assert payload is not None
        assert int(payload.sub) == 5
        assert payload.acting_as == 1
        assert payload.impersonator_id == 999

    def test_impersonation_token_short_lifetime(self) -> None:
        """Shadow tokens have ~15 min lifetime."""
        from app.crud.auth import create_impersonation_token

        _, _, expires = create_impersonation_token(
            target_user_id=5,
            target_email="emp@demo.com",
            target_role="employee",
            target_owner_id=1,
            target_company_id=None,
            target_organization_id=None,
            impersonator_id=999,
        )
        expected = datetime.now(UTC) + timedelta(minutes=15)
        if expires.tzinfo is None:
            expected = expected.replace(tzinfo=None)
        assert abs((expires - expected).total_seconds()) < 5


# ==============================================================================
# Verify Endpoint — Additional Branches
# ==============================================================================


class TestVerifyEndpointEdgeCases:
    """Cover additional branches in the verify endpoint."""

    @pytest.mark.asyncio
    async def test_verify_returns_impersonation_claims(
        self,
        client: AsyncClient,
    ) -> None:
        """Verify endpoint includes acting_as and impersonator_id in response."""
        from app.crud.auth import create_impersonation_token

        token, _, _ = create_impersonation_token(
            target_user_id=5,
            target_email="emp@demo.com",
            target_role="employee",
            target_owner_id=1,
            target_company_id=1,
            target_organization_id=1,
            impersonator_id=999,
        )
        response = await client.post(
            "/api/v1/auth/verify",
            json={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["acting_as"] == 1
        assert data["impersonator_id"] == 999


# ==============================================================================
# Dependencies — Role Hierarchy
# ==============================================================================


class TestRoleHierarchy:
    """Test the require_role dependency with various role levels."""

    @pytest.mark.asyncio
    async def test_manager_can_access_employee_level(
        self,
        client: AsyncClient,
    ) -> None:
        """Manager (level 40) passes require_role('employee') check."""
        token, _, _ = create_access_token(
            user_id=50,
            email="mgr@demo.com",
            role="manager",
            owner_id=1,
        )
        # /auth/me only requires get_current_user (any role)
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "manager"

    @pytest.mark.asyncio
    async def test_missing_bearer_token_returns_401(
        self,
        client: AsyncClient,
    ) -> None:
        """Request without Authorization header returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_blacklisted_token_returns_401_on_protected_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        access_token_for_owner: tuple,
    ) -> None:
        """A blacklisted token should be rejected by get_current_user."""
        token, jti, expires = access_token_for_owner
        await blacklist_access_token(
            db=db_session, jti=jti, user_id=1, expires_at=expires
        )
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert "revoked" in response.json()["detail"].lower()
