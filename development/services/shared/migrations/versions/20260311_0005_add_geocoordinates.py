"""add latitude and longitude columns to jobs and customers tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- Jobs table: add geocoordinate columns --------------------------------
    op.add_column("jobs", sa.Column("latitude", sa.Float, nullable=True))
    op.add_column("jobs", sa.Column("longitude", sa.Float, nullable=True))
    op.create_index("ix_jobs_lat_lng", "jobs", ["latitude", "longitude"])

    # -- Customers table: add geocoordinate columns ---------------------------
    op.add_column("customers", sa.Column("latitude", sa.Float, nullable=True))
    op.add_column("customers", sa.Column("longitude", sa.Float, nullable=True))
    op.create_index("ix_customers_lat_lng", "customers", ["latitude", "longitude"])


def downgrade() -> None:
    # -- Customers table: remove geocoordinate columns ------------------------
    op.drop_index("ix_customers_lat_lng", table_name="customers")
    op.drop_column("customers", "longitude")
    op.drop_column("customers", "latitude")

    # -- Jobs table: remove geocoordinate columns -----------------------------
    op.drop_index("ix_jobs_lat_lng", table_name="jobs")
    op.drop_column("jobs", "longitude")
    op.drop_column("jobs", "latitude")
