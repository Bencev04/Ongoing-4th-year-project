"""
Health check utilities for Kubernetes probes.

Provides liveness and readiness probe handlers for all services.
Liveness checks if the service is running.
Readiness checks if the service can handle traffic (all dependencies healthy).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx

from .schemas import HealthResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
else:
    AsyncSession = Any


async def check_database(db: AsyncSession) -> dict[str, Any]:
    """
    Check if the database is accessible.

    Args:
        db: Async database session.

    Returns:
        Dict with 'healthy' (bool) and 'message' (str).
    """
    try:
        from sqlalchemy import text

        # Simple query to verify DB connectivity
        await db.execute(text("SELECT 1"))
        return {"healthy": True, "message": "Database connection OK"}
    except ModuleNotFoundError:
        return {
            "healthy": False,
            "message": "SQLAlchemy is not installed in this service",
        }
    except Exception as exc:
        return {"healthy": False, "message": f"Database error: {str(exc)}"}


async def _check_redis_health() -> dict[str, Any]:
    """
    Check if Redis is accessible.

    Returns:
        Dict with 'healthy' (bool) and 'message' (str).
        If Redis is unavailable, returns healthy: False (expected for fallback scenarios).
    """
    try:
        from .redis import get_redis

        redis = await get_redis()
        if redis:
            await redis.ping()
            return {"healthy": True, "message": "Redis connection OK"}
        # Redis disabled or not configured
        return {"healthy": True, "message": "Redis not configured (optional)"}
    except ModuleNotFoundError:
        return {
            "healthy": True,
            "message": "Redis library not installed (optional)",
        }
    except Exception as exc:
        # Redis is optional — apps must work without it
        return {
            "healthy": False,
            "message": f"Redis unavailable (optional): {str(exc)}",
        }


check_redis = _check_redis_health


async def check_service_http(
    service_url: str,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """
    Check if a remote service is healthy via HTTP.

    Args:
        service_url: Base URL of the service to check.
        timeout: Request timeout in seconds.

    Returns:
        Dict with 'healthy' (bool) and 'message' (str).
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{service_url}/health")
            if response.status_code == 200:
                return {
                    "healthy": True,
                    "message": f"{service_url} is healthy",
                }
            return {
                "healthy": False,
                "message": f"{service_url} returned {response.status_code}",
            }
    except httpx.TimeoutException:
        return {"healthy": False, "message": f"{service_url} timeout"}
    except httpx.ConnectError:
        return {"healthy": False, "message": f"{service_url} unreachable"}
    except Exception as exc:
        return {"healthy": False, "message": f"{service_url} error: {str(exc)}"}


class HealthChecker:
    """Utility class for checking service health and readiness."""

    def __init__(self, service_name: str, version: str = "1.0.0") -> None:
        """
        Initialize the health checker.

        Args:
            service_name: Name of the service (e.g., 'auth-service').
            version: Version string (default: 1.0.0).
        """
        self.service_name = service_name
        self.version = version

    async def liveness_probe(self) -> HealthResponse:
        """
        Liveness probe — reports if the service is running.

        K8s uses this to determine if the container should be restarted.
        Should be fast and not check external dependencies.

        Returns:
            Health response with status='healthy'.
        """
        return HealthResponse(
            status="healthy",
            service=self.service_name,
            version=self.version,
            timestamp=datetime.utcnow(),
        )

    async def readiness_probe(
        self,
        db: AsyncSession | None = None,
        check_redis_enabled: bool = True,
        check_services: dict[str, str] | None = None,
        check_redis: bool | None = None,
    ) -> HealthResponse:
        """
        Readiness probe — reports if the service can handle traffic.

        K8s uses this to determine if traffic should be routed to this instance.
        Checks all critical dependencies.

        Args:
            db: Optional database session to check.
            check_redis_enabled: Whether to check Redis health (default: True).
            check_services: Optional dict of service_name: service_url to check.
            check_redis: Backward-compatible alias for check_redis_enabled.

        Returns:
            Health response with status='healthy' or 'unhealthy'.
        """
        checks = {}

        # Keep backward compatibility with existing call sites using check_redis=.
        if check_redis is not None:
            check_redis_enabled = check_redis

        # Check database if provided
        if db:
            checks["database"] = await check_database(db)

        # Check Redis if requested
        if check_redis_enabled:
            checks["redis"] = await _check_redis_health()

        # Check dependent services if provided
        if check_services:
            for svc_name, svc_url in check_services.items():
                checks[svc_name] = await check_service_http(svc_url)

        # Determine overall status
        all_healthy = all(check.get("healthy", False) for check in checks.values())
        status = "healthy" if all_healthy else "unhealthy"

        return HealthResponse(
            status=status,
            service=self.service_name,
            version=self.version,
            timestamp=datetime.utcnow(),
        )
