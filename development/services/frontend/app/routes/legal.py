"""Public legal pages (Privacy Policy, Terms of Service).

These pages are accessible without authentication and serve as GDPR
transparency requirements (Articles 13/14).

Routes
------
GET /privacy  -- Privacy Policy page.
GET /terms    -- Terms of Service page.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.template_config import get_templates

templates = get_templates()

router = APIRouter(tags=["legal"])


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request) -> HTMLResponse:
    """Render the Privacy Policy page."""
    return templates.TemplateResponse(request, "pages/privacy.html")


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request) -> HTMLResponse:
    """Render the Terms of Service page."""
    return templates.TemplateResponse(request, "pages/terms.html")
