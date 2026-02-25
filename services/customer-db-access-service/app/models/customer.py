"""
Customer database models.

Defines SQLAlchemy ORM models for customers and their notes.
These models map directly to PostgreSQL tables.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    ForeignKey, Text,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

import sys
sys.path.append("../../shared")
from common.database import Base


class Customer(Base):
    """
    Customer model representing clients of business owners.

    Maps to the ``customers`` table defined in ``init-db.sql``.

    Attributes:
        id: Primary key
        owner_id: Reference to the business owner (user)
        name: Customer's full name
        email: Contact email
        phone: Contact phone number
        address: Street address
        eircode: Irish postal code (Eircode)
        company_name: Company or trading name
        is_active: Whether the customer is active
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Owner relationship (foreign key to users table in user-service)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Contact information
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Address
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    eircode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Company
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    notes: Mapped[List["CustomerNote"]] = relationship(
        "CustomerNote",
        back_populates="customer",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
    
    @property
    def full_address(self) -> str:
        """Return formatted full address."""
        parts = [self.address, self.eircode]
        return ", ".join(p for p in parts if p)


class CustomerNote(Base):
    """
    Customer notes model for storing communication and internal notes.

    Maps to the ``customer_notes`` table defined in ``init-db.sql``.

    Attributes:
        id: Primary key
        customer_id: Reference to parent customer
        created_by_id: User who created the note
        content: Note content text
        created_at: Note creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "customer_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Note author (foreign key to users table)
    created_by_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Note content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="notes")
    
    def __repr__(self) -> str:
        return f"<CustomerNote(id={self.id}, customer_id={self.customer_id})>"
