"""
Google Maps API adapter.

Wraps the Google Geocoding API with Redis DB5 caching and
graceful degradation when the API key is not configured or
the API is unreachable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx
import redis.asyncio as aioredis

from common.config import settings

logger = logging.getLogger(__name__)

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Redis DB5 for maps geocode cache
_redis_client: aioredis.Redis | None = None
_CACHE_TTL = 86400 * 7  # 7 days — geocode results rarely change


async def get_redis() -> aioredis.Redis | None:
    """Get or create a Redis client for maps cache (DB5).

    Returns:
        Redis client or None if unavailable.
    """
    global _redis_client
    if _redis_client is None:
        try:
            base_url = str(settings.redis_url)
            # Replace DB number with 5
            if base_url.endswith("/0"):
                redis_url = base_url[:-1] + "5"
            else:
                redis_url = base_url.rsplit("/", 1)[0] + "/5"
            _redis_client = aioredis.from_url(redis_url, decode_responses=True)
            await _redis_client.ping()
        except Exception:
            logger.debug("Redis unavailable for maps cache — using API only")
            _redis_client = None
    return _redis_client


def _cache_key(prefix: str, value: str) -> str:
    """Build a deterministic cache key.

    Args:
        prefix: Cache namespace (e.g. ``geocode``, ``reverse``).
        value: Input to hash.

    Returns:
        Cache key string.
    """
    digest = hashlib.sha256(value.lower().strip().encode()).hexdigest()
    return f"maps:{prefix}:{digest}"


async def _cache_get(key: str) -> dict[str, Any] | None:
    """Read from Redis cache, returning None on miss or error."""
    try:
        r = await get_redis()
        if r is None:
            return None
        data = await r.get(key)
        if data:
            return json.loads(data)
    except Exception:
        logger.debug("Redis cache read failed for %s", key)
    return None


async def _cache_set(key: str, value: dict[str, Any]) -> None:
    """Write to Redis cache, silently ignoring errors."""
    try:
        r = await get_redis()
        if r is None:
            return
        await r.setex(key, _CACHE_TTL, json.dumps(value))
    except Exception:
        logger.debug("Redis cache write failed for %s", key)


def _extract_eircode(address_components: list[dict[str, Any]]) -> str | None:
    """Extract Eircode (postal_code) from Google address components.

    Args:
        address_components: Google Geocoding API address_components array.

    Returns:
        Eircode string or None.
    """
    for component in address_components:
        if "postal_code" in component.get("types", []):
            return component.get("long_name")
    return None


def is_configured() -> bool:
    """Check whether the Google Maps server key is configured.

    Returns:
        True if the server key is a non-empty string.
    """
    return bool(settings.google_maps_server_key)


async def geocode_address(address: str) -> dict[str, Any] | None:
    """Forward-geocode an address to coordinates.

    Args:
        address: Free-text address string.

    Returns:
        Dict with ``latitude``, ``longitude``, ``formatted_address``,
        ``eircode`` on success; None on failure.
    """
    if not is_configured():
        return None

    key = _cache_key("geocode", address)
    cached = await _cache_get(key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GOOGLE_GEOCODE_URL,
                params={
                    "address": address,
                    "key": settings.google_maps_server_key,
                    "region": "ie",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.debug("Geocode failed for '%s': %s", address, data.get("status"))
            return None

        result = data["results"][0]
        geo = result["geometry"]["location"]
        output = {
            "latitude": geo["lat"],
            "longitude": geo["lng"],
            "formatted_address": result.get("formatted_address", address),
            "eircode": _extract_eircode(result.get("address_components", [])),
        }

        await _cache_set(key, output)
        return output

    except Exception:
        logger.exception("Google Geocoding API call failed for '%s'", address)
        return None


async def reverse_geocode(latitude: float, longitude: float) -> dict[str, Any] | None:
    """Reverse-geocode coordinates to an address.

    Args:
        latitude: Latitude value.
        longitude: Longitude value.

    Returns:
        Dict with ``latitude``, ``longitude``, ``formatted_address``,
        ``eircode`` on success; None on failure.
    """
    if not is_configured():
        return None

    key = _cache_key("reverse", f"{latitude},{longitude}")
    cached = await _cache_get(key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GOOGLE_GEOCODE_URL,
                params={
                    "latlng": f"{latitude},{longitude}",
                    "key": settings.google_maps_server_key,
                    "region": "ie",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            logger.debug(
                "Reverse geocode failed for (%s, %s): %s",
                latitude,
                longitude,
                data.get("status"),
            )
            return None

        result = data["results"][0]
        output = {
            "latitude": latitude,
            "longitude": longitude,
            "formatted_address": result.get("formatted_address", ""),
            "eircode": _extract_eircode(result.get("address_components", [])),
        }

        await _cache_set(key, output)
        return output

    except Exception:
        logger.exception(
            "Google Reverse Geocoding API call failed for (%s, %s)",
            latitude,
            longitude,
        )
        return None


async def geocode_eircode(eircode: str) -> dict[str, Any] | None:
    """Geocode an Irish Eircode to coordinates and address.

    Args:
        eircode: Irish postal code (Eircode).

    Returns:
        Dict with ``latitude``, ``longitude``, ``formatted_address``,
        ``eircode`` on success; None on failure.
    """
    return await geocode_address(f"{eircode}, Ireland")
