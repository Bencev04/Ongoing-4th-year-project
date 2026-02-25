"""
Security-focused tests for Auth Service.

Covers:
- Superadmin JWT handling (owner_id=None, organisation_id=None)
- Impersonation endpoint access control
- Token claims integrity
- Role-based access guards
- Token blacklist / revocation behaviour

All tests use the async in-memory SQLite + mocked Redis from conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient

from app.crud.auth import create_access_token, create_impersonation_token


# ==========================================================================
# Superadmin Token Tests
# ==========================================================================


class TestSuperadminTokenClaims:
    """Verify JWT payload shape for the superadmin role."""

    def test_superadmin_token_has_null_owner_id(self) -> None:
        """Superadmin tokens MUST carry ``owner_id=None``."""
        from jose import jwt as jose_jwt
        from common.config import settings

        token, jti, expires = create_access_token(
            user_id=999,
            email="superadmin@system.local",
            role="superadmin",
            owner_id=None,
        )
        assert token is not None
        assert jti is not None

        payload = jose_jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["owner_id"] is None
        assert payload["role"] == "superadmin"
        assert payload["sub"] == "999"

    def test_superadmin_token_includes_organization_id(self) -> None:
        """Superadmin tokens MAY carry ``organization_id=None``."""
        from jose import jwt as jose_jwt
        from common.config import settings

        token, jti, _ = create_access_token(
            user_id=999,
            email="superadmin@system.local",
            role="superadmin",
            owner_id=None,
            organization_id=None,
        )
        assert token is not None

        payload = jose_jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["organization_id"] is None
        assert payload["owner_id"] is None

    def test_regular_user_token_has_owner_id(self) -> None:
        """Non-superadmin tokens MUST have a non-null ``owner_id``."""
        from jose import jwt as jose_jwt
        from common.config import settings

        token, _, _ = create_access_token(
            user_id=1,
            email="owner@demo.com",
            role="owner",
            owner_id=1,
        )
        assert token is not None

        payload = jose_jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["owner_id"] == 1
        assert payload["role"] == "owner"
        assert payload["sub"] == "1"


# ==========================================================================
# Impersonation Token Tests
# ==========================================================================


class TestImpersonationTokenClaims:
    """Verify impersonation shadow tokens carry the right claims."""

    def test_impersonation_token_carries_acting_as(self) -> None:
        """Shadow tokens must embed ``acting_as`` with the target user's owner_id."""
        token, jti, _ = create_impersonation_token(
            target_user_id=1,
            target_email="owner@demo.com",
            target_role="owner",
            target_owner_id=1,
            target_company_id=1,
            target_organization_id=None,
            impersonator_id=999,
        )
        assert token is not None
        # Decode to verify claims
        from jose import jwt
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
        from common.config import settings
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["acting_as"] == 1  # target_owner_id
        assert payload["impersonator_id"] == 999
        assert payload["sub"] == "1"  # target user id

    def test_impersonation_token_short_expiry(self) -> None:
        """Impersonation tokens should expire in ~15 minutes."""
        token, _, expires = create_impersonation_token(
            target_user_id=1,
            target_email="owner@demo.com",
            target_role="owner",
            target_owner_id=1,
            target_company_id=1,
            target_organization_id=None,
            impersonator_id=999,
        )
        # Expires should be within 20 minutes from now (15 min + buffer)
        now = datetime.now(timezone.utc)
        exp = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
        delta = (exp - now).total_seconds()
        assert 0 < delta <= 20 * 60, f"Impersonation token expiry ({delta}s) is unexpectedly large"


# ==========================================================================
# Impersonation Endpoint Tests
# ==========================================================================


