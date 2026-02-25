"""Schemas package for customer-service."""

from .customer import (
    CustomerCreate, CustomerUpdate, CustomerResponse, 
    CustomerWithNotesResponse, CustomerListResponse,
    CustomerNoteCreate, CustomerNoteUpdate, CustomerNoteResponse,
    CustomerSearchParams
)

__all__ = [
    "CustomerCreate", "CustomerUpdate", "CustomerResponse",
    "CustomerWithNotesResponse", "CustomerListResponse",
    "CustomerNoteCreate", "CustomerNoteUpdate", "CustomerNoteResponse",
    "CustomerSearchParams"
]
