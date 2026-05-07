"""
Pydantic schemas for Customer service API.

Defines request/response models for customer operations.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==============================================================================
# Base Schemas
# ==============================================================================


class CustomerBase(BaseModel):
    """
    Base customer schema with common fields.
    """

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    address: str | None = None
    eircode: str | None = Field(None, max_length=10)
    latitude: float | None = None
    longitude: float | None = None
    company_name: str | None = Field(None, max_length=255)


class CustomerNoteBase(BaseModel):
    """Base customer note schema."""

    content: str = Field(..., min_length=1)


# ==============================================================================
# Create Schemas (Input)
# ==============================================================================


class CustomerCreate(CustomerBase):
    """
    Schema for creating a new customer.
    """

    owner_id: int
    notify_whatsapp: bool = False
    notify_email: bool = False
    data_processing_consent: bool = False
    data_processing_consent_at: datetime | None = None


class CustomerNoteCreate(CustomerNoteBase):
    """Schema for creating a customer note."""

    customer_id: int
    created_by_id: int


# ==============================================================================
# Update Schemas (Input)
# ==============================================================================


class CustomerUpdate(BaseModel):
    """
    Schema for updating customer fields.
    All fields are optional to allow partial updates.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=50)
    address: str | None = None
    eircode: str | None = Field(None, max_length=10)
    latitude: float | None = None
    longitude: float | None = None
    company_name: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    notify_whatsapp: bool | None = None
    notify_email: bool | None = None
    data_processing_consent: bool | None = None
    data_processing_consent_at: datetime | None = None


class CustomerNoteUpdate(BaseModel):
    """Schema for updating customer note."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(None, min_length=1)


# ==============================================================================
# Response Schemas (Output)
# ==============================================================================


class CustomerNoteResponse(CustomerNoteBase):
    """Schema for customer note API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    created_by_id: int
    created_at: datetime
    updated_at: datetime


class CustomerResponse(CustomerBase):
    """
    Schema for customer API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    is_active: bool
    notify_whatsapp: bool = False
    notify_email: bool = False
    data_processing_consent: bool = False
    data_processing_consent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CustomerWithNotesResponse(CustomerResponse):
    """Customer response including notes."""

    notes: list[CustomerNoteResponse] = []


class CustomerListResponse(BaseModel):
    """Paginated customer list response."""

    items: list[CustomerResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Search/Filter Schemas
# ==============================================================================


class CustomerSearchParams(BaseModel):
    """Parameters for searching customers."""

    query: str | None = None  # Search in name, email, phone, company_name
    is_active: bool | None = None
