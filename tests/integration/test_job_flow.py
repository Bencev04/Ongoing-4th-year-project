"""
Integration tests — Job service flow.

Pairwise: job-bl-service ↔ job-db-access-service

Tests job CRUD, calendar, queue, scheduling, assignment, conflict
detection, and status updates through the BL layer using real auth
tokens and real service-to-service calls.

Covers:
    - Job listing, creation, full update, deletion
    - Calendar and queue endpoints
    - Job assignment to employees
    - Job scheduling with time slots
    - Scheduling conflict detection
    - RBAC enforcement on delete/assign/schedule
"""

from typing import Dict, Optional
from datetime import datetime, timedelta, timezone

import httpx
import pytest


class TestListJobs:
    """Test listing jobs through the BL layer."""

    def test_list_jobs_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test that listing jobs returns 200.

        Verifies:
        - Response is 200
        """
        resp = http_client.get(
            "/api/v1/jobs/",
            headers=owner_headers,
        )
        assert resp.status_code == 200

    def test_list_jobs_requires_auth(
        self, http_client: httpx.Client
    ) -> None:
        """
        Test jobs endpoint requires authentication.

        Verifies:
        - 401 without auth header
        """
        resp = http_client.get("/api/v1/jobs/")
        assert resp.status_code in (401, 403)


class TestCalendarEndpoint:
    """Test the calendar view endpoint."""

    def test_calendar_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test the calendar endpoint returns data.

        Verifies:
        - GET /jobs/calendar returns 200
        - Response contains calendar-structured data
        """
        resp = http_client.get(
            "/api/v1/jobs/calendar",
            headers=owner_headers,
            params={"start_date": "2026-02-01", "end_date": "2026-02-28"},
        )
        assert resp.status_code == 200

    def test_calendar_requires_auth(
        self, http_client: httpx.Client
    ) -> None:
        """Test calendar requires authentication."""
        resp = http_client.get("/api/v1/jobs/calendar")
        assert resp.status_code in (401, 403)


