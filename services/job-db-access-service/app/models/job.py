"""
Job/Event database models.

Defines SQLAlchemy ORM models for jobs (calendar events)
and their audit history.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, 
    ForeignKey, Text, Enum as SQLEnum, Float,
    CheckConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

import sys
sys.path.append("../../shared")
from common.database import Base


class JobStatus(str, enum.Enum):
    """
    Job status enumeration.
    
    Defines the lifecycle states of a job.
    """
    PENDING = "pending"          # Job created but not scheduled
    SCHEDULED = "scheduled"      # Job has a scheduled time
    IN_PROGRESS = "in_progress"  # Work has started
    COMPLETED = "completed"      # Job finished successfully
    CANCELLED = "cancelled"      # Job was cancelled
    ON_HOLD = "on_hold"          # Job temporarily paused


class JobPriority(str, enum.Enum):
    """
    Job priority enumeration.
    """
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Job(Base):
    """
    Job model representing calendar events/appointments.
    
    Attributes:
        id: Primary key
        owner_id: Business owner (user) this job belongs to
        title: Job title/name
        description: Detailed description
        start_time: Scheduled start time (null if unscheduled)
        end_time: Scheduled end time
        all_day: Whether this is an all-day event
        status: Current job status
        priority: Job priority level
        assigned_employee_id: Employee assigned to the job
        customer_id: Associated customer
        location: Job location/address
        eircode: Postal code for location
        estimated_duration: Estimated duration in minutes
        actual_duration: Actual duration in minutes (after completion)
        notes: Internal notes
        color: UI display color
        is_recurring: Whether this is a recurring job
        recurrence_rule: iCal RRULE for recurring jobs
        parent_job_id: For recurring jobs, reference to parent
        created_by_id: User who created the job
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = "jobs"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    # Owner relationship
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Scheduling
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Status and priority
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True
    )
    priority: Mapped[str] = mapped_column(
        String(50),
        default="normal",
        nullable=False
    )
    
    # Assignments (foreign keys to other services' tables)
    assigned_employee_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True,
        index=True
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True,
        index=True
    )
    
    # Location
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    eircode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Duration tracking
    estimated_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # minutes
    actual_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # minutes
    
    # Additional fields
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # hex color
    
    # Recurrence
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    parent_job_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("jobs.id"),
        nullable=True
    )
    
    # Audit
    created_by_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    history: Mapped[List["JobHistory"]] = relationship(
        "JobHistory",
        back_populates="job",
        cascade="all, delete-orphan"
    )
    
    recurring_instances: Mapped[List["Job"]] = relationship(
        "Job",
        backref="parent_job",
        remote_side=[id],
        foreign_keys=[parent_job_id]
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR (end_time > start_time)",
            name="valid_time_range"
        ),
    )
    
    def __repr__(self) -> str:
        return f"<Job(id={self.id}, title='{self.title}', status={self.status})>"
    
    @property
    def duration_minutes(self) -> Optional[int]:
        """Calculate duration from start/end times."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() / 60)
        return self.estimated_duration
    
    @property
    def is_scheduled(self) -> bool:
        """Check if job has a scheduled time."""
        return self.start_time is not None


class JobHistory(Base):
    """
    Job history model for audit trail.
    
    Tracks all changes made to jobs for compliance and debugging.
    
    Attributes:
        id: Primary key
        job_id: Reference to parent job
        changed_by_id: User who made the change
        change_type: Type of change (create, update, delete, status_change)
        field_changed: Name of field that was changed
        old_value: Previous value (as string)
        new_value: New value (as string)
        created_at: When the change was made
    """
    __tablename__ = "job_history"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    changed_by_id: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False)
    field_changed: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        nullable=False
    )
    
    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="history")
    
    def __repr__(self) -> str:
        return f"<JobHistory(id={self.id}, job_id={self.job_id}, change_type='{self.change_type}')>"
