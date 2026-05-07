"""Schemas package for customer-service."""

from .customer import (
    CustomerCreate,
    CustomerListResponse,
    CustomerNoteCreate,
    CustomerNoteResponse,
    CustomerNoteUpdate,
    CustomerResponse,
    CustomerSearchParams,
    CustomerUpdate,
    CustomerWithNotesResponse,
)

__all__ = [
    "CustomerCreate",
    "CustomerUpdate",
    "CustomerResponse",
    "CustomerWithNotesResponse",
    "CustomerListResponse",
    "CustomerNoteCreate",
    "CustomerNoteUpdate",
    "CustomerNoteResponse",
    "CustomerSearchParams",
]
