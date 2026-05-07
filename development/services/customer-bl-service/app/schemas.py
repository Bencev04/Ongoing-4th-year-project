"""
Pydantic schemas for Customer Service (Business Logic Layer).

Defines the public API contract for customer management,
notes, and enriched responses.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==============================================================================
# Request Schemas
# ==============================================================================


class CustomerCreateRequest(BaseModel):
    """Request body for creating a customer."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    company: str | None = Field(None, max_length=200)
    address: str | None = None
    eircode: str | None = Field(None, max_length=10)
    latitude: float | None = None
    longitude: float | None = None
    notify_whatsapp: bool = False
    notify_email: bool = False


class CustomerUpdateRequest(BaseModel):
    """Partial update request for a customer."""

    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=20)
    company: str | None = Field(None, max_length=200)
    address: str | None = None
    eircode: str | None = Field(None, max_length=10)
    latitude: float | None = None
    longitude: float | None = None
    notify_whatsapp: bool | None = None
    notify_email: bool | None = None


class CustomerNoteCreateRequest(BaseModel):
    """Request body for adding a note to a customer."""

    content: str = Field(..., min_length=1)


class CustomerNoteUpdateRequest(BaseModel):
    """Request body for updating a customer note."""

    content: str = Field(..., min_length=1)


class CustomerSearchRequest(BaseModel):
    """Search criteria for customers."""

    query: str = Field(..., min_length=1, max_length=200)


# ==============================================================================
# Response Schemas
# ==============================================================================


class CustomerResponse(BaseModel):
    """Public customer response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    address: str | None = None
    eircode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    owner_id: int
    is_active: bool
    notify_whatsapp: bool = False
    notify_email: bool = False
    created_at: datetime
    updated_at: datetime


class CustomerNoteResponse(BaseModel):
    """Public customer note response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    content: str
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    """Lightweight job summary for customer enrichment."""

    id: int
    title: str
    status: str
    start_time: datetime | None = None


class CustomerWithHistoryResponse(CustomerResponse):
    """Customer enriched with recent job history and notes."""

    recent_jobs: list[JobSummary] = []
    customer_notes: list[CustomerNoteResponse] = []
    total_jobs: int = 0


class CustomerListResponse(BaseModel):
    """Paginated customer list response."""

    items: list[CustomerResponse]
    total: int
    page: int
    per_page: int
    pages: int
