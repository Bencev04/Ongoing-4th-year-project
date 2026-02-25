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

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))
from common.config import settings
from common.schemas import HealthResponse

from .api.routes import router

logger = logging.getLogger(__name__)


# ==============================================================================
# Application Lifespan
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

app = FastAPI(
    title="Admin BL Service",
    description="Platform administration service for superadmins",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the admin router
app.include_router(router)


# ==============================================================================
# Root Health Check (convenience)
# ==============================================================================

@app.get("/health", response_model=HealthResponse)
async def root_health() -> HealthResponse:
    """Root-level health check (mirrors /api/v1/health)."""
    return HealthResponse(
        status="healthy",
        service="admin-bl-service",
        version="1.0.0",
        timestamp=datetime.utcnow(),
    )
