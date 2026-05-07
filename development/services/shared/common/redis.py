"""
Redis client helper for CRM Calendar microservices.

Provides an async Redis connection pool used for:
- Token blacklist caching (auth-service)
- Inter-service response caching (BL services)
- Rate-limit state (future)

Usage:
    from common.redis import get_redis, close_redis

    redis = await get_redis()
    await redis.set("key", "value", ex=60)
"""

import json
import logging
import os
import re
import time
from typing import Any

import redis.asyncio as aioredis

from .config import settings
from .metrics_config import (
    record_cache_error,
    record_cache_hit,
    record_cache_miss,
    record_cache_operation,
)

logger = logging.getLogger(__name__)

# Module-level connection — lazily initialised
_redis: aioredis.Redis | None = None

_CACHE_TYPE_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")


def _service_name() -> str:
    return os.environ.get("SERVICE_NAME", "unknown-service")


def _cache_type(key_or_pattern: str) -> str:
    prefix = key_or_pattern.split(":", 1)[0] if key_or_pattern else "default"
    prefix = _CACHE_TYPE_PATTERN.sub("_", prefix).strip("_").lower()
    if not prefix or len(prefix) > 32:
        return "default"
    return prefix


async def get_redis() -> aioredis.Redis:
    """
    Return a lazily-initialised async Redis client.

    The connection pool is managed internally by ``redis.asyncio``.
    Subsequent calls return the same client instance.

    Returns:
        aioredis.Redis: Connected async Redis client.
    """
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )
    return _redis


async def close_redis() -> None:
    """
    Shut down the Redis connection pool gracefully.

    Should be called from the FastAPI ``shutdown`` event.
    """
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
        logger.info("Redis connection pool closed")


# ==============================================================================
# Cache helper utilities
# ==============================================================================


async def cache_get(key: str) -> Any | None:
    """
    Retrieve a JSON-serialised value from Redis.

    Args:
        key: Cache key.

    Returns:
        The deserialised Python object, or ``None`` on cache miss
        or if Redis is unavailable.
    """
    cache_type = _cache_type(key)
    started_at = time.perf_counter()
    try:
        redis_client = await get_redis()
        raw: str | None = await redis_client.get(key)
        if raw is not None:
            record_cache_hit(cache_type, _service_name())
            return json.loads(raw)
        record_cache_miss(cache_type, _service_name())
    except Exception:
        record_cache_error("get", cache_type, _service_name())
        logger.debug("Redis cache miss or error for key=%s", key)
    finally:
        record_cache_operation(
            "get",
            cache_type,
            time.perf_counter() - started_at,
            _service_name(),
        )
    return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """
    Store a JSON-serialisable value in Redis with a TTL.

    Args:
        key:   Cache key.
        value: Any JSON-serialisable Python object.
        ttl:   Time-to-live in seconds.
    """
    cache_type = _cache_type(key)
    started_at = time.perf_counter()
    try:
        redis_client = await get_redis()
        await redis_client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        record_cache_error("set", cache_type, _service_name())
        logger.debug("Redis cache write error for key=%s", key)
    finally:
        record_cache_operation(
            "set",
            cache_type,
            time.perf_counter() - started_at,
            _service_name(),
        )


async def cache_delete(key: str) -> None:
    """
    Delete a single cache entry.

    Args:
        key: Cache key to remove.
    """
    cache_type = _cache_type(key)
    started_at = time.perf_counter()
    try:
        redis_client = await get_redis()
        await redis_client.delete(key)
    except Exception:
        record_cache_error("delete", cache_type, _service_name())
        logger.debug("Redis cache delete error for key=%s", key)
    finally:
        record_cache_operation(
            "delete",
            cache_type,
            time.perf_counter() - started_at,
            _service_name(),
        )


async def cache_delete_pattern(pattern: str) -> None:
    """
    Delete all cache entries matching a glob pattern.

    Uses ``SCAN`` internally to avoid blocking Redis.

    Args:
        pattern: Glob pattern (e.g. ``"customer:*"``).
    """
    cache_type = _cache_type(pattern)
    started_at = time.perf_counter()
    try:
        redis_client = await get_redis()
        cursor: int = 0
        while True:
            cursor, keys = await redis_client.scan(
                cursor=cursor, match=pattern, count=100
            )
            if keys:
                await redis_client.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        record_cache_error("delete_pattern", cache_type, _service_name())
        logger.debug("Redis cache pattern delete error for pattern=%s", pattern)
    finally:
        record_cache_operation(
            "delete_pattern",
            cache_type,
            time.perf_counter() - started_at,
            _service_name(),
        )
