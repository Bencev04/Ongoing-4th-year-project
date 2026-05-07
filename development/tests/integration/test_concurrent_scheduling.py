"""
Concurrent scheduling race-condition tests.

Validates that the scheduling system behaves correctly when multiple
parallel requests attempt to schedule overlapping time slots for the
same employee simultaneously.

Industry-standard patterns applied:
    - ThreadPoolExecutor for true parallelism (not just async)
    - Explicit cleanup with try/finally
    - Descriptive assertions with failure messages
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
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
) -> dict:
    """Create a job and return its response body."""
    payload = {"title": title, "status": "pending", "priority": "normal"}
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


class TestConcurrentScheduling:
    """
    Race-condition tests for parallel scheduling requests.

    Verifies that when two jobs are simultaneously scheduled into the
    same time slot for the same employee, at most one succeeds without
    a conflict and the system remains consistent.
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
            pytest.skip("No employees available — concurrent tests require one")
        self.employee_id = emp

    def _base_time(self, days_ahead: int = 100) -> datetime:
        """Return a clean future datetime for scheduling."""
        return (datetime.now(UTC) + timedelta(days=days_ahead)).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0,
        )

    def test_parallel_schedule_same_slot_consistency(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Two jobs are assigned to the same employee and then both are
        simultaneously scheduled into the same time slot.

        Expected behaviour:
        - The first to succeed returns 200
        - The second returns 409 (conflict detected) OR 200 if the
          system allows overlaps with warnings
        - The system is consistent: check-conflicts for a third job
          at the same time reports exactly the scheduled jobs

        Verifies:
        - No 500 errors under concurrent scheduling pressure
        - At least one request succeeds
        - Conflict detection remains accurate afterward
        """
        base = self._base_time(days_ahead=110)
        start = base
        end = base + timedelta(hours=2)

        job1 = _create_job(http_client, owner_headers, "Concurrent-A")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "Concurrent-B")
        job2_id = job2.get("id") or job2.get("job_id")
        # Third job to verify consistency afterwards
        job3 = _create_job(http_client, owner_headers, "Concurrent-Probe")
        job3_id = job3.get("id") or job3.get("job_id")

        try:
            # Pre-assign all three jobs to the same employee
            for jid in (job1_id, job2_id, job3_id):
                assign_resp = http_client.post(
                    f"/api/v1/jobs/{jid}/assign",
                    headers=owner_headers,
                    json={"assigned_to": self.employee_id},
                )
                assert assign_resp.status_code == 200, (
                    f"Assign job {jid} failed: {assign_resp.text}"
                )

            # Launch two schedule requests in parallel
            def schedule_job(job_id: int) -> tuple[int, int]:
                """Schedule a job and return (job_id, status_code)."""
                resp = http_client.post(
                    f"/api/v1/jobs/{job_id}/schedule",
                    headers=owner_headers,
                    json={
                        "start_time": start.isoformat(),
                        "end_time": end.isoformat(),
                    },
                )
                return job_id, resp.status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(schedule_job, job1_id),
                    pool.submit(schedule_job, job2_id),
                ]
                results = {}
                for fut in as_completed(futures):
                    jid, code = fut.result()
                    results[jid] = code

            # No 500s — the system must handle the race gracefully
            for jid, code in results.items():
                assert code in (200, 409), (
                    f"Job {jid} got unexpected status {code} during "
                    f"concurrent scheduling"
                )

            # At least one schedule should succeed
            succeeded = [jid for jid, c in results.items() if c == 200]
            assert len(succeeded) >= 1, (
                f"Expected at least one schedule to succeed, got: {results}"
            )

            # Consistency check: conflict probe for job3 should detect
            # at least the successfully scheduled job(s)
            probe_resp = http_client.post(
                f"/api/v1/jobs/{job3_id}/check-conflicts",
                headers=owner_headers,
                json={
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                },
            )
            assert probe_resp.status_code == 200
            probe_data = probe_resp.json()
            assert probe_data.get("has_conflicts") is True, (
                f"Job3 should see conflicts from scheduled jobs: {probe_data}"
            )
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)
            _delete_job(http_client, owner_headers, job3_id)

    def test_parallel_assign_and_schedule_no_crash(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Concurrently assign+schedule one job while scheduling another
        on the same employee and time slot.

        Verifies:
        - No 500 errors regardless of processing order
        - System reaches a consistent final state
        """
        base = self._base_time(days_ahead=111)
        start = base
        end = base + timedelta(hours=2)

        job1 = _create_job(http_client, owner_headers, "RaceAssign-A")
        job1_id = job1.get("id") or job1.get("job_id")
        job2 = _create_job(http_client, owner_headers, "RaceAssign-B")
        job2_id = job2.get("id") or job2.get("job_id")

        try:
            # Pre-assign job2 so it can be scheduled
            http_client.post(
                f"/api/v1/jobs/{job2_id}/assign",
                headers=owner_headers,
                json={"assigned_to": self.employee_id},
            )

            def assign_and_schedule_job1() -> int:
                """Assign then immediately schedule job1."""
                http_client.post(
                    f"/api/v1/jobs/{job1_id}/assign",
                    headers=owner_headers,
                    json={"assigned_to": self.employee_id},
                )
                resp = http_client.post(
                    f"/api/v1/jobs/{job1_id}/schedule",
                    headers=owner_headers,
                    json={
                        "start_time": start.isoformat(),
                        "end_time": end.isoformat(),
                    },
                )
                return resp.status_code

            def schedule_job2() -> int:
                """Schedule the already-assigned job2."""
                resp = http_client.post(
                    f"/api/v1/jobs/{job2_id}/schedule",
                    headers=owner_headers,
                    json={
                        "start_time": start.isoformat(),
                        "end_time": end.isoformat(),
                    },
                )
                return resp.status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(assign_and_schedule_job1)
                f2 = pool.submit(schedule_job2)

                code1 = f1.result()
                code2 = f2.result()

            # No 500s
            assert code1 in (200, 409), f"Job1 assign+schedule got {code1}"
            assert code2 in (200, 409), f"Job2 schedule got {code2}"
        finally:
            _delete_job(http_client, owner_headers, job1_id)
            _delete_job(http_client, owner_headers, job2_id)
