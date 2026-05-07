"""
Maps Access Service — FastAPI Application Entry Point.

Wraps the Google Maps / Geocoding API for internal use by
BL services.  No authentication — this is an access-layer
service, unreachable from outside the Docker network
(no NGINX upstream).

Port: 8009
"""

import os
import sys
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Configure structured logging BEFORE importing FastAPI/Uvicorn
from common.logging_config import configure_logging
from common.metrics_config import PrometheusMiddleware, get_metrics

configure_logging(
    service_name="maps-access-service",
    level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "development"),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
)

# Now import FastAPI and other dependencies
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.exceptions import BaseServiceException

from .api.routes import router

_debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

# Create FastAPI application
app = FastAPI(
    title="Maps Access Service",
    description=(
        "Internal access-layer service that wraps the Google Maps "
        "Geocoding API.  Called by BL services (job-bl, customer-bl) "
        "to resolve addresses ↔ coordinates.  Not exposed externally."
    ),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
)

# Configure CORS (internal only, but kept for test clients)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)
app.add_middleware(PrometheusMiddleware, service_name="maps-access-service")


# ==============================================================================
# Exception Handlers
# ==============================================================================


@app.exception_handler(BaseServiceException)
async def service_exception_handler(
    request: Request,
    exc: BaseServiceException,
) -> JSONResponse:
    """Convert custom service exceptions into structured JSON responses."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "details": exc.details,
        },
    )


# ==============================================================================
# Startup / Shutdown Events
# ==============================================================================


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup handler."""
    print("Maps Access Service started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown handler."""
    print("Maps Access Service shutting down")


# Include routers
app.include_router(router)


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint returning service information."""
    return {
        "service": "maps-access-service",
        "version": "1.0.0",
        "status": "running",
    }


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()
