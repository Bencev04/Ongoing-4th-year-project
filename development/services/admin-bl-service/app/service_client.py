"""
HTTP service client for Admin BL Service.

Encapsulates all outbound HTTP calls to ``user-db-access-service``
for organization CRUD, user lookups, audit log queries, and
platform settings management.

Architecture
------------
The admin BL service **never** touches the database directly.
All data operations are delegated to DB-access services via HTTP.
This file is the single point of integration.

Error Handling
--------------
Every function raises ``HTTPException`` on failure so that callers
(route handlers) can propagate structured errors to the client.
"""

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from common.config import settings

logger = logging.getLogger(__name__)

# Shared async HTTP client (closed in app lifespan shutdown)
_http_client = httpx.AsyncClient(timeout=10.0)


def _safe_detail(resp: httpx.Response, fallback: str) -> str:
    """Extract error detail from response body, or return *fallback*."""
    try:
        return resp.json().get("detail", fallback)
    except Exception:
        return f"{fallback} (HTTP {resp.status_code})"


# ==============================================================================
# Organization Operations
# ==============================================================================


async def list_organizations(
    page: int = 1,
    per_page: int = 50,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """
    List all organizations with optional filtering.

    Args:
        page:      Page number (1-based).
        per_page:  Items per page.
        is_active: Filter by active status.

    Returns:
        Dictionary with ``items``, ``total``, ``page``, ``per_page``, ``pages``.

    Raises:
        HTTPException 503: If user-db-access-service is unreachable.
    """
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if is_active is not None:
        params["is_active"] = is_active

    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/organizations",
            params=params,
        )
    except httpx.RequestError:
        logger.error("User DB service unreachable for organization listing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code != 200:
        logger.warning("Organization list returned status %d", resp.status_code)
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to list organizations"),
        )

    return resp.json()


async def get_organization(org_id: int) -> dict[str, Any]:
    """
    Fetch a single organization by ID.

    Args:
        org_id: Organization primary key.

    Returns:
        Organization data dictionary.

    Raises:
        HTTPException 404: If organization not found.
        HTTPException 503: If user-db-access-service is unreachable.
    """
    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/organizations/{org_id}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to fetch organization"),
        )

    return resp.json()


async def create_organization(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Create a new organization.

    Args:
        payload: Organization creation data.

    Returns:
        Created organization data.

    Raises:
        HTTPException 409: If slug already exists.
        HTTPException 503: If service is unreachable.
    """
    try:
        resp = await _http_client.post(
            f"{settings.user_service_url}/api/v1/organizations",
            json=payload,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 409:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization with this slug already exists",
        )

    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to create organization"),
        )

    return resp.json()


async def delete_organization(org_id: int) -> None:
    """
    Delete an organization by ID.

    Args:
        org_id: Organization primary key.

    Raises:
        HTTPException 404: If organization not found.
        HTTPException 503: If service is unreachable.
    """
    try:
        resp = await _http_client.delete(
            f"{settings.user_service_url}/api/v1/organizations/{org_id}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )

    if resp.status_code not in (200, 204):
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to delete organization"),
        )


async def update_organization(org_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing organization.

    Args:
        org_id:  Organization primary key.
        payload: Fields to update.

    Returns:
        Updated organization data.

    Raises:
        HTTPException 404: If organization not found.
        HTTPException 503: If service is unreachable.
    """
    try:
        resp = await _http_client.put(
            f"{settings.user_service_url}/api/v1/organizations/{org_id}",
            json=payload,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Organization {org_id} not found",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to update organization"),
        )

    return resp.json()


# ==============================================================================
# Audit Log Operations
# ==============================================================================


async def list_audit_logs(
    page: int = 1,
    per_page: int = 50,
    organization_id: int | None = None,
    actor_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
) -> dict[str, Any]:
    """
    Query the audit log with optional filters.

    Args:
        page:            Page number (1-based).
        per_page:        Items per page.
        organization_id: Filter by organization.
        actor_id:        Filter by acting user.
        action:          Filter by action string (e.g. ``"user.create"``).
        resource_type:   Filter by resource type (e.g. ``"user"``).

    Returns:
        Paginated audit log data.

    Raises:
        HTTPException 503: If service is unreachable.
    """
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if organization_id is not None:
        params["organization_id"] = organization_id
    if actor_id is not None:
        params["actor_id"] = actor_id
    if action is not None:
        params["action"] = action
    if resource_type is not None:
        params["resource_type"] = resource_type

    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/audit-logs",
            params=params,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to fetch audit logs"),
        )

    return resp.json()


