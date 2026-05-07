"""
Multi-employee job assignment: junction table and data migration.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-06

This migration introduces the `job_employees` junction table to enable
multiple employees to be assigned to a single job. The existing single-
employee `assigned_employee_id` column is migrated to the new structure
and then dropped.

**Overview:**
1. Create new `job_employees` junction table with FK relations
2. Migrate existing assignments: 1 row per job with assigned_employee_id
3. Drop the now-unused `assigned_employee_id` column and its index

**Rationale:**
- Supports many-to-many relationship (jobs ↔ employees)
- Maintains tenant isolation via owner_id on junction table
- Cascading deletes ensure referential integrity
- UNIQUE constraint prevents duplicate assignments
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Create job_employees junction table, migrate data, drop old column.

    Steps:
    1. Create the new junction table with foreign keys and indexes
    2. Migrate existing assignments from jobs.assigned_employee_id
    3. Drop the old column and its index from jobs table
    """

    # =====================================================================
    # 1. CREATE job_employees JUNCTION TABLE
    # =====================================================================
    # This table represents the many-to-many relationship between jobs and
    # employees. Each row indicates that a specific employee is assigned to
    # a specific job. The UNIQUE constraint prevents duplicate assignments.
    #
    # Design decisions:
    # - id: Surrogate key (not strictly necessary but useful for history/audit)
    # - owner_id: Tenant isolation (matches jobs.owner_id for consistency)
    # - created_at: Track when assignment was made (useful for audit trail)
    # - Cascading deletes: Job deletion removes assignments automatically

    op.create_table(
        "job_employees",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.Integer,
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.Integer,
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        # UNIQUE constraint: prevent assigning the same employee twice to same job
        sa.UniqueConstraint(
            "job_id", "employee_id", name="unique_job_employee_assignment"
        ),
    )

    # Indexes for efficient querying:
    # - Primary lookup: find all employees for a job
    # - Filter: find all jobs assigned to a specific employee
    # - Tenant filtering: filter by owner_id for multi-tenancy
    op.create_index("idx_job_employees_job_id", "job_employees", ["job_id"])
    op.create_index("idx_job_employees_employee_id", "job_employees", ["employee_id"])
    op.create_index("idx_job_employees_owner_id", "job_employees", ["owner_id"])

    # =====================================================================
    # 2. MIGRATE DATA: jobs.assigned_employee_id → job_employees
    # =====================================================================
    # Copy existing assignments to the new junction table. Only jobs with
    # a non-null assigned_employee_id are migrated (empty assignments are
    # handled by nullable logic in the BL layer).

    op.execute(
        sa.text(
            """
            INSERT INTO job_employees (job_id, employee_id, owner_id, created_at)
            SELECT
                j.id,
                j.assigned_employee_id,
                j.owner_id,
                CURRENT_TIMESTAMP
            FROM jobs j
            WHERE j.assigned_employee_id IS NOT NULL
            """
        )
    )

    # =====================================================================
    # 3. DROP OLD COLUMN AND ITS INDEX
    # =====================================================================
    # Remove the now-obsolete assigned_employee_id column and its index
    # from the jobs table. This ensures there's a single source of truth.

    op.drop_index("idx_jobs_assigned_employee_id", table_name="jobs")
    op.drop_column("jobs", "assigned_employee_id")


def downgrade() -> None:
    """
    Rollback: restore old column, restore data, drop junction table.

    Steps:
    1. Add the assigned_employee_id column back to jobs
    2. Restore data from job_employees to jobs.assigned_employee_id
    3. Drop the job_employees table and its indexes
    """

    # =====================================================================
    # 1. RESTORE assigned_employee_id COLUMN
    # =====================================================================
    op.add_column(
        "jobs",
        sa.Column("assigned_employee_id", sa.Integer, nullable=True),
    )

    # =====================================================================
    # 2. RESTORE DATA FROM job_employees
    # =====================================================================
    # For jobs with multiple employees, only the first one is restored.
    # This is a data loss scenario, but necessary for clean rollback.
    # (In production, you'd want to coordinate with the team on how to
    # handle multi-employee assignments during rollback.)

    op.execute(
        sa.text(
            """
            UPDATE jobs j
            SET assigned_employee_id = (
                SELECT MIN(je.employee_id)
                FROM job_employees je
                WHERE je.job_id = j.id
            )
            WHERE EXISTS (
                SELECT 1
                FROM job_employees je
                WHERE je.job_id = j.id
            )
            """
        )
    )

    # =====================================================================
    # 3. RECREATE INDEX
    # =====================================================================
    op.create_index(
        "idx_jobs_assigned_employee_id",
        "jobs",
        ["assigned_employee_id"],
    )

    # =====================================================================
    # 4. DROP junction TABLE AND INDEXES
    # =====================================================================
    op.drop_index("idx_job_employees_owner_id", table_name="job_employees")
    op.drop_index("idx_job_employees_employee_id", table_name="job_employees")
    op.drop_index("idx_job_employees_job_id", table_name="job_employees")
    op.drop_table("job_employees")
