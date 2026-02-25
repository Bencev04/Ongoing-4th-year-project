"""
User Service (Business Logic) — FastAPI Application Entry Point.

Orchestrates tenant-scoped user and employee management.
All requests are authenticated via the auth-service.
Delegates database operations to user-db-access-service.
"""

import sys
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.exceptions import BaseServiceException
from common.redis import close_redis

from .api.routes import router

# Create FastAPI application
app = FastAPI(
    title="User Service (Business Logic)",
    description=(
        "Tenant-scoped user and employee management service.  "
        "Authenticates via auth-service and delegates persistence "
        "to user-db-access-service."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
