"""Internal HTTP client for frontend → backend service calls.

Provides async helpers that the calendar route handlers use to fetch
job data from **job-bl-service** for server-side rendering.  Auth
tokens are forwarded from the original browser request so that
tenant isolation is enforced end-to-end.

The module-level ``_http_client`` is shared across calls for
connection-pooling.  It is deliberately *not* closed on shutdown —
``httpx.AsyncClient`` handles this gracefully.

Usage
-----
::

    from app.service_client import fetch_calendar_events

    events = await fetch_calendar_events(request, start, end)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx
from fastapi import Request

from common.config import settings

logger = logging.getLogger(__name__)

# Shared async HTTP client — connection-pooled, 10-second timeout.
_http_client = httpx.AsyncClient(timeout=10.0)

# Cookie names — must match ``api_proxy.py``.
_ACCESS_COOKIE = "wp_access_token"
_REFRESH_COOKIE = "wp_refresh_token"


def _auth_headers(request: Request) -> dict[str, str]:
    """Extract the ``Authorization`` header from the incoming request.

    Args:
        request: The original browser request forwarded by FastAPI.

    Returns:
        A dict containing the ``Authorization`` header if present,
        otherwise an empty dict.
    """
    auth: str | None = request.headers.get("authorization")
    if auth:
        return {"Authorization": auth}

    access_token: str | None = request.cookies.get(_ACCESS_COOKIE)
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}

    return {}


async def _ensure_auth(request: Request) -> dict[str, str]:
    """Return auth headers, performing a server-side token refresh if needed.

    When the access-token cookie has expired but the longer-lived
    refresh-token cookie is still present, this helper calls the
    auth-service ``/refresh`` endpoint to obtain a new access token.
    The refreshed token is stashed on ``request.state`` so that the
    calling route handler can set it as a cookie on the outgoing
    response (see :func:`propagate_refreshed_cookie`).

    Within a single request cycle the refresh is attempted at most
    once; concurrent calls (e.g. via ``asyncio.gather``) reuse the
    cached result.

    Args:
        request: The original browser request forwarded by FastAPI.

    Returns:
        A dict with the ``Authorization`` header, or ``{}`` if
        authentication is unavailable.
    """
    # Fast path — token already present.
    headers = _auth_headers(request)
    if headers:
        return headers

    # Re-use a token that was already refreshed earlier in this request.
    refreshed: str | None = getattr(request.state, "refreshed_access_token", None)
    if refreshed:
        return {"Authorization": f"Bearer {refreshed}"}

    # Only attempt once per request.
    if getattr(request.state, "_refresh_attempted", False):
        return {}
    request.state._refresh_attempted = True

    refresh_token: str | None = request.cookies.get(_REFRESH_COOKIE)
    if not refresh_token:
        return {}

    try:
        resp = await _http_client.post(
            f"{settings.auth_service_url}/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            new_token: str | None = data.get("access_token")
            new_refresh: str | None = data.get("refresh_token")
            if new_token:
                request.state.refreshed_access_token = new_token
                # Stash rotated refresh token so the middleware can
                # set it as a cookie on the outgoing response.
                if new_refresh:
                    request.state.refreshed_refresh_token = new_refresh
                logger.info("Server-side token refresh succeeded")
                return {"Authorization": f"Bearer {new_token}"}
        logger.warning("Server-side token refresh returned %s", resp.status_code)
    except httpx.RequestError as exc:
        logger.warning("Server-side token refresh failed: %s", exc)

    return {}


def propagate_refreshed_cookie(
    request: Request,
    response: Any,
    *,
    max_age: int = 30 * 60,
) -> None:
    """Set the refreshed access-token cookie on *response* if one exists.

    Call this in any route handler that uses :func:`_ensure_auth` so
    the browser receives the renewed cookie and subsequent requests
    (including HTMX calls) carry a valid token.

    Args:
        request:  The incoming request (checked for ``state``).
        response: A Starlette/FastAPI ``Response`` object.
        max_age:  Cookie lifetime in seconds (default 30 min).
    """
    new_token: str | None = getattr(request.state, "refreshed_access_token", None)
    if not new_token:
        return

    # Determine the Secure flag the same way api_proxy does.
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_secure = (
        forwarded_proto.lower() == "https"
        if forwarded_proto
        else request.url.scheme == "https"
    )

    response.set_cookie(
        key=_ACCESS_COOKIE,
        value=new_token,
        max_age=max_age,
        httponly=True,
        secure=is_secure,
        samesite="lax",
        path="/",
    )

    # Also propagate the rotated refresh token when available.
    new_refresh: str | None = getattr(request.state, "refreshed_refresh_token", None)
    if new_refresh:
        response.set_cookie(
            key=_REFRESH_COOKIE,
            value=new_refresh,
            max_age=7 * 24 * 60 * 60,  # 7 days
            httponly=True,
            secure=is_secure,
            samesite="lax",
            path="/",
        )


async def get_current_user(request: Request) -> dict[str, Any] | None:
    """Fetch the current user's context from auth-service.

    Calls ``GET /api/v1/auth/me`` using the access token from
    the request (refreshing it if necessary).  Returns the user
    context dict (including ``role``, ``owner_id``, etc.) or
    ``None`` if the user is unauthenticated.

    Args:
        request: The incoming HTTP request.

    Returns:
        User context dict on success, ``None`` otherwise.
    """
    headers = await _ensure_auth(request)
    if not headers:
        return None

    try:
        resp = await _http_client.get(
            f"{settings.auth_service_url}/api/v1/auth/me",
            headers=headers,
        )
        if resp.status_code == 200:
            return resp.json()  # type: ignore[no-any-return]
        logger.warning("auth-service /me returned %s", resp.status_code)
    except httpx.RequestError as exc:
        logger.warning("Failed to reach auth-service /me: %s", exc)

    return None


async def fetch_calendar_events(
    request: Request,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch calendar events from job-bl-service for a date range.

    Calls ``GET /api/v1/jobs/calendar?start_date=...&end_date=...``
    and returns the list of ``CalendarDayResponse`` dicts (one per day
    in the range, each containing a ``jobs`` list).

    On any error (network, auth, timeout) an empty list is returned
    so the calendar page degrades gracefully rather than crashing.

    Args:
        request:    Original browser request (used to forward auth).
        start_date: First date of the range (inclusive).
        end_date:   Last date of the range (inclusive).

    Returns:
        A list of day-dicts, each shaped like::

            {"date": "2026-03-01", "jobs": [...], "total_jobs": 2}
    """
    try:
        response = await _http_client.get(
            f"{settings.job_bl_service_url}/api/v1/jobs/calendar",
            params={
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            headers=await _ensure_auth(request),
        )
        if response.status_code == 200:
            return response.json()  # type: ignore[no-any-return]

        logger.warning(
            "job-bl-service /calendar returned %s: %s",
            response.status_code,
            response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to reach job-bl-service: %s", exc)

    return []


async def fetch_day_events(
    request: Request,
    target_date: date,
) -> list[dict[str, Any]]:
    """Fetch events for a single day from job-bl-service.

    Queries a 1-day range and collects all unique jobs whose
    start/end date range overlaps the target day.  This mirrors
    the robust approach used by the week view (parsing job
    timestamps) rather than relying on exact date-field matching.

    Args:
        request:     Original browser request (auth forwarding).
        target_date: The date to query.

    Returns:
        A list of job dicts for the given day (may be empty).
    """
    days = await fetch_calendar_events(request, target_date, target_date)

    # Collect all unique jobs across the API response.
    seen_ids: set[int] = set()
    result: list[dict[str, Any]] = []
    for day_data in days:
        for job in day_data.get("jobs", []):
            job_id = job.get("id")
            if job_id is not None and job_id not in seen_ids:
                seen_ids.add(job_id)
                result.append(job)

    return result


async def fetch_unscheduled_jobs(
    request: Request,
) -> list[dict[str, Any]]:
    """Fetch unscheduled jobs from the job queue.

    Calls ``GET /api/v1/jobs/queue`` and returns the ``items`` list.
    Returns an empty list on failure.

    Args:
        request: Original browser request (auth forwarding).

    Returns:
        A list of unscheduled job dicts.
    """
    try:
        response = await _http_client.get(
            f"{settings.job_bl_service_url}/api/v1/jobs/queue",
            headers=await _ensure_auth(request),
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("items", [])  # type: ignore[no-any-return]

        logger.warning(
            "job-bl-service /queue returned %s: %s",
            response.status_code,
            response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to reach job-bl-service (queue): %s", exc)

    return []


async def fetch_job_detail(
    request: Request,
    job_id: int,
) -> dict[str, Any] | None:
    """Fetch a single job by ID from job-bl-service.

    Used by the job-edit modal to pre-populate form fields.

    Args:
        request: Original browser request (auth forwarding).
        job_id:  The ID of the job to retrieve.

    Returns:
        A job dict if found, or ``None`` on error / 404.
    """
    try:
        response = await _http_client.get(
            f"{settings.job_bl_service_url}/api/v1/jobs/{job_id}",
            headers=await _ensure_auth(request),
        )
        if response.status_code == 200:
            return response.json()  # type: ignore[no-any-return]

        logger.warning(
            "job-bl-service /jobs/%s returned %s: %s",
            job_id,
            response.status_code,
            response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to fetch job %s: %s", job_id, exc)

    return None


async def fetch_employees(
    request: Request,
) -> list[dict[str, Any]]:
    """Fetch employees from user-bl-service for the current tenant.

    Calls ``GET /api/v1/employees`` and returns the list of employee
    dicts.  Returns an empty list on failure so the job modal still
    renders (the dropdown will simply be empty).

    Args:
        request: Original browser request (auth forwarding).

    Returns:
        A list of employee dicts, each containing at least ``id``,
        ``first_name``, and ``last_name``.
    """
    try:
        response = await _http_client.get(
            f"{settings.user_bl_service_url}/api/v1/employees",
            headers=await _ensure_auth(request),
        )
        if response.status_code == 200:
            data = response.json()
            # user-bl-service may return a paginated envelope or plain list.
            if isinstance(data, list):
                return data  # type: ignore[return-value]
            return data.get("items", data.get("employees", []))  # type: ignore[return-value]

        logger.warning(
            "user-bl-service /employees returned %s: %s",
            response.status_code,
            response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to reach user-bl-service (employees): %s", exc)

    return []


async def fetch_company(
    request: Request,
) -> dict[str, Any] | None:
    """Fetch the company profile from user-bl-service.

    Calls ``GET /api/v1/company`` and returns the company dict
    (includes ``address``, ``eircode``, etc.).  Returns ``None`` on
    failure so callers can degrade gracefully.
    """
    try:
        response = await _http_client.get(
            f"{settings.user_bl_service_url}/api/v1/company",
            headers=await _ensure_auth(request),
        )
        if response.status_code == 200:
            return response.json()  # type: ignore[return-value]

        logger.warning(
            "user-bl-service /company returned %s: %s",
            response.status_code,
            response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to reach user-bl-service (company): %s", exc)

    return None


async def fetch_customers(
    request: Request,
) -> list[dict[str, Any]]:
    """Fetch customers from customer-bl-service for the current tenant.

    Calls ``GET /api/v1/customers`` and returns the list of customer
    dicts.  Returns an empty list on failure so the job modal still
    renders (the dropdown will simply be empty).

    Args:
        request: Original browser request (auth forwarding).

    Returns:
        A list of customer dicts, each containing at least ``id``
        and ``name``.
    """
    try:
        response = await _http_client.get(
            f"{settings.customer_bl_service_url}/api/v1/customers",
            headers=await _ensure_auth(request),
        )
        if response.status_code == 200:
            data = response.json()
            # customer-bl-service may return a paginated envelope or plain list.
            if isinstance(data, list):
                return data  # type: ignore[return-value]
            return data.get("items", data.get("customers", []))  # type: ignore[return-value]

        logger.warning(
            "customer-bl-service /customers returned %s: %s",
            response.status_code,
            response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.warning("Failed to reach customer-bl-service (customers): %s", exc)

    return []
