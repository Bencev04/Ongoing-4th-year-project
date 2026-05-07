"""
Admin portal page route.

Serves the superadmin administration dashboard page where
platform-level management operations are performed.

Server-side role enforcement redirects non-superadmin users
before the page is rendered.  The admin.js Alpine component
also checks the role client-side as defense-in-depth.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from app.service_client import get_current_user, propagate_refreshed_cookie
from app.template_config import get_templates

# Configure templates
templates = get_templates()

router = APIRouter(tags=["admin"])


@router.get("/admin", response_class=HTMLResponse, response_model=None)
async def admin_page(request: Request) -> Response:
    """
    Render the superadmin administration portal.

    Verifies the caller is an authenticated superadmin before
    rendering.  Non-superadmins are redirected to ``/calendar``,
    unauthenticated users to ``/login``.  The resolved
    ``user_role`` is passed into the template context so that
    ``base.html`` can render the correct nav state immediately
    (avoiding the async JS flash).

    Returns:
        The admin page HTML for superadmins, or a 302 redirect.
    """
    user = await get_current_user(request)

    if not user:
        return RedirectResponse(url="/login?next=/admin", status_code=302)

    if user.get("role") != "superadmin":
        return RedirectResponse(url="/calendar", status_code=302)

    response = templates.TemplateResponse(
        request,
        "pages/admin.html",
        {
            "title": "Admin Portal",
            "user_role": "superadmin",
        },
    )
    propagate_refreshed_cookie(request, response)
    return response
