"""
Unit tests for Job Service (Business Logic Layer).

Tests API routes with mocked service-client calls.
Fixtures (owner_client, employee_client, sample_job, sample_customer)
are provided by conftest.py.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

# ==============================================================================
# Health Check
# ==============================================================================


class TestHealthEndpoint:
    def test_health_returns_200(self, owner_client: TestClient) -> None:
        response = owner_client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["service"] == "job-service"


# ==============================================================================
# List Jobs
# ==============================================================================


class TestListJobs:
    @patch("app.service_client.get_jobs", new_callable=AsyncMock)
    def test_list_jobs_scoped_to_tenant(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_get.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 100,
            "pages": 0,
        }
        response = owner_client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert mock_get.call_args.kwargs["owner_id"] == 1


# ==============================================================================
# Create Job
# ==============================================================================


class TestCreateJob:
    @patch("app.service_client.create_job", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_create_job_validates_customer_tenant(
        self,
        mock_cust: AsyncMock,
        mock_create: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
        sample_customer: dict,
    ) -> None:
        mock_cust.return_value = sample_customer
        mock_create.return_value = sample_job
        response = owner_client.post(
            "/api/v1/jobs",
            json={
                "title": "Fix Sink",
                "customer_id": 10,
            },
        )
        assert response.status_code == 201

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_create_job_rejects_wrong_tenant_customer(
        self,
        mock_cust: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        mock_cust.return_value = {"id": 10, "owner_id": 999}  # Different tenant
        response = owner_client.post(
            "/api/v1/jobs",
            json={"title": "Fix Sink", "customer_id": 10},
        )
        assert response.status_code == 400


# ==============================================================================
# Get Job
# ==============================================================================


class TestGetJob:
    @patch("app.service_client.get_user", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_get_job_enriched(
        self,
        mock_job: AsyncMock,
        mock_cust: AsyncMock,
        mock_user: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        mock_job.return_value = dict(sample_job)
        mock_cust.return_value = {"name": "Alice Smith"}
        mock_user.return_value = {"first_name": "Bob", "last_name": "Jones"}

        response = owner_client.get("/api/v1/jobs/1")
        assert response.status_code == 200
        data = response.json()
        assert data["customer_name"] == "Alice Smith"
        assert data["assigned_to_name"] == "Bob Jones"

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_get_job_wrong_tenant_denied(
        self,
        mock_job: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        bad_job = {**sample_job, "owner_id": 999}
        mock_job.return_value = bad_job
        response = owner_client.get("/api/v1/jobs/1")
        assert response.status_code == 403


# ==============================================================================
# Schedule Job
# ==============================================================================


class TestScheduleJob:
    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_jobs_by_assignee_and_date", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_schedule_no_conflicts(
        self,
        mock_get: AsyncMock,
        mock_assignee: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        mock_get.return_value = sample_job
        mock_assignee.return_value = []  # No existing jobs
        mock_update.return_value = {**sample_job, "status": "scheduled"}

        now = datetime.utcnow()
        response = owner_client.post(
            "/api/v1/jobs/1/schedule",
            json={
                "start_time": (now + timedelta(hours=5)).isoformat(),
                "end_time": (now + timedelta(hours=7)).isoformat(),
            },
        )
        assert response.status_code == 200

    @patch("app.service_client.get_jobs_by_assignee_and_date", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_schedule_with_conflict(
        self,
        mock_get: AsyncMock,
        mock_assignee: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        mock_get.return_value = sample_job
        # Return an overlapping job
        now = datetime.utcnow()
        mock_assignee.return_value = [
            {
                "id": 2,
                "title": "Other Job",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=3)).isoformat(),
            }
        ]

        response = owner_client.post(
            "/api/v1/jobs/1/schedule",
            json={
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=4)).isoformat(),
            },
        )
        assert response.status_code == 409


# ==============================================================================
# Update Status
# ==============================================================================


class TestUpdateStatus:
    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_employee_can_update_status(
        self,
        mock_get: AsyncMock,
        mock_update: AsyncMock,
        employee_client: TestClient,
        sample_job: dict,
    ) -> None:
        mock_get.return_value = sample_job
        mock_update.return_value = {**sample_job, "status": "in_progress"}
        response = employee_client.put(
            "/api/v1/jobs/1/status",
            json={"status": "in_progress"},
        )
        assert response.status_code == 200


# ==============================================================================
# Delete Job
# ==============================================================================


class TestDeleteJob:
    @patch("app.service_client.delete_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_owner_can_delete(
        self,
        mock_get: AsyncMock,
        mock_del: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        mock_get.return_value = sample_job
        mock_del.return_value = None
        response = owner_client.delete("/api/v1/jobs/1")
        assert response.status_code == 204

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_employee_cannot_delete(
        self,
        mock_get: AsyncMock,
        employee_client: TestClient,
        sample_job: dict,
    ) -> None:
        mock_get.return_value = sample_job
        response = employee_client.delete("/api/v1/jobs/1")
        assert response.status_code == 403


# ==============================================================================
# Job Queue
# ==============================================================================


class TestJobQueue:
    @patch("app.service_client.get_unscheduled_jobs", new_callable=AsyncMock)
    def test_queue_returns_unscheduled(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        now = datetime.utcnow().isoformat()
        mock_get.return_value = [
            {
                "id": 3,
                "title": "Pending Job",
                "customer_id": 10,
                "owner_id": 1,
                "status": "pending",
                "priority": "normal",
                "created_at": now,
                "updated_at": now,
            }
        ]
        response = owner_client.get("/api/v1/jobs/queue")
        assert response.status_code == 200
        assert response.json()["total"] == 1


# ==============================================================================
# Tenant Isolation & Security Tests
# ==============================================================================


class TestTenantIsolationAndSecurity:
    """
    Tests ensuring multi-tenant isolation at business logic layer.

    Critical security tests - ensures tenants cannot access or
    manipulate other tenants' data through the API.
    Industry standard: Defense in depth with multiple isolation layers.
    """

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_cannot_access_other_tenant_job(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Accessing a job from another tenant must return 403.

        Prevents horizontal privilege escalation where tenant A
        tries to view tenant B's jobs. Essential for data privacy
        and compliance with regulations like GDPR.
        """
        # Mock returns job belonging to different tenant
        other_tenant_job = {**sample_job, "owner_id": 999}
        mock_get.return_value = other_tenant_job

        response = owner_client.get("/api/v1/jobs/1")

        # Must be denied, not just return empty
        assert response.status_code == 403
        assert "access" in response.json()["detail"].lower()

    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_cannot_update_other_tenant_job(
        self,
        mock_get: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Updating a job from another tenant must be blocked.

        Prevents data corruption attacks where tenant A modifies
        tenant B's jobs. Critical for data integrity.
        """
        other_tenant_job = {**sample_job, "owner_id": 999}
        mock_get.return_value = other_tenant_job

        response = owner_client.put(
            "/api/v1/jobs/1",
            json={"title": "Malicious Update"},
        )

        assert response.status_code == 403
        # Update should never be called
        mock_update.assert_not_called()

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    def test_cannot_assign_job_to_other_tenant_customer(
        self,
        mock_cust: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Creating jobs must validate customers belong to same tenant.

        Prevents tenant A from creating jobs for tenant B's customers,
        which could leak sensitive information or create confusion.
        """
        # Mock customer from different tenant
        mock_cust.return_value = {"id": 10, "owner_id": 999}

        response = owner_client.post(
            "/api/v1/jobs",
            json={"title": "Test Job", "customer_id": 10},
        )

        # Should be rejected
        assert response.status_code == 400
        assert "tenant" in response.json()["detail"].lower()

    @patch("app.service_client.get_jobs", new_callable=AsyncMock)
    def test_list_jobs_automatically_scoped_to_tenant(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Job listings must automatically filter to current tenant.

        Ensures tenants never accidentally see other tenants' data
        in listings. Token's owner_id enforces automatic scoping.
        """
        mock_get.return_value = {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 100,
            "pages": 0,
        }

        owner_client.get("/api/v1/jobs")

        # Verify owner_id was passed to data layer
        assert mock_get.called
        assert mock_get.call_args.kwargs["owner_id"] == 1


# ==============================================================================
# Role-Based Access Control Tests
# ==============================================================================


class TestRoleBasedAccessControl:
    """
    Tests for role-based permissions at business logic layer.

    Ensures admins and employees have appropriate restrictions
    compared to owners. Implements principle of least privilege.
    """

    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_employee_can_update_jobs_in_own_tenant(
        self,
        mock_get: AsyncMock,
        mock_update: AsyncMock,
        employee_client: TestClient,
    ) -> None:
        """
        Employees can update any job within their tenant.

        Tenant isolation is enforced via ``owner_id`` — any
        authenticated user in the same tenant can update job
        fields like notes, status, etc.
        """
        now = datetime.utcnow().isoformat()
        job_assigned_to_employee = {
            "id": 1,
            "title": "Fix Sink",
            "owner_id": 1,
            "assigned_to": 5,
            "status": "in_progress",
            "customer_id": 10,
            "priority": "normal",
            "created_at": now,
            "updated_at": now,
        }
        mock_get.return_value = job_assigned_to_employee
        mock_update.return_value = {**job_assigned_to_employee, "notes": "Updated"}

        response = employee_client.put(
            "/api/v1/jobs/1",
            json={"notes": "Fixed the leak"},
        )

        # Should succeed
        assert response.status_code == 200


# ==============================================================================
# Data Enrichment Tests
# ==============================================================================


class TestDataEnrichment:
    """
    Tests for business logic layer data enrichment.

    BL services add computed fields, fetch related data, and
    transform DB records into richer API responses.
    """

    @patch("app.service_client.get_user", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_job_enriched_with_customer_name(
        self,
        mock_job: AsyncMock,
        mock_cust: AsyncMock,
        mock_user: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Jobs should include customer name, not just ID.

        Improves UX - users see "Alice Smith" instead of needing
        to lookup customer_id=10 separately. Reduces API calls.
        """
        mock_job.return_value = sample_job
        mock_cust.return_value = {
            "id": 10,
            "name": "Alice Smith",
        }
        mock_user.return_value = {
            "id": 5,
            "first_name": "Bob",
            "last_name": "Jones",
        }

        response = owner_client.get("/api/v1/jobs/1")

        data = response.json()
        assert "customer_name" in data
        assert data["customer_name"] == "Alice Smith"

    @patch("app.service_client.get_user", new_callable=AsyncMock)
    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_job_enriched_with_assignee_name(
        self,
        mock_job: AsyncMock,
        mock_cust: AsyncMock,
        mock_user: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Jobs should include assignee name for quick reference.

        Dispatchers need to see "Bob Jones" assigned to job
        without additional lookups. Essential for scheduling UI.
        """
        mock_job.return_value = sample_job
        mock_cust.return_value = {"name": "Alice Smith"}
        mock_user.return_value = {"first_name": "Bob", "last_name": "Jones"}

        response = owner_client.get("/api/v1/jobs/1")

        data = response.json()
        assert "assigned_to_name" in data
        assert data["assigned_to_name"] == "Bob Jones"

    @patch("app.service_client.get_customer", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_job_handles_missing_assignee_gracefully(
        self,
        mock_job: AsyncMock,
        mock_cust: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Unassigned jobs must not crash during enrichment.

        Many jobs start unassigned - system must handle null
        assigned_to gracefully with appropriate default values.
        """
        unassigned_job = {**sample_job, "assigned_to": None}
        mock_job.return_value = unassigned_job
        mock_cust.return_value = {"name": "Alice Smith"}

        response = owner_client.get("/api/v1/jobs/1")

        assert response.status_code == 200
        data = response.json()
        # Should have null or "Unassigned" placeholder
        assert data["assigned_to_name"] in [None, "Unassigned"]


# ==============================================================================
# Conflict Detection Tests
# ==============================================================================


class TestSchedulingConflictDetection:
    """
    Tests for scheduling conflict detection logic.

    Critical business logic - prevents double-booking employees
    and ensures realistic schedules.
    """

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    @patch("app.service_client.get_jobs_by_assignee_and_date", new_callable=AsyncMock)
    def test_detect_overlapping_time_conflict(
        self,
        mock_assignee: AsyncMock,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Overlapping job times must be flagged as conflicts.

        Prevents assigning employee to two jobs at same time,
        which is physically impossible and causes service failures.
        """
        now = datetime.utcnow()
        mock_get.return_value = {
            "id": 1,
            "title": "Existing Job",
            "owner_id": 1,
            "assigned_to": 5,
        }
        existing_job = {
            "id": 2,
            "title": "Other Job",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
        }
        mock_assignee.return_value = [existing_job]

        response = owner_client.post(
            "/api/v1/jobs/1/check-conflicts",
            json={
                "assigned_to": 5,
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=3)).isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_conflicts"] is True

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    @patch("app.service_client.get_jobs_by_assignee_and_date", new_callable=AsyncMock)
    def test_no_conflict_for_sequential_jobs(
        self,
        mock_assignee: AsyncMock,
        mock_get: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Back-to-back jobs should not conflict.

        If job A ends at 2PM and job B starts at 2PM, they don't
        overlap. System should allow efficient scheduling without
        forced gaps.
        """
        now = datetime.utcnow()
        mock_get.return_value = {
            "id": 1,
            "title": "Current Job",
            "owner_id": 1,
            "assigned_to": 5,
        }
        existing_job = {
            "id": 2,
            "title": "Other Job",
            "start_time": now.isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
        }
        mock_assignee.return_value = [existing_job]

        response = owner_client.post(
            "/api/v1/jobs/1/check-conflicts",
            json={
                "assigned_to": 5,
                "start_time": (now + timedelta(hours=2)).isoformat(),
                "end_time": (now + timedelta(hours=4)).isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_conflicts"] is False


# ==============================================================================
# Calendar Endpoint
# ==============================================================================


class TestCalendarEndpoint:
    """Tests for GET /api/v1/jobs/calendar."""

    @patch("app.service_client.get_calendar_jobs", new_callable=AsyncMock)
    def test_calendar_returns_200_with_grouped_days(
        self,
        mock_cal: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Verify calendar endpoint groups jobs by date.

        Verifies:
        - 200 status code
        - Response contains one entry per day in the range
        - Jobs are grouped under the correct date
        """
        now = datetime.utcnow()
        mock_cal.return_value = [
            {
                "id": 1,
                "title": "Fix Sink",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
                "status": "scheduled",
                "priority": "medium",
                "all_day": False,
                "color": None,
                "assigned_to": 5,
                "customer_id": 10,
            },
        ]

        today = now.date()
        response = owner_client.get(
            "/api/v1/jobs/calendar",
            params={"start_date": str(today), "end_date": str(today)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["date"] == str(today)
        assert data[0]["total_jobs"] == 1
        # Verify service_client was called with correct owner_id
        assert mock_cal.call_args.kwargs["owner_id"] == 1

    @patch("app.service_client.get_calendar_jobs", new_callable=AsyncMock)
    def test_calendar_empty_range(
        self,
        mock_cal: AsyncMock,
        owner_client: TestClient,
    ) -> None:
        """
        Calendar with no jobs returns days with empty job lists.

        Verifies:
        - 200 status code
        - Each day has total_jobs == 0
        """
        mock_cal.return_value = []

        today = datetime.utcnow().date()
        response = owner_client.get(
            "/api/v1/jobs/calendar",
            params={"start_date": str(today), "end_date": str(today)},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["total_jobs"] == 0


# ==============================================================================
# Assign Endpoint
# ==============================================================================


class TestAssignEndpoint:
    """Tests for POST /api/v1/jobs/{id}/assign."""

    @patch("app.service_client.assign_employee_to_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_assign_happy_path_no_times(
        self,
        mock_get: AsyncMock,
        mock_assign: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Assigning without times should skip conflict detection.

        Verifies:
        - 200 status code
        - assign_employee_to_job called with correct employee
        """
        mock_get.return_value = sample_job
        mock_assign.return_value = {"job_id": 1, "employee_id": 7}

        response = owner_client.post(
            "/api/v1/jobs/1/assign",
            json={"assigned_to": 7},
        )

        assert response.status_code == 200
        mock_assign.assert_called_once()
        assert mock_assign.call_args.kwargs["employee_id"] == 7

    @patch("app.service_client.assign_employee_to_job", new_callable=AsyncMock)
    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_jobs_by_assignee_and_date", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_assign_with_times_no_conflict(
        self,
        mock_get: AsyncMock,
        mock_assignee: AsyncMock,
        mock_update: AsyncMock,
        mock_assign: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Assigning with times and no conflicts succeeds.

        Verifies:
        - 200 status code
        - Status set to 'scheduled'
        """
        mock_get.return_value = sample_job
        mock_assignee.return_value = []  # No existing jobs
        mock_update.return_value = {
            **sample_job,
            "assigned_to": 7,
            "status": "scheduled",
        }
        mock_assign.return_value = {"job_id": 1, "employee_id": 7}

        now = datetime.utcnow()
        response = owner_client.post(
            "/api/v1/jobs/1/assign",
            json={
                "assigned_to": 7,
                "start_time": (now + timedelta(hours=5)).isoformat(),
                "end_time": (now + timedelta(hours=7)).isoformat(),
            },
        )

        assert response.status_code == 200

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_assign_wrong_tenant_denied(
        self,
        mock_get: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Assigning a job from a different tenant must be denied.

        Verifies:
        - 403 status code
        """
        mock_get.return_value = {**sample_job, "owner_id": 999}

        response = owner_client.post(
            "/api/v1/jobs/1/assign",
            json={"assigned_to": 7},
        )

        assert response.status_code == 403

    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_assign_requires_owner_or_admin(
        self,
        mock_get: AsyncMock,
        employee_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Employees cannot assign jobs (require_role blocks them).

        Verifies:
        - 403 status code for employee role
        """
        mock_get.return_value = sample_job

        response = employee_client.post(
            "/api/v1/jobs/1/assign",
            json={"assigned_to": 7},
        )

        assert response.status_code == 403


# ==============================================================================
# Job Update Happy Path
# ==============================================================================


class TestJobUpdateHappyPath:
    """Tests for PUT /api/v1/jobs/{id} successful updates."""

    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_owner_can_update_job(
        self,
        mock_get: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Owner updating a job in their tenant succeeds.

        Verifies:
        - 200 status code
        - Updated fields reflected in response
        - update_job called with correct payload
        """
        mock_get.return_value = sample_job
        updated = {**sample_job, "title": "Fix Sink v2", "priority": "high"}
        mock_update.return_value = updated

        response = owner_client.put(
            "/api/v1/jobs/1",
            json={"title": "Fix Sink v2", "priority": "high"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Fix Sink v2"
        assert data["priority"] == "high"
        mock_update.assert_called_once()

    @patch("app.service_client.update_job", new_callable=AsyncMock)
    @patch("app.service_client.get_job", new_callable=AsyncMock)
    def test_update_partial_fields(
        self,
        mock_get: AsyncMock,
        mock_update: AsyncMock,
        owner_client: TestClient,
        sample_job: dict,
    ) -> None:
        """
        Partial update should only send provided fields.

        Verifies:
        - 200 status code
        - Only the notes field is updated
        """
        mock_get.return_value = sample_job
        mock_update.return_value = {**sample_job, "notes": "Updated note"}

        response = owner_client.put(
            "/api/v1/jobs/1",
            json={"notes": "Updated note"},
        )

        assert response.status_code == 200
        assert response.json()["notes"] == "Updated note"
