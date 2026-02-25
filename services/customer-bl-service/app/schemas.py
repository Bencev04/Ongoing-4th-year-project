"""
Pydantic schemas for Customer Service (Business Logic Layer).

Defines the public API contract for customer management,
notes, and enriched responses.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ==============================================================================
# Request Schemas
# ==============================================================================

class CustomerCreateRequest(BaseModel):
    """Request body for creating a customer."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    company: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    eircode: Optional[str] = Field(None, max_length=10)


class CustomerUpdateRequest(BaseModel):
    """Partial update request for a customer."""
    model_config = ConfigDict(extra="forbid")

    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    company: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = None
    eircode: Optional[str] = Field(None, max_length=10)


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
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    address: Optional[str] = None
    eircode: Optional[str] = None
    owner_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerNoteResponse(BaseModel):
    """Public customer note response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    content: str
    created_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class JobSummary(BaseModel):
    """Lightweight job summary for customer enrichment."""
    id: int
    title: str
    status: str
    start_time: Optional[datetime] = None


class CustomerWithHistoryResponse(CustomerResponse):
    """Customer enriched with recent job history and notes."""
    recent_jobs: List[JobSummary] = []
    customer_notes: List[CustomerNoteResponse] = []
    total_jobs: int = 0


class CustomerListResponse(BaseModel):
    """Paginated customer list response."""
    items: List[CustomerResponse]
    total: int
    page: int
    per_page: int
    pages: int
