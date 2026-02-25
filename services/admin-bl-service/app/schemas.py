"""
Pydantic schemas for Admin BL Service API.

Defines request / response models for:
- Organization management
- Audit log querying
- Platform settings
- Admin-level user lookups

These schemas are **separate** from the DB-access schemas.
The admin BL service translates between its own API contract
and the internal DB-access service payloads.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


# ==============================================================================
# Organization Schemas
# ==============================================================================

class OrganizationCreateRequest(BaseModel):
    """
    Request to create a new organization.

    Attributes:
        name:          Display name for the organization.
        slug:          URL-safe unique identifier (lowercase, hyphens).
        billing_email: Primary billing contact email address.
        billing_plan:  Subscription tier (free / starter / professional / enterprise).
        max_users:     Maximum users allowed in this organization.
        max_customers: Maximum customers allowed.
    """

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    billing_email: Optional[str] = Field(None, max_length=255)
    billing_plan: str = Field(
        "free", pattern=r"^(free|starter|professional|enterprise)$"
    )
    max_users: int = Field(50, ge=1)
    max_customers: int = Field(500, ge=1)


class OrganizationUpdateRequest(BaseModel):
    """
    Request to update an existing organization.

    All fields are optional for partial updates.
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    billing_email: Optional[str] = Field(None, max_length=255)
    billing_plan: Optional[str] = Field(
        None, pattern=r"^(free|starter|professional|enterprise)$"
    )
    max_users: Optional[int] = Field(None, ge=1)
    max_customers: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    suspended_reason: Optional[str] = Field(None, max_length=500)


class OrganizationResponse(BaseModel):
    """API response for a single organization."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    billing_email: Optional[str] = None
    billing_plan: str
    max_users: int
    max_customers: int
    is_active: bool
    suspended_at: Optional[datetime] = None
    suspended_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class OrganizationListResponse(BaseModel):
    """Paginated list of organizations."""

    items: List[OrganizationResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Audit Log Schemas
# ==============================================================================

class AuditLogResponse(BaseModel):
    """
    API response for a single audit log entry.

    Audit logs are **immutable** — there are no create / update
    request schemas because entries are generated automatically
    by the audit trail module.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    actor_id: int
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    impersonator_id: Optional[int] = None
    organization_id: Optional[int] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: List[AuditLogResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Platform Settings Schemas
# ==============================================================================

class PlatformSettingResponse(BaseModel):
    """API response for a single platform setting."""

    key: str
    value: Any
    description: Optional[str] = None
    updated_by: Optional[int] = None
    updated_at: Optional[datetime] = None


class PlatformSettingUpdateRequest(BaseModel):
    """Request to update a platform setting value."""

    value: Any = Field(..., description="New value for the setting (JSON-compatible)")
    description: Optional[str] = Field(None, max_length=500)


class PlatformSettingsListResponse(BaseModel):
    """List of all platform settings."""

    items: List[PlatformSettingResponse]
    total: int


# ==============================================================================
# Admin User Lookup Schemas
# ==============================================================================

class AdminUserResponse(BaseModel):
    """
    User response for superadmin cross-tenant user listing.

    Contains tenant-identifying fields that regular user responses
    do not expose.
    """

    id: int
    email: str
    first_name: str
    last_name: str
    role: str
    owner_id: Optional[int] = None
    company_id: Optional[int] = None
    organization_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    """Paginated cross-tenant user list for superadmins."""

    items: List[AdminUserResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Suspend / Unsuspend
# ==============================================================================

class SuspendRequest(BaseModel):
    """Request to suspend an organization."""

    reason: str = Field(..., min_length=1, max_length=500)


class MessageResponse(BaseModel):
    """Generic success message response."""

    message: str
    detail: Optional[str] = None
