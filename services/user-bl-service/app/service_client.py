"""
Service client for communicating with user-db-access-service.

Encapsulates all HTTP calls to the DB-access layer so that
route handlers stay clean and testable.  Every function accepts
explicit parameters rather than raw ``Request`` objects.

GET operations are **Redis-cached** with configurable TTLs to
reduce latency and load on the DB-access layer.  Mutations
(POST / PUT / DELETE) automatically invalidate the relevant
cache entries.
"""

import logging
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

import sys
sys.path.append("../../shared")
from common.config import settings
from common.redis import cache_get, cache_set, cache_delete, cache_delete_pattern

logger = logging.getLogger(__name__)

# Shared async HTTP client (connection pooling)
_client = httpx.AsyncClient(
    base_url=settings.user_service_url,
    timeout=10.0,
)

# Base path on user-db-access-service
_API = "/api/v1"

# Cache key prefixes
_CK_USER = "user:bl:user"
_CK_USERS = "user:bl:users"
_CK_EMPLOYEES = "user:bl:employees"
_CK_COMPANY = "user:bl:company"


# ==============================================================================
# Helpers
# ==============================================================================

async def _handle_response(response: httpx.Response) -> dict:
    """
    Raise an appropriate HTTPException if the downstream service
    returned an error, otherwise return the parsed JSON body.
    """
    if response.status_code == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if response.status_code == 409:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=response.json().get("detail", "Conflict"))
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def _service_unavailable() -> HTTPException:
    """Reusable 503 exception."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="User DB Access Service is unavailable",
    )


# ==============================================================================
# User Operations
# ==============================================================================

async def get_users(
    *,
    skip: int = 0,
    limit: int = 100,
    owner_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    role: Optional[str] = None,
) -> dict:
    """
    Fetch a paginated list of users from the DB-access layer.

    Results are cached with a short TTL since user lists may change
    frequently.

    Returns:
        The raw JSON response as a dict (matches UserListResponse).
    """
    cache_key = f"{_CK_USERS}:{skip}:{limit}:{owner_id}:{is_active}:{role}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {"skip": skip, "limit": limit}
    if owner_id is not None:
        params["owner_id"] = owner_id
    if is_active is not None:
        params["is_active"] = is_active
    if role is not None:
        params["role"] = role

    try:
        resp = await _client.get(f"{_API}/users", params=params)
        data = await _handle_response(resp)
        await cache_set(cache_key, data, settings.cache_ttl_short)
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def get_user(user_id: int) -> dict:
    """Fetch a single user by ID (cached)."""
    cache_key = f"{_CK_USER}:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _client.get(f"{_API}/users/{user_id}")
        data = await _handle_response(resp)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def create_user(payload: dict) -> dict:
    """Create a new user via the DB-access layer and invalidate cache."""
    try:
        resp = await _client.post(f"{_API}/users", json=payload)
        data = await _handle_response(resp)
        await cache_delete_pattern(f"{_CK_USERS}:*")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def update_user(user_id: int, payload: dict) -> dict:
    """Update a user's fields and invalidate cache."""
    try:
        resp = await _client.put(f"{_API}/users/{user_id}", json=payload)
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_USER}:{user_id}")
        await cache_delete_pattern(f"{_CK_USERS}:*")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def delete_user(user_id: int) -> None:
    """Delete (deactivate) a user and invalidate cache."""
    try:
        resp = await _client.delete(f"{_API}/users/{user_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="User not found")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        await cache_delete(f"{_CK_USER}:{user_id}")
        await cache_delete_pattern(f"{_CK_USERS}:*")
    except httpx.ConnectError:
        raise _service_unavailable()


# ==============================================================================
# Employee Operations
# ==============================================================================

async def get_employees_by_owner(
    owner_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[dict]:
    """Fetch employees belonging to an owner (cached)."""
    cache_key = f"{_CK_EMPLOYEES}:{owner_id}:{skip}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _client.get(
            f"{_API}/users/{owner_id}/employees",
            params={"skip": skip, "limit": limit},
        )
        data = await _handle_response(resp)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def create_employee(payload: dict) -> dict:
    """Create employee details and invalidate cache."""
    try:
        resp = await _client.post(f"{_API}/employees", json=payload)
        data = await _handle_response(resp)
        await cache_delete_pattern(f"{_CK_EMPLOYEES}:*")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def update_employee(employee_id: int, payload: dict) -> dict:
    """Update employee details and invalidate cache."""
    try:
        resp = await _client.put(f"{_API}/employees/{employee_id}", json=payload)
        data = await _handle_response(resp)
        await cache_delete_pattern(f"{_CK_EMPLOYEES}:*")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def get_employee(employee_id: int) -> dict:
    """Fetch a single employee by ID (cached)."""
    cache_key = f"{_CK_EMPLOYEES}:single:{employee_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _client.get(f"{_API}/employees/{employee_id}")
        data = await _handle_response(resp)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


# ==============================================================================
# Company Operations
# ==============================================================================

async def get_company(company_id: int) -> dict:
    """Fetch a single company by ID (cached)."""
    cache_key = f"{_CK_COMPANY}:{company_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _client.get(f"{_API}/companies/{company_id}")
        data = await _handle_response(resp)
        await cache_set(cache_key, data, settings.cache_ttl_long)
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def update_company(company_id: int, payload: dict) -> dict:
    """Update a company's fields and invalidate cache."""
    try:
        resp = await _client.put(f"{_API}/companies/{company_id}", json=payload)
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_COMPANY}:{company_id}")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()
