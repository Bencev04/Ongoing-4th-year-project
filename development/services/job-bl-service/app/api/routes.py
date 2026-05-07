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

import asyncio
import sys
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

sys.path.append("../../../shared")
from common.audit import log_action
from common.health import HealthChecker
from common.schemas import HealthResponse

from .. import service_client
from ..dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
    verify_tenant_access,
)
from ..logic.scheduling import check_schedule_conflicts, enrich_job_with_details
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

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _audit_scope_id(current_user: CurrentUser) -> int | None:
    """Resolve the tenant audit-scope identifier for the current user."""
    return current_user.organization_id or current_user.company_id


import logging as _logging

_logger = _logging.getLogger(__name__)

from common.config import settings as _app_settings

_NOTIFICATION_URL = getattr(
    _app_settings, "notification_service_url", "http://notification-service:8011"
)


async def _send_welcome_notification(
    *,
    job_id: int,
    customer_id: int,
    send_email: bool,
    send_whatsapp: bool,
    auth_header: str,
) -> None:
    """Fire-and-forget POST to notification-service to send welcome messages."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{_NOTIFICATION_URL}/api/v1/notifications/send-welcome",
                json={
                    "job_id": job_id,
                    "customer_id": customer_id,
                    "send_email": send_email,
                    "send_whatsapp": send_whatsapp,
                },
                headers={"Authorization": auth_header} if auth_header else {},
            )
    except Exception:
        _logger.warning(
            "Welcome notification failed for job %s (non-blocking)",
            job_id,
            exc_info=True,
        )


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("job-service", "1.0.0")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness probe — is the service running?

    K8s uses this to determine if the container should be restarted.
    Returns quickly without checking external dependencies.
    """
    return await _health_checker.liveness_probe()


@router.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """
    Readiness probe — can the service handle traffic?

    K8s uses this to determine if the pod should receive traffic.
    Checks dependent services and Redis.
    """
    return await _health_checker.readiness_probe(
        db=None,  # Job BL doesn't touch DB directly
        check_redis=True,
        check_services={
            "job-db-access": "http://job-db-access-service:8003",
        },
    )


# ==============================================================================
# CRUD Endpoints
# ==============================================================================


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    page: int | None = Query(None, ge=1),
    per_page: int | None = Query(None, ge=1, le=1000),
    status_filter: str | None = Query(None, alias="status"),
    assigned_to: int | None = Query(None),
    customer_id: int | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """List all jobs belonging to the current tenant."""
    if page is not None and per_page is not None:
        skip = (page - 1) * per_page
        limit = per_page
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
    current_user: CurrentUser = Depends(require_permission("jobs.create")),
    request: Request = None,
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

    # Extract welcome message flags before building DB payload
    send_welcome_email = body.send_welcome_email
    send_welcome_whatsapp = body.send_welcome_whatsapp

    payload = body.model_dump(
        mode="json", exclude={"send_welcome_email", "send_welcome_whatsapp"}
    )
    payload["owner_id"] = current_user.effective_owner_id
    payload["created_by_id"] = current_user.user_id
    job = await service_client.create_job(payload)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="job.create",
        resource_type="job",
        resource_id=str(job["id"]),
        details={
            "title": job.get("title") or body.title,
            "customer_id": job.get("customer_id"),
            "assigned_to": job.get("assigned_to"),
            "status": job.get("status"),
        },
        ip_address=request.client.host if request and request.client else None,
    )

    # Fire-and-forget welcome notification if requested
    if body.customer_id and (send_welcome_email or send_welcome_whatsapp):
        auth_header = request.headers.get("authorization", "") if request else ""
        asyncio.create_task(
            _send_welcome_notification(
                job_id=job["id"],
                customer_id=body.customer_id,
                send_email=send_welcome_email,
                send_whatsapp=send_welcome_whatsapp,
                auth_header=auth_header,
            )
        )

    return job


