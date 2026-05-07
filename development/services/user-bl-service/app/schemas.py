"""
Pydantic schemas for User Service (Business Logic Layer).

These schemas define the public-facing API contract.
They intentionally mirror the DB-access layer schemas where
applicable but add business-specific fields.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==============================================================================
# Request Schemas
# ==============================================================================


class UserCreateRequest(BaseModel):
    """
    Public request body for creating a user.

    The ``owner_id`` is injected from the JWT token — callers
    do not supply it themselves.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=20)
    role: str = Field(
        default="employee", description="owner | admin | employee | viewer"
    )


class UserUpdateRequest(BaseModel):
    """
    Public request body for updating a user.

    All fields optional to support partial updates.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=20)
    role: str | None = None
    is_active: bool | None = None
    privacy_consent_at: datetime | None = None
    privacy_consent_version: str | None = Field(None, max_length=20)


class EmployeeCreateRequest(BaseModel):
    """
    Public request body for adding employee details.

    ``user_id`` is required — the user must already exist.
    """

    user_id: int
    position: str | None = Field(None, max_length=100)
    hourly_rate: float | None = Field(None, ge=0)
    skills: str | None = None
    notes: str | None = None


class EmployeeUpdateRequest(BaseModel):
    """Public request body for updating employee details."""

    model_config = ConfigDict(extra="forbid")

    position: str | None = Field(None, max_length=100)
    hourly_rate: float | None = Field(None, ge=0)
    skills: str | None = None
    notes: str | None = None


class InviteEmployeeRequest(BaseModel):
    """
    Invite a new employee (create user + employee details in one step).

    This is a business-layer convenience endpoint.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(None, max_length=20)
    position: str | None = Field(None, max_length=100)
    hourly_rate: float | None = Field(None, ge=0)
    skills: str | None = None


# ==============================================================================
# Response Schemas
# ==============================================================================


class UserResponse(BaseModel):
    """Public user response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    phone: str | None = None
    role: str
    is_active: bool
    owner_id: int | None = None
    company_id: int | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeResponse(BaseModel):
    """Public employee response schema with user data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    position: str | None = None
    hourly_rate: float | None = None
    skills: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class UserWithEmployeeResponse(UserResponse):
    """User response enriched with employee details."""

    employee_details: EmployeeResponse | None = None


class UserListResponse(BaseModel):
    """Paginated user list response."""

    items: list[UserResponse]
    total: int
    page: int
    per_page: int
    pages: int


class EmployeeListResponse(BaseModel):
    """Paginated employee list response."""

    items: list[EmployeeResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Company Schemas
# ==============================================================================


class CompanyCreateRequest(BaseModel):
    """Public request body for creating a company."""

    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    eircode: str | None = Field(None, max_length=10)
    logo_url: str | None = Field(None, max_length=500)


class CompanyUpdateRequest(BaseModel):
    """Public request body for updating a company."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = None
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)
    eircode: str | None = Field(None, max_length=10)
    logo_url: str | None = Field(None, max_length=500)
    notification_preferences: dict | None = None


class CompanyResponse(BaseModel):
    """Public company response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    eircode: str | None = None
    logo_url: str | None = None
    is_active: bool
    notification_preferences: dict | None = None
    created_at: datetime
    updated_at: datetime


# ==============================================================================
# Permission Schemas
# ==============================================================================


class PermissionUpdateRequest(BaseModel):
    """Bulk upsert permission grants for a user."""

    permissions: dict[str, bool] = Field(
        ..., description="Map of permission key → granted (true/false)"
    )


# ==============================================================================
# Audit Log Schemas
# ==============================================================================


class AuditLogResponse(BaseModel):
    """Tenant-scoped audit log response schema."""

    id: int
    timestamp: datetime
    actor_id: int | None = None
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
    """Paginated list of audit log entries."""

    items: list[AuditLogResponse]
    total: int
    page: int
    per_page: int
    pages: int
