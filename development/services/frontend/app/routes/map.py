"""Map page route.

Serves the dedicated Map View page where users can see all
scheduled jobs plotted on a Google Map, filter by date/status/employee,
and plan routes between job locations.

Routes
------
GET /map  – Full map page.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..template_config import get_templates

logger = logging.getLogger(__name__)

# ── Template engine ──────────────────────────────────────────────────────────
templates = get_templates()

router = APIRouter(tags=["map"])


@router.get("/map", response_class=HTMLResponse)
async def map_page(request: Request) -> HTMLResponse:
    """Render the full-page map view.

    Jobs are loaded client-side via ``authFetch`` — this route only
    serves the template shell with the Google Maps API script tag.

    Args:
        request: The incoming HTTP request.

    Returns:
        Rendered map.html template.
    """
    return templates.TemplateResponse(
        request,
        "pages/map.html",
    )
