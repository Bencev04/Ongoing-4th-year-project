"""Frontend Service -- FastAPI application entry point.

Serves server-rendered Jinja2 templates enhanced with HTMX for
partial-page swaps and Alpine.js for lightweight client-side
interactivity.  Also acts as a single-origin API gateway by
proxying ``/api/*`` requests to the backend micro-services.

Routes
------
GET /          -- Redirect to ``/calendar``.
GET /health    -- Health check (for load balancers / Docker).
/login, /logout          -- Auth page routes   (``auth.router``).
/calendar, /calendar/*   -- Calendar routes     (``calendar.router``).
/employees               -- Employees page      (``employees.router``).
/admin                   -- Admin portal        (``admin.router``).
/api/*                   -- Reverse-proxy       (``api_proxy.router``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# -- Shared package path and logging setup --
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

# Configure structured logging BEFORE importing FastAPI/Uvicorn
from common.logging_config import configure_logging
from common.metrics_config import PrometheusMiddleware, get_metrics

configure_logging(
    service_name="frontend",
    level=os.environ.get("LOG_LEVEL", "INFO"),
    environment=os.environ.get("ENVIRONMENT", "development"),
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
)

# Now import FastAPI and other dependencies
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from common.health import HealthChecker
from common.schemas import HealthResponse

from .routes import (  # noqa: E402
    admin,
    api_proxy,
    auth,
    calendar,
    customers,
    employees,
    legal,
    map,
    profile,
    settings,
)
from .template_config import get_templates

# -- Lifespan (replaces deprecated on_event) ----------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler.

    Code before ``yield`` runs at **startup**; code after ``yield``
    runs at **shutdown**.
    """
    print("Frontend Service started successfully")
    yield
    print("Frontend Service shutting down")


# -- Application factory ------------------------------------------------------

_debug = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")

app = FastAPI(
    title="Workflow Platform Frontend",
    description="Web frontend for Workflow Platform application",
    version=os.environ.get("SERVICE_VERSION", "1.0.0"),
    docs_url="/api/docs" if _debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Cross-origin resource sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
)

# Prometheus metrics middleware
app.add_middleware(PrometheusMiddleware, service_name="frontend")


# -- Token refresh middleware --------------------------------------------------


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """Propagate a server-side-refreshed access token as a Set-Cookie header.

    When ``_ensure_auth()`` in *service_client* performs a silent token
    refresh (because the ``wp_access_token`` cookie expired but the
    long-lived ``wp_refresh_token`` is still valid), it stashes the new
    token on ``request.state.refreshed_access_token``.  This middleware
    detects that attribute and sets the cookie on the outgoing response
    so the browser receives the renewed token transparently.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request and attach refreshed cookie if needed."""
        response = await call_next(request)

        new_token: str | None = getattr(request.state, "refreshed_access_token", None)
        if new_token:
            from .service_client import propagate_refreshed_cookie

            propagate_refreshed_cookie(request, response)

        return response


app.add_middleware(TokenRefreshMiddleware)

# -- Static files & templates -------------------------------------------------

_static_path: Path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static_path), name="static")

templates = get_templates()


# -- Root routes ---------------------------------------------------------------

_health_checker = HealthChecker("frontend", "1.0.0")


@app.get("/")
async def index(request: Request) -> RedirectResponse:
    """Redirect the bare root URL based on user role.

    Unauthenticated users are sent to ``/login``. Superadmins are sent to
    ``/admin``; other authenticated users go to ``/calendar``.
    """
    from app.service_client import get_current_user

    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if user and user.get("role") == "superadmin":
        return RedirectResponse(url="/admin", status_code=302)
    return RedirectResponse(url="/calendar", status_code=302)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness probe — is the frontend service running?

    K8s uses this to determine if the container should be restarted.
    Returns quickly without checking external dependencies.
    """
    return await _health_checker.liveness_probe()


@app.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """
    Readiness probe — can the frontend handle traffic?

    K8s uses this to determine if the pod should receive traffic.
    Checks if critical backend services are reachable.
    """
    return await _health_checker.readiness_probe(
        db=None,  # Frontend doesn't touch DB
        check_redis=False,  # Frontend uses auth-service blacklist, not direct Redis
        check_services={
            "auth-service": "http://auth-service:8005",
        },
    )


# Metrics endpoint for Prometheus
@app.get("/metrics")
async def metrics():
    """Return Prometheus metrics."""
    return get_metrics()


# -- Register sub-routers -----------------------------------------------------

app.include_router(auth.router)
app.include_router(legal.router)
app.include_router(calendar.router)
app.include_router(customers.router)
app.include_router(employees.router)
app.include_router(profile.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(map.router)
app.include_router(api_proxy.router, prefix="/api")
