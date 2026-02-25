"""
Pydantic schemas for User Service (Business Logic Layer).

These schemas define the public-facing API contract.
They intentionally mirror the DB-access layer schemas where
applicable but add business-specific fields.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, ConfigDict


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
    phone: Optional[str] = Field(None, max_length=20)
    role: str = Field(default="employee", description="owner | admin | employee | viewer")


class UserUpdateRequest(BaseModel):
    """
    Public request body for updating a user.

    All fields optional to support partial updates.
    """
    model_config = ConfigDict(extra="forbid")

    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    role: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeCreateRequest(BaseModel):
    """
    Public request body for adding employee details.

    ``user_id`` is required — the user must already exist.
    """

    user_id: int
    position: Optional[str] = Field(None, max_length=100)
    hourly_rate: Optional[float] = Field(None, ge=0)
    skills: Optional[str] = None
    notes: Optional[str] = None


class EmployeeUpdateRequest(BaseModel):
    """Public request body for updating employee details."""
    model_config = ConfigDict(extra="forbid")

    position: Optional[str] = Field(None, max_length=100)
    hourly_rate: Optional[float] = Field(None, ge=0)
    skills: Optional[str] = None
    notes: Optional[str] = None


class InviteEmployeeRequest(BaseModel):
    """
    Invite a new employee (create user + employee details in one step).

    This is a business-layer convenience endpoint.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    position: Optional[str] = Field(None, max_length=100)
    hourly_rate: Optional[float] = Field(None, ge=0)
    skills: Optional[str] = None


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
    phone: Optional[str] = None
    role: str
    is_active: bool
    owner_id: Optional[int] = None
    company_id: Optional[int] = None
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
    position: Optional[str] = None
    hourly_rate: Optional[float] = None
    skills: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class UserWithEmployeeResponse(UserResponse):
    """User response enriched with employee details."""
    employee_details: Optional[EmployeeResponse] = None


class UserListResponse(BaseModel):
    """Paginated user list response."""
    items: List[UserResponse]
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
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    eircode: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = Field(None, max_length=500)


class CompanyUpdateRequest(BaseModel):
    """Public request body for updating a company."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    eircode: Optional[str] = Field(None, max_length=10)
    logo_url: Optional[str] = Field(None, max_length=500)


class CompanyResponse(BaseModel):
    """Public company response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    eircode: Optional[str] = None
    logo_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
