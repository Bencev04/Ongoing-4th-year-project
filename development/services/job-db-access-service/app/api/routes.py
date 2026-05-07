"""
API routes for Job service.

Defines all **async** HTTP endpoints for job/calendar operations.
"""

import sys
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append("../../../shared")
from common.database import get_async_db
from common.health import HealthChecker
from common.schemas import HealthResponse

from ..crud import (
    assign_employee_to_job,
    create_job,
    delete_job,
    get_job,
    get_job_employees,
    get_job_history,
    get_jobs,
    get_jobs_for_calendar,
    get_unscheduled_jobs,
    remove_employee_from_job,
    update_job,
    update_job_status,
)
from ..models.job import JobPriority, JobStatus
from ..models.job_employee import JobEmployee
from ..schemas import (
    CalendarEventResponse,
    CalendarViewResponse,
    JobCreate,
    JobEmployeeAssignRequest,
    JobEmployeeResponse,
    JobHistoryResponse,
    JobListResponse,
    JobQueueResponse,
    JobResponse,
    JobStatusUpdate,
    JobUpdate,
    JobWithHistoryResponse,
)

# Create router with prefix
router = APIRouter(prefix="/api/v1", tags=["jobs"])


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("job-db-access-service", "1.0.0")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness probe — is the service running?

    K8s uses this to determine if the container should be restarted.
    Returns quickly without checking external dependencies.
    """
    return await _health_checker.liveness_probe()


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(
    db: AsyncSession = Depends(get_async_db),
) -> HealthResponse:
    """
    Readiness probe — can the service handle traffic?

    K8s uses this to determine if the pod should receive traffic.
    Checks database connectivity.
    """
    return await _health_checker.readiness_probe(db=db, check_redis=False)


# ==============================================================================
# Job Endpoints
# ==============================================================================


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    owner_id: int | None = Query(
        None, description="Owner's user ID (None for superadmin = all tenants)"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: list[JobStatus] | None = Query(None, description="Filter by status(es)"),
    priority: list[JobPriority] | None = Query(
        None, description="Filter by priority(ies)"
    ),
    employee_id: int | None = Query(None, description="Filter by assigned employee"),
    customer_id: int | None = Query(None, description="Filter by customer"),
    start_date: datetime | None = Query(None, description="Jobs starting after"),
    end_date: datetime | None = Query(None, description="Jobs ending before"),
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
    owner_id: int | None = Query(
        None, description="Owner's user ID (None for superadmin = all tenants)"
    ),
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
    owner_id: int | None = Query(
        None, description="Owner's user ID (None for superadmin = all tenants)"
    ),
    start_date: datetime = Query(..., description="Start of date range"),
    end_date: datetime = Query(..., description="End of date range"),
    employee_id: int | None = Query(None, description="Filter by employee"),
    db: AsyncSession = Depends(get_async_db),
) -> CalendarViewResponse:
    """
    Get jobs for calendar view.

    Returns jobs within the specified date range, optimised for calendar display.
    Includes ``assigned_to`` (first employee from the job_employees junction
    table) so the frontend can filter by employee.
    """
    jobs = await get_jobs_for_calendar(db, owner_id, start_date, end_date, employee_id)

    # Batch-fetch employee assignments so each event carries assigned_to.
    job_ids = [j.id for j in jobs]
    emp_map: dict[int, int] = {}
    if job_ids:
        rows = await db.execute(
            select(JobEmployee.job_id, JobEmployee.employee_id)
            .where(JobEmployee.job_id.in_(job_ids))
            .order_by(JobEmployee.id)
        )
        for row in rows:
            emp_map.setdefault(row.job_id, row.employee_id)

    events = []
    for j in jobs:
        ev = CalendarEventResponse.model_validate(j)
        ev.assigned_to = emp_map.get(j.id)
        events.append(ev)

    return CalendarViewResponse(
        events=events,
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


@router.get("/jobs/{job_id}/history", response_model=list[JobHistoryResponse])
async def get_job_history_endpoint(
    job_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
) -> list[JobHistoryResponse]:
    """Get change history for a job."""
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    history = await get_job_history(db, job_id, skip, limit)
    return [JobHistoryResponse.model_validate(h) for h in history]


# ==============================================================================
# Job-Employee Assignment Endpoints
# ==============================================================================


@router.post(
    "/jobs/{job_id}/employees",
    response_model=JobEmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_employee(
    job_id: int,
    body: JobEmployeeAssignRequest,
    db: AsyncSession = Depends(get_async_db),
) -> JobEmployeeResponse:
    """Assign an employee to a job."""
    job = await get_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    assignment = await assign_employee_to_job(
        db, job_id, body.employee_id, body.owner_id
    )
    return JobEmployeeResponse.model_validate(assignment)


@router.get("/jobs/{job_id}/employees", response_model=list[int])
async def list_job_employees(
    job_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> list[int]:
    """Get all employee IDs assigned to a job."""
    return await get_job_employees(db, job_id)


@router.delete(
    "/jobs/{job_id}/employees/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unassign_employee(
    job_id: int,
    employee_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Remove an employee assignment from a job."""
    removed = await remove_employee_from_job(db, job_id, employee_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )
