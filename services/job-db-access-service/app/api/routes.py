"""
API routes for Job service.

Defines all **async** HTTP endpoints for job/calendar operations.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.append("../../../shared")
from common.database import get_async_db
from common.schemas import HealthResponse

from ..models.job import JobStatus, JobPriority
from ..schemas import (
    JobCreate, JobUpdate, JobStatusUpdate, JobResponse,
    JobWithHistoryResponse, JobListResponse,
    JobHistoryResponse, CalendarEventResponse,
    CalendarViewResponse, JobQueueResponse
)
from ..crud import (
    get_job, get_jobs, get_jobs_for_calendar, get_unscheduled_jobs,
    create_job, update_job, update_job_status, delete_job,
    get_job_history
)

# Create router with prefix
router = APIRouter(prefix="/api/v1", tags=["jobs"])


# ==============================================================================
# Health Check
# ==============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="job-service",
        version="1.0.0",
        timestamp=datetime.utcnow()
    )


# ==============================================================================
# Job Endpoints
# ==============================================================================

@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    owner_id: Optional[int] = Query(None, description="Owner's user ID (None for superadmin = all tenants)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[List[JobStatus]] = Query(None, description="Filter by status(es)"),
    priority: Optional[List[JobPriority]] = Query(None, description="Filter by priority(ies)"),
    employee_id: Optional[int] = Query(None, description="Filter by assigned employee"),
    customer_id: Optional[int] = Query(None, description="Filter by customer"),
    start_date: Optional[datetime] = Query(None, description="Jobs starting after"),
    end_date: Optional[datetime] = Query(None, description="Jobs ending before"),
    db: AsyncSession = Depends(get_async_db),
) -> JobListResponse:
    """List jobs with optional filtering and pagination."""
    jobs, total = await get_jobs(
        db,
        owner_id=owner_id,
        skip=skip,
        limit=limit,
        status=status,
        priority=priority,
        employee_id=employee_id,
        customer_id=customer_id,
        start_date=start_date,
        end_date=end_date,
    )

    pages = (total + limit - 1) // limit if limit > 0 else 0
    page = (skip // limit) + 1 if limit > 0 else 1

    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        per_page=limit,
        pages=pages,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_new_job(
    job_data: JobCreate,
    db: AsyncSession = Depends(get_async_db),
) -> JobResponse:
    """Create a new job."""
    job = await create_job(db, job_data)
    return JobResponse.model_validate(job)


@router.get("/jobs/queue", response_model=JobQueueResponse)
async def get_job_queue(
    owner_id: Optional[int] = Query(None, description="Owner's user ID (None for superadmin = all tenants)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
) -> JobQueueResponse:
    """
    Get unscheduled jobs (job queue).

    Returns jobs without a scheduled time, ordered by priority and age.
    """
    jobs, total = await get_unscheduled_jobs(db, owner_id, skip, limit)

    return JobQueueResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
    )


@router.get("/jobs/calendar", response_model=CalendarViewResponse)
async def get_calendar_view(
    owner_id: Optional[int] = Query(None, description="Owner's user ID (None for superadmin = all tenants)"),
    start_date: datetime = Query(..., description="Start of date range"),
    end_date: datetime = Query(..., description="End of date range"),
    employee_id: Optional[int] = Query(None, description="Filter by employee"),
    db: AsyncSession = Depends(get_async_db),
) -> CalendarViewResponse:
    """
    Get jobs for calendar view.

    Returns jobs within the specified date range, optimised for calendar display.
    """
    jobs = await get_jobs_for_calendar(db, owner_id, start_date, end_date, employee_id)

    return CalendarViewResponse(
        events=[CalendarEventResponse.model_validate(j) for j in jobs],
        start_date=start_date,
        end_date=end_date,
        total=len(jobs),
    )


@router.get("/jobs/{job_id}", response_model=JobWithHistoryResponse)
async def get_job_by_id(
    job_id: int,
    include_history: bool = Query(False, description="Include change history"),
    db: AsyncSession = Depends(get_async_db),
) -> JobWithHistoryResponse:
    """Get a specific job by ID."""
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    # Build from base response to avoid lazy-loading the history relationship
    base = JobResponse.model_validate(job)
    history_list: list[JobHistoryResponse] = []

    if include_history:
        history = await get_job_history(db, job_id)
        history_list = [JobHistoryResponse.model_validate(h) for h in history]

    return JobWithHistoryResponse(**base.model_dump(), history=history_list)


@router.put("/jobs/{job_id}", response_model=JobResponse)
async def update_existing_job(
    job_id: int,
    job_data: JobUpdate,
    changed_by_id: int = Query(..., description="ID of user making the change"),
    db: AsyncSession = Depends(get_async_db),
) -> JobResponse:
    """Update a job."""
    job = await update_job(db, job_id, job_data, changed_by_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return JobResponse.model_validate(job)


@router.patch("/jobs/{job_id}/status", response_model=JobResponse)
async def update_job_status_endpoint(
    job_id: int,
    status_data: JobStatusUpdate,
    changed_by_id: int = Query(..., description="ID of user making the change"),
    db: AsyncSession = Depends(get_async_db),
) -> JobResponse:
    """
    Update just the job status.

    Use this for quick status changes like marking a job complete.
    """
    job = await update_job_status(db, job_id, status_data, changed_by_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return JobResponse.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_job(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Delete a job."""
    success = await delete_job(db, job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )


@router.get("/jobs/{job_id}/history", response_model=List[JobHistoryResponse])
async def get_job_history_endpoint(
    job_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
) -> List[JobHistoryResponse]:
    """Get change history for a job."""
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    history = await get_job_history(db, job_id, skip, limit)
    return [JobHistoryResponse.model_validate(h) for h in history]
