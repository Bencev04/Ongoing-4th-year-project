"""
Service clients for inter-service communication from the Job Service.

Encapsulates HTTP calls to:
- job-db-access-service  (persistence)
- customer-db-access-service  (customer lookups)
- user-db-access-service  (employee lookups)

GET operations are **Redis-cached** with configurable TTLs.
Mutations automatically invalidate the relevant cache entries.
"""

import logging
from typing import Any, Optional
from datetime import date

import httpx
from fastapi import HTTPException, status

import sys
sys.path.append("../../shared")
from common.config import settings
from common.redis import cache_get, cache_set, cache_delete, cache_delete_pattern

logger = logging.getLogger(__name__)

# Shared async HTTP clients
_job_client = httpx.AsyncClient(
    base_url=settings.job_service_url,
    timeout=10.0,
)

_customer_client = httpx.AsyncClient(
    base_url=settings.customer_service_url,
    timeout=10.0,
)

_user_client = httpx.AsyncClient(
    base_url=settings.user_service_url,
    timeout=10.0,
)

_API = "/api/v1"

# Cache key prefixes
_CK_JOB = "job:bl:job"
_CK_JOBS = "job:bl:jobs"
_CK_CALENDAR = "job:bl:calendar"
_CK_QUEUE = "job:bl:queue"
_CK_CUSTOMER = "job:bl:customer"
_CK_USER = "job:bl:user"


# ==============================================================================
# Helpers
# ==============================================================================

async def _handle(response: httpx.Response) -> dict | list:
    """Parse response or raise appropriate HTTPException."""
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Resource not found")
    if response.status_code == 409:
        raise HTTPException(status_code=409, detail=response.json().get("detail", "Conflict"))
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def _unavailable(service: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"{service} is unavailable",
    )


# ==============================================================================
# Field Translation (BL ↔ DB)
# ==============================================================================

# BL public name → DB internal name
_BL_TO_DB_FIELDS = {
    "assigned_to": "assigned_employee_id",
    "address": "location",
}

# DB internal name → BL public name
_DB_TO_BL_FIELDS = {v: k for k, v in _BL_TO_DB_FIELDS.items()}


def _to_db_payload(data: dict) -> dict:
    """
    Translate BL field names to DB field names before sending to job-db-access.

    Mapping:
        assigned_to  → assigned_employee_id
        address      → location
    """
    translated = {}
    for key, value in data.items():
        db_key = _BL_TO_DB_FIELDS.get(key, key)
        translated[db_key] = value
    return translated


def _from_db_response(data: dict) -> dict:
    """
    Translate DB field names to BL field names in responses.

    Mapping:
        assigned_employee_id → assigned_to
        location             → address
    """
    translated = {}
    for key, value in data.items():
        bl_key = _DB_TO_BL_FIELDS.get(key, key)
        translated[bl_key] = value
    return translated


def _from_db_response_list(data: list[dict]) -> list[dict]:
    """Translate a list of DB dicts to BL dicts."""
    return [_from_db_response(item) for item in data]


# ==============================================================================
# Job DB Access Service
# ==============================================================================

async def get_jobs(
    *,
    skip: int = 0,
    limit: int = 100,
    owner_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    assigned_to: Optional[int] = None,
    customer_id: Optional[int] = None,
) -> dict:
    """Fetch paginated jobs from job-db-access-service (cached)."""
    cache_key = (
        f"{_CK_JOBS}:{owner_id}:{skip}:{limit}"
        f":{status_filter}:{assigned_to}:{customer_id}"
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {"skip": skip, "limit": limit}
    if owner_id is not None:
        params["owner_id"] = owner_id
    if status_filter:
        params["status"] = status_filter
    if assigned_to is not None:
        params["employee_id"] = assigned_to
    if customer_id is not None:
        params["customer_id"] = customer_id

    try:
        resp = await _job_client.get(f"{_API}/jobs", params=params)
        data = await _handle(resp)
        # Translate DB field names → BL field names in response items
        if isinstance(data, dict) and "items" in data:
            data["items"] = _from_db_response_list(data["items"])
        await cache_set(cache_key, data, settings.cache_ttl_short)
        return data
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def get_job(job_id: int) -> dict:
    """Fetch a single job (cached)."""
    cache_key = f"{_CK_JOB}:{job_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _job_client.get(f"{_API}/jobs/{job_id}")
        data = await _handle(resp)
        data = _from_db_response(data)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def create_job(payload: dict) -> dict:
    """Create a new job and invalidate cache."""
    try:
        db_payload = _to_db_payload(payload)
        resp = await _job_client.post(f"{_API}/jobs", json=db_payload)
        data = await _handle(resp)
        data = _from_db_response(data)
        await cache_delete_pattern(f"{_CK_JOBS}:*")
        await cache_delete_pattern(f"{_CK_CALENDAR}:*")
        await cache_delete_pattern(f"{_CK_QUEUE}:*")
        return data
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def update_job(job_id: int, payload: dict, changed_by_id: int = None) -> dict:
    """Update a job and invalidate cache."""
    try:
        db_payload = _to_db_payload(payload)
        params = {}
        if changed_by_id is not None:
            params["changed_by_id"] = changed_by_id
        resp = await _job_client.put(
            f"{_API}/jobs/{job_id}", json=db_payload, params=params
        )
        data = await _handle(resp)
        data = _from_db_response(data)
        await cache_delete(f"{_CK_JOB}:{job_id}")
        await cache_delete_pattern(f"{_CK_JOBS}:*")
        await cache_delete_pattern(f"{_CK_CALENDAR}:*")
        await cache_delete_pattern(f"{_CK_QUEUE}:*")
        return data
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def delete_job(job_id: int) -> None:
    """Delete a job and invalidate cache."""
    try:
        resp = await _job_client.delete(f"{_API}/jobs/{job_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Job not found")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        await cache_delete(f"{_CK_JOB}:{job_id}")
        await cache_delete_pattern(f"{_CK_JOBS}:*")
        await cache_delete_pattern(f"{_CK_CALENDAR}:*")
        await cache_delete_pattern(f"{_CK_QUEUE}:*")
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def get_calendar_jobs(
    owner_id: Optional[int],
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Fetch jobs within a date range for the calendar view (cached)."""
    cache_key = f"{_CK_CALENDAR}:{owner_id}:{start_date}:{end_date}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if owner_id is not None:
        params["owner_id"] = owner_id

    try:
        resp = await _job_client.get(
            f"{_API}/jobs/calendar",
            params=params,
        )
        data = await _handle(resp)
        # Extract events from the CalendarViewResponse
        # DB service returns: {events: [...], start_date, end_date, total}
        events = data.get("events", []) if isinstance(data, dict) else data
        events = _from_db_response_list(events)
        await cache_set(cache_key, events, settings.cache_ttl_short)
        return events
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def get_unscheduled_jobs(owner_id: Optional[int]) -> list[dict]:
    """Fetch unscheduled jobs — the queue (cached)."""
    cache_key = f"{_CK_QUEUE}:{owner_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params = {}
    if owner_id is not None:
        params["owner_id"] = owner_id

    try:
        resp = await _job_client.get(
            f"{_API}/jobs/queue",
            params=params,
        )
        data = await _handle(resp)
        # Extract items from the JobQueueResponse
        # DB service returns: {items: [...], total}
        items = data.get("items", []) if isinstance(data, dict) else data
        items = _from_db_response_list(items)
        await cache_set(cache_key, items, settings.cache_ttl_short)
        return items
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


async def get_jobs_by_assignee_and_date(
    assigned_to: int,
    target_date: date,
    owner_id: Optional[int],
) -> list[dict]:
    """Fetch all jobs for a specific employee on a specific date (cached)."""
    cache_key = f"{_CK_JOBS}:assignee:{assigned_to}:{target_date}:{owner_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "employee_id": assigned_to,
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
    }
    if owner_id is not None:
        params["owner_id"] = owner_id

    try:
        resp = await _job_client.get(
            f"{_API}/jobs",
            params=params,
        )
        data = await _handle(resp)
        # Response might be paginated dict or a list
        items = data.get("items", []) if isinstance(data, dict) else data
        items = _from_db_response_list(items)
        await cache_set(cache_key, items, settings.cache_ttl_short)
        return items
    except httpx.ConnectError:
        raise _unavailable("Job DB Access Service")


# ==============================================================================
# Customer DB Access Service
# ==============================================================================

async def get_customer(customer_id: int) -> dict:
    """Fetch a customer from customer-db-access-service (cached)."""
    cache_key = f"{_CK_CUSTOMER}:{customer_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _customer_client.get(f"{_API}/customers/{customer_id}")
        data = await _handle(resp)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


# ==============================================================================
# User DB Access Service
# ==============================================================================

async def get_user(user_id: int) -> dict:
    """Fetch a user from user-db-access-service (cached)."""
    cache_key = f"{_CK_USER}:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _user_client.get(f"{_API}/users/{user_id}")
        data = await _handle(resp)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _unavailable("User DB Access Service")
