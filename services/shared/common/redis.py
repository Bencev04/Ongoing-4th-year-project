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
from typing import Any, Optional

import redis.asyncio as aioredis

from .config import settings

logger = logging.getLogger(__name__)

# Module-level connection — lazily initialised
_redis: Optional[aioredis.Redis] = None


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

async def cache_get(key: str) -> Optional[Any]:
    """
    Retrieve a JSON-serialised value from Redis.

    Args:
        key: Cache key.

    Returns:
        The deserialised Python object, or ``None`` on cache miss
        or if Redis is unavailable.
    """
    try:
        r = await get_redis()
        raw: Optional[str] = await r.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:
        logger.debug("Redis cache miss or error for key=%s", key)
    return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """
    Store a JSON-serialisable value in Redis with a TTL.

    Args:
        key:   Cache key.
        value: Any JSON-serialisable Python object.
        ttl:   Time-to-live in seconds.
    """
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        logger.debug("Redis cache write error for key=%s", key)


async def cache_delete(key: str) -> None:
    """
    Delete a single cache entry.

    Args:
        key: Cache key to remove.
    """
    try:
        r = await get_redis()
        await r.delete(key)
    except Exception:
        logger.debug("Redis cache delete error for key=%s", key)


async def cache_delete_pattern(pattern: str) -> None:
    """
    Delete all cache entries matching a glob pattern.

    Uses ``SCAN`` internally to avoid blocking Redis.

    Args:
        pattern: Glob pattern (e.g. ``"customer:*"``).
    """
    try:
        r = await get_redis()
        cursor: int = 0
        while True:
            cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await r.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        logger.debug("Redis cache pattern delete error for pattern=%s", pattern)
