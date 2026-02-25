"""
Auth Service — FastAPI Application Entry Point.

Configures and starts the authentication service responsible for
login, JWT issuance, token refresh / revocation, and multi-tenant
access-control primitives.
"""

import sys
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.database import async_init_db
from common.exceptions import BaseServiceException
from common.redis import close_redis

from .api.routes import router

# Create FastAPI application
app = FastAPI(
    title="Auth Service",
    description=(
        "Authentication and authorisation service for the CRM Calendar "
        "platform.  Issues JWT access tokens, manages refresh tokens, "
        "and enforces multi-tenant isolation."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ==============================================================================
# Startup / Shutdown Events
# ==============================================================================

@app.on_event("startup")
async def startup_event() -> None:
    """
    Application startup handler.

    Initialises database tables for refresh tokens and blacklist.
    In production, use Alembic migrations instead.
    """
    await async_init_db()
    print("Auth Service started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown handler — close Redis connections."""
    await close_redis()
    print("Auth Service shutting down")


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
