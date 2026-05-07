"""HTTP client for calling downstream services.

Communicates with job-bl-service, customer-bl-service, and admin-bl-service
to fetch jobs, customers, and platform settings.
"""

import logging
from typing import Any

import httpx

from common.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def init_http_client() -> None:
    global _client
    _client = httpx.AsyncClient(timeout=10.0)


async def close_http_client() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


def _get_client() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError(
            "HTTP client not initialised — call init_http_client() first"
        )
    return _client


# -- Job BL Service -----------------------------------------------------------


async def get_upcoming_jobs(
    token: str,
    hours_before: int,
    owner_id: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch jobs starting within the next ``hours_before`` hours."""
    client = _get_client()
    url = f"{settings.job_bl_service_url}/api/v1/jobs/calendar"
    params: dict[str, Any] = {"hours_before": hours_before}
    if owner_id:
        params["owner_id"] = owner_id
    try:
        resp = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("items", [])
            logger.warning("Unexpected response shape from %s: %s", url, type(data))
    except httpx.HTTPError:
        logger.exception("Failed to fetch upcoming jobs")
    return []


async def get_job(token: str, job_id: int) -> dict[str, Any] | None:
    """Fetch a single job by ID."""
    client = _get_client()
    url = f"{settings.job_bl_service_url}/api/v1/jobs/{job_id}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if not isinstance(data, dict):
                logger.warning("Expected dict for job %s, got %s", job_id, type(data))
                return None
            return data
    except httpx.HTTPError:
        logger.exception("Failed to fetch job %s", job_id)
    return None


# -- Customer BL Service ------------------------------------------------------


async def get_customer(token: str, customer_id: int) -> dict[str, Any] | None:
    """Fetch a single customer by ID."""
    client = _get_client()
    url = f"{settings.customer_bl_service_url}/api/v1/customers/{customer_id}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if not isinstance(data, dict):
                logger.warning(
                    "Expected dict for customer %s, got %s", customer_id, type(data)
                )
                return None
            return data
    except httpx.HTTPError:
        logger.exception("Failed to fetch customer %s", customer_id)
    return None


# -- Admin BL Service (platform settings) ------------------------------------


async def get_platform_setting(token: str, key: str) -> str | None:
    """Fetch a single platform setting value."""
    client = _get_client()
    url = f"{settings.admin_bl_service_url}/api/v1/admin/settings/{key}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if not isinstance(data, dict):
                logger.warning("Expected dict for setting %s, got %s", key, type(data))
                return None
            return data.get("value")
    except httpx.HTTPError:
        logger.exception("Failed to fetch platform setting %s", key)
    return None


async def get_platform_settings_bulk(token: str, prefix: str) -> dict[str, str]:
    """Fetch all platform settings matching a key prefix."""
    client = _get_client()
    url = f"{settings.admin_bl_service_url}/api/v1/admin/settings"
    try:
        resp = await client.get(
            url,
            params={"prefix": prefix},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            # Response may be {"items": [...], "total": N} or a plain list
            if isinstance(data, dict):
                items = data.get("items", [])
            elif isinstance(data, list):
                items = data
            else:
                logger.warning(
                    "Unexpected response shape for settings prefix %s: %s",
                    prefix,
                    type(data),
                )
                return {}
            if isinstance(items, list):
                result = {}
                for item in items:
                    if isinstance(item, dict) and "key" in item and "value" in item:
                        result[item["key"]] = item["value"]
                    else:
                        logger.warning("Skipping malformed settings item: %s", item)
                return result
            return {}
    except httpx.HTTPError:
        logger.exception("Failed to fetch platform settings with prefix %s", prefix)
    return {}


async def get_organization(token: str, org_id: int) -> dict[str, Any] | None:
    """Fetch a single organization (includes notification_settings)."""
    client = _get_client()
    url = f"{settings.admin_bl_service_url}/api/v1/admin/organizations/{org_id}"
    try:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if not isinstance(data, dict):
                logger.warning("Expected dict for org %s, got %s", org_id, type(data))
                return None
            return data
    except httpx.HTTPError:
        logger.exception("Failed to fetch organization %s", org_id)
    return None
