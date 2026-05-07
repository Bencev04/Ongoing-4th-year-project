"""
Customer Service (Business Logic) — FastAPI Application Entry Point.

Orchestrates tenant-scoped customer management and enrichment.
Authenticates via auth-service and delegates persistence to
customer-db-access-service.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

# Configure structured logging BEFORE importing FastAPI/Uvicorn
from common.logging_config import configure_logging, get_logger
from common.metrics_config import PrometheusMiddleware, get_metrics

configure_logging(
    service_name="customer-bl-service",
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

app = FastAPI(
    title="Customer Service (Business Logic)",
    description=(
        "Tenant-scoped customer management with job-history enrichment. "
        "Authenticates via auth-service and delegates persistence to "
        "customer-db-access-service."
    ),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    docs_url="/docs" if _debug else None,
    redoc_url="/redoc" if _debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)
app.add_middleware(PrometheusMiddleware, service_name="customer-bl-service")


@app.exception_handler(BaseServiceException)
async def service_exception_handler(
    request: Request,
    exc: BaseServiceException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "details": exc.details},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    _logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"},
    )


@app.on_event("startup")
async def startup_event() -> None:
    print("Customer Service (Business Logic) started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_redis()
    print("Customer Service (Business Logic) shutting down")


app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {"service": "customer-service", "version": "1.0.0", "status": "running"}


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()
