"""CRUD package for customer-service."""

from .customer import (
    get_customer, get_customer_by_email, get_customers,
    create_customer, update_customer, delete_customer,
    get_note, get_customer_notes, create_note, update_note, delete_note
)

__all__ = [
    "get_customer", "get_customer_by_email", "get_customers",
    "create_customer", "update_customer", "delete_customer",
    "get_note", "get_customer_notes", "create_note", "update_note", "delete_note"
]
