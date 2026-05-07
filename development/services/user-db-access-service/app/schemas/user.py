"""
Pydantic schemas for User service API.

Defines request/response models for user, employee, and organization
operations.  These schemas handle validation and serialization.

Models
------
- Organization schemas: create / update / response for platform-level orgs.
- Company schemas: create / update / response for tenant companies.
- User schemas: create / update / response / internal for user accounts.
- Employee schemas: create / update / response for employee details.
- AuditLog schemas: response-only for platform audit trail entries.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ..models.user import UserRole

# ==============================================================================
# Organization Schemas (Platform-Level)
# ==============================================================================


class OrganizationBase(BaseModel):
    """
    Base organization schema with common fields.

    Organizations are the top-level platform entity that groups
    one or more companies under a single billing / admin umbrella.
    """

    name: str = Field(
        ..., min_length=1, max_length=255, description="Organization display name"
    )
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe unique identifier (lowercase, hyphens only)",
    )
    billing_email: str | None = Field(
        None, max_length=255, description="Primary billing contact"
    )
    billing_plan: str = Field(
        "free",
        description="Subscription tier",
        pattern=r"^(free|starter|professional|enterprise)$",
    )
    max_users: int = Field(
        50, ge=1, description="Maximum allowed users in this organization"
    )
    max_customers: int = Field(500, ge=1, description="Maximum allowed customers")


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    pass


class OrganizationUpdate(BaseModel):
    """
    Schema for updating organization fields.

    All fields are optional to allow partial updates.
    Only superadmins may call the corresponding endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    slug: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    billing_email: str | None = Field(None, max_length=255)
    billing_plan: str | None = Field(
        None, pattern=r"^(free|starter|professional|enterprise)$"
    )
    max_users: int | None = Field(None, ge=1)
    max_customers: int | None = Field(None, ge=1)
    is_active: bool | None = None
    suspended_reason: str | None = Field(None, max_length=500)
    notification_settings: dict | None = Field(
        None,
        description=(
            "Per-org notification overrides. Structure: "
            "{use_custom_smtp: bool, smtp: {...}, use_custom_whatsapp: bool, whatsapp: {...}}"
        ),
    )


class OrganizationResponse(OrganizationBase):
    """
    Schema for organization API responses.

    Includes server-managed fields: ``id``, ``is_active``,
    suspension info, and timestamps.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    suspended_at: datetime | None = None
    suspended_reason: str | None = None
    notification_settings: dict | None = None
    created_at: datetime
    updated_at: datetime


# ==============================================================================
# Company Schemas
# ==============================================================================


class CompanyBase(BaseModel):
    """Base company schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    eircode: str | None = Field(None, max_length=10)
    logo_url: str | None = Field(None, max_length=500)


class CompanyCreate(CompanyBase):
    """Schema for creating a new company."""

    organization_id: int | None = Field(
        None, description="Organization this company belongs to"
    )


class CompanyUpdate(BaseModel):
    """Schema for updating company fields. All fields optional."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    eircode: str | None = Field(None, max_length=10)
    logo_url: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class CompanyResponse(CompanyBase):
    """Schema for company API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ==============================================================================
# Base Schemas
# ==============================================================================


class UserBase(BaseModel):
    """
    Base user schema with common fields.

    Used as foundation for create/update/response schemas.
    """

    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=255)
    last_name: str = Field(..., min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=50)
    role: UserRole = UserRole.EMPLOYEE


class EmployeeBase(BaseModel):
    """Base employee schema with common fields."""

    department: str | None = Field(None, max_length=100)
    position: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    hire_date: datetime | None = None
    hourly_rate: float | None = Field(
        None, ge=0, description="Hourly rate in currency units"
    )
    skills: str | None = Field(None, description="Comma-separated list of skills")
    notes: str | None = Field(None, description="Additional notes about employee")
    is_active: bool = True


# ==============================================================================
# Create Schemas (Input)
# ==============================================================================


class UserCreate(UserBase):
    """
    Schema for creating a new user.

    Includes password field for registration.  The ``organization_id``
    is set by the system when the user is created through the admin
    portal — callers should NOT set it directly.
    """

    password: str = Field(..., min_length=8, max_length=100)
    owner_id: int | None = None  # If creating an employee under an owner
    company_id: int | None = None  # The company this user belongs to
    organization_id: int | None = Field(
        None, description="Organization this user belongs to (system-managed)"
    )


class EmployeeCreate(EmployeeBase):
    """Schema for creating employee details."""

    user_id: int
    owner_id: int


# ==============================================================================
# Update Schemas (Input)
# ==============================================================================


class UserUpdate(BaseModel):
    """
    Schema for updating user fields.

    All fields are optional to allow partial updates.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    first_name: str | None = Field(None, min_length=1, max_length=255)
    last_name: str | None = Field(None, min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=50)
    role: UserRole | None = None
    is_active: bool | None = None
    owner_id: int | None = None
    privacy_consent_at: datetime | None = None
    privacy_consent_version: str | None = Field(None, max_length=20)
    anonymize_scheduled_at: datetime | None = None


class EmployeeUpdate(BaseModel):
    """Schema for updating employee details."""

    model_config = ConfigDict(extra="forbid")

    department: str | None = Field(None, max_length=100)
    position: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    hire_date: datetime | None = None
    hourly_rate: float | None = Field(None, ge=0)
    skills: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class PasswordUpdate(BaseModel):
    """Schema for password update (internal use by auth-service)."""

    new_password: str = Field(..., min_length=8, max_length=100)


# ==============================================================================
# Response Schemas (Output)
# ==============================================================================


class UserResponse(UserBase):
    """
    Schema for user API responses.

    Includes all user fields except password.  The ``organization_id``
    field links the user to a platform-level organization.

    Note:
        ``email`` is overridden to ``str`` (instead of inheriting
        ``EmailStr`` from ``UserBase``) so that reserved-TLD addresses
        such as ``superadmin@system.local`` can be serialised without
        Pydantic raising a validation error.
    """

    model_config = ConfigDict(from_attributes=True)

    # Override EmailStr from UserBase — output schema must accept any
    # stored address, including reserved TLDs like .local
    email: str

    id: int
    is_active: bool
    owner_id: int | None = None
    company_id: int | None = None
    organization_id: int | None = None
    privacy_consent_at: datetime | None = None
    privacy_consent_version: str | None = None
    anonymize_scheduled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeResponse(EmployeeBase):
    """Schema for employee API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime


