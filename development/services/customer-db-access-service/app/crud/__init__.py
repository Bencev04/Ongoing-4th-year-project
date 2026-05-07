"""CRUD package for customer-service."""

from .customer import (
    anonymize_customer,
    create_customer,
    create_note,
    delete_customer,
    delete_note,
    export_customer_data,
    get_customer,
    get_customer_by_email,
    get_customer_notes,
    get_customers,
    get_note,
    update_customer,
    update_note,
)

__all__ = [
    "get_customer",
    "get_customer_by_email",
    "get_customers",
    "create_customer",
    "update_customer",
    "delete_customer",
    "get_note",
    "get_customer_notes",
    "create_note",
    "update_note",
    "delete_note",
    "export_customer_data",
    "anonymize_customer",
]
