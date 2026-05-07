"""
Settings page route — tenant administration for owners and admins.

Renders the organisation-level settings page where owner/admin users
can manage company info, team members (including password resets),
and fine-grained user permissions.

Tabs
----
1. **Organisation** — view and edit company details.
2. **People**       — list team members, reset passwords.
3. **Permissions**  — toggle per-user permission grants.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.template_config import get_templates

templates = get_templates()

router = APIRouter(tags=["settings"])


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """
    Render the tenant settings page.

    All data is loaded client-side by the Alpine.js ``settingsApp()``
    component via ``authFetch()`` calls to the backend API proxy.
    Access is restricted to owner/admin roles on the client.

    Returns:
        HTMLResponse: The rendered settings page.
    """
    return templates.TemplateResponse(
        request,
        "pages/settings.html",
        {"title": "Settings"},
    )
