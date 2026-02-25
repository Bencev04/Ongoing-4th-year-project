"""
Job Service - FastAPI Application Entry Point.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.database import async_init_db
from common.exceptions import BaseServiceException

from .api.routes import router

app = FastAPI(
    title="Job Service",
    description="Database access layer for jobs/calendar events",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

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
    exc: BaseServiceException
) -> JSONResponse:
    """Handle custom service exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "code": exc.code,
            "details": exc.details
        }
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Application startup handler."""
    await async_init_db()
    print("Job Service started successfully")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown handler."""
    print("Job Service shutting down")


app.include_router(router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint for Docker."""
    return {"status": "healthy", "service": "job-db-access-service"}


@app.get("/")
async def root() -> dict:
    """Root endpoint returning service info."""
    return {
        "service": "job-service",
        "version": "1.0.0",
        "status": "running"
    }
