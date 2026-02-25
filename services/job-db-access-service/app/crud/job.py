"""
CRUD operations for Job service.

Provides **async** database access functions for jobs and history.
"""

from datetime import datetime, timezone
from typing import Optional, List, Tuple

from sqlalchemy import and_, or_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.job import Job, JobHistory, JobStatus, JobPriority
from ..schemas.job import JobCreate, JobUpdate, JobStatusUpdate


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise a datetime to UTC-aware; leaves None and aware values unchanged."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ==============================================================================
# Job CRUD Operations
# ==============================================================================

async def get_job(db: AsyncSession, job_id: int) -> Optional[Job]:
    """
    Retrieve a job by ID.

    Args:
        db: Async database session
        job_id: Job's primary key

    Returns:
        Optional[Job]: Job if found, None otherwise
    """
    result = await db.execute(select(Job).filter(Job.id == job_id))
    return result.scalar_one_or_none()


async def get_jobs(
    db: AsyncSession,
    owner_id: Optional[int],
    skip: int = 0,
    limit: int = 100,
    status: Optional[List[JobStatus]] = None,
    priority: Optional[List[JobPriority]] = None,
    employee_id: Optional[int] = None,
    customer_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Tuple[List[Job], int]:
    """
    Retrieve jobs with optional filtering and pagination.

    Args:
        db: Async database session
        owner_id: Owner's user ID (None for superadmin = all tenants)
        skip: Number of records to skip
        limit: Maximum number of records to return
        status: Filter by status(es)
        priority: Filter by priority(ies)
        employee_id: Filter by assigned employee
        customer_id: Filter by customer
        start_date: Filter jobs starting after this date
        end_date: Filter jobs ending before this date

    Returns:
        Tuple[List[Job], int]: List of jobs and total count
    """
    stmt = select(Job)
    if owner_id is not None:
        stmt = stmt.filter(Job.owner_id == owner_id)

    if status:
        stmt = stmt.filter(Job.status.in_(status))
    if priority:
        stmt = stmt.filter(Job.priority.in_(priority))
    if employee_id is not None:
        stmt = stmt.filter(Job.assigned_employee_id == employee_id)
    if customer_id is not None:
        stmt = stmt.filter(Job.customer_id == customer_id)
    if start_date:
        stmt = stmt.filter(Job.start_time >= _ensure_utc(start_date))
    if end_date:
        stmt = stmt.filter(Job.end_time <= _ensure_utc(end_date))

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Apply ordering and pagination
    result = await db.execute(
        stmt.order_by(Job.start_time.asc().nullsfirst()).offset(skip).limit(limit)
    )
    jobs = list(result.scalars().all())

    return jobs, total


async def get_jobs_for_calendar(
    db: AsyncSession,
    owner_id: Optional[int],
    start_date: datetime,
    end_date: datetime,
    employee_id: Optional[int] = None,
) -> List[Job]:
    """
    Retrieve jobs for calendar view within a date range.

    Args:
        db: Async database session
        owner_id: Owner's user ID (None for superadmin = all tenants)
        start_date: Start of date range
        end_date: End of date range
        employee_id: Optional employee filter

    Returns:
        List[Job]: Jobs within the date range
    """
    _start = _ensure_utc(start_date)
    _end = _ensure_utc(end_date)
    filters = [
        Job.start_time.isnot(None),
        or_(
            and_(Job.start_time >= _start, Job.start_time <= _end),
            and_(Job.end_time >= _start, Job.end_time <= _end),
            and_(Job.start_time <= _start, Job.end_time >= _end),
        ),
    ]
    if owner_id is not None:
        filters.append(Job.owner_id == owner_id)

    stmt = select(Job).filter(*filters)

    if employee_id:
        stmt = stmt.filter(Job.assigned_employee_id == employee_id)

    result = await db.execute(stmt.order_by(Job.start_time))
    return list(result.scalars().all())


async def get_unscheduled_jobs(
    db: AsyncSession,
    owner_id: Optional[int],
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Job], int]:
    """
    Retrieve unscheduled jobs (job queue).

    Args:
        db: Async database session
        owner_id: Owner's user ID (None for superadmin = all tenants)
        skip: Pagination offset
        limit: Maximum results

    Returns:
        Tuple[List[Job], int]: Unscheduled jobs and total count
    """
    filters = [
        Job.start_time.is_(None),
        Job.status == JobStatus.PENDING,
    ]
    if owner_id is not None:
        filters.append(Job.owner_id == owner_id)

    stmt = select(Job).filter(*filters)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Map priority strings to numeric rank for correct business ordering:
    # urgent (4) > high (3) > normal (2) > low (1)
    priority_rank = case(
        (Job.priority == JobPriority.URGENT, 4),
        (Job.priority == JobPriority.HIGH, 3),
        (Job.priority == JobPriority.NORMAL, 2),
        (Job.priority == JobPriority.LOW, 1),
        else_=0,
    )

    result = await db.execute(
        stmt.order_by(
            priority_rank.desc(),  # Highest priority first
            Job.created_at.asc(),  # Oldest first
        ).offset(skip).limit(limit)
    )
    jobs = list(result.scalars().all())

    return jobs, total


