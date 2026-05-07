"""add notification preference columns to customers table

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "notify_whatsapp", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "customers",
        sa.Column("notify_email", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("customers", "notify_email")
    op.drop_column("customers", "notify_whatsapp")
