"""
Customer Service (Business Logic) — FastAPI Application Entry Point.

Orchestrates tenant-scoped customer management and enrichment.
Authenticates via auth-service and delegates persistence to
customer-db-access-service.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from common.exceptions import BaseServiceException
from common.redis import close_redis

from .api.routes import router

app = FastAPI(
    title="Customer Service (Business Logic)",
    description=(
        "Tenant-scoped customer management with job-history enrichment. "
        "Authenticates via auth-service and delegates persistence to "
        "customer-db-access-service."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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
    request: Request, exc: BaseServiceException,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "details": exc.details},
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