class TestImpersonationEndpoint:
    """Test the POST /api/v1/auth/impersonate endpoint."""

    @pytest.mark.asyncio
    async def test_impersonate_requires_auth(self, client: AsyncClient) -> None:
        """Impersonation without a Bearer token should be rejected."""
        resp = await client.post(
            "/api/v1/auth/impersonate",
            json={"target_user_id": 1, "reason": "test"},
        )
        # Expect 401 or 403 (no token)
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_impersonate_owner_is_forbidden(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple[str, str, datetime],
    ) -> None:
        """Owners (non-superadmin) must NOT be able to impersonate."""
        token, _, _ = access_token_for_owner
        resp = await client.post(
            "/api/v1/auth/impersonate",
            json={"target_user_id": 2, "reason": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_impersonate_employee_is_forbidden(
        self,
        client: AsyncClient,
        access_token_for_employee: tuple[str, str, datetime],
    ) -> None:
        """Employees must NOT be able to impersonate."""
        token, _, _ = access_token_for_employee
        resp = await client.post(
            "/api/v1/auth/impersonate",
            json={"target_user_id": 1, "reason": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_superadmin_can_impersonate_regular_user(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple[str, str, datetime],
    ) -> None:
        """Superadmin must be able to impersonate a regular (non-superadmin) user."""
        token, _, _ = access_token_for_superadmin
        resp = await client.post(
            "/api/v1/auth/impersonate",
            json={"target_user_id": 1, "reason": "Support investigation"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["impersonating"] == 1
        assert data["impersonator_id"] == 999
        assert data["token_type"] == "bearer"

        # Verify the shadow token has correct claims
        from jose import jwt as jose_jwt
        from common.config import settings

        payload = jose_jwt.decode(
            data["access_token"],
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        assert payload["sub"] == "1"  # target user
        assert payload["impersonator_id"] == 999
        assert payload["acting_as"] == 1  # target owner_id

    @pytest.mark.asyncio
    async def test_superadmin_cannot_impersonate_another_superadmin(
        self,
        client: AsyncClient,
        access_token_for_superadmin: tuple[str, str, datetime],
        _mock_httpx_client,
    ) -> None:
        """Superadmin-to-superadmin impersonation must be blocked."""
        import httpx as httpx_mod

        # Override the autouse httpx mock to return a superadmin user
        mock_response = MagicMock(spec=httpx_mod.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": 998,
            "email": "other-admin@system.local",
            "role": "superadmin",
            "owner_id": None,
        }
        mock_client = AsyncMock(spec=httpx_mod.AsyncClient)
        mock_client.get.return_value = mock_response

        import app.api.routes as routes_mod
        original_client = routes_mod._http_client
        routes_mod._http_client = mock_client

        try:
            token, _, _ = access_token_for_superadmin
            resp = await client.post(
                "/api/v1/auth/impersonate",
                json={"target_user_id": 998, "reason": "test"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403
            assert "superadmin" in resp.json()["detail"].lower()
        finally:
            routes_mod._http_client = original_client


# ==========================================================================
# Verify Endpoint — Role & Claims Tests
# ==========================================================================


class TestVerifyEndpointClaims:
    """Ensure /api/v1/auth/verify returns correct role-related claims."""

    @pytest.mark.asyncio
    async def test_verify_returns_role(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple[str, str, datetime],
    ) -> None:
        """Verify endpoint must include the ``role`` field in the response."""
        token, _, _ = access_token_for_owner
        resp = await client.post(
            "/api/v1/auth/verify",
            json={"access_token": token},
        )
        assert resp.status_code == 200
        data: Dict[str, Any] = resp.json()
        assert data.get("valid") is True
        assert data.get("role") == "owner"

    @pytest.mark.asyncio
    async def test_verify_returns_owner_id(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple[str, str, datetime],
    ) -> None:
        """Verify endpoint must include ``owner_id`` in the response."""
        token, _, _ = access_token_for_owner
        resp = await client.post(
            "/api/v1/auth/verify",
            json={"access_token": token},
        )
        data = resp.json()
        assert data.get("owner_id") == 1


# ==========================================================================
# Token Revocation Tests
# ==========================================================================


class TestTokenRevocation:
    """Ensure tokens can be properly revoked / blacklisted."""

    @pytest.mark.asyncio
    async def test_logout_invalidates_token(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple[str, str, datetime],
        stored_refresh_token: tuple[str, Any],
    ) -> None:
        """After logout, the same access token should no longer verify."""
        token, _, _ = access_token_for_owner
        refresh_raw, _ = stored_refresh_token

        # First logout — include access_token so it gets blacklisted
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_raw, "access_token": token},
        )
        assert resp.status_code == 204

        # Verify should now fail (blacklisted)
        resp2 = await client.post(
            "/api/v1/auth/verify",
            json={"access_token": token},
        )
        data = resp2.json()
        assert data.get("valid") is False

    @pytest.mark.asyncio
    async def test_verify_without_token_fails(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /api/v1/auth/verify with no body must return 422 (missing required field)."""
        resp = await client.post("/api/v1/auth/verify")
        # TokenVerifyRequest.access_token is required (min_length=1),
        # so omitting the body gives a 422 validation error.
        assert resp.status_code == 422


# ==========================================================================
# Me Endpoint — Claims Integrity
# ==========================================================================


class TestMeEndpoint:
    """Test that /api/v1/auth/me returns all expected claim fields."""

    @pytest.mark.asyncio
    async def test_me_returns_all_claims(
        self,
        client: AsyncClient,
        access_token_for_owner: tuple[str, str, datetime],
    ) -> None:
        """The /me endpoint must echo back all JWT claims."""
        token, _, _ = access_token_for_owner
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert "email" in data
        assert "role" in data
        assert data["role"] == "owner"

    @pytest.mark.asyncio
    async def test_me_without_auth_fails(
        self,
        client: AsyncClient,
    ) -> None:
        """The /me endpoint without a token should return 401."""
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
