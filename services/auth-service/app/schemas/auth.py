"""
Pydantic schemas for Auth Service API.

Defines request / response models for login, token refresh,
token verification, logout, and impersonation operations.

Every schema carries full type hints and field-level validation
so that FastAPI automatically generates accurate OpenAPI docs.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic_core import PydanticCustomError
import re


# ==============================================================================
# Token Payload (Internal)
# ==============================================================================

class TokenPayload(BaseModel):
    """
    Decoded JWT payload used internally by all services.

    Attributes:
        sub:             Subject — the user ID as a string.
        email:           User's email address.
        role:            User's role (superadmin | owner | admin | manager |
                         employee | viewer).
        owner_id:        Tenant identifier — the business-owner user ID.
                         ``None`` for superadmins.
        company_id:      Company identifier for tenant metadata.
        organization_id: Platform-level organization ID (``None`` for superadmins).
        acting_as:       Effective owner_id when impersonating.
        impersonator_id: Superadmin's real user ID when impersonating.
        jti:             Unique token identifier (UUID4 hex).
        exp:             Expiry timestamp (epoch seconds).
        iat:             Issued-at timestamp (epoch seconds).
        token_type:      ``\"access\"`` or ``\"refresh\"``.
    """

    sub: str
    email: str
    role: str
    owner_id: Optional[int] = None
    company_id: Optional[int] = None
    organization_id: Optional[int] = None
    acting_as: Optional[int] = None
    impersonator_id: Optional[int] = None
    jti: str
    exp: int
    iat: int
    token_type: str = "access"


# ==============================================================================
# Login
# ==============================================================================

class LoginRequest(BaseModel):
    """
    Credentials submitted by the user to obtain tokens.

    Attributes:
        email:       User's email address (allows .local TLD for superadmins).
        password:    Plain-text password (validated server-side).
        device_info: Optional device / browser identifier.
    """

    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    device_info: Optional[str] = Field(
        None,
        max_length=500,
        description="User-agent or device identifier for session tracking",
    )

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format, allowing .local TLD for superadmin."""
        # Basic email format check
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            # Special case: allow .local TLD for superadmin
            if not v.endswith('@system.local'):
                raise PydanticCustomError(
                    'value_error',
                    'Invalid email format',
                )
        return v.lower()


class LoginResponse(BaseModel):
    """
    Tokens returned after successful authentication.

    Attributes:
        access_token:  Short-lived JWT for API authorisation.
        refresh_token: Long-lived opaque token for obtaining new access tokens.
        token_type:    Always ``"bearer"``.
        expires_in:    Access-token lifetime in seconds.
        user_id:       Authenticated user's ID.
        owner_id:      Tenant (business-owner) ID.
        company_id:    Company identifier for tenant metadata.
        role:          User's role string.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: int
    owner_id: Optional[int] = None
    company_id: Optional[int] = None
    organization_id: Optional[int] = None
    role: str


# ==============================================================================
# Token Refresh
# ==============================================================================

class TokenRefreshRequest(BaseModel):
    """
    Request body for the ``/refresh`` endpoint.

    Attributes:
        refresh_token: The refresh token previously issued at login.
    """

    refresh_token: str = Field(..., min_length=1)


class TokenRefreshResponse(BaseModel):
    """
    New access token returned after a successful refresh.

    Attributes:
        access_token: Freshly minted JWT.
        token_type:   Always ``"bearer"``.
        expires_in:   Lifetime in seconds.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ==============================================================================
# Token Verification (Service-to-Service)
# ==============================================================================

class TokenVerifyRequest(BaseModel):
    """
    Request body for the ``/verify`` endpoint.

    Other microservices call this to validate an access token
    and retrieve the tenant context without sharing the JWT secret.

    Attributes:
        access_token: The JWT to validate.
    """

    access_token: str = Field(..., min_length=1)


class TokenVerifyResponse(BaseModel):
    """
    Result of token verification.

    Attributes:
        valid:           Whether the token is valid and not blacklisted.
        user_id:         Extracted user ID (None when invalid).
        email:           Extracted email (None when invalid).
        role:            Extracted role (None when invalid).
        owner_id:        Extracted tenant / owner ID (None when invalid
                         or for superadmins).
        company_id:      Extracted company ID (None when invalid).
        organization_id: Platform-level organization ID.
        acting_as:       Effective owner_id if impersonating.
        impersonator_id: Superadmin’s real user ID if impersonating.
        message:         Human-readable status message.
    """

    valid: bool
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    owner_id: Optional[int] = None
    company_id: Optional[int] = None
    organization_id: Optional[int] = None
    acting_as: Optional[int] = None
    impersonator_id: Optional[int] = None
    message: str = "Token is valid"


# ==============================================================================
# Logout / Revocation
# ==============================================================================

class LogoutRequest(BaseModel):
    """
    Request body for the ``/logout`` endpoint.

    Attributes:
        refresh_token: The refresh token to revoke.
        access_token:  Optionally blacklist the current access token too.
    """

    refresh_token: str = Field(..., min_length=1)
    access_token: Optional[str] = None


class RevokeAllRequest(BaseModel):
    """
    Request body for the ``/revoke-all`` (logout everywhere) endpoint.

    Attributes:
        user_id: The user whose sessions should be terminated.
    """

    user_id: int


# ==============================================================================
# Password Change (delegates to user-db-access-service)
# ==============================================================================

class PasswordChangeRequest(BaseModel):
    """
    Request body for the ``/change-password`` endpoint.

    Attributes:
        current_password: The user's current password.
        new_password:     The desired new password.
    """

    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    """
    Request body for the ``/reset-password`` endpoint.

    Used by admins/owners/superadmins to reset another user's password
    without requiring the current password.

    Attributes:
        user_id:      The ID of the user whose password should be reset.
        new_password: The new password to set.
    """

    user_id: int = Field(..., gt=0)
    new_password: str = Field(..., min_length=8, max_length=128)

# ==============================================================================
# Impersonation (Superadmin Only)
# ==============================================================================

class ImpersonateRequest(BaseModel):
    """
    Request body for the ``/impersonate`` endpoint.

    Only superadmins may call this endpoint.  A *shadow token* is
    returned that carries the target user’s identity but retains
    an audit trail back to the superadmin via ``impersonator_id``.

    Attributes:
        target_user_id: The user to impersonate.
        reason:         Human-readable justification for the impersonation.
                        Stored in the audit log.
    """

    target_user_id: int = Field(..., gt=0, description="ID of the user to impersonate")
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for impersonation (logged for audit trail)",
    )


class ImpersonateResponse(BaseModel):
    """
    Shadow token returned after a successful impersonation request.

    The ``access_token`` behaves exactly like a normal access token
    but contains extra claims (``acting_as``, ``impersonator_id``)
    so downstream services can attribute actions correctly.

    Attributes:
        access_token:    Shadow JWT for the impersonated session.
        token_type:      Always ``"bearer"``.
        expires_in:      Lifetime in seconds (shorter than normal: 15 min).
        impersonating:   User ID being impersonated.
        impersonator_id: The superadmin’s own user ID.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    impersonating: int
    impersonator_id: int