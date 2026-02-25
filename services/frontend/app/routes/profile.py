"""
Profile page route — user settings and password change.

Renders the user profile page where users can view their information
and change their password.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")

router = APIRouter(tags=["profile"])


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request) -> HTMLResponse:
    """
    Render the user profile page.
    
    Displays user information and allows password changes.
    """
    return templates.TemplateResponse("pages/profile.html", {"request": request})
