"""add notification_log table

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column("job_id", sa.Integer, nullable=True),
        sa.Column("customer_id", sa.Integer, nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("message_body", sa.Text, nullable=False),
        sa.Column("external_message_id", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Indexes for common query patterns
    op.create_index(
        "ix_notification_log_owner_job",
        "notification_log",
        ["owner_id", "job_id"],
    )
    op.create_index(
        "ix_notification_log_owner_created",
        "notification_log",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "ix_notification_log_status_retry",
        "notification_log",
        ["status", "next_retry_at"],
    )
    op.create_index(
        "ix_notification_log_external_msg_id",
        "notification_log",
        ["external_message_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_log_external_msg_id", table_name="notification_log")
    op.drop_index("ix_notification_log_status_retry", table_name="notification_log")
    op.drop_index("ix_notification_log_owner_created", table_name="notification_log")
    op.drop_index("ix_notification_log_owner_job", table_name="notification_log")
    op.drop_table("notification_log")
