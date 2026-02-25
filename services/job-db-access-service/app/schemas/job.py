"""
Pydantic schemas for Job service API.

Defines request/response models for job/calendar operations.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict, field_validator

from ..models.job import JobStatus, JobPriority


# ==============================================================================
# Base Schemas
# ==============================================================================

class JobBase(BaseModel):
    """
    Base job schema with common fields.
    """
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: bool = False
    status: JobStatus = JobStatus.PENDING
    priority: JobPriority = JobPriority.NORMAL
    assigned_employee_id: Optional[int] = None
    customer_id: Optional[int] = None
    location: Optional[str] = Field(None, max_length=500)
    eircode: Optional[str] = Field(None, max_length=20)
    estimated_duration: Optional[int] = Field(None, ge=0)  # minutes
    notes: Optional[str] = None
    color: Optional[str] = Field(None, max_length=20)
    
    @field_validator("end_time")
    @classmethod
    def end_time_after_start(cls, v: Optional[datetime], info) -> Optional[datetime]:
        """Validate that end_time is after start_time."""
        start_time = info.data.get("start_time")
        if v and start_time and v <= start_time:
            raise ValueError("end_time must be after start_time")
        return v


class JobHistoryBase(BaseModel):
    """Base job history schema."""
    change_type: str
    field_changed: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None


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
    recurrence_rule: Optional[str] = None


# ==============================================================================
# Update Schemas (Input)
# ==============================================================================

class JobUpdate(BaseModel):
    """
    Schema for updating job fields.
    All fields are optional to allow partial updates.
    """
    model_config = ConfigDict(extra="forbid")
    
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    all_day: Optional[bool] = None
    status: Optional[JobStatus] = None
    priority: Optional[JobPriority] = None
    assigned_employee_id: Optional[int] = None
    customer_id: Optional[int] = None
    location: Optional[str] = Field(None, max_length=500)
    eircode: Optional[str] = Field(None, max_length=20)
    estimated_duration: Optional[int] = Field(None, ge=0)
    actual_duration: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = None
    color: Optional[str] = Field(None, max_length=20)


class JobStatusUpdate(BaseModel):
    """Schema for updating just the job status."""
    status: JobStatus
    actual_duration: Optional[int] = None  # For completion


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
    actual_duration: Optional[int] = None
    is_recurring: bool = False
    recurrence_rule: Optional[str] = None
    parent_job_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class JobWithHistoryResponse(JobResponse):
    """Job response including history."""
    history: List[JobHistoryResponse] = []


class JobListResponse(BaseModel):
    """Paginated job list response."""
    items: List[JobResponse]
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
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    all_day: bool
    status: JobStatus
    priority: JobPriority
    color: Optional[str]
    assigned_employee_id: Optional[int]
    customer_id: Optional[int]


class CalendarViewResponse(BaseModel):
    """Response for calendar view endpoints."""
    events: List[CalendarEventResponse]
    start_date: datetime
    end_date: datetime
    total: int


class JobQueueResponse(BaseModel):
    """Response for unscheduled jobs queue."""
    items: List[JobResponse]
    total: int
