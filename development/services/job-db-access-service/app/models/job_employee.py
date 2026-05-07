"""
Job-Employee association model for many-to-many relationships.

Defines the SQLAlchemy ORM model for the job_employees junction table,
which represents the assignment of employees to jobs.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .job import Base


class JobEmployee(Base):
    """
    Junction table model for job-employee assignments.

    This model enables the many-to-many relationship between jobs and employees.
    Each row represents one employee assigned to one job. The UNIQUE constraint
    prevents duplicate assignments.

    **Design rationale:**
    - Supports multiple employees per job (1:N → M:N)
    - Maintains tenant isolation via owner_id
    - Cascading deletes ensure referential integrity
    - created_at tracks assignment timestamp for audit trail
    - No composite primary key; surrogate id allows for future extension

    **Indexes:**
    - job_id: Find all employees assigned to a job
    - employee_id: Find all jobs assigned to an employee
    - owner_id: Filter assignments by tenant

    Attributes:
        id: Surrogate primary key
        job_id: Foreign key to jobs table (cascading delete)
        employee_id: Foreign key to employees table (cascading delete)
        owner_id: Tenant owner for multi-tenancy isolation
        created_at: Timestamp when assignment was made
    """

    __tablename__ = "job_employees"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys with cascading deletes
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Tenant isolation key (matches jobs.owner_id)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Audit timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "employee_id",
            name="unique_job_employee_assignment",
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<JobEmployee("
            f"id={self.id}, "
            f"job_id={self.job_id}, "
            f"employee_id={self.employee_id}, "
            f"owner_id={self.owner_id}"
            ")>"
        )
