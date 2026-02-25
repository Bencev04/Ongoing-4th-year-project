"""
User Service - FastAPI Application Entry Point.

Main application module that configures and starts the User service.
"""

import sys
from pathlib import Path

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.database import async_init_db
from common.exceptions import BaseServiceException

from .api.routes import router

# Create FastAPI application
app = FastAPI(
    title="User Service",
    description="Database access layer for users and employees",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
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
    exc: BaseServiceException
) -> JSONResponse:
    """
    Handle custom service exceptions.
    
    Converts BaseServiceException to proper HTTP response.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "details": exc.details
        }
    )


# ==============================================================================
# Startup/Shutdown Events
# ==============================================================================

@app.on_event("startup")
async def startup_event() -> None:
    """
    Application startup handler.
    
    Initializes database tables and any other required resources.
    """
    # Initialize database tables
    # Note: In production, use Alembic migrations instead
    await async_init_db()
    print("User Service started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """
    Application shutdown handler.
    
    Cleanup resources on shutdown.
    """
    print("User Service shutting down")


# Include routers
app.include_router(router)


# Health check endpoint
@app.get("/health")
async def health() -> dict:
    """Health check endpoint for Docker."""
    return {"status": "healthy", "service": "user-db-access-service"}


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint returning service info."""
    return {
        "service": "user-service",
        "version": "1.0.0",
        "status": "running"
    }
