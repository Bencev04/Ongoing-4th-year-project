"""
Auth Service — FastAPI Application Entry Point.

Configures and starts the authentication service responsible for
login, JWT issuance, token refresh / revocation, and multi-tenant
access-control primitives.
"""

import os
import sys
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Configure structured logging BEFORE importing FastAPI/Uvicorn
from common.logging_config import configure_logging, get_logger
from common.metrics_config import PrometheusMiddleware, get_metrics

configure_logging(
    service_name="auth-service",
    level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "development"),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
)

_logger = get_logger(__name__)

# Now import FastAPI and other dependencies
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from common.exceptions import BaseServiceException
from common.redis import close_redis

from .api.routes import close_http_client, init_http_client, limiter, router

# Disable OpenAPI docs outside of development
_debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

# Create FastAPI application
app = FastAPI(
    title="Auth Service",
    description=(
        "Authentication and authorisation service for the CRM Calendar "
        "platform.  Issues JWT access tokens, manages refresh tokens, "
        "and enforces multi-tenant isolation."
    ),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(PrometheusMiddleware, service_name="auth-service")


# ==============================================================================
# Exception Handlers
# ==============================================================================


@app.exception_handler(BaseServiceException)
async def service_exception_handler(
    request: Request,
    exc: BaseServiceException,
) -> JSONResponse:
    """
    Convert custom service exceptions into structured JSON responses.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "details": exc.details,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all: log the real error, return a safe 500 to the client."""
    _logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


# ==============================================================================
# Startup / Shutdown Events
# ==============================================================================


@app.on_event("startup")
async def startup_event() -> None:
    """
    Application startup handler.

    Schema is managed by Alembic via the migration-runner container.
    """
    await init_http_client()
    _logger.info("Auth Service started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown handler — close Redis and HTTP connections."""
    await close_http_client()
    await close_redis()
    _logger.info("Auth Service shutting down")


# Include routers
app.include_router(router)


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint returning service information."""
    return {
        "service": "auth-service",
        "version": "1.0.0",
        "status": "running",
    }


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()
