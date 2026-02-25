"""
Admin portal page route.

Serves the superadmin administration dashboard page where
platform-level management operations are performed.

The page is client-rendered using Alpine.js — all data is
fetched via the ``/api/admin/*`` proxy endpoints.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Configure templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=templates_path)

router = APIRouter(tags=["admin"])


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    """
    Render the superadmin administration portal.

    Access control is enforced client-side — the page checks
    the user's role from the JWT and redirects non-superadmins
    to the calendar page.  Server-side enforcement happens at
    the API layer (admin-bl-service).
    """
    return templates.TemplateResponse(
        "pages/admin.html",
        {
            "request": request,
            "title": "Admin Portal",
        },
    )
