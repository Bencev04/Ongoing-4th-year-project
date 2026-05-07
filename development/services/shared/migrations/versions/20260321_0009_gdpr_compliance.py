"""GDPR compliance columns and platform settings

Adds consent tracking, anonymization scheduling, and notification log
hashing columns.  Seeds platform_settings with retention/privacy defaults.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- users: consent tracking + anonymization scheduling ----------------
    op.add_column(
        "users",
        sa.Column("privacy_consent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("privacy_consent_version", sa.String(20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("anonymize_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # -- customers: data-processing consent --------------------------------
    op.add_column(
        "customers",
        sa.Column(
            "data_processing_consent",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "customers",
        sa.Column(
            "data_processing_consent_at", sa.DateTime(timezone=True), nullable=True
        ),
    )

    # -- notification_log: recipient hash for post-delivery minimisation ---
    op.add_column(
        "notification_log",
        sa.Column("recipient_hash", sa.String(64), nullable=True),
    )

    # -- platform_settings seeds ------------------------------------------
    settings_table = sa.table(
        "platform_settings",
        sa.column("key", sa.String),
        sa.column("value", sa.JSON),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "key": "notification_log_retention_days",
                "value": 90,
                "description": "Days to retain delivered/failed notification logs before cleanup",
            },
            {
                "key": "audit_log_retention_days",
                "value": 730,
                "description": "Days to retain audit log entries (default 2 years)",
            },
            {
                "key": "privacy_policy_version",
                "value": "1.0",
                "description": "Current privacy policy version — users must re-consent when this changes",
            },
        ],
    )


def downgrade() -> None:
    # Remove platform_settings seeds
    op.execute(
        "DELETE FROM platform_settings WHERE key IN "
        "('notification_log_retention_days', 'audit_log_retention_days', 'privacy_policy_version')"
    )

    op.drop_column("notification_log", "recipient_hash")
    op.drop_column("customers", "data_processing_consent_at")
    op.drop_column("customers", "data_processing_consent")
    op.drop_column("users", "anonymize_scheduled_at")
    op.drop_column("users", "privacy_consent_version")
    op.drop_column("users", "privacy_consent_at")
