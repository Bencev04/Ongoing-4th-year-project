"""
Customer database models.

Defines SQLAlchemy ORM models for customers and their notes.
These models map directly to PostgreSQL tables.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from common.database import Base


class Customer(Base):
    """
    Customer model representing clients of business owners.

    Maps to the ``customers`` table managed by Alembic migrations.

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
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Address
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    eircode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Company
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Notification preferences
    notify_whatsapp: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    notify_email: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # GDPR: data-processing consent (controller acknowledgment)
    data_processing_consent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        doc="Owner/admin confirmed they have consent to process this customer's data",
    )
    data_processing_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When data-processing consent was recorded",
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    notes: Mapped[list["CustomerNote"]] = relationship(
        "CustomerNote", back_populates="customer", cascade="all, delete-orphan"
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

    Maps to the ``customer_notes`` table managed by Alembic migrations.

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
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    customer: Mapped["Customer"] = relationship("Customer", back_populates="notes")

    def __repr__(self) -> str:
        return f"<CustomerNote(id={self.id}, customer_id={self.customer_id})>"
