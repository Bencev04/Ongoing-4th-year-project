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

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# -- Shared package path ------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from .routes import auth, calendar, api_proxy, customers, employees, admin, profile  # noqa: E402


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

app = FastAPI(
    title="Workflow Platform Frontend",
    description="Web frontend for Workflow Platform application",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# Cross-origin resource sharing (permissive for dev; tighten in production).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Static files & templates -------------------------------------------------

_static_path: Path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_static_path), name="static")

_templates_path: Path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=_templates_path)


# -- Root routes ---------------------------------------------------------------

@app.get("/")
async def index() -> RedirectResponse:
    """Redirect the bare root URL to the calendar page."""
    return RedirectResponse(url="/calendar", status_code=302)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health-check endpoint for load balancers and Docker."""
    return {"status": "healthy", "service": "frontend"}


# -- Register sub-routers -----------------------------------------------------

app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(customers.router)
app.include_router(employees.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(api_proxy.router, prefix="/api")
