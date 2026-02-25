"""
Business logic for the Job Service.

Contains scheduling conflict detection, job enrichment,
and other orchestration logic that doesn't belong in routes.
"""

from datetime import datetime
from typing import Optional

from ..schemas import ScheduleConflict
from .. import service_client


async def check_schedule_conflicts(
    *,
    assigned_to: int,
    start_time: datetime,
    end_time: datetime,
    owner_id: int,
    exclude_job_id: Optional[int] = None,
) -> list[ScheduleConflict]:
    """
    Detect scheduling conflicts for an employee on a given time range.

    Checks all jobs assigned to the employee on that date and
    returns any whose time range overlaps with the proposed slot.

    Args:
        assigned_to: Employee user_id.
        start_time: Proposed start time.
        end_time: Proposed end time.
        owner_id: Tenant ID.
        exclude_job_id: Job ID to exclude from conflict check
                        (used when updating a job's own schedule).

    Returns:
        List of ``ScheduleConflict`` objects (empty if no conflicts).
    """
    existing_jobs = await service_client.get_jobs_by_assignee_and_date(
        assigned_to=assigned_to,
        target_date=start_time.date(),
        owner_id=owner_id,
    )

    conflicts: list[ScheduleConflict] = []

    for job in existing_jobs:
        if exclude_job_id and job.get("id") == exclude_job_id:
            continue

        job_start = job.get("start_time")
        job_end = job.get("end_time")

        if not job_start or not job_end:
            continue

        # Parse ISO strings if needed
        if isinstance(job_start, str):
            job_start = datetime.fromisoformat(job_start)
        if isinstance(job_end, str):
            job_end = datetime.fromisoformat(job_end)

        # Overlap detection: two ranges overlap when start1 < end2 AND start2 < end1
        if start_time < job_end and job_start < end_time:
            conflicts.append(
                ScheduleConflict(
                    conflicting_job_id=job["id"],
                    conflicting_job_title=job.get("title", "Untitled"),
                    start_time=job_start,
                    end_time=job_end,
                )
            )

    return conflicts


async def enrich_job_with_details(job_data: dict) -> dict:
    """
    Enrich a job dict with customer and assignee display names.

    Fails silently — if a lookup fails, the name fields are left
    as ``None``.
    """
    # Customer name
    customer_id = job_data.get("customer_id")
    if customer_id:
        try:
            customer = await service_client.get_customer(customer_id)
            # Customer DB stores a single "name" field
            job_data["customer_name"] = customer.get("name", "")
        except Exception:
            job_data["customer_name"] = None

    # Assignee name
    assigned_to = job_data.get("assigned_to")
    if assigned_to:
        try:
            user = await service_client.get_user(assigned_to)
            first = user.get("first_name", "")
            last = user.get("last_name", "")
            job_data["assigned_to_name"] = f"{first} {last}".strip()
        except Exception:
            job_data["assigned_to_name"] = None

    return job_data