async def create_audit_log(entry: dict[str, Any]) -> dict[str, Any]:
    """
    Write an audit log entry.

    Args:
        entry: Audit log data (actor_id, action, resource_type, etc.).

    Returns:
        Created audit log entry.

    Raises:
        HTTPException 503: If service is unreachable.
    """
    try:
        resp = await _http_client.post(
            f"{settings.user_service_url}/api/v1/audit-logs",
            json=entry,
        )
    except httpx.RequestError:
        # Fire-and-forget — audit failures must not block the operation
        logger.warning("Failed to write audit log — service unreachable")
        return {}

    if resp.status_code not in (200, 201):
        logger.warning("Audit log write failed with status %d", resp.status_code)
        # Audit log failures should not block the operation — log and continue
        return {}

    return resp.json()


# ==============================================================================
# Platform Settings Operations
# ==============================================================================


async def list_platform_settings() -> list[dict[str, Any]]:
    """
    Retrieve all platform settings.

    Returns:
        List of platform setting dictionaries.

    Raises:
        HTTPException 503: If service is unreachable.
    """
    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/platform-settings",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail="Failed to fetch platform settings",
        )

    data = resp.json()
    return data.get("items", [])


async def get_platform_setting(key: str) -> dict[str, Any]:
    """
    Retrieve a single platform setting by key.

    Args:
        key: Setting key (e.g. ``"maintenance_mode"``).

    Returns:
        Setting data dictionary.

    Raises:
        HTTPException 404: If key does not exist.
    """
    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/platform-settings/{key}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail="Failed to fetch platform setting",
        )

    return resp.json()


async def update_platform_setting(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Update a platform setting value.

    Args:
        key:     Setting key.
        payload: New value and optional description.

    Returns:
        Updated setting data.

    Raises:
        HTTPException 404: If key does not exist.
    """
    try:
        resp = await _http_client.put(
            f"{settings.user_service_url}/api/v1/platform-settings/{key}",
            json=payload,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail="Failed to update platform setting",
        )

    return resp.json()


# ==============================================================================
# Cross-Tenant User Operations
# ==============================================================================


async def list_all_users(
    page: int = 1,
    per_page: int = 50,
    organization_id: int | None = None,
    role: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """
    List users across all tenants (superadmin only).

    Args:
        page:            Page number (1-based).
        per_page:        Items per page.
        organization_id: Filter by organization.
        role:            Filter by role.
        is_active:       Filter by active status.

    Returns:
        Paginated user list.

    Raises:
        HTTPException 503: If service is unreachable.
    """
    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if organization_id is not None:
        params["organization_id"] = organization_id
    if role is not None:
        params["role"] = role
    if is_active is not None:
        params["is_active"] = is_active

    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/users",
            params=params,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail="Failed to list users",
        )

    return resp.json()


async def get_user(user_id: int) -> dict[str, Any]:
    """
    Fetch a single user by ID (cross-tenant).

    Args:
        user_id: User primary key.

    Returns:
        User data dictionary.

    Raises:
        HTTPException 404: If user not found.
    """
    try:
        resp = await _http_client.get(
            f"{settings.user_service_url}/api/v1/users/{user_id}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail="Failed to fetch user",
        )

    return resp.json()


async def update_user(user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Update a user (cross-tenant). Used for role changes by superadmin.

    Args:
        user_id: User primary key.
        payload: Fields to update (e.g. {"role": "admin"}).

    Returns:
        Updated user data dictionary.
    """
    try:
        resp = await _http_client.put(
            f"{settings.user_service_url}/api/v1/users/{user_id}",
            json=payload,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User DB service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=_safe_detail(resp, "Failed to update user"),
        )

    return resp.json()
