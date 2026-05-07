"""
User Service (Business Logic) — FastAPI Application Entry Point.

Orchestrates tenant-scoped user and employee management.
All requests are authenticated via the auth-service.
Delegates database operations to user-db-access-service.
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
    service_name="user-bl-service",
    level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "development"),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
)

_logger = get_logger(__name__)

# Now import FastAPI and other dependencies
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.exceptions import BaseServiceException
from common.redis import close_redis

from .api.routes import router

_debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

# Create FastAPI application
app = FastAPI(
    title="User Service (Business Logic)",
    description=(
        "Tenant-scoped user and employee management service.  "
        "Authenticates via auth-service and delegates persistence "
        "to user-db-access-service."
    ),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)
app.add_middleware(PrometheusMiddleware, service_name="user-bl-service")


@app.exception_handler(BaseServiceException)
async def service_exception_handler(
    request: Request,
    exc: BaseServiceException,
) -> JSONResponse:
    """Convert custom exceptions to JSON responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "details": exc.details,
        },
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup handler."""
    print("User Service (Business Logic) started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown handler."""
    await close_redis()
    print("User Service (Business Logic) shutting down")


app.include_router(router)


@app.get("/")
async def root() -> dict:
    """Root endpoint returning service information."""
    return {
        "service": "user-service",
        "version": "1.0.0",
        "status": "running",
    }


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()
