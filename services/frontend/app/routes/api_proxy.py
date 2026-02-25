"""API proxy routes.

Single-origin reverse-proxy that forwards browser requests to the
appropriate backend micro-service.  The proxy transparently passes
query parameters, headers (except ``Host`` / ``Content-Length``),
and request bodies.

Route mapping
-------------
/api/auth/*        -> auth-service       :8005
/api/users/*       -> user-bl-service    :8004
/api/employees/*   -> user-bl-service    :8004
/api/customers/*   -> customer-bl-service:8007
/api/notes/*       -> customer-bl-service:8007
/api/admin/*       -> admin-bl-service   :8008  (superadmin only)
/api/jobs/*        -> job-bl-service     :8006
/api/jobs/calendar -> job-bl-service     :8006  (specific -- before catch-all)
/api/jobs/queue    -> job-bl-service     :8006  (specific -- before catch-all)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

# Add shared package to the module search path.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from common.config import settings  # noqa: E402

router = APIRouter(tags=["api-proxy"])

# Shared async HTTP client -- reused across all proxy calls.
_http_client = httpx.AsyncClient(timeout=30.0)

# HTTP methods that carry a request body.
_BODY_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH"})

# Headers that must NOT be forwarded to upstream services.
_HOP_BY_HOP: frozenset[str] = frozenset({"host", "content-length"})


# -- Core proxy helper --------------------------------------------------------

async def proxy_request(
    service_url: str,
    path: str,
    request: Request,
    method: str = "GET",
) -> JSONResponse:
    """Forward an incoming request to a backend micro-service.

    Args:
        service_url: Base URL of the target service
                     (e.g. ``http://auth-service:8005``).
        path:        Path to append (e.g. ``/api/v1/auth/login``).
        request:     The original browser request.
        method:      HTTP verb to use (``GET``, ``POST``, ...).

    Returns:
        A ``JSONResponse`` mirroring the upstream status code and body.

    Raises:
        HTTPException: 503 if the service is unreachable, 500 on any
                       other transport error.
    """
    url: str = f"{service_url}{path}"

    # Forward query string.
    query_params: dict[str, str] = dict(request.query_params)

    # Forward body only for methods that expect one.
    body: bytes | None = await request.body() if method in _BODY_METHODS else None

    # Forward headers (strip hop-by-hop).
    headers: dict[str, str] = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }

    try:
        response: httpx.Response = await _http_client.request(
            method=method,
            url=url,
            params=query_params,
            content=body,
            headers=headers,
        )

        # Parse JSON when there is a body; return None otherwise.
        content: Any = response.json() if response.content else None
        return JSONResponse(content=content, status_code=response.status_code)

    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend service unavailable",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


# -- Auth Service  (/api/auth/*) ----------------------------------------------

@router.api_route("/auth/{path:path}", methods=["GET", "POST"])
async def proxy_auth_service(path: str, request: Request) -> JSONResponse:
    """Forward authentication requests to **auth-service** (:8005)."""
    return await proxy_request(
        settings.auth_service_url,
        f"/api/v1/auth/{path}" if path else "/api/v1/auth",
        request,
        request.method,
    )


# -- User Service  (/api/users/* , /api/employees/*) --------------------------

@router.api_route("/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_user_service(path: str, request: Request) -> JSONResponse:
    """Forward user requests to **user-bl-service** (:8004)."""
    return await proxy_request(
        settings.user_bl_service_url,
        f"/api/v1/users/{path}" if path else "/api/v1/users",
        request,
        request.method,
    )


@router.api_route("/employees/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_employee_service(path: str, request: Request) -> JSONResponse:
    """Forward employee requests to **user-bl-service** (:8004)."""
    return await proxy_request(
        settings.user_bl_service_url,
        f"/api/v1/employees/{path}" if path else "/api/v1/employees",
        request,
        request.method,
    )


# -- Customer Service  (/api/customers/*) -------------------------------------

@router.api_route("/customers/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_customer_service(path: str, request: Request) -> JSONResponse:
    """Forward customer requests to **customer-bl-service** (:8007)."""
    return await proxy_request(
        settings.customer_bl_service_url,
        f"/api/v1/customers/{path}" if path else "/api/v1/customers",
        request,
        request.method,
    )


@router.api_route("/notes/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_notes_service(path: str, request: Request) -> JSONResponse:
    """Forward customer-note requests to **customer-bl-service** (:8007)."""
    return await proxy_request(
        settings.customer_bl_service_url,
        f"/api/v1/notes/{path}" if path else "/api/v1/notes",
        request,
        request.method,
    )


# -- Admin Service  (/api/admin/*) ---------------------------------------------

@router.api_route("/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_admin_service(path: str, request: Request) -> JSONResponse:
    """Forward admin requests to **admin-bl-service** (:8008).

    All endpoints behind this proxy require the ``superadmin`` role.
    Access control is enforced by the admin-bl-service itself.
    """
    return await proxy_request(
        settings.admin_bl_service_url,
        f"/api/v1/admin/{path}" if path else "/api/v1/admin",
        request,
        request.method,
    )


# -- Job Service  (/api/jobs/*) -----------------------------------------------
# Specific endpoints MUST be registered before the catch-all ``{path:path}``
# route, otherwise FastAPI will never match them.

@router.get("/jobs/calendar")
async def proxy_calendar_jobs(request: Request) -> JSONResponse:
    """Forward calendar-view requests to **job-bl-service** (:8006)."""
    return await proxy_request(
        settings.job_bl_service_url,
        "/api/v1/jobs/calendar",
        request,
        "GET",
    )


@router.get("/jobs/queue")
async def proxy_job_queue(request: Request) -> JSONResponse:
    """Forward job-queue requests to **job-bl-service** (:8006)."""
    return await proxy_request(
        settings.job_bl_service_url,
        "/api/v1/jobs/queue",
        request,
        "GET",
    )


@router.api_route("/jobs/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_job_service(path: str, request: Request) -> JSONResponse:
    """Forward general job requests to **job-bl-service** (:8006)."""
    return await proxy_request(
        settings.job_bl_service_url,
        f"/api/v1/jobs/{path}" if path else "/api/v1/jobs",
        request,
        request.method,
    )
