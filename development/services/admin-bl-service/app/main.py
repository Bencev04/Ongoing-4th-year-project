"""
Admin BL Service — FastAPI application entry point.

This service provides **superadmin-only** endpoints for
platform-level administration:

- Organization CRUD (create / list / get / update / suspend)
- Audit log retrieval (read-only, immutable records)
- Platform settings management
- Cross-tenant user listing and management

All endpoints require the ``superadmin`` role.  The service
delegates data operations to ``user-db-access-service`` and
reads/writes audit logs through its own service client.

Port: 8008 (internal only, routed via NGINX).
"""

import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Configure structured logging BEFORE importing FastAPI/Uvicorn
from common.logging_config import configure_logging, get_logger
from common.metrics_config import PrometheusMiddleware, get_metrics

configure_logging(
    service_name="admin-bl-service",
    level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "development"),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
)

logger = get_logger(__name__)

# Now import FastAPI and other dependencies
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.schemas import HealthResponse

from .api.routes import router

# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown.

    On startup:  log readiness.
    On shutdown: close HTTP client pool.
    """
    logger.info("Admin BL service starting on port 8008")
    yield
    # Cleanup: close the shared httpx client
    from .service_client import _http_client

    await _http_client.aclose()
    logger.info("Admin BL service shut down")


# ==============================================================================
# FastAPI App
# ==============================================================================

_debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

app = FastAPI(
    title="Admin BL Service",
    description="Platform administration service for superadmins",
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    lifespan=lifespan,
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

# Prometheus metrics middleware
app.add_middleware(PrometheusMiddleware, service_name="admin-bl-service")

# Include the admin router
app.include_router(router)


# ==============================================================================
# Exception Handlers
# ==============================================================================


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request,
    exc: Exception,
):
    """Catch-all: log the real error, return a safe 500 to the client."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# ==============================================================================
# Root Health Check (convenience)
# ==============================================================================


@app.get("/health", response_model=HealthResponse)
async def root_health() -> HealthResponse:
    """Root-level health check (mirrors /api/v1/health)."""
    return HealthResponse(
        status="healthy",
        service="admin-bl-service",
        version=os.environ.get("SERVICE_VERSION", "1.0.0"),
        timestamp=datetime.utcnow(),
    )


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()
