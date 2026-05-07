"""
Pydantic schemas for Job Service (Business Logic Layer).

These schemas define the public-facing API contract for job
management, scheduling, and calendar queries.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

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
    description: str | None = None
    customer_id: int | None = None
    assigned_to: int | None = None
    status: str = Field(
        default="pending",
        description="pending | scheduled | in_progress | completed | cancelled",
    )
    priority: str = Field(default="normal", description="low | normal | high | urgent")
    start_time: datetime | None = None
    end_time: datetime | None = None
    estimated_duration: int | None = Field(
        None, ge=0, description="Duration in minutes"
    )
    address: str | None = None
    eircode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None

    # Welcome message flags — not persisted, consumed at the BL layer
    send_welcome_email: bool = False
    send_welcome_whatsapp: bool = False


class JobUpdateRequest(BaseModel):
    """Partial update request for a job."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    customer_id: int | None = None
    assigned_to: int | None = None
    status: str | None = None
    priority: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    estimated_duration: int | None = Field(None, ge=0)
    address: str | None = None
    eircode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None


class JobAssignRequest(BaseModel):
    """Assign a job to an employee."""

    assigned_to: int
    start_time: datetime | None = None
    end_time: datetime | None = None


class JobScheduleRequest(BaseModel):
    """Schedule a job to a time slot."""

    start_time: datetime
    end_time: datetime
    assigned_to: int | None = None


class JobStatusUpdateRequest(BaseModel):
    """Update only the status of a job."""

    status: str = Field(
        ..., description="pending | scheduled | in_progress | completed | cancelled"
    )
    notes: str | None = None


# ==============================================================================
# Response Schemas
# ==============================================================================


class JobResponse(BaseModel):
    """Public job response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    customer_id: int | None = None
    owner_id: int
    assigned_to: int | None = None
    status: str
    priority: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    estimated_duration: int | None = None
    address: str | None = None
    eircode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class JobWithDetailsResponse(JobResponse):
    """Job response enriched with customer and assignee names."""

    customer_name: str | None = None
    assigned_to_name: str | None = None


class CalendarJobResponse(BaseModel):
    """Simplified job schema for calendar views (matches db-access CalendarEventResponse)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    all_day: bool
    status: str
    priority: str
    color: str | None = None
    assigned_to: int | None = None
    customer_id: int | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CalendarDayResponse(BaseModel):
    """Calendar view: jobs for a specific day."""

    date: date
    jobs: list[CalendarJobResponse]
    total_jobs: int


class CalendarMonthResponse(BaseModel):
    """Calendar view: summary for a whole month."""

    year: int
    month: int
    days: list[CalendarDayResponse]


class ScheduleConflict(BaseModel):
    """Describes a scheduling conflict with an existing job."""

    conflicting_job_id: int
    conflicting_job_title: str
    start_time: datetime
    end_time: datetime


class ScheduleConflictResponse(BaseModel):
    """Response when a scheduling conflict is detected."""

    has_conflicts: bool
    conflicts: list[ScheduleConflict]


class JobQueueResponse(BaseModel):
    """Unscheduled jobs waiting in the queue."""

    items: list[JobResponse]
    total: int


class JobListResponse(BaseModel):
    """Paginated job list response."""

    items: list[JobResponse]
    total: int
    page: int
    per_page: int
    pages: int
