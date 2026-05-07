"""Authentication page routes.

Serves the login page (standalone HTML -- no navbar) and a logout
endpoint that clears auth cookies. Token lifecycle is managed by the
frontend API proxy using HttpOnly cookies.

Routes
------
GET  /login  -- Render the sign-in form.
POST /logout -- Clear auth cookies and redirect to ``/login``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.api_proxy import (
    _ACCESS_COOKIE,
    _ADMIN_ORIGINAL_ACCESS_COOKIE,
    _ADMIN_ORIGINAL_REFRESH_COOKIE,
    _REFRESH_COOKIE,
    _delete_cookie,
)
from app.template_config import get_templates

# -- Template engine -----------------------------------------------------------
templates = get_templates()

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
        request,
        "pages/login.html",
        {"title": "Sign In", "next": next},
    )


@router.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    """Log the user out by redirecting to the login page.

    Uses POST to prevent CSRF — a GET endpoint could be triggered
    by a malicious ``<img src="/logout">`` on an external page.

    Cookie attributes (secure, httponly, samesite) are matched to
    the values used at creation so browsers reliably delete them.

    Args:
        request: Incoming HTTP request (needed for secure-flag check).

    Returns:
        302 redirect to ``/login``.
    """
    response = RedirectResponse(url="/login", status_code=302)
    for cookie_name in (
        _ACCESS_COOKIE,
        _REFRESH_COOKIE,
        _ADMIN_ORIGINAL_ACCESS_COOKIE,
        _ADMIN_ORIGINAL_REFRESH_COOKIE,
    ):
        _delete_cookie(response, request, cookie_name)
    return response
