"""
Pydantic schemas for Job Service (Business Logic Layer).

These schemas define the public-facing API contract for job
management, scheduling, and calendar queries.
"""

from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


# ==============================================================================
# Request Schemas
# ==============================================================================

class JobCreateRequest(BaseModel):
    """
    Request body for creating a new job.

    ``owner_id`` and ``customer_id`` validation happen at the
    business layer.
    """

    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    customer_id: Optional[int] = None
    assigned_to: Optional[int] = None
    status: str = Field(default="pending", description="pending | scheduled | in_progress | completed | cancelled")
    priority: str = Field(default="normal", description="low | normal | high | urgent")
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_duration: Optional[int] = Field(None, ge=0, description="Duration in minutes")
    address: Optional[str] = None
    notes: Optional[str] = None


class JobUpdateRequest(BaseModel):
    """Partial update request for a job."""
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    customer_id: Optional[int] = None
    assigned_to: Optional[int] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_duration: Optional[int] = Field(None, ge=0)
    address: Optional[str] = None
    notes: Optional[str] = None


class JobAssignRequest(BaseModel):
    """Assign a job to an employee."""
    assigned_to: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class JobScheduleRequest(BaseModel):
    """Schedule a job to a time slot."""
    start_time: datetime
    end_time: datetime
    assigned_to: Optional[int] = None


class JobStatusUpdateRequest(BaseModel):
    """Update only the status of a job."""
    status: str = Field(..., description="pending | scheduled | in_progress | completed | cancelled")
    notes: Optional[str] = None


# ==============================================================================
# Response Schemas
# ==============================================================================

class JobResponse(BaseModel):
    """Public job response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    customer_id: Optional[int] = None
    owner_id: int
    assigned_to: Optional[int] = None
    status: str
    priority: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    estimated_duration: Optional[int] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobWithDetailsResponse(JobResponse):
    """Job response enriched with customer and assignee names."""
    customer_name: Optional[str] = None
    assigned_to_name: Optional[str] = None


class CalendarJobResponse(BaseModel):
    """Simplified job schema for calendar views (matches db-access CalendarEventResponse)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: bool
    status: str
    priority: str
    color: Optional[str] = None
    assigned_to: Optional[int] = None
    customer_id: Optional[int] = None


class CalendarDayResponse(BaseModel):
    """Calendar view: jobs for a specific day."""
    date: date
    jobs: List[CalendarJobResponse]
    total_jobs: int


class CalendarMonthResponse(BaseModel):
    """Calendar view: summary for a whole month."""
    year: int
    month: int
    days: List[CalendarDayResponse]


class ScheduleConflict(BaseModel):
    """Describes a scheduling conflict with an existing job."""
    conflicting_job_id: int
    conflicting_job_title: str
    start_time: datetime
    end_time: datetime


class ScheduleConflictResponse(BaseModel):
    """Response when a scheduling conflict is detected."""
    has_conflicts: bool
    conflicts: List[ScheduleConflict]


class JobQueueResponse(BaseModel):
    """Unscheduled jobs waiting in the queue."""
    items: List[JobResponse]
    total: int


class JobListResponse(BaseModel):
    """Paginated job list response."""
    items: List[JobResponse]
    total: int
    page: int
    per_page: int
    pages: int
