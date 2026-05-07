"""
Pydantic schemas for Job service API.

Defines request/response models for job/calendar operations.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.job import JobPriority, JobStatus

# ==============================================================================
# Base Schemas
# ==============================================================================


class JobBase(BaseModel):
    """
    Base job schema with common fields.
    """

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    all_day: bool = False
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    customer_id: int | None = None
    location: str | None = Field(None, max_length=500)
    eircode: str | None = Field(None, max_length=20)
    latitude: float | None = None
    longitude: float | None = None
    estimated_duration: int | None = Field(None, ge=0)  # minutes
    notes: str | None = None
    color: str | None = Field(None, max_length=20)

    @field_validator("end_time")
    @classmethod
    def end_time_after_start(cls, v: datetime | None, info) -> datetime | None:
        """Validate that end_time is after start_time."""
        start_time = info.data.get("start_time")
        if v and start_time and v <= start_time:
            raise ValueError("end_time must be after start_time")
        return v


class JobHistoryBase(BaseModel):
    """Base job history schema."""

    change_type: str
    field_changed: str | None = None
    old_value: str | None = None
    new_value: str | None = None


# ==============================================================================
# Create Schemas (Input)
# ==============================================================================


class JobCreate(JobBase):
    """
    Schema for creating a new job.
    """

    owner_id: int
    created_by_id: int
    is_recurring: bool = False
    recurrence_rule: str | None = None


# ==============================================================================
# Update Schemas (Input)
# ==============================================================================


class JobUpdate(BaseModel):
    """
    Schema for updating job fields.
    All fields are optional to allow partial updates.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    all_day: bool | None = None
    status: JobStatus | None = None
    priority: JobPriority | None = None
    customer_id: int | None = None
    location: str | None = Field(None, max_length=500)
    eircode: str | None = Field(None, max_length=20)
    latitude: float | None = None
    longitude: float | None = None
    estimated_duration: int | None = Field(None, ge=0)
    actual_duration: int | None = Field(None, ge=0)
    notes: str | None = None
    color: str | None = Field(None, max_length=20)


class JobStatusUpdate(BaseModel):
    """Schema for updating just the job status."""

    status: JobStatus
    actual_duration: int | None = None  # For completion


# ==============================================================================
# Response Schemas (Output)
# ==============================================================================


class JobHistoryResponse(JobHistoryBase):
    """Schema for job history API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    changed_by_id: int
    created_at: datetime


class JobResponse(JobBase):
    """
    Schema for job API responses.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_by_id: int
    actual_duration: int | None = None
    is_recurring: bool = False
    recurrence_rule: str | None = None
    parent_job_id: int | None = None
    created_at: datetime
    updated_at: datetime


class JobWithHistoryResponse(JobResponse):
    """Job response including history."""

    history: list[JobHistoryResponse] = []


class JobListResponse(BaseModel):
    """Paginated job list response."""

    items: list[JobResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ==============================================================================
# Calendar View Schemas
# ==============================================================================


class CalendarEventResponse(BaseModel):
    """
    Simplified job schema for calendar views.

    Contains only essential fields for rendering calendar.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_time: datetime | None
    end_time: datetime | None
    all_day: bool
    status: JobStatus
    priority: JobPriority
    color: str | None
    assigned_to: int | None = None
    customer_id: int | None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class CalendarViewResponse(BaseModel):
    """Response for calendar view endpoints."""

    events: list[CalendarEventResponse]
    start_date: datetime
    end_date: datetime
    total: int


class JobQueueResponse(BaseModel):
    """Response for unscheduled jobs queue."""

    items: list[JobResponse]
    total: int


# ==============================================================================
# Job-Employee Assignment Schemas
# ==============================================================================


class JobEmployeeAssignRequest(BaseModel):
    """Request to assign an employee to a job."""

    employee_id: int
    owner_id: int


class JobEmployeeResponse(BaseModel):
    """Response for a job-employee assignment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    employee_id: int
    owner_id: int
