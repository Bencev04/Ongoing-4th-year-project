"""fix datetime tz, soft-delete, and nullable flag

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _upgrade_to_timestamptz(table_name: str, column_name: str) -> None:
    """Convert timestamp columns to TIMESTAMPTZ only when needed."""
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                v_table text := :table_name;
                v_column text := :column_name;
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = v_table
                      AND column_name = v_column
                      AND data_type = 'timestamp without time zone'
                ) THEN
                    EXECUTE format(
                        'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMP WITH TIME ZONE USING %I AT TIME ZONE ''UTC''',
                        v_table,
                        v_column,
                        v_column
                    );
                END IF;
            END $$;
            """
        ).bindparams(table_name=table_name, column_name=column_name)
    )


def _downgrade_to_timestamp(table_name: str, column_name: str) -> None:
    """Convert TIMESTAMPTZ columns back to TIMESTAMP only when needed."""
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE
                v_table text := :table_name;
                v_column text := :column_name;
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = v_table
                      AND column_name = v_column
                      AND data_type = 'timestamp with time zone'
                ) THEN
                    EXECUTE format(
                        'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMP WITHOUT TIME ZONE USING %I AT TIME ZONE ''UTC''',
                        v_table,
                        v_column,
                        v_column
                    );
                END IF;
            END $$;
            """
        ).bindparams(table_name=table_name, column_name=column_name)
    )


def upgrade() -> None:
    # 8a) DateTime naive -> timezone-aware (safe for existing schemas).
    datetime_columns: list[tuple[str, str]] = [
        ("users", "created_at"),
        ("users", "updated_at"),
        ("companies", "created_at"),
        ("companies", "updated_at"),
        ("employees", "created_at"),
        ("employees", "updated_at"),
        ("audit_logs", "timestamp"),
        ("platform_settings", "updated_at"),
        ("customers", "created_at"),
        ("customers", "updated_at"),
        ("customer_notes", "created_at"),
        ("customer_notes", "updated_at"),
    ]
    for table_name, column_name in datetime_columns:
        _upgrade_to_timestamptz(table_name, column_name)

    # 8b) Jobs soft-delete column.
    op.add_column(
        "jobs",
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=True,
        ),
    )
    op.execute(sa.text("UPDATE jobs SET is_active = TRUE WHERE is_active IS NULL"))
    op.alter_column("jobs", "is_active", nullable=False)
    op.create_index("idx_jobs_is_active", "jobs", ["is_active"])

    # 8c) employees.is_active nullable -> non-null.
    op.execute(sa.text("UPDATE employees SET is_active = TRUE WHERE is_active IS NULL"))
    op.alter_column("employees", "is_active", nullable=False)


def downgrade() -> None:
    op.alter_column("employees", "is_active", nullable=True)

    op.drop_index("idx_jobs_is_active", table_name="jobs")
    op.drop_column("jobs", "is_active")

    datetime_columns: list[tuple[str, str]] = [
        ("users", "created_at"),
        ("users", "updated_at"),
        ("companies", "created_at"),
        ("companies", "updated_at"),
        ("employees", "created_at"),
        ("employees", "updated_at"),
        ("audit_logs", "timestamp"),
        ("platform_settings", "updated_at"),
        ("customers", "created_at"),
        ("customers", "updated_at"),
        ("customer_notes", "created_at"),
        ("customer_notes", "updated_at"),
    ]
    for table_name, column_name in datetime_columns:
        _downgrade_to_timestamp(table_name, column_name)
