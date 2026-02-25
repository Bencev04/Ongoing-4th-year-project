"""Authentication page routes.

Serves the login page (standalone HTML -- no navbar) and a simple
``/logout`` redirect.  Actual token storage and removal is handled
entirely client-side in ``localStorage``; these routes just serve
the appropriate HTML / redirect.

Routes
------
GET /login  -- Render the sign-in form.
GET /logout -- Redirect to ``/login`` (client clears tokens).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# -- Template engine -----------------------------------------------------------
_templates_path: Path = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=_templates_path)

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: str = "/calendar",
) -> HTMLResponse:
    """Render the login page.

    The ``next`` query-parameter is passed into the template so the
    client-side JS can redirect there after a successful login.

    Args:
        request: Incoming HTTP request.
        next:    URL to redirect to after login (default ``/calendar``).

    Returns:
        Rendered ``pages/login.html`` (standalone -- no base layout).
    """
    return templates.TemplateResponse(
        "pages/login.html",
        {"request": request, "title": "Sign In", "next": next},
    )


@router.get("/logout")
async def logout() -> RedirectResponse:
    """Log the user out by redirecting to the login page.

    Token removal is handled client-side -- a ``click`` listener in
    ``base.html`` calls ``localStorage.clear()`` before this redirect
    fires.

    Returns:
        302 redirect to ``/login``.
    """
    return RedirectResponse(url="/login", status_code=302)