async def create_job(db: AsyncSession, job_data: JobCreate) -> Job:
    """
    Create a new job.

    Args:
        db: Async database session
        job_data: Job creation data

    Returns:
        Job: Newly created job
    """
    # Determine initial status based on scheduling
    job_status = job_data.status
    if job_data.start_time and job_status == JobStatus.PENDING:
        job_status = JobStatus.SCHEDULED

    db_job = Job(
        owner_id=job_data.owner_id,
        title=job_data.title,
        description=job_data.description,
        start_time=job_data.start_time,
        end_time=job_data.end_time,
        all_day=job_data.all_day,
        status=job_status,
        priority=job_data.priority,
        assigned_employee_id=job_data.assigned_employee_id,
        customer_id=job_data.customer_id,
        location=job_data.location,
        eircode=job_data.eircode,
        estimated_duration=job_data.estimated_duration,
        notes=job_data.notes,
        color=job_data.color,
        is_recurring=job_data.is_recurring,
        recurrence_rule=job_data.recurrence_rule,
        created_by_id=job_data.created_by_id,
    )

    db.add(db_job)
    await db.commit()
    await db.refresh(db_job)

    # Create history entry
    await create_job_history(
        db, db_job.id, job_data.created_by_id,
        "create", None, None, None,
    )

    return db_job


async def update_job(
    db: AsyncSession,
    job_id: int,
    job_data: JobUpdate,
    changed_by_id: int,
) -> Optional[Job]:
    """
    Update an existing job.

    Args:
        db: Async database session
        job_id: Job's primary key
        job_data: Fields to update
        changed_by_id: User making the change

    Returns:
        Optional[Job]: Updated job if found, None otherwise
    """
    db_job = await get_job(db, job_id)
    if not db_job:
        return None

    update_data = job_data.model_dump(exclude_unset=True)

    for field, new_value in update_data.items():
        old_value = getattr(db_job, field)
        if old_value != new_value:
            await create_job_history(
                db, job_id, changed_by_id,
                "update", field,
                str(old_value) if old_value else None,
                str(new_value) if new_value else None,
            )
            setattr(db_job, field, new_value)

    # Auto-update status if scheduling
    if (
        "start_time" in update_data
        and update_data["start_time"]
        and db_job.status == JobStatus.PENDING
    ):
        db_job.status = JobStatus.SCHEDULED

    await db.commit()
    await db.refresh(db_job)

    return db_job


async def update_job_status(
    db: AsyncSession,
    job_id: int,
    status_data: JobStatusUpdate,
    changed_by_id: int,
) -> Optional[Job]:
    """
    Update just the job status.

    Args:
        db: Async database session
        job_id: Job's primary key
        status_data: New status data
        changed_by_id: User making the change

    Returns:
        Optional[Job]: Updated job if found, None otherwise
    """
    db_job = await get_job(db, job_id)
    if not db_job:
        return None

    old_status = db_job.status
    db_job.status = status_data.status

    if status_data.actual_duration is not None:
        db_job.actual_duration = status_data.actual_duration

    await create_job_history(
        db, job_id, changed_by_id,
        "status_change", "status",
        old_status if isinstance(old_status, str) else old_status.value,
        status_data.status.value if hasattr(status_data.status, 'value') else str(status_data.status),
    )

    await db.commit()
    await db.refresh(db_job)

    return db_job


async def delete_job(db: AsyncSession, job_id: int) -> bool:
    """
    Delete a job (hard delete).

    Args:
        db: Async database session
        job_id: Job's primary key

    Returns:
        bool: True if job was deleted, False if not found
    """
    db_job = await get_job(db, job_id)
    if not db_job:
        return False

    await db.delete(db_job)
    await db.commit()

    return True


# ==============================================================================
# Job History CRUD Operations
# ==============================================================================

async def create_job_history(
    db: AsyncSession,
    job_id: int,
    changed_by_id: int,
    change_type: str,
    field_changed: Optional[str],
    old_value: Optional[str],
    new_value: Optional[str],
) -> JobHistory:
    """
    Create a job history entry.

    Args:
        db: Async database session
        job_id: Job's primary key
        changed_by_id: User who made the change
        change_type: Type of change
        field_changed: Field that was changed
        old_value: Previous value
        new_value: New value

    Returns:
        JobHistory: Created history entry
    """
    history = JobHistory(
        job_id=job_id,
        changed_by_id=changed_by_id,
        change_type=change_type,
        field_changed=field_changed,
        old_value=old_value,
        new_value=new_value,
    )

    db.add(history)
    await db.commit()
    await db.refresh(history)

    return history


async def get_job_history(
    db: AsyncSession,
    job_id: int,
    skip: int = 0,
    limit: int = 50,
) -> List[JobHistory]:
    """
    Retrieve history for a job.

    Args:
        db: Async database session
        job_id: Job's primary key
        skip: Pagination offset
        limit: Maximum results

    Returns:
        List[JobHistory]: History entries
    """
    result = await db.execute(
        select(JobHistory)
        .filter(JobHistory.job_id == job_id)
        .order_by(JobHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())
