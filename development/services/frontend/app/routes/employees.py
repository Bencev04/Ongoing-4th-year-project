"""
Employees page routes.

Serves the employees list/management page and HTMX partials.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.template_config import get_templates

# Configure templates
templates = get_templates()

router = APIRouter(tags=["employees"])


@router.get("/employees", response_class=HTMLResponse)
async def employees_page(request: Request) -> HTMLResponse:
    """
    Render the employees list page.

    Employee data is loaded client-side via HTMX / fetch calls
    to the /api/employees proxy endpoints.
    """
    return templates.TemplateResponse(
        request,
        "pages/employees.html",
        {
            "title": "Employees",
        },
    )
