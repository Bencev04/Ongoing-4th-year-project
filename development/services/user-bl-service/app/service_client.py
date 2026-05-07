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
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, status

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from common.config import settings
from common.redis import cache_delete, cache_delete_pattern, cache_get, cache_set

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
_CK_PERMS = "user:bl:perms"


# ==============================================================================
# Helpers
# ==============================================================================


async def _handle_response(response: httpx.Response) -> dict:
    """
    Raise an appropriate HTTPException if the downstream service
    returned an error, otherwise return the parsed JSON body.
    """
    if response.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found"
        )
    if response.status_code == 409:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=response.json().get("detail", "Conflict"),
        )
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
    owner_id: int | None = None,
    is_active: bool | None = None,
    role: str | None = None,
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
    search: str | None = None,
) -> dict:
    """Fetch employees belonging to an owner (cached)."""
    cache_key = f"{_CK_EMPLOYEES}:{owner_id}:{skip}:{limit}:{search}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        params: dict[str, Any] = {"skip": skip, "limit": limit}
        if search:
            params["search"] = search
        resp = await _client.get(
            f"{_API}/users/{owner_id}/employees",
            params=params,
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
        await cache_delete(f"{_CK_EMPLOYEES}:single:{employee_id}")
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


# ==============================================================================
# Organization Operations
# ==============================================================================


async def get_organization(org_id: int) -> dict:
    """Fetch a single organization by ID."""
    try:
        resp = await _client.get(f"{_API}/organizations/{org_id}")
        return await _handle_response(resp)
    except httpx.ConnectError:
        raise _service_unavailable()


async def update_organization(org_id: int, payload: dict) -> dict:
    """Update an organization's fields."""
    try:
        resp = await _client.put(f"{_API}/organizations/{org_id}", json=payload)
        return await _handle_response(resp)
    except httpx.ConnectError:
        raise _service_unavailable()


# ==============================================================================
# Permission Operations
# ==============================================================================


async def get_permission_catalog() -> dict:
    """Fetch the full permission catalog with per-role defaults."""
    try:
        resp = await _client.get(f"{_API}/permissions/catalog")
        return await _handle_response(resp)
    except httpx.ConnectError:
        raise _service_unavailable()


async def get_user_permissions(owner_id: int, user_id: int) -> dict:
    """Fetch all permission grants for a user within a tenant (cached)."""
    cache_key = f"{_CK_PERMS}:{owner_id}:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _client.get(f"{_API}/permissions/{owner_id}/{user_id}")
        data = await _handle_response(resp)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def update_user_permissions(
    owner_id: int, user_id: int, permissions: dict[str, bool]
) -> dict:
    """Bulk upsert permission grants for a user and invalidate cache."""
    try:
        resp = await _client.put(
            f"{_API}/permissions/{owner_id}/{user_id}",
            json={"permissions": permissions},
        )
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_PERMS}:{owner_id}:{user_id}")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def seed_user_permissions(owner_id: int, user_id: int, role: str) -> dict:
    """Seed default permissions for a newly created user."""
    try:
        resp = await _client.post(
            f"{_API}/permissions/{owner_id}/{user_id}/seed",
            params={"role": role},
        )
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_PERMS}:{owner_id}:{user_id}")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def get_audit_logs(
    *,
    organization_id: int,
    page: int = 1,
    per_page: int = 100,
    actor_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Fetch tenant-scoped audit log entries from the DB-access layer."""
    params: dict[str, Any] = {
        "page": page,
        "per_page": per_page,
        "organization_id": organization_id,
    }
    if actor_id is not None:
        params["actor_id"] = actor_id
    if action is not None:
        params["action"] = action
    if resource_type is not None:
        params["resource_type"] = resource_type
    if search is not None:
        params["search"] = search
    if date_from is not None:
        params["date_from"] = date_from
    if date_to is not None:
        params["date_to"] = date_to

    try:
        resp = await _client.get(f"{_API}/audit-logs", params=params)
        return await _handle_response(resp)
    except httpx.ConnectError:
        raise _service_unavailable()


# ==============================================================================
# GDPR Operations (Data Export & Anonymization)
# ==============================================================================


async def export_user_data(user_id: int) -> dict:
    """Export all personal data for a user (GDPR right of access)."""
    try:
        resp = await _client.get(f"{_API}/users/{user_id}/export")
        return await _handle_response(resp)
    except httpx.ConnectError:
        raise _service_unavailable()


async def anonymize_user(user_id: int) -> dict:
    """Immediately anonymize a user's personal data (GDPR right to erasure)."""
    try:
        resp = await _client.post(f"{_API}/users/{user_id}/anonymize")
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_USER}:{user_id}")
        await cache_delete_pattern(f"{_CK_USERS}:*")
        await cache_delete_pattern(f"{_CK_EMPLOYEES}:*")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def schedule_user_anonymization(user_id: int) -> dict:
    """Schedule user anonymization with a 72-hour grace period."""
    try:
        resp = await _client.post(f"{_API}/users/{user_id}/anonymize/schedule")
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_USER}:{user_id}")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()


async def cancel_user_anonymization(user_id: int) -> dict:
    """Cancel a pending anonymization request."""
    try:
        resp = await _client.post(f"{_API}/users/{user_id}/anonymize/cancel")
        data = await _handle_response(resp)
        await cache_delete(f"{_CK_USER}:{user_id}")
        return data
    except httpx.ConnectError:
        raise _service_unavailable()
