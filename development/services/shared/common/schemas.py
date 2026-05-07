"""
Common schemas shared across microservices.

Contains base Pydantic models and common response schemas
used for API responses and inter-service communication.
"""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

# Generic type variable for pagination
T = TypeVar("T")


class BaseSchema(BaseModel):
    """
    Base schema with common configuration.

    All schemas should inherit from this for consistent behavior.
    """

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy models
        str_strip_whitespace=True,  # Strip whitespace from strings
    )


class TimestampMixin(BaseModel):
    """
    Mixin for models with timestamp fields.

    Provides created_at and updated_at fields.
    """

    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response schema.

    Attributes:
        items: List of items for current page
        total: Total number of items
        page: Current page number
        per_page: Number of items per page
        pages: Total number of pages
    """

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


class HealthResponse(BaseModel):
    """
    Health check response schema.

    Used by all services to report their health status.
    """

    status: str = "healthy"
    service: str
    version: str = "1.0.0"
    timestamp: datetime


class ErrorResponse(BaseModel):
    """
    Standard error response schema.

    Attributes:
        detail: Error message
        code: Error code for client handling
        timestamp: When the error occurred
    """

    detail: str
    code: str | None = None
    timestamp: datetime = datetime.utcnow()


class SuccessResponse(BaseModel):
    """
    Standard success response schema.

    Used for operations that don't return data.
    """

    success: bool = True
    message: str
    timestamp: datetime = datetime.utcnow()