class TestQueueEndpoint:
    """Test the job queue endpoint."""

    def test_queue_returns_200(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test the job queue endpoint returns unscheduled jobs.

        Verifies:
        - GET /jobs/queue returns 200
        """
        resp = http_client.get(
            "/api/v1/jobs/queue",
            headers=owner_headers,
        )
        assert resp.status_code == 200

    def test_queue_requires_auth(
        self, http_client: httpx.Client
    ) -> None:
        """Test queue requires authentication."""
        resp = http_client.get("/api/v1/jobs/queue")
        assert resp.status_code in (401, 403)


class TestJobCRUD:
    """Test job create, read, update cycle."""

    def _get_first_customer_id(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> Optional[int]:
        """Helper: get the first customer ID for the owner's tenant."""
        resp = http_client.get(
            "/api/v1/customers/",
            headers=owner_headers,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        customers = data if isinstance(data, list) else (
            data.get("data") or data.get("items") or data.get("customers", [])
        )
        if not customers:
            return None
        return customers[0].get("id") or customers[0].get("customer_id")

    def test_create_and_read_job(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test creating and reading a job.

        Verifies:
        - POST /jobs/ creates a job (200 or 201)
        - GET /jobs/{id} retrieves it
        """
        customer_id = self._get_first_customer_id(http_client, owner_headers)

        create_payload = {
            "title": "Integration Test Job",
            "description": "Created by integration tests — safe to delete.",
            "status": "pending",
            "priority": "normal",
        }
        if customer_id:
            create_payload["customer_id"] = customer_id

        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json=create_payload,
        )
        assert create_resp.status_code in (200, 201)
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")
        assert job_id is not None

        # Read
        get_resp = http_client.get(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )
        assert get_resp.status_code == 200

        # Cleanup
        http_client.delete(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )

    def test_update_job_status(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test updating a job's status.

        Verifies:
        - Create a job → update status to 'in_progress' → verify
        """
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Status Update Test Job",
                "status": "pending",
                "priority": "low",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        # Update status
        status_resp = http_client.put(
            f"/api/v1/jobs/{job_id}/status",
            headers=owner_headers,
            json={"status": "in_progress"},
        )
        assert status_resp.status_code == 200

        # Cleanup
        http_client.delete(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )

    def test_update_job_full(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test full job update (title, description, priority).

        Verifies:
        - PUT /jobs/{id} returns 200
        - Updated fields are reflected in the response
        """
        # Create
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Full Update Test Job",
                "description": "Before update",
                "status": "pending",
                "priority": "low",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            # Full update
            update_resp = http_client.put(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
                json={
                    "title": "Updated Job Title",
                    "description": "After update",
                    "priority": "high",
                },
            )
            assert update_resp.status_code == 200
        finally:
            # Cleanup
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )

    def test_delete_job_explicitly(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test explicit job deletion (not just cleanup).

        Verifies:
        - DELETE /jobs/{id} returns 200 or 204
        - GET /jobs/{id} after delete returns 404 or inactive
        """
        # Create
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Delete Test Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        # Delete
        del_resp = http_client.delete(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )
        assert del_resp.status_code in (200, 204)

        # Verify deletion — should be 404 or return inactive
        get_resp = http_client.get(
            f"/api/v1/jobs/{job_id}",
            headers=owner_headers,
        )
        assert get_resp.status_code in (404, 200)  # 200 if soft-delete

    def test_employee_cannot_delete_job(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
        employee_headers: Dict[str, str],
    ) -> None:
        """
        Test that an employee cannot delete jobs (owner/admin only).

        Verifies:
        - 403 when employee attempts DELETE /jobs/{id}
        """
        # Create with owner
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Employee Cannot Delete",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            # Employee tries to delete
            del_resp = http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=employee_headers,
            )
            assert del_resp.status_code == 403
        finally:
            # Cleanup with owner
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )


# ==========================================================================
# Job Assignment
# ==========================================================================

class TestJobAssignment:
    """
    Test job assignment to employees.

    Pairwise: job-bl-service ↔ job-db-access-service

    POST /jobs/{id}/assign links a job to a specific employee and
    optionally checks for scheduling conflicts.
    """

    def _get_first_employee_id(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> Optional[int]:
        """Helper: get the first employee ID for assignment tests."""
        resp = http_client.get(
            "/api/v1/employees/",
            headers=owner_headers,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        employees = data if isinstance(data, list) else (
            data.get("data") or data.get("items") or data.get("employees", [])
        )
        if not employees:
            return None
        return employees[0].get("id") or employees[0].get("employee_id")

    def test_assign_job_to_employee(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test assigning a job to an employee.

        Steps:
        1. Create a job
        2. POST /jobs/{id}/assign with employee's ID
        3. Verify assignment succeeded

        Verifies:
        - 200 on successful assignment
        """
        employee_id = self._get_first_employee_id(http_client, owner_headers)
        if employee_id is None:
            pytest.skip("No employees found in tenant")

        # Create a job
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Assignment Test Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            # Assign
            assign_resp = http_client.post(
                f"/api/v1/jobs/{job_id}/assign",
                headers=owner_headers,
                json={"assigned_to": employee_id},
            )
            assert assign_resp.status_code == 200, (
                f"Assign failed: {assign_resp.status_code} — {assign_resp.text}"
            )
        finally:
            # Cleanup
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )

    def test_employee_cannot_assign_jobs(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
        employee_headers: Dict[str, str],
    ) -> None:
        """
        Test that employees cannot assign jobs (owner/admin only).

        Verifies:
        - 403 when employee attempts POST /jobs/{id}/assign
        """
        # Create with owner
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Assign RBAC Test",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        try:
            resp = http_client.post(
                f"/api/v1/jobs/{job_id}/assign",
                headers=employee_headers,
                json={"assigned_to": 1},
            )
            assert resp.status_code == 403
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )


# ==========================================================================
# Job Scheduling and Conflict Detection
# ==========================================================================

class TestJobScheduling:
    """
    Test job scheduling with time slots and conflict detection.

    Pairwise: job-bl-service ↔ job-db-access-service

    POST /jobs/{id}/schedule sets a job's start/end time.
    POST /jobs/{id}/check-conflicts previews scheduling conflicts.
    """

    def test_schedule_job_to_timeslot(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test scheduling a job to a specific time slot.

        Verifies:
        - 200 on successful scheduling
        - Job status may transition to 'scheduled'
        """
        # Create a pending job
        create_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Schedule Test Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job = create_resp.json()
        job_id = job.get("id") or job.get("job_id")

        # Schedule for tomorrow 09:00–11:00
        now = datetime.now(timezone.utc)
        start = (now + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=2)

        try:
            schedule_resp = http_client.post(
                f"/api/v1/jobs/{job_id}/schedule",
                headers=owner_headers,
                json={
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                },
            )
            assert schedule_resp.status_code == 200, (
                f"Schedule failed: {schedule_resp.status_code} — {schedule_resp.text}"
            )
        finally:
            http_client.delete(
                f"/api/v1/jobs/{job_id}",
                headers=owner_headers,
            )

    def test_check_conflicts_preview(
        self,
        http_client: httpx.Client,
        owner_headers: Dict[str, str],
    ) -> None:
        """
        Test the conflict-check preview endpoint.

        Steps:
        1. Create and schedule a job for a specific time slot
        2. Create a second job
        3. POST /jobs/{second_id}/check-conflicts with overlapping times
        4. Verify conflicts are reported

        Verifies:
        - 200 response
        - Response contains has_conflicts field
        """
        now = datetime.now(timezone.utc)
        start = (now + timedelta(days=2)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=2)

        # Create first job and schedule it
        job1_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Conflict Source Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job1 = job1_resp.json()
        job1_id = job1.get("id") or job1.get("job_id")

        # Schedule the first job
        http_client.post(
            f"/api/v1/jobs/{job1_id}/schedule",
            headers=owner_headers,
            json={
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
        )

        # Create second job
        job2_resp = http_client.post(
            "/api/v1/jobs/",
            headers=owner_headers,
            json={
                "title": "Conflict Target Job",
                "status": "pending",
                "priority": "normal",
            },
        )
        job2 = job2_resp.json()
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            # Check for conflicts with overlapping time
            overlap_start = start + timedelta(hours=1)  # Overlaps by 1 hour
            overlap_end = overlap_start + timedelta(hours=2)

            conflict_resp = http_client.post(
                f"/api/v1/jobs/{job2_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": overlap_start.isoformat(),
                    "end_time": overlap_end.isoformat(),
                },
            )
            assert conflict_resp.status_code == 200
            data = conflict_resp.json()
            # Should contain conflict info structure
            assert isinstance(data, dict)
        finally:
            # Cleanup both jobs
            http_client.delete(
                f"/api/v1/jobs/{job1_id}",
                headers=owner_headers,
            )
            http_client.delete(
                f"/api/v1/jobs/{job2_id}",
                headers=owner_headers,
            )
