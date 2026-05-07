"""
Prometheus metrics and request observability configuration for microservices.

Provides centralized metrics collection for:
- HTTP request latency, count, and error rates
- Business logic operations
- Database operations
- Cache hits/misses
- Service health indicators
Structured request logs share the same request ID as response headers.
"""

import os
import time
import uuid

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging_config import (
    clear_correlation_context,
    get_logger,
    set_correlation_context,
)

# ============================================================================
# Shared Metrics (used by all services)
# ============================================================================

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status", "service"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "status", "service"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint", "service"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000),
)

http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "endpoint", "status", "service"],
    buckets=(100, 500, 1000, 5000, 10000, 50000, 100000),
)

# Error Metrics
errors_total = Counter(
    "errors_total",
    "Total errors by type",
    ["type", "service"],
)

errors_by_endpoint = Counter(
    "errors_by_endpoint",
    "Errors by endpoint",
    ["endpoint", "status", "service"],
)

# Exception Metrics
exceptions_total = Counter(
    "exceptions_total",
    "Total exceptions",
    ["exception_type", "service"],
)

# Service Health
service_health_status = Gauge(
    "service_health_status",
    "Service health status (1=healthy, 0=unhealthy)",
    ["service"],
)

service_info = Gauge(
    "service_info",
    "Service metadata (always 1)",
    ["service", "version", "environment"],
)

# Database Metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["query_type", "table", "service"],
    buckets=(0.001, 0.01, 0.1, 0.5, 1.0, 2.5, 5.0),
)

db_pool_connections = Gauge(
    "db_pool_connections",
    "Database connection pool size",
    ["service"],
)

db_pool_available = Gauge(
    "db_pool_available",
    "Available connections in database pool",
    ["service"],
)

# Cache Metrics
cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["cache_type", "service"],
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["cache_type", "service"],
)

cache_errors_total = Counter(
    "cache_errors_total",
    "Total cache operation errors",
    ["operation", "cache_type", "service"],
)

