"""
Service clients for Customer Service inter-service communication.

Encapsulates HTTP calls to:
- customer-db-access-service  (persistence)
- job-db-access-service  (job history enrichment)

GET operations are **Redis-cached** with configurable TTLs.
Mutations automatically invalidate the relevant cache entries.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from common.config import settings
from common.redis import cache_delete, cache_delete_pattern, cache_get, cache_set

logger = logging.getLogger(__name__)

_customer_client = httpx.AsyncClient(
    base_url=settings.customer_service_url,
    timeout=10.0,
)

_job_client = httpx.AsyncClient(
    base_url=settings.job_service_url,
    timeout=10.0,
)

_maps_client = httpx.AsyncClient(
    base_url=settings.maps_service_url,
    timeout=10.0,
)

_API = "/api/v1"

# Cache key prefixes
_CK_CUSTOMER = "cust:bl:customer"
_CK_CUSTOMERS = "cust:bl:customers"
_CK_NOTES = "cust:bl:notes"
_CK_JOBS = "cust:bl:jobs_for"


# ==============================================================================
# Field Translation (BL schema ↔ DB schema)
# ==============================================================================


def _to_db_payload(bl_data: dict) -> dict:
    """Translate BL-layer fields to DB-access-layer fields.

    The BL layer presents ``first_name`` / ``last_name`` / ``company``
    while the DB layer stores ``name`` / ``company_name``.

    Args:
        bl_data: Dict with BL-schema keys.

    Returns:
        Dict with DB-schema keys ready for the DB-access service.
    """
    db_data: dict = {}

    # Combine first_name + last_name → name
    first = bl_data.pop("first_name", None)
    last = bl_data.pop("last_name", None)
    if first is not None or last is not None:
        db_data["name"] = f"{first or ''} {last or ''}".strip()

    # company → company_name
    company = bl_data.pop("company", None)
    if company is not None:
        db_data["company_name"] = company

    # Pass through remaining fields unchanged
    db_data.update(bl_data)
    return db_data


def _from_db_response(db_data: dict) -> dict:
    """Translate a DB-access-layer response to BL-layer fields.

    Splits ``name`` back into ``first_name`` / ``last_name`` and
    renames ``company_name`` → ``company``.

    Args:
        db_data: Dict returned by the DB-access service.

    Returns:
        Dict with BL-schema keys for the public API.
    """
    bl_data: dict = dict(db_data)

    # name → first_name + last_name
    raw_name: str = str(bl_data.pop("name", "") or "")
    name = raw_name.strip()
    if not name:
        bl_data["first_name"] = ""
        bl_data["last_name"] = ""
    else:
        parts = name.split(" ", 1)
        bl_data["first_name"] = parts[0]
        bl_data["last_name"] = parts[1] if len(parts) > 1 else ""

    # company_name → company
    bl_data["company"] = bl_data.pop("company_name", None)

    return bl_data


# ==============================================================================
# Helpers
# ==============================================================================


async def _handle(response: httpx.Response) -> dict | list:
    """Parse response or raise appropriate HTTPException."""
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Resource not found")
    if response.status_code == 409:
        raise HTTPException(
            status_code=409, detail=response.json().get("detail", "Conflict")
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


def _unavailable(service: str) -> HTTPException:
    return HTTPException(status_code=503, detail=f"{service} is unavailable")


# ==============================================================================
# Geocoding (non-blocking)
# ==============================================================================


async def _maybe_geocode(payload: dict) -> dict:
    """Auto-geocode address/eircode if lat/lng are missing.

    Geocoding failure is non-blocking — the payload is returned
    unchanged if maps-access-service is unreachable or returns no
    results.  This follows the same resilience pattern as Redis
    caching (silent degradation).

    Args:
        payload: Customer payload dict (BL field names).

    Returns:
        The same dict, potentially enriched with ``latitude`` and
        ``longitude``.
    """
    if payload.get("latitude") and payload.get("longitude"):
        return payload

    address = payload.get("address")
    eircode = payload.get("eircode")

    if not address and not eircode:
        return payload

    try:
        if eircode:
            resp = await _maps_client.post(
                f"{_API}/maps/geocode-eircode",
                json={"eircode": eircode},
            )
        else:
            resp = await _maps_client.post(
                f"{_API}/maps/geocode",
                json={"address": address},
            )

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                payload["latitude"] = results[0]["latitude"]
                payload["longitude"] = results[0]["longitude"]
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        logger.debug(
            "Geocoding failed for customer payload — continuing without coords"
        )

    return payload


# ==============================================================================
# Customer DB Access Service
# ==============================================================================


async def get_customers(
    *,
    skip: int = 0,
    limit: int = 100,
    owner_id: int | None = None,
    search: str | None = None,
    is_active: bool | None = None,
) -> dict:
    """Fetch paginated customers (cached)."""
    cache_key = f"{_CK_CUSTOMERS}:{owner_id}:{skip}:{limit}:{search}:{is_active}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    params: dict[str, Any] = {"skip": skip, "limit": limit}
    if owner_id is not None:
        params["owner_id"] = owner_id
    if search:
        params["search"] = search
    if is_active is not None:
        params["is_active"] = is_active

    try:
        resp = await _customer_client.get(f"{_API}/customers", params=params)
        data = await _handle(resp)
        # Translate DB fields → BL fields for each item
        if isinstance(data, dict) and "items" in data:
            data["items"] = [_from_db_response(c) for c in data["items"]]
        await cache_set(cache_key, data, settings.cache_ttl_short)
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def get_customer(customer_id: int) -> dict:
    """Fetch a single customer (cached)."""
    cache_key = f"{_CK_CUSTOMER}:{customer_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _customer_client.get(f"{_API}/customers/{customer_id}")
        data = await _handle(resp)
        data = _from_db_response(data)
        await cache_set(cache_key, data, settings.cache_ttl_medium)
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def create_customer(payload: dict) -> dict:
    """Create a new customer and invalidate cache."""
    try:
        payload = await _maybe_geocode(dict(payload))
        db_payload = _to_db_payload(dict(payload))
        resp = await _customer_client.post(f"{_API}/customers", json=db_payload)
        data = await _handle(resp)
        data = _from_db_response(data)
        await cache_delete_pattern(f"{_CK_CUSTOMERS}:*")
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def update_customer(customer_id: int, payload: dict) -> dict:
    """Update a customer and invalidate cache."""
    try:
        payload = await _maybe_geocode(dict(payload))
        db_payload = _to_db_payload(dict(payload))
        resp = await _customer_client.put(
            f"{_API}/customers/{customer_id}", json=db_payload
        )
        data = await _handle(resp)
        data = _from_db_response(data)
        await cache_delete(f"{_CK_CUSTOMER}:{customer_id}")
        await cache_delete_pattern(f"{_CK_CUSTOMERS}:*")
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def delete_customer(customer_id: int) -> None:
    """Delete (soft-delete) a customer and invalidate cache."""
    try:
        resp = await _customer_client.delete(f"{_API}/customers/{customer_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Customer not found")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        await cache_delete(f"{_CK_CUSTOMER}:{customer_id}")
        await cache_delete_pattern(f"{_CK_CUSTOMERS}:*")
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


# ==============================================================================
# Customer Notes
# ==============================================================================


async def get_customer_notes(customer_id: int) -> list[dict]:
    """Fetch notes for a customer (cached)."""
    cache_key = f"{_CK_NOTES}:{customer_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _customer_client.get(f"{_API}/customer-notes/{customer_id}")
        data = await _handle(resp)
        await cache_set(cache_key, data, settings.cache_ttl_short)
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def create_customer_note(customer_id: int, payload: dict) -> dict:
    """Create a note for a customer and invalidate cache."""
    try:
        # Ensure customer_id is in the body (DB-access expects it there)
        payload["customer_id"] = customer_id
        resp = await _customer_client.post(f"{_API}/customer-notes/", json=payload)
        data = await _handle(resp)
        await cache_delete(f"{_CK_NOTES}:{customer_id}")
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def update_customer_note(note_id: int, payload: dict) -> dict:
    """Update a customer note and invalidate cache."""
    try:
        resp = await _customer_client.put(
            f"{_API}/customer-notes/{note_id}", json=payload
        )
        data = await _handle(resp)
        # We don't know which customer the note belongs to, so wipe all note caches
        await cache_delete_pattern(f"{_CK_NOTES}:*")
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def get_customer_note(note_id: int) -> dict:
    """
    Fetch a single customer note by ID.

    Used by BL routes for tenant isolation checks before mutations.
    The returned dict includes ``customer_id`` which is needed
    to trace the note back to its parent customer for ownership
    verification.

    Args:
        note_id: Note's primary key.

    Returns:
        Note data dict containing at least ``id``, ``customer_id``,
        ``content``, ``created_by_id``.

    Raises:
        HTTPException: 404 if note not found.
        HTTPException: 503 if DB-access service is unreachable.
    """
    try:
        resp = await _customer_client.get(f"{_API}/customer-notes/note/{note_id}")
        return await _handle(resp)
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def delete_customer_note(note_id: int) -> None:
    """Delete a customer note and invalidate cache."""
    try:
        resp = await _customer_client.delete(f"{_API}/customer-notes/{note_id}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Note not found")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        await cache_delete_pattern(f"{_CK_NOTES}:*")
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


# ==============================================================================
# Job DB Access Service (for enrichment)
# ==============================================================================


async def get_jobs_for_customer(
    customer_id: int,
    owner_id: int,
    limit: int = 10,
) -> list[dict]:
    """Fetch recent jobs for a customer (cached, for enrichment)."""
    cache_key = f"{_CK_JOBS}:{customer_id}:{owner_id}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _job_client.get(
            f"{_API}/jobs",
            params={
                "customer_id": customer_id,
                "owner_id": owner_id,
                "limit": limit,
            },
        )
        data = await _handle(resp)
        items = data.get("items", []) if isinstance(data, dict) else data
        await cache_set(cache_key, items, settings.cache_ttl_short)
        return items
    except httpx.ConnectError:
        # Graceful degradation — enrichment failure shouldn't block the response
        return []


# ==============================================================================
# GDPR Operations (Data Export & Anonymization)
# ==============================================================================


async def export_customer_data(customer_id: int) -> dict:
    """Export all personal data for a customer (GDPR right of access)."""
    try:
        resp = await _customer_client.get(f"{_API}/customers/{customer_id}/export")
        data = await _handle(resp)
        if "profile" in data:
            data["profile"] = _from_db_response(data["profile"])
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")


async def anonymize_customer(customer_id: int) -> dict:
    """Immediately anonymize a customer's personal data (GDPR right to erasure)."""
    try:
        resp = await _customer_client.post(f"{_API}/customers/{customer_id}/anonymize")
        data = await _handle(resp)
        await cache_delete(f"{_CK_CUSTOMER}:{customer_id}")
        await cache_delete_pattern(f"{_CK_CUSTOMERS}:*")
        await cache_delete_pattern(f"{_CK_NOTES}:{customer_id}:*")
        return data
    except httpx.ConnectError:
        raise _unavailable("Customer DB Access Service")