class UserWithEmployeeResponse(UserResponse):
    """User response including employee details if available."""

    employee_details: EmployeeResponse | None = None


class EmployeeWithUserResponse(EmployeeResponse):
    """
    Employee response enriched with user information.

    Contains all employee fields plus the associated user's
    first_name, last_name, and email for display purposes.
    """

    first_name: str
    last_name: str
    email: str


class UserListResponse(BaseModel):
    """Paginated user list response."""

    items: list[UserResponse]
    total: int
    page: int
    per_page: int
    pages: int


class EmployeeListResponse(BaseModel):
    """Paginated employee list response."""

    items: list[EmployeeWithUserResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Internal Schemas (Service-to-Service)
# ==============================================================================


class UserInternal(UserResponse):
    """
    Internal user schema for service-to-service communication.

    Includes additional fields not exposed to external API.
    """

    hashed_password: str


# ==============================================================================
# Audit Log Schemas
# ==============================================================================


class AuditLogCreate(BaseModel):
    """
    Schema for creating a new audit log entry.

    Used by admin-bl-service to record platform-wide actions
    such as organization creation, suspension, impersonation, etc.

    Attributes:
        actor_id:        User who performed the action.
        actor_email:     Email of the actor at the time of the action.
        actor_role:      Role of the actor at the time of the action.
        impersonator_id: If impersonating, the real superadmin's ID.
        organization_id: Organization context (NULL for platform-wide ops).
        action:          Machine-readable action name (e.g. ``"org.create"``).
        resource_type:   Type of resource affected (e.g. ``"organization"``).
        resource_id:     Primary key of the affected resource (as string).
        details:         Arbitrary JSON with action-specific metadata.
        ip_address:      Client IP from the originating request.
    """

    actor_id: int
    actor_email: str | None = None
    actor_role: str | None = None
    impersonator_id: int | None = None
    organization_id: int | None = None
    action: str = Field(..., min_length=1, max_length=100)
    resource_type: str | None = Field(None, max_length=100)
    resource_id: str | None = Field(None, max_length=100)
    details: dict | None = None
    ip_address: str | None = Field(None, max_length=45)


class AuditLogResponse(BaseModel):
    """
    Schema for audit log API responses.

    Audit logs are **immutable** — entries cannot be updated or
    deleted once created.

    Attributes:
        id:              Auto-generated BIGSERIAL primary key.
        timestamp:       UTC timestamp of the audited action.
        actor_id:        User who performed the action.
        actor_email:     Email of the actor at the time of the action.
        actor_role:      Role of the actor at the time of the action.
        impersonator_id: If the action was performed via impersonation,
                         the superadmin's user ID.
        organization_id: Organization context (NULL for platform-wide ops).
        action:          Machine-readable action identifier
                         (e.g. ``"user.create"``, ``"org.suspend"``).
        resource_type:   Type of resource affected (e.g. ``"user"``, ``"job"``).
        resource_id:     Primary key of the affected resource.
        details:         Arbitrary JSON with action-specific metadata.
        ip_address:      Client IP from the request.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    actor_id: int
    actor_email: str | None = None
    actor_role: str | None = None
    impersonator_id: int | None = None
    organization_id: int | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict | None = None
    ip_address: str | None = None


class AuditLogListResponse(BaseModel):
    """Paginated audit log list response."""

    items: list[AuditLogResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Platform Setting Schemas
# ==============================================================================


class PlatformSettingCreate(BaseModel):
    """
    Schema for creating a new platform setting.

    Attributes:
        key:         Unique setting identifier (e.g. ``"maintenance_mode"``).
        value:       JSON-serialisable setting value.
        description: Human-readable explanation of the setting's purpose.
    """

    key: str = Field(..., min_length=1, max_length=100)
    value: Any = None
    description: str | None = Field(None, max_length=500)


class PlatformSettingUpdate(BaseModel):
    """
    Schema for updating a platform setting.

    Attributes:
        value:       New value for the setting.
        description: Updated description (optional).
    """

    value: Any = None
    description: str | None = Field(None, max_length=500)


class PlatformSettingResponse(BaseModel):
    """
    Schema for platform setting API responses.

    Attributes:
        key:         Unique setting identifier.
        value:       Current JSON value.
        description: Human-readable explanation.
        updated_by:  User ID of last updater.
        updated_at:  Timestamp of last update.
    """

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any = None
    description: str | None = None
    updated_by: int | None = None
    updated_at: datetime | None = None


class PlatformSettingListResponse(BaseModel):
    """List wrapper for platform settings (no pagination — small dataset)."""

    items: list[PlatformSettingResponse]
    total: int
