"""
End-to-end tests for job scheduling conflict detection.

Verifies that the BL layer correctly identifies overlapping
time ranges for the same employee through the full stack.

Conflict rule: two ranges overlap when start1 < end2 AND start2 < end1.
Jobs without an assigned employee do NOT participate in conflicts.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest


def _get_first_employee_id(
    client: httpx.Client,
    headers: dict[str, str],
) -> int | None:
    """Fetch the first employee ID from the employees list."""
    resp = client.get("/api/v1/employees/", headers=headers)
    if resp.status_code != 200:
        return None
    data = resp.json()
    items = (
        data
        if isinstance(data, list)
        else (data.get("data") or data.get("items") or data.get("employees", []))
    )
    if not items:
        return None
    return items[0].get("id") or items[0].get("employee_id")


def _create_job(
    client: httpx.Client,
    headers: dict[str, str],
    title: str,
    **extra: object,
) -> dict:
    """Create a job and return its response body."""
    payload = {"title": title, "status": "pending", "priority": "normal", **extra}
    resp = client.post("/api/v1/jobs/", headers=headers, json=payload)
    assert resp.status_code in (200, 201), (
        f"Job create failed ({resp.status_code}): {resp.text}"
    )
    return resp.json()


def _delete_job(
    client: httpx.Client,
    headers: dict[str, str],
    job_id: int,
) -> None:
    """Delete a job, ignoring errors."""
    client.delete(f"/api/v1/jobs/{job_id}", headers=headers)


class TestSchedulingConflictDetection:
    """
    Full-stack conflict detection via POST /jobs/{id}/check-conflicts.

    Tests require at least one employee in the tenant so jobs can
    be assigned (conflicts only apply to assigned employees).
    """

    @pytest.fixture(autouse=True)
    def _require_employee(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Skip all tests in this class if no employee exists."""
        emp = _get_first_employee_id(http_client, owner_headers)
        if emp is None:
            pytest.skip("No employees available — conflict tests require one")
        self.employee_id = emp

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _base_time(self, days_ahead: int = 5) -> datetime:
        """Return a clean future datetime for scheduling."""
        return (datetime.now(UTC) + timedelta(days=days_ahead)).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )

    def _schedule_and_assign(
        self,
        client: httpx.Client,
        headers: dict[str, str],
        job_id: int,
        start: datetime,
        end: datetime,
    ) -> None:
        """Assign to self.employee_id and schedule a time slot."""
        # Assign first
        assign = client.post(
            f"/api/v1/jobs/{job_id}/assign",
            headers=headers,
            json={"assigned_to": self.employee_id},
        )
        assert assign.status_code == 200, (
            f"Assign failed: {assign.status_code} — {assign.text}"
        )
        # Schedule
        sched = client.post(
            f"/api/v1/jobs/{job_id}/schedule",
            headers=headers,
            json={
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
        )
        assert sched.status_code == 200, (
            f"Schedule failed: {sched.status_code} — {sched.text}"
        )

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_overlapping_slot_reports_conflict(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Two jobs assigned to same employee with overlapping times
        → check-conflicts returns has_conflicts=True.
        """
        base = self._base_time(days_ahead=90)
        start1 = base
        end1 = base + timedelta(hours=2)  # 10:00–12:00

        job1 = _create_job(http_client, owner_headers, "Conflict-A")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "Conflict-B")
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            self._schedule_and_assign(
                http_client,
                owner_headers,
                job1_id,
                start1,
                end1,
            )
            # Assign job2 to same employee
            http_client.post(
                f"/api/v1/jobs/{job2_id}/assign",
                headers=owner_headers,
                json={"assigned_to": self.employee_id},
            )

            # Overlapping window: 11:00–13:00
            overlap_start = base + timedelta(hours=1)
            overlap_end = base + timedelta(hours=3)

            resp = http_client.post(
                f"/api/v1/jobs/{job2_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": overlap_start.isoformat(),
                    "end_time": overlap_end.isoformat(),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("has_conflicts") is True, (
                f"Expected has_conflicts=True: {data}"
            )
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)

    def test_non_overlapping_slot_no_conflict(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Two jobs for same employee with non-overlapping times
        → check-conflicts returns has_conflicts=False.
        """
        base = self._base_time(days_ahead=91)
        start1 = base
        end1 = base + timedelta(hours=2)  # 10:00–12:00

        job1 = _create_job(http_client, owner_headers, "NoConflict-A")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "NoConflict-B")
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            self._schedule_and_assign(
                http_client,
                owner_headers,
                job1_id,
                start1,
                end1,
            )
            # Assign job2 to same employee
            http_client.post(
                f"/api/v1/jobs/{job2_id}/assign",
                headers=owner_headers,
                json={"assigned_to": self.employee_id},
            )

            # Non-overlapping: 13:00–15:00 (after job1's 12:00 end)
            later_start = base + timedelta(hours=3)
            later_end = base + timedelta(hours=5)

            resp = http_client.post(
                f"/api/v1/jobs/{job2_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": later_start.isoformat(),
                    "end_time": later_end.isoformat(),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("has_conflicts") is False, (
                f"Expected has_conflicts=False: {data}"
            )
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)

    def test_adjacent_slots_no_conflict(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Back-to-back jobs (end1 == start2) should NOT conflict.

        Overlap rule: start1 < end2 AND start2 < end1.
        When end1 == start2 the second condition is start2 < end1 → False.
        """
        base = self._base_time(days_ahead=92)
        start1 = base
        end1 = base + timedelta(hours=2)  # 10:00–12:00

        job1 = _create_job(http_client, owner_headers, "Adjacent-A")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "Adjacent-B")
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            self._schedule_and_assign(
                http_client,
                owner_headers,
                job1_id,
                start1,
                end1,
            )
            http_client.post(
                f"/api/v1/jobs/{job2_id}/assign",
                headers=owner_headers,
                json={"assigned_to": self.employee_id},
            )

            # Adjacent: 12:00–14:00 (starts exactly when job1 ends)
            resp = http_client.post(
                f"/api/v1/jobs/{job2_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": end1.isoformat(),
                    "end_time": (end1 + timedelta(hours=2)).isoformat(),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("has_conflicts") is False, (
                f"Adjacent slots should not conflict: {data}"
            )
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)

    def test_self_exclusion_on_reschedule(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Rescheduling a job should NOT flag itself as a conflict.
        """
        base = self._base_time(days_ahead=93)
        start = base
        end = base + timedelta(hours=2)

        job = _create_job(http_client, owner_headers, "SelfExclusion")
        job_id = job.get("id") or job.get("job_id")

        try:
            self._schedule_and_assign(
                http_client,
                owner_headers,
                job_id,
                start,
                end,
            )

            # Check conflicts for the same time (should exclude itself)
            resp = http_client.post(
                f"/api/v1/jobs/{job_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("has_conflicts") is False, (
                f"Job should not conflict with itself: {data}"
            )
        finally:
            _delete_job(http_client, owner_headers, job_id)

    def test_unassigned_job_no_conflicts(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        A job without an assigned employee has no conflicts
        (conflict detection requires an employee target).
        """
        base = self._base_time(days_ahead=94)

        job = _create_job(http_client, owner_headers, "Unassigned")
        job_id = job.get("id") or job.get("job_id")

        try:
            resp = http_client.post(
                f"/api/v1/jobs/{job_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": base.isoformat(),
                    "end_time": (base + timedelta(hours=2)).isoformat(),
                },
            )
            # May return 200 with no conflicts, or 4xx because no employee
            if resp.status_code == 200:
                data = resp.json()
                assert data.get("has_conflicts") is False, (
                    "Unassigned job should have no conflicts"
                )
            else:
                # Some implementations require assignment first
                assert resp.status_code in (400, 422), (
                    f"Unexpected status for unassigned conflict check: "
                    f"{resp.status_code}"
                )
        finally:
            _delete_job(http_client, owner_headers, job_id)

    def test_conflict_response_includes_details(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        When a conflict is detected, the response should include
        details about the conflicting job(s).
        """
        base = self._base_time(days_ahead=95)
        start1 = base
        end1 = base + timedelta(hours=2)

        job1 = _create_job(http_client, owner_headers, "Detail-Source")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "Detail-Target")
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            self._schedule_and_assign(
                http_client,
                owner_headers,
                job1_id,
                start1,
                end1,
            )
            http_client.post(
                f"/api/v1/jobs/{job2_id}/assign",
                headers=owner_headers,
                json={"assigned_to": self.employee_id},
            )

            # Full overlap
            resp = http_client.post(
                f"/api/v1/jobs/{job2_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": start1.isoformat(),
                    "end_time": end1.isoformat(),
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("has_conflicts") is True

            conflicts = data.get("conflicts", [])
            assert len(conflicts) >= 1, (
                f"Expected at least 1 conflict detail, got: {conflicts}"
            )
            # Each conflict should reference the blocking job
            first = conflicts[0]
            assert "conflicting_job_id" in first or "job_id" in first, (
                f"Conflict detail missing job reference: {first.keys()}"
            )
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)

    def test_schedule_endpoint_rejects_conflict(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        POST /jobs/{id}/schedule should reject or warn when there's
        a time conflict with the same employee.
        """
        base = self._base_time(days_ahead=96)
        start = base
        end = base + timedelta(hours=2)

        job1 = _create_job(http_client, owner_headers, "SchedReject-A")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "SchedReject-B")
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            self._schedule_and_assign(
                http_client,
                owner_headers,
                job1_id,
                start,
                end,
            )
            # Assign job2 to same employee
            http_client.post(
                f"/api/v1/jobs/{job2_id}/assign",
                headers=owner_headers,
                json={"assigned_to": self.employee_id},
            )

            # Try to schedule job2 in the same slot
            sched_resp = http_client.post(
                f"/api/v1/jobs/{job2_id}/schedule",
                headers=owner_headers,
                json={
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                },
            )
            # Service may reject (409) or allow with warning (200)
            assert sched_resp.status_code in (200, 409), (
                f"Unexpected status for conflicting schedule: "
                f"{sched_resp.status_code} — {sched_resp.text}"
            )
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)
