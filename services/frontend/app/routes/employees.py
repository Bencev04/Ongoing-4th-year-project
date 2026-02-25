"""
Employees page routes.

Serves the employees list/management page and HTMX partials.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Configure templates
templates_path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=templates_path)

router = APIRouter(tags=["employees"])


@router.get("/employees", response_class=HTMLResponse)
async def employees_page(request: Request) -> HTMLResponse:
    """
    Render the employees list page.

    Employee data is loaded client-side via HTMX / fetch calls
    to the /api/employees proxy endpoints.
    """
    return templates.TemplateResponse(
        "pages/employees.html",
        {
            "request": request,
            "title": "Employees",
        },
    )
