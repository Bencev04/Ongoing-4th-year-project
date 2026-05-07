"""
UserPermission database model for tenant-scoped permission assignments.

Each row grants (or explicitly denies) a single permission to a
subordinate user within a tenant.  Owner and admin users bypass
permission checks entirely, so they never need rows here.

The permission catalog is defined as a module-level constant so
that CRUD and seeding logic can reference it without duplication.
"""

import sys
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

sys.path.append("../../shared")
from common.database import Base

# ── Permission catalog ───────────────────────────────────────────────────────
# Canonical list of all assignable permissions.
PERMISSION_CATALOG: tuple[str, ...] = (
    "company.view",
    "company.update",
    "audit.view",
    "users.invite",
    "users.deactivate",
    "users.reset_password",
    "employees.create",
    "employees.edit",
    "employees.delete",
    "customers.create",
    "customers.edit",
    "customers.delete",
    "jobs.create",
    "jobs.edit",
    "jobs.delete",
    "jobs.assign",
    "jobs.schedule",
    "jobs.update_status",
    "notes.create",
    "notes.edit",
    "notes.delete",
)

# Default permissions per subordinate role.
DEFAULT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "manager": {
        "company.view",
        "employees.create",
        "employees.edit",
        "customers.create",
        "customers.edit",
        "jobs.create",
        "jobs.edit",
        "jobs.assign",
        "jobs.schedule",
        "jobs.update_status",
        "notes.create",
        "notes.edit",
    },
    "employee": {
        "company.view",
        "customers.create",
        "customers.edit",
        "jobs.create",
        "jobs.edit",
        "jobs.update_status",
        "notes.create",
        "notes.edit",
    },
    "viewer": {
        "company.view",
    },
}


class UserPermission(Base):
    """
    Tenant-scoped permission assignment for a subordinate user.

    Attributes:
        id:          Auto-incrementing primary key.
        owner_id:    Tenant isolation key (FK → users.id).
        user_id:     The subordinate user receiving the permission.
        permission:  Machine-readable permission name from the catalog.
        granted:     Whether the permission is granted (True) or denied.
        created_at:  Row creation timestamp.
        updated_at:  Last modification timestamp.
    """

    __tablename__ = "user_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "user_id",
            "permission",
            name="uq_user_permissions_owner_user_perm",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserPermission(user_id={self.user_id}, "
            f"permission='{self.permission}', granted={self.granted})>"
        )
