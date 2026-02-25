"""
User, Employee, Organization, and AuditLog database models.

Defines SQLAlchemy ORM models for users, employees, organizations,
and the platform audit trail.  These models map directly to
PostgreSQL tables defined in ``scripts/init-db.sql``.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Date,
    ForeignKey, Enum as SQLEnum, Text, Numeric, BigInteger,
    UniqueConstraint, JSON,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

import sys
sys.path.append("../../shared")
from common.database import Base


class UserRole(str, enum.Enum):
    """
    User role enumeration.

    Defines permission levels within the system.  The numeric
    ranking used for hierarchy checks lives in ``common.auth.ROLE_HIERARCHY``.
    """
    SUPERADMIN = "superadmin"
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"
    VIEWER = "viewer"


class Organization(Base):
    """
    Organization model representing a platform-level entity.

    Organizations are the top-level grouping managed by superadmins.
    Each tenant (company + owner user) belongs to exactly one
    organization.  Superadmins can create, suspend, and configure
    organizations.

    Attributes:
        id:                Primary key.
        name:              Display name of the organization.
        slug:              URL-safe unique identifier.
        billing_email:     Contact email for billing.
        billing_plan:      Current subscription tier.
        max_users:         Maximum users allowed in this org.
        max_customers:     Maximum customers allowed in this org.
        is_active:         Whether the org is currently active.
        suspended_at:      Timestamp when org was suspended (if any).
        suspended_reason:  Human-readable reason for suspension.
        created_at:        Record creation timestamp.
        updated_at:        Last update timestamp.
    """
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    billing_plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_customers: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    suspended_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    companies: Mapped[List["Company"]] = relationship(
        "Company", back_populates="organization"
    )
    users: Mapped[List["User"]] = relationship(
        "User", back_populates="organization"
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class Company(Base):
    """
    Company model representing a business tenant.
    
    Each company is a distinct tenant in the multi-tenancy model.
    Users belong to a company, and all resources (customers, jobs)
    are scoped by the owner_id of the company's owner user.

    Attributes:
        id: Primary key
        organization_id: FK to the parent organization
        name: Company display name
        address: Business address
        phone: Contact phone number
        email: Contact email address
        eircode: Irish postal code
        logo_url: URL to company logo image
        is_active: Whether the company is active
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "companies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    eircode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
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
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", back_populates="companies", foreign_keys=[organization_id]
    )
    users: Mapped[List["User"]] = relationship("User", back_populates="company")
    
    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}')>"


class User(Base):
    """
    User model representing business owners and their team members.
    
    Attributes:
        id: Primary key
        email: Unique email address
        hashed_password: Bcrypt hashed password
        first_name: User's first name
        last_name: User's last name
        phone: User's phone number
        role: User's permission role
        is_active: Whether the user can log in
        owner_id: If employee, reference to owner user
        company_id: Reference to the company this user belongs to
        organization_id: Reference to the parent organization
        created_at: Account creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    role: Mapped[str] = mapped_column(
        String(50), 
        default="employee", 
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Self-referential relationship for owner -> employees
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("users.id"), 
        nullable=True,
        index=True
    )
    
    # Company relationship for tenant metadata
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("companies.id"),
        nullable=True,
        index=True
    )

    # Organization relationship for platform-level grouping
    organization_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=True,
        index=True
    )
    
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
    employees: Mapped[List["User"]] = relationship(
        "User",
        backref="owner",
        remote_side=[id],
        foreign_keys=[owner_id]
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company", back_populates="users", foreign_keys=[company_id]
    )
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization", back_populates="users", foreign_keys=[organization_id]
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role={self.role})>"


class Employee(Base):
    """
    Employee model for detailed employee information.
    
    Extends basic user info with employee-specific fields like
    position, department, and phone.
    
    Attributes:
        id: Primary key
        user_id: Reference to User model
        owner_id: Reference to owner User
        department: Department name
        position: Job title/position
        phone: Contact phone number
        hire_date: Date of hire
        hourly_rate: Employee hourly rate
        skills: Employee skills (comma-separated)
        notes: Additional notes about employee
        is_active: Whether the employee is active
    """
    __tablename__ = "employees"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("users.id"), 
        nullable=False,
        index=True
    )
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hire_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    hourly_rate: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    skills: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=True)

    # Unique constraint matching DB schema
    __table_args__ = (
        UniqueConstraint("user_id", "owner_id", name="employees_user_id_owner_id_key"),
    )

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
    
    # Relationship to User
    user: Mapped["User"] = relationship("User", backref="employee_details", foreign_keys=[user_id])
    
    def __repr__(self) -> str:
        return f"<Employee(id={self.id}, user_id={self.user_id}, position='{self.position}')>"


class AuditLog(Base):
    """
    Audit log model for recording platform-wide actions.

    Every significant admin action (org creation, suspension,
    impersonation, password resets, etc.) writes a row here.
    The ``impersonator_id`` field is populated when actions are
    performed under impersonation, enabling full traceability.

    Attributes:
        id:               Auto-incrementing primary key (BIGSERIAL).
        timestamp:        When the action occurred.
        actor_id:         User who performed the action.
        actor_email:      Denormalised email for quick log readability.
        actor_role:       Role at the time of the action.
        impersonator_id:  If impersonating, the real superadmin's ID.
        organization_id:  Org context (NULL for system-level actions).
        action:           Machine-readable action name (e.g. 'org.create').
        resource_type:    Type of resource affected (e.g. 'organization').
        resource_id:      Primary key of the affected resource (string).
        details:          JSONB payload with action-specific data.
        ip_address:       Client IP address.
    """
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    actor_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    impersonator_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    organization_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizations.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', "
            f"actor_id={self.actor_id})>"
        )


class PlatformSetting(Base):
    """
    Platform setting model for system-wide configuration.

    Stores key-value configuration entries managed exclusively by
    superadmins.  Examples include maintenance mode toggles,
    rate-limit thresholds, and feature flags.

    Attributes:
        key:         Unique setting key (primary key, max 100 chars).
        value:       JSON payload containing the setting value.
        description: Human-readable explanation of the setting's purpose.
        updated_by:  FK to the user who last modified this setting.
        updated_at:  Timestamp of the most recent update.
    """
    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(
        String(100), primary_key=True, nullable=False
    )
    value: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )

    def __repr__(self) -> str:
        return f"<PlatformSetting(key='{self.key}')>"
