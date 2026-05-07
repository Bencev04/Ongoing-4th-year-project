"""add user_permissions table for tenant-scoped permission assignments

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Permission catalog with role-based defaults ──────────────────────────────
# Maps permission_name → set of roles that receive it by default.
_DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    "company.view": {"manager", "employee", "viewer"},
    "company.update": set(),
    "audit.view": set(),
    "users.invite": set(),
    "users.deactivate": set(),
    "users.reset_password": set(),
    "employees.create": {"manager"},
    "employees.edit": {"manager"},
    "employees.delete": set(),
    "customers.create": {"manager", "employee"},
    "customers.edit": {"manager", "employee"},
    "customers.delete": set(),
    "jobs.create": {"manager", "employee"},
    "jobs.edit": {"manager", "employee"},
    "jobs.delete": set(),
    "jobs.assign": {"manager"},
    "jobs.schedule": {"manager"},
    "jobs.update_status": {"manager", "employee"},
    "notes.create": {"manager", "employee"},
    "notes.edit": {"manager", "employee"},
    "notes.delete": set(),
}


def upgrade() -> None:
    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("permission", sa.String(100), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "owner_id",
            "user_id",
            "permission",
            name="uq_user_permissions_owner_user_perm",
        ),
    )

    # Seed default permissions for every existing subordinate user.
    # owner/admin/superadmin users bypass permission checks, so we
    # only seed for manager, employee, and viewer roles.
    conn = op.get_bind()
    subordinate_users = conn.execute(
        sa.text(
            "SELECT id, owner_id, role FROM users "
            "WHERE role IN ('manager', 'employee', 'viewer') "
            "AND owner_id IS NOT NULL AND is_active = true"
        )
    ).fetchall()

    if subordinate_users:
        rows = []
        for user_id, owner_id, role in subordinate_users:
            for perm_name, default_roles in _DEFAULT_PERMISSIONS.items():
                if role in default_roles:
                    rows.append(
                        {
                            "owner_id": owner_id,
                            "user_id": user_id,
                            "permission": perm_name,
                            "granted": True,
                        }
                    )
        if rows:
            op.bulk_insert(
                sa.table(
                    "user_permissions",
                    sa.column("owner_id", sa.Integer),
                    sa.column("user_id", sa.Integer),
                    sa.column("permission", sa.String),
                    sa.column("granted", sa.Boolean),
                ),
                rows,
            )


def downgrade() -> None:
    op.drop_table("user_permissions")
