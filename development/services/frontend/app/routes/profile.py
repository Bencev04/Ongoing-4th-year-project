"""
Profile page route — user settings and password change.

Renders the user profile page where users can view their information
and change their password.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.template_config import get_templates

templates = get_templates()

router = APIRouter(tags=["profile"])


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    """
    Render the user profile page.

    Displays user information and allows password changes.
    """
    return templates.TemplateResponse(request, "pages/profile.html")
