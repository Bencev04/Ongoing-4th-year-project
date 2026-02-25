"""
Unit tests for Job Service.

Covers CRUD operations, API endpoints, date/time handling,
status lifecycle, priority queuing, and audit history.

All database interactions are async (matching the production layer).
"""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    create_job,
    get_job,
    get_jobs,
    get_unscheduled_jobs,
    update_job,
    update_job_status,
    delete_job,
    get_job_history,
)
from app.schemas import JobCreate, JobUpdate, JobStatusUpdate
from app.models import Job, JobStatus, JobPriority


# ==============================================================================
# Job CRUD Tests
# ==============================================================================


class TestJobCRUD:
    """Tests for Job CRUD operations."""

    async def test_create_scheduled_job(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Creating a scheduled job should persist to database."""
        job_data = JobCreate(**sample_job_data)
        job = await create_job(db_session, job_data)

        assert job.id is not None
        assert job.title == sample_job_data["title"]
        assert job.owner_id == sample_job_data["owner_id"]
        assert job.status == JobStatus.SCHEDULED
        assert job.start_time is not None

    async def test_create_unscheduled_job(
        self, db_session: AsyncSession, sample_unscheduled_job_data: dict
    ) -> None:
        """Creating an unscheduled job should have pending status."""
        job_data = JobCreate(**sample_unscheduled_job_data)
        job = await create_job(db_session, job_data)

        assert job.id is not None
        assert job.status == JobStatus.PENDING
        assert job.start_time is None
        assert job.priority == JobPriority.URGENT

    async def test_get_job_by_id(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Should retrieve a job by primary key."""
        created = await create_job(db_session, JobCreate(**sample_job_data))
        retrieved = await get_job(db_session, created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == created.title

    async def test_get_jobs_with_filters(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Should filter jobs by status."""
        await create_job(db_session, JobCreate(**sample_job_data))

        jobs, total = await get_jobs(
            db_session, owner_id=1, status=[JobStatus.SCHEDULED]
        )

        assert total == 1
        assert len(jobs) == 1
        assert jobs[0].status == JobStatus.SCHEDULED

    async def test_get_unscheduled_jobs(
        self, db_session: AsyncSession, sample_unscheduled_job_data: dict
    ) -> None:
        """Should retrieve unscheduled jobs ordered by priority."""
        for priority in ["low", "normal", "urgent"]:
            data = {**sample_unscheduled_job_data, "priority": priority}
            await create_job(db_session, JobCreate(**data))

        jobs, total = await get_unscheduled_jobs(db_session, owner_id=1)

        assert total == 3
        # Urgent should be first (highest priority)
        assert jobs[0].priority == JobPriority.URGENT

    async def test_update_job(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Should update job fields and create audit history."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        update_data = JobUpdate(title="Updated Title", priority="high")
        updated = await update_job(db_session, job.id, update_data, changed_by_id=1)

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.priority == JobPriority.HIGH

        # At least the create entry + update entries
        history = await get_job_history(db_session, job.id)
        assert len(history) >= 2

    async def test_update_job_status(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Should update the job status."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        status_data = JobStatusUpdate(status=JobStatus.IN_PROGRESS)
        updated = await update_job_status(
            db_session, job.id, status_data, changed_by_id=1
        )

        assert updated is not None
        assert updated.status == JobStatus.IN_PROGRESS

    async def test_complete_job_with_duration(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Completing a job should allow setting actual duration."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        status_data = JobStatusUpdate(
            status=JobStatus.COMPLETED, actual_duration=180
        )
        updated = await update_job_status(
            db_session, job.id, status_data, changed_by_id=1
        )

        assert updated.status == JobStatus.COMPLETED
        assert updated.actual_duration == 180

    async def test_delete_job(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Deleting removes the job from the database (hard delete)."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        result = await delete_job(db_session, job.id)
        assert result is True
        assert await get_job(db_session, job.id) is None


# ==============================================================================
# Job API Endpoint Tests
# ==============================================================================


class TestJobAPI:
    """Tests for Job HTTP API endpoints."""

    async def test_health_check(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "job-service"

    async def test_create_job_endpoint(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        response = await client.post("/api/v1/jobs", json=sample_job_data)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == sample_job_data["title"]
        assert "id" in data

    async def test_get_job_endpoint(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]

        response = await client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["id"] == job_id

    async def test_list_jobs_without_owner_id_returns_all(self, client: AsyncClient) -> None:
        """Without owner_id the endpoint returns all jobs (superadmin path)."""
        response = await client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert "items" in response.json()

    async def test_list_jobs_with_filters(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        await client.post("/api/v1/jobs", json=sample_job_data)
        response = await client.get("/api/v1/jobs?owner_id=1&status=scheduled")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 1

    async def test_get_job_queue(
        self, client: AsyncClient, sample_unscheduled_job_data: dict
    ) -> None:
        await client.post("/api/v1/jobs", json=sample_unscheduled_job_data)
        response = await client.get("/api/v1/jobs/queue?owner_id=1")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] >= 1

    async def test_get_calendar_view(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        await client.post("/api/v1/jobs", json=sample_job_data)
        start = datetime.utcnow().isoformat()
        end = (datetime.utcnow() + timedelta(days=7)).isoformat()
        response = await client.get(
            f"/api/v1/jobs/calendar?owner_id=1&start_date={start}&end_date={end}"
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) >= 1

    async def test_update_job_endpoint(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]
        response = await client.put(
            f"/api/v1/jobs/{job_id}?changed_by_id=1",
            json={"title": "Updated Job Title"},
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Job Title"

    async def test_update_job_status_endpoint(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]
        response = await client.patch(
            f"/api/v1/jobs/{job_id}/status?changed_by_id=1",
            json={"status": "in_progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

    async def test_delete_job_endpoint(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]
        response = await client.delete(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 204
        get_resp = await client.get(f"/api/v1/jobs/{job_id}")
        assert get_resp.status_code == 404

    async def test_get_job_history_endpoint(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]
        response = await client.get(f"/api/v1/jobs/{job_id}/history")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# ==============================================================================
# Date & Time Handling Tests
# ==============================================================================


class TestJobDateTimeHandling:
    """Tests for date/time edge cases in job scheduling."""

    async def test_create_job_spanning_midnight(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """A job can span midnight (start on one day, end the next)."""
        start = datetime.utcnow().replace(hour=23, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=3)
        data = {**sample_job_data, "start_time": start, "end_time": end}
        job = await create_job(db_session, JobCreate(**data))
        assert job.start_time.date() != job.end_time.date()
        assert job.start_time < job.end_time

    async def test_all_day_jobs_have_no_specific_time(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """All-day jobs should be stored without start/end times."""
        data = {
            **sample_job_data,
            "start_time": None,
            "end_time": None,
            "all_day": True,
            "status": "pending",
        }
        job = await create_job(db_session, JobCreate(**data))
        assert job.all_day is True
        assert job.start_time is None

    async def test_job_duration_calculation_accuracy(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Actual duration can differ from estimated duration after completion."""
        start = datetime.utcnow()
        end = start + timedelta(hours=3, minutes=30)
        data = {
            **sample_job_data,
            "start_time": start,
            "end_time": end,
            "estimated_duration": 180,
        }
        job = await create_job(db_session, JobCreate(**data))

        status_update = JobStatusUpdate(
            status=JobStatus.COMPLETED, actual_duration=210
        )
        completed = await update_job_status(
            db_session, job.id, status_update, changed_by_id=1
        )
        assert completed.actual_duration == 210
        assert completed.actual_duration > completed.estimated_duration

    async def test_jobs_ordered_by_start_time(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Scheduled jobs should be returned ordered by start_time ASC."""
        base = datetime.utcnow()
        offsets = [5, 1, 3]  # Create out of order
        for h in offsets:
            data = {
                **sample_job_data,
                "start_time": base + timedelta(hours=h),
                "end_time": base + timedelta(hours=h + 1),
            }
            await create_job(db_session, JobCreate(**data))

        jobs, _ = await get_jobs(
            db_session, owner_id=1, status=[JobStatus.SCHEDULED]
        )
        for i in range(len(jobs) - 1):
            assert jobs[i].start_time <= jobs[i + 1].start_time


# ==============================================================================
# Job Status Lifecycle Tests
# ==============================================================================


class TestJobStatusLifecycle:
    """Tests for job status transitions."""

    async def test_pending_to_scheduled_on_scheduling(
        self, db_session: AsyncSession, sample_unscheduled_job_data: dict
    ) -> None:
        """Assigning a start_time should auto-transition pending → scheduled."""
        job = await create_job(
            db_session, JobCreate(**sample_unscheduled_job_data)
        )
        assert job.status == JobStatus.PENDING

        now = datetime.utcnow()
        update = JobUpdate(
            start_time=now, end_time=now + timedelta(hours=2)
        )
        updated = await update_job(db_session, job.id, update, changed_by_id=1)
        assert updated.status == JobStatus.SCHEDULED

    async def test_cancelled_job_preserves_original_data(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Cancelling a job should keep all original fields intact."""
        job = await create_job(db_session, JobCreate(**sample_job_data))
        original_title: str = job.title
        original_customer = job.customer_id

        status_update = JobStatusUpdate(status=JobStatus.CANCELLED)
        cancelled = await update_job_status(
            db_session, job.id, status_update, changed_by_id=1
        )

        assert cancelled.status == JobStatus.CANCELLED
        assert cancelled.title == original_title
        assert cancelled.customer_id == original_customer


# ==============================================================================
# Job Priority & Queue Management Tests
# ==============================================================================


class TestJobPriorityAndQueueing:
    """Tests for the unscheduled job queue ordering."""

    async def test_unscheduled_jobs_ordered_by_priority(
        self, db_session: AsyncSession, sample_unscheduled_job_data: dict
    ) -> None:
        """Unscheduled jobs should be returned highest-priority first."""
        for priority_str in ["low", "urgent", "normal", "high"]:
            data = {**sample_unscheduled_job_data, "priority": priority_str}
            await create_job(db_session, JobCreate(**data))

        jobs, _ = await get_unscheduled_jobs(db_session, owner_id=1)
        # Business priority order: urgent > high > normal > low
        assert jobs[0].priority == JobPriority.URGENT
        assert jobs[1].priority == JobPriority.HIGH
        assert jobs[2].priority == JobPriority.NORMAL
        assert jobs[3].priority == JobPriority.LOW

    async def test_completed_jobs_not_in_active_queue(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Completed jobs should not appear in active status queries."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        await update_job_status(
            db_session,
            job.id,
            JobStatusUpdate(status=JobStatus.COMPLETED),
            changed_by_id=1,
        )

        jobs, _ = await get_jobs(
            db_session, owner_id=1, status=[JobStatus.SCHEDULED]
        )
        assert job.id not in [j.id for j in jobs]


# ==============================================================================
# Job History & Audit Trail Tests
# ==============================================================================


class TestJobHistoryAndAudit:
    """Tests for the job audit history trail."""

    async def test_job_creation_recorded_in_history(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Creating a job should generate a 'create' history entry."""
        job = await create_job(db_session, JobCreate(**sample_job_data))
        history = await get_job_history(db_session, job.id)
        assert len(history) >= 1
        assert history[0].change_type == "create"

    async def test_job_updates_create_history_entries(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """Each field change should produce a new history entry."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        initial_count: int = len(await get_job_history(db_session, job.id))

        await update_job(
            db_session, job.id, JobUpdate(title="New Title"), changed_by_id=1
        )
        await update_job(
            db_session, job.id, JobUpdate(priority="high"), changed_by_id=1
        )

        history = await get_job_history(db_session, job.id)
        assert len(history) >= initial_count + 2

    async def test_job_history_includes_user_attribution(
        self, db_session: AsyncSession, sample_job_data: dict
    ) -> None:
        """History entries must record which user made the change."""
        job = await create_job(db_session, JobCreate(**sample_job_data))

        await update_job(
            db_session,
            job.id,
            JobUpdate(notes="Updated by dispatcher"),
            changed_by_id=5,
        )

        history = await get_job_history(db_session, job.id)
        update_entries = [h for h in history if h.change_type == "update"]
        assert any(entry.changed_by_id == 5 for entry in update_entries)


# ==============================================================================
# 404 Not-Found Path Tests
# ==============================================================================


class TestJob404Paths:
    """Tests that API returns 404 for nonexistent job IDs."""

    async def test_get_nonexistent_job_returns_404(
        self, client: AsyncClient
    ) -> None:
        """GET /api/v1/jobs/{id} returns 404 when job does not exist."""
        response = await client.get("/api/v1/jobs/99999")
        assert response.status_code == 404

    async def test_update_nonexistent_job_returns_404(
        self, client: AsyncClient
    ) -> None:
        """PUT /api/v1/jobs/{id} returns 404 when job does not exist."""
        response = await client.put(
            "/api/v1/jobs/99999?changed_by_id=1",
            json={"title": "Ghost Job"},
        )
        assert response.status_code == 404

    async def test_patch_status_nonexistent_job_returns_404(
        self, client: AsyncClient
    ) -> None:
        """PATCH /api/v1/jobs/{id}/status returns 404 when job does not exist."""
        response = await client.patch(
            "/api/v1/jobs/99999/status?changed_by_id=1",
            json={"status": "in_progress"},
        )
        assert response.status_code == 404

    async def test_delete_nonexistent_job_returns_404(
        self, client: AsyncClient
    ) -> None:
        """DELETE /api/v1/jobs/{id} returns 404 when job does not exist."""
        response = await client.delete("/api/v1/jobs/99999")
        assert response.status_code == 404

    async def test_get_history_nonexistent_job_returns_404(
        self, client: AsyncClient
    ) -> None:
        """GET /api/v1/jobs/{id}/history returns 404 when job does not exist."""
        response = await client.get("/api/v1/jobs/99999/history")
        assert response.status_code == 404


# ==============================================================================
# Include History Query Parameter Tests
# ==============================================================================


class TestJobIncludeHistory:
    """Tests for GET /api/v1/jobs/{id}?include_history=true."""

    async def test_get_job_with_history_flag(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """include_history=true should populate the history key."""
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]

        # Make an update so there's more than just the create entry
        await client.put(
            f"/api/v1/jobs/{job_id}?changed_by_id=1",
            json={"title": "Revised Kitchen Renovation"},
        )

        response = await client.get(
            f"/api/v1/jobs/{job_id}?include_history=true"
        )
        assert response.status_code == 200

        data = response.json()
        assert "history" in data
        assert isinstance(data["history"], list)
        assert len(data["history"]) >= 2  # create + update

    async def test_get_job_without_history_flag(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """Without include_history the history list should be empty."""
        create_resp = await client.post("/api/v1/jobs", json=sample_job_data)
        job_id: int = create_resp.json()["id"]

        response = await client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200

        data = response.json()
        assert "history" in data
        assert data["history"] == []


# ==============================================================================
# Multi-Tenant Isolation Tests
# ==============================================================================


class TestJobMultiTenantIsolation:
    """Tests that owner_id filtering correctly isolates tenants."""

    async def test_list_jobs_filtered_by_owner_id(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """GET /api/v1/jobs?owner_id=N returns only that tenant's jobs."""
        # Create jobs for two different owners
        owner1_data = {**sample_job_data, "owner_id": 1, "title": "Owner 1 Job"}
        owner2_data = {**sample_job_data, "owner_id": 2, "title": "Owner 2 Job"}

        await client.post("/api/v1/jobs", json=owner1_data)
        await client.post("/api/v1/jobs", json=owner2_data)

        # Query for owner 1
        resp1 = await client.get("/api/v1/jobs?owner_id=1")
        assert resp1.status_code == 200
        items1 = resp1.json()["items"]
        assert all(j["owner_id"] == 1 for j in items1)
        assert any(j["title"] == "Owner 1 Job" for j in items1)

        # Query for owner 2
        resp2 = await client.get("/api/v1/jobs?owner_id=2")
        assert resp2.status_code == 200
        items2 = resp2.json()["items"]
        assert all(j["owner_id"] == 2 for j in items2)
        assert any(j["title"] == "Owner 2 Job" for j in items2)

    async def test_owner_1_does_not_see_owner_2_jobs(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """Owner 1's listing must not include Owner 2's jobs."""
        await client.post(
            "/api/v1/jobs",
            json={**sample_job_data, "owner_id": 2, "title": "Secret Job"},
        )

        resp = await client.get("/api/v1/jobs?owner_id=1")
        items = resp.json()["items"]
        assert not any(j["title"] == "Secret Job" for j in items)


# ==============================================================================
# Calendar Date-Range Overlap Tests
# ==============================================================================


class TestJobCalendarOverlap:
    """Tests that the calendar endpoint only returns overlapping jobs."""

    async def test_calendar_returns_only_overlapping_jobs(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """
        Jobs outside the queried date window should be excluded.

        Creates three jobs:
          - Job A: day 1–2 (inside window)
          - Job B: day 3–4 (inside window)
          - Job C: day 10–11 (outside window)
        Query window: day 0–5 → should return A and B only.
        """
        base = datetime.utcnow().replace(
            hour=9, minute=0, second=0, microsecond=0
        )

        job_a = {
            **sample_job_data,
            "title": "Job A",
            "start_time": (base + timedelta(days=1)).isoformat(),
            "end_time": (base + timedelta(days=1, hours=4)).isoformat(),
        }
        job_b = {
            **sample_job_data,
            "title": "Job B",
            "start_time": (base + timedelta(days=3)).isoformat(),
            "end_time": (base + timedelta(days=3, hours=4)).isoformat(),
        }
        job_c = {
            **sample_job_data,
            "title": "Job C",
            "start_time": (base + timedelta(days=10)).isoformat(),
            "end_time": (base + timedelta(days=10, hours=4)).isoformat(),
        }

        await client.post("/api/v1/jobs", json=job_a)
        await client.post("/api/v1/jobs", json=job_b)
        await client.post("/api/v1/jobs", json=job_c)

        window_start = base.isoformat()
        window_end = (base + timedelta(days=5)).isoformat()

        response = await client.get(
            f"/api/v1/jobs/calendar?owner_id=1"
            f"&start_date={window_start}&end_date={window_end}"
        )
        assert response.status_code == 200
        data = response.json()

        titles = [e["title"] for e in data["events"]]
        assert "Job A" in titles
        assert "Job B" in titles
        assert "Job C" not in titles

    async def test_calendar_includes_job_spanning_window_boundary(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """A job that starts before the window but ends inside it should appear."""
        base = datetime.utcnow().replace(
            hour=9, minute=0, second=0, microsecond=0
        )

        spanning_job = {
            **sample_job_data,
            "title": "Spanning Job",
            "start_time": (base - timedelta(days=1)).isoformat(),
            "end_time": (base + timedelta(hours=4)).isoformat(),
        }
        await client.post("/api/v1/jobs", json=spanning_job)

        window_start = base.isoformat()
        window_end = (base + timedelta(days=3)).isoformat()

        response = await client.get(
            f"/api/v1/jobs/calendar?owner_id=1"
            f"&start_date={window_start}&end_date={window_end}"
        )
        assert response.status_code == 200
        titles = [e["title"] for e in response.json()["events"]]
        assert "Spanning Job" in titles


# ==============================================================================
# Auto Status-Promotion on Create Tests
# ==============================================================================


class TestJobAutoStatusPromotion:
    """Tests that creating a job with start_time auto-promotes pending → scheduled."""

    async def test_pending_with_start_time_promotes_to_scheduled_via_api(
        self, client: AsyncClient, sample_job_data: dict
    ) -> None:
        """
        POST /api/v1/jobs with status=pending but a start_time should
        auto-promote the returned status to 'scheduled'.
        """
        data = {
            **sample_job_data,
            "status": "pending",
            # start_time & end_time already set in sample_job_data
        }
        response = await client.post("/api/v1/jobs", json=data)
        assert response.status_code == 201
        assert response.json()["status"] == "scheduled"

    async def test_pending_without_start_time_stays_pending_via_api(
        self, client: AsyncClient, sample_unscheduled_job_data: dict
    ) -> None:
        """
        POST /api/v1/jobs with status=pending and no start_time should
        remain 'pending' (no promotion).
        """
        response = await client.post(
            "/api/v1/jobs", json=sample_unscheduled_job_data
        )
        assert response.status_code == 201
        assert response.json()["status"] == "pending"
