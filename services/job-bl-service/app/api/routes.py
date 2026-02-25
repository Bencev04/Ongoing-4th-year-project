"""
API routes for Job Service (Business Logic Layer).

All endpoints enforce multi-tenant isolation through ``owner_id``
extracted from the JWT.

Route summary
-------------
GET    /api/v1/jobs                     – List jobs in tenant.
POST   /api/v1/jobs                     – Create a job.
GET    /api/v1/jobs/{id}                – Get job with enriched details.
PUT    /api/v1/jobs/{id}                – Update a job.
DELETE /api/v1/jobs/{id}                – Delete/cancel a job.
POST   /api/v1/jobs/{id}/assign         – Assign job to employee.
POST   /api/v1/jobs/{id}/schedule       – Schedule job to time slot.
PUT    /api/v1/jobs/{id}/status         – Update job status only.
GET    /api/v1/jobs/calendar            – Calendar view (date range).
GET    /api/v1/jobs/queue               – Unscheduled job queue.
POST   /api/v1/jobs/{id}/check-conflicts – Check scheduling conflicts.
GET    /api/v1/health                   – Health check.
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

import sys
sys.path.append("../../../shared")
from common.schemas import HealthResponse

from ..dependencies import CurrentUser, get_current_user, require_role, verify_tenant_access
from ..schemas import (
    CalendarDayResponse,
    JobAssignRequest,
    JobCreateRequest,
    JobListResponse,
    JobQueueResponse,
    JobResponse,
    JobScheduleRequest,
    JobStatusUpdateRequest,
    JobUpdateRequest,
    JobWithDetailsResponse,
    ScheduleConflictResponse,
)
from .. import service_client
from ..logic.scheduling import check_schedule_conflicts, enrich_job_with_details

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
        timestamp=datetime.utcnow(),
    )


# ==============================================================================
# CRUD Endpoints
# ==============================================================================

@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status_filter: Optional[str] = Query(None, alias="status"),
    assigned_to: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """List all jobs belonging to the current tenant."""
    return await service_client.get_jobs(
        skip=skip,
        limit=limit,
        owner_id=current_user.owner_id,
        status_filter=status_filter,
        assigned_to=assigned_to,
        customer_id=customer_id,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreateRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "manager", "employee")),
) -> dict:
    """
    Create a new job under the current tenant.

    Security: viewers are blocked from creating jobs via the role
    hierarchy check.  Validates that the referenced customer belongs
    to the same tenant before creating.
    """
    # Validate customer belongs to tenant (skip if no customer_id)
    if body.customer_id is not None:
        try:
            customer = await service_client.get_customer(body.customer_id)
            if not verify_tenant_access(current_user, customer.get("owner_id")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Customer does not belong to your tenant",
                )
        except HTTPException as e:
            if e.status_code == 404:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Customer not found",
                )
            raise

    # Time validation
    if body.start_time and body.end_time and body.start_time >= body.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be before end_time",
        )

    payload = body.model_dump(mode="json")
    payload["owner_id"] = current_user.owner_id
    payload["created_by_id"] = current_user.user_id
    return await service_client.create_job(payload)


@router.get("/jobs/calendar", response_model=list[CalendarDayResponse])
async def get_calendar_view(
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """
    Get jobs grouped by day for the calendar view.

    Returns a list of ``CalendarDayResponse`` objects within the
    requested date range.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be before or equal to end_date",
        )

    jobs = await service_client.get_calendar_jobs(
        owner_id=current_user.owner_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Group jobs by date
    days_map: dict[date, list[dict]] = {}
    for job in jobs:
        start = job.get("start_time")
        if start:
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            job_date = start.date() if isinstance(start, datetime) else start
            days_map.setdefault(job_date, []).append(job)

    result = []
    current = start_date
    from datetime import timedelta
    while current <= end_date:
        day_jobs = days_map.get(current, [])
        result.append({
            "date": current,
            "jobs": day_jobs,
            "total_jobs": len(day_jobs),
        })
        current += timedelta(days=1)

    return result


@router.get("/jobs/queue", response_model=JobQueueResponse)
async def get_job_queue(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Get unscheduled jobs waiting to be assigned/scheduled."""
    jobs = await service_client.get_unscheduled_jobs(
        owner_id=current_user.owner_id,
    )
    return {"items": jobs, "total": len(jobs)}


@router.get("/jobs/{job_id}", response_model=JobWithDetailsResponse)
async def get_job(
    job_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a job by ID with enriched customer/assignee names.

    Enforces tenant isolation.
    """
    job_data = await service_client.get_job(job_id)

    if not verify_tenant_access(current_user, job_data.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied: job belongs to a different tenant")

    return await enrich_job_with_details(job_data)


@router.put("/jobs/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    body: JobUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update a job's fields."""
    # Verify ownership
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    payload = body.model_dump(exclude_unset=True, mode="json")
    return await service_client.update_job(
        job_id, payload, changed_by_id=current_user.user_id
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> None:
    """Delete a job. Only owners and admins may do this."""
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    await service_client.delete_job(job_id)


# ==============================================================================
# Scheduling Endpoints
# ==============================================================================

@router.post("/jobs/{job_id}/assign", response_model=JobResponse)
async def assign_job(
    job_id: int,
    body: JobAssignRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """
    Assign a job to an employee.

    Optionally include start/end times. If times are provided,
    scheduling conflict detection runs automatically.
    """
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    update_payload: dict = {"assigned_to": body.assigned_to}

    if body.start_time and body.end_time:
        # Check conflicts
        conflicts = await check_schedule_conflicts(
            assigned_to=body.assigned_to,
            start_time=body.start_time,
            end_time=body.end_time,
            owner_id=current_user.owner_id,
            exclude_job_id=job_id,
        )
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Scheduling conflicts detected",
                    "conflicts": [c.model_dump(mode="json") for c in conflicts],
                },
            )
        update_payload["start_time"] = body.start_time.isoformat()
        update_payload["end_time"] = body.end_time.isoformat()
        update_payload["status"] = "scheduled"

    return await service_client.update_job(
        job_id, update_payload, changed_by_id=current_user.user_id
    )


@router.post("/jobs/{job_id}/schedule", response_model=JobResponse)
async def schedule_job(
    job_id: int,
    body: JobScheduleRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """
    Schedule a job to a specific time slot.

    Runs conflict detection if the job is assigned to an employee.
    """
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    if body.start_time >= body.end_time:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")

    assignee = body.assigned_to or existing.get("assigned_to")

    if assignee:
        conflicts = await check_schedule_conflicts(
            assigned_to=assignee,
            start_time=body.start_time,
            end_time=body.end_time,
            owner_id=current_user.owner_id,
            exclude_job_id=job_id,
        )
        if conflicts:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Scheduling conflicts detected",
                    "conflicts": [c.model_dump(mode="json") for c in conflicts],
                },
            )

    update_payload: dict = {
        "start_time": body.start_time.isoformat(),
        "end_time": body.end_time.isoformat(),
        "status": "scheduled",
    }
    if body.assigned_to:
        update_payload["assigned_to"] = body.assigned_to

    return await service_client.update_job(
        job_id, update_payload, changed_by_id=current_user.user_id
    )


@router.put("/jobs/{job_id}/status", response_model=JobResponse)
async def update_job_status(
    job_id: int,
    body: JobStatusUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update the status of a job.

    Any authenticated user in the tenant can update status
    (e.g., employees marking jobs as in_progress or completed).
    """
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    update_payload: dict = {"status": body.status}
    if body.notes:
        update_payload["notes"] = body.notes

    return await service_client.update_job(
        job_id, update_payload, changed_by_id=current_user.user_id
    )


@router.post(
    "/jobs/{job_id}/check-conflicts",
    response_model=ScheduleConflictResponse,
)
async def check_conflicts(
    job_id: int,
    body: JobScheduleRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Check for scheduling conflicts without actually scheduling.

    Useful for the UI to preview conflicts before confirming.
    """
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    assignee = body.assigned_to or existing.get("assigned_to")
    if not assignee:
        return {"has_conflicts": False, "conflicts": []}

    conflicts = await check_schedule_conflicts(
        assigned_to=assignee,
        start_time=body.start_time,
        end_time=body.end_time,
        owner_id=current_user.owner_id,
        exclude_job_id=job_id,
    )

    return {
        "has_conflicts": len(conflicts) > 0,
        "conflicts": [c.model_dump(mode="json") for c in conflicts],
    }