cache_operation_duration_seconds = Histogram(
    "cache_operation_duration_seconds",
    "Cache operation duration in seconds",
    ["operation", "cache_type", "service"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Cache size in bytes",
    ["cache_type", "service"],
)

# Authentication Metrics
auth_attempts_total = Counter(
    "auth_attempts_total",
    "Total authentication attempts",
    ["status", "service"],
)

auth_token_validations_total = Counter(
    "auth_token_validations_total",
    "Total token validations",
    ["status", "service"],
)

# Business Logic Metrics (can be extended per service)
business_operations_total = Counter(
    "business_operations_total",
    "Total business operations",
    ["operation", "status", "service"],
)

business_operation_duration_seconds = Histogram(
    "business_operation_duration_seconds",
    "Business operation duration in seconds",
    ["operation", "service"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0),
)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP metrics and structured request logs.

    Tracks:
    - Request count and latency
    - Request/response sizes
    - Error rates
    - HTTP status codes
    - Request correlation IDs for log searches and AWS CloudWatch traces
    """

    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name
        self.logger = get_logger("common.observability")
        init_metrics(
            service_name=service_name,
            version=os.environ.get("SERVICE_VERSION", "1.0.0"),
            environment=os.environ.get("ENVIRONMENT", "development"),
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and collect metrics."""
        # Skip metrics endpoint itself
        if request.url.path == "/metrics":
            return await call_next(request)

        start_time = time.perf_counter()
        request_id = (
            request.headers.get("x-request-id")
            or request.headers.get("x-correlation-id")
            or str(uuid.uuid4())
        )
        context_token = set_correlation_context(trace_id=request_id)

        # Try to get request size
        request_size = 0
        try:
            if request.headers.get("content-length"):
                request_size = int(request.headers.get("content-length", 0))
        except (ValueError, TypeError):
            pass

        # Prefer route templates over concrete paths to avoid high-cardinality metrics.
        endpoint = _get_endpoint_template(request)
        method = request.method
        status_code = "500"
        response_size = 0
        response: Response | None = None

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
            response.headers["X-Request-ID"] = request_id
            if response.headers.get("content-length"):
                try:
                    response_size = int(response.headers.get("content-length", 0))
                except (ValueError, TypeError):
                    pass
            return response
        except Exception as exc:
            exceptions_total.labels(
                exception_type=type(exc).__name__,
                service=self.service_name,
            ).inc()
            raise
        finally:
            latency = time.perf_counter() - start_time
            status_int = int(status_code)

            http_requests_total.labels(
                method=method,
                endpoint=endpoint,
                status=status_code,
                service=self.service_name,
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=endpoint,
                status=status_code,
                service=self.service_name,
            ).observe(latency)

            http_request_size_bytes.labels(
                method=method,
                endpoint=endpoint,
                service=self.service_name,
            ).observe(request_size)

            http_response_size_bytes.labels(
                method=method,
                endpoint=endpoint,
                status=status_code,
                service=self.service_name,
            ).observe(response_size)

            if status_int >= 400:
                errors_total.labels(
                    type=f"http_{status_code}",
                    service=self.service_name,
                ).inc()
                errors_by_endpoint.labels(
                    endpoint=endpoint,
                    status=status_code,
                    service=self.service_name,
                ).inc()

            self.logger.info(
                "HTTP request completed",
                extra={
                    "http_method": method,
                    "http_path": request.url.path,
                    "http_route": endpoint,
                    "status_code": status_code,
                    "duration_ms": round(latency * 1000, 2),
                    "request_size_bytes": request_size,
                    "response_size_bytes": response_size,
                },
            )
            clear_correlation_context(context_token)


def _get_endpoint_template(request: Request) -> str:
    """Return the matched route template for stable metric cardinality."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    return route_path or request.url.path


def init_metrics(
    service_name: str, version: str = "1.0.0", environment: str = "development"
) -> None:
    """
    Initialize Prometheus metrics for a service.

    Call this early in your application startup.

    Args:
        service_name: Name of the service
        version: Service version
        environment: Environment name (dev, staging, prod)
    """
    # Set service info metric
    service_info.labels(
        service=service_name,
        version=version,
        environment=environment,
    ).set(1)

    # Set initial health status
    service_health_status.labels(service=service_name).set(1)


def get_metrics() -> Response:
    """
    Get Prometheus metrics in text format.

    Returns:
        Starlette response with the Prometheus content type
    """
    from prometheus_client import REGISTRY

    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


def record_db_query(
    query_type: str, table: str, duration: float, service_name: str
) -> None:
    """
    Record a database query metric.

    Args:
        query_type: Type of query (SELECT, INSERT, UPDATE, DELETE)
        table: Table name
        duration: Query duration in seconds
        service_name: Service name
    """
    db_query_duration_seconds.labels(
        query_type=query_type,
        table=table,
        service=service_name,
    ).observe(duration)


def record_cache_hit(cache_type: str, service_name: str) -> None:
    """Record a cache hit."""
    cache_hits_total.labels(cache_type=cache_type, service=service_name).inc()


def record_cache_miss(cache_type: str, service_name: str) -> None:
    """Record a cache miss."""
    cache_misses_total.labels(cache_type=cache_type, service=service_name).inc()


def record_cache_error(operation: str, cache_type: str, service_name: str) -> None:
    """Record a cache operation error."""
    cache_errors_total.labels(
        operation=operation,
        cache_type=cache_type,
        service=service_name,
    ).inc()


def record_cache_operation(
    operation: str, cache_type: str, duration: float, service_name: str
) -> None:
    """Record cache operation latency."""
    cache_operation_duration_seconds.labels(
        operation=operation,
        cache_type=cache_type,
        service=service_name,
    ).observe(duration)


def record_auth_attempt(status: str, service_name: str) -> None:
    """Record an authentication attempt."""
    auth_attempts_total.labels(status=status, service=service_name).inc()


def record_auth_token_validation(status: str, service_name: str) -> None:
    """Record an authentication token validation attempt."""
    auth_token_validations_total.labels(status=status, service=service_name).inc()


def record_business_operation(
    operation: str, status: str, duration: float, service_name: str
) -> None:
    """
    Record a business operation metric.

    Args:
        operation: Operation name (e.g., 'create_customer', 'schedule_job')
        status: Operation status (success, failure, error)
        duration: Operation duration in seconds
        service_name: Service name
    """
    business_operations_total.labels(
        operation=operation,
        status=status,
        service=service_name,
    ).inc()

    business_operation_duration_seconds.labels(
        operation=operation,
        service=service_name,
    ).observe(duration)


def update_service_health(healthy: bool, service_name: str) -> None:
    """
    Update service health status.

    Args:
        healthy: True if service is healthy, False otherwise
        service_name: Service name
    """
    service_health_status.labels(service=service_name).set(1 if healthy else 0)


def update_db_pool_status(pool_size: int, available: int, service_name: str) -> None:
    """
    Update database pool metrics.

    Args:
        pool_size: Total pool size
        available: Available connections
        service_name: Service name
    """
    db_pool_connections.labels(service=service_name).set(pool_size)
    db_pool_available.labels(service=service_name).set(available)