@router.get("/jobs/calendar", response_model=list[CalendarDayResponse])
async def get_calendar_view(
    start_date: date = Query(...),
    end_date: date = Query(...),
    employee_id: int | None = Query(None, description="Filter by assigned employee"),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """
    Get jobs grouped by day for the calendar view.

    Optionally filters by ``employee_id`` so only jobs assigned to
    that employee (via the job_employees junction table) are returned.

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
        employee_id=employee_id,
    )

    # Group jobs by every date they span —————————————————————————
    # A job that starts on 2025-01-05 and ends on 2025-01-07 will
    # appear in the lists for 05, 06 and 07.  This is essential for
    # multi-day jobs to show on every calendar day they occupy.
    days_map: dict[date, list[dict]] = {}
    for job in jobs:
        raw_start = job.get("start_time")
        raw_end = job.get("end_time")
        if not raw_start:
            continue

        if isinstance(raw_start, str):
            raw_start = datetime.fromisoformat(raw_start)
        job_start: date = (
            raw_start.date() if isinstance(raw_start, datetime) else raw_start
        )

        if raw_end:
            if isinstance(raw_end, str):
                raw_end = datetime.fromisoformat(raw_end)
            job_end: date = raw_end.date() if isinstance(raw_end, datetime) else raw_end
        else:
            job_end = job_start

        # Clamp to the requested range and emit on each spanned date.
        cur = max(job_start, start_date)
        bound = min(job_end, end_date)
        while cur <= bound:
            days_map.setdefault(cur, []).append(job)
            cur += timedelta(days=1)

    result = []
    current = start_date

    while current <= end_date:
        day_jobs = days_map.get(current, [])
        result.append(
            {
                "date": current,
                "jobs": day_jobs,
                "total_jobs": len(day_jobs),
            }
        )
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
        raise HTTPException(
            status_code=403, detail="Access denied: job belongs to a different tenant"
        )

    return await enrich_job_with_details(job_data)


@router.put("/jobs/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    body: JobUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    request: Request = None,
) -> dict:
    """Update a job's fields."""
    # Verify ownership
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    payload = body.model_dump(exclude_unset=True, mode="json")
    job = await service_client.update_job(
        job_id, payload, changed_by_id=current_user.user_id
    )

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="job.update",
        resource_type="job",
        resource_id=str(job_id),
        details={"updated_fields": sorted(payload.keys())},
        ip_address=request.client.host if request and request.client else None,
    )

    return job


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: int,
    current_user: CurrentUser = Depends(require_permission("jobs.delete")),
    request: Request = None,
) -> None:
    """Delete a job. Only owners and admins may do this."""
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    await service_client.delete_job(job_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="job.delete",
        resource_type="job",
        resource_id=str(job_id),
        details={
            "title": existing.get("title"),
            "status": existing.get("status"),
        },
        ip_address=request.client.host if request and request.client else None,
    )


# ==============================================================================
# Scheduling Endpoints
# ==============================================================================


@router.post("/jobs/{job_id}/assign", response_model=JobResponse)
async def assign_job(
    job_id: int,
    body: JobAssignRequest,
    current_user: CurrentUser = Depends(require_permission("jobs.assign")),
    request: Request = None,
) -> dict:
    """
    Assign a job to an employee.

    Optionally include start/end times. If times are provided,
    scheduling conflict detection runs automatically.
    """
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

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
                detail=f"Scheduling conflicts detected: {len(conflicts)} conflict(s)",
            )
        # Schedule the job via update (times + status only)
        update_payload: dict = {
            "start_time": body.start_time.isoformat(),
            "end_time": body.end_time.isoformat(),
            "status": "scheduled",
        }
        await service_client.update_job(
            job_id, update_payload, changed_by_id=current_user.user_id
        )

    # Assign employee via the junction table
    await service_client.assign_employee_to_job(
        job_id=job_id,
        employee_id=body.assigned_to,
        owner_id=current_user.effective_owner_id,
    )

    # Re-fetch the enriched job to return correct state
    job = await service_client.get_job(job_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="job.assign",
        resource_type="job",
        resource_id=str(job_id),
        details={"assigned_to": body.assigned_to},
        ip_address=request.client.host if request and request.client else None,
    )

    return job


@router.post("/jobs/{job_id}/schedule", response_model=JobResponse)
async def schedule_job(
    job_id: int,
    body: JobScheduleRequest,
    current_user: CurrentUser = Depends(require_permission("jobs.schedule")),
    request: Request = None,
) -> dict:
    """
    Schedule a job to a specific time slot.

    Runs conflict detection if the job is assigned to an employee.
    """
    existing = await service_client.get_job(job_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    if body.start_time >= body.end_time:
        raise HTTPException(
            status_code=400, detail="start_time must be before end_time"
        )

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
                detail=f"Scheduling conflicts detected: {len(conflicts)} conflict(s)",
            )

    update_payload: dict = {
        "start_time": body.start_time.isoformat(),
        "end_time": body.end_time.isoformat(),
        "status": "scheduled",
    }
    if body.assigned_to:
        update_payload["assigned_to"] = body.assigned_to

    job = await service_client.update_job(
        job_id, update_payload, changed_by_id=current_user.user_id
    )

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="job.schedule",
        resource_type="job",
        resource_id=str(job_id),
        details={
            "assigned_to": update_payload.get("assigned_to", assignee),
            "start_time": update_payload["start_time"],
            "end_time": update_payload["end_time"],
        },
        ip_address=request.client.host if request and request.client else None,
    )

    return job


@router.put("/jobs/{job_id}/status", response_model=JobResponse)
async def update_job_status(
    job_id: int,
    body: JobStatusUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    request: Request = None,
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

    job = await service_client.update_job(
        job_id, update_payload, changed_by_id=current_user.user_id
    )

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="job.status.update",
        resource_type="job",
        resource_id=str(job_id),
        details={"status": body.status, "notes": body.notes},
        ip_address=request.client.host if request and request.client else None,
    )

    return job


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
