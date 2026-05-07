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
/api/company/*     -> user-bl-service    :8004  (company CRUD)
/api/permissions/* -> user-bl-service    :8004  (permission catalog)
/api/customers/*   -> customer-bl-service:8007
/api/notes/*       -> customer-bl-service:8007
/api/admin/*       -> admin-bl-service   :8008  (superadmin only)
/api/maps/*        -> maps-access-service:8009  (geocoding, eircode lookup)
/api/jobs/*        -> job-bl-service     :8006
/api/jobs/calendar -> job-bl-service     :8006  (specific -- before catch-all)
/api/jobs/queue    -> job-bl-service     :8006  (specific -- before catch-all)
"""

from __future__ import annotations

import json
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

# Auth cookie names managed by the frontend proxy.
_ACCESS_COOKIE = "wp_access_token"
_REFRESH_COOKIE = "wp_refresh_token"
_ADMIN_ORIGINAL_ACCESS_COOKIE = "wp_admin_original_access_token"
_ADMIN_ORIGINAL_REFRESH_COOKIE = "wp_admin_original_refresh_token"


def _is_secure_request(request: Request) -> bool:
    """Return whether auth cookies should use the Secure flag.

    In production behind NGINX/TLS, ``X-Forwarded-Proto`` is preferred.
    Local HTTP development remains functional with ``secure=False``.
    """
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.lower() == "https"
    return request.url.scheme == "https"


def _set_cookie(
    response: JSONResponse,
    request: Request,
    name: str,
    value: str,
    *,
    max_age: int,
) -> None:
    """Set a security-hardened auth cookie."""
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        httponly=True,
        secure=_is_secure_request(request),
        samesite="lax",
        path="/",
    )


def _delete_cookie(response: JSONResponse, request: Request, name: str) -> None:
    """Delete a cookie using the same attributes as creation."""
    response.delete_cookie(
        key=name,
        path="/",
        secure=_is_secure_request(request),
        httponly=True,
        samesite="lax",
    )


def _extract_json_body(raw_body: bytes) -> dict[str, Any]:
    """Decode request/response JSON bytes into a dict safely."""
    if not raw_body:
        return {}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _sanitized_auth_content(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Strip raw tokens from auth responses before returning to the browser."""
    if path in {"login", "refresh", "impersonate"}:
        return {
            key: value
            for key, value in payload.items()
            if key not in {"access_token", "refresh_token"}
        }
    return payload


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
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP
    }

    # If the browser has no explicit Authorization header, promote the
    # HttpOnly access token cookie to a Bearer token for upstream services.
    if "authorization" not in {k.lower() for k in headers}:
        access_token = request.cookies.get(_ACCESS_COOKIE)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

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
    except Exception:
        # Generic message — never leak internal exception details to clients.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# -- Auth Service  (/api/auth/*) ----------------------------------------------


@router.api_route("/auth/{path:path}", methods=["GET", "POST"])
async def proxy_auth_service(path: str, request: Request) -> JSONResponse:
    """Forward authentication requests to **auth-service** (:8005).

    This proxy endpoint also manages secure token cookies so browser JS
    never needs to persist raw JWT/refresh tokens in localStorage.
    """
    auth_path = f"/api/v1/auth/{path}" if path else "/api/v1/auth"

    query_params: dict[str, str] = dict(request.query_params)
    headers: dict[str, str] = {
        k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP
    }
    if "authorization" not in {k.lower() for k in headers}:
        access_token = request.cookies.get(_ACCESS_COOKIE)
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

    raw_body = await request.body() if request.method in _BODY_METHODS else b""
    body_data = _extract_json_body(raw_body)

    # Pull refresh/access tokens from HttpOnly cookies when callers send
    # empty bodies (or bodies without token fields).
    if path == "refresh" and request.method == "POST":
        if "refresh_token" not in body_data:
            refresh_token = request.cookies.get(_REFRESH_COOKIE)
            if refresh_token:
                body_data["refresh_token"] = refresh_token
        raw_body = json.dumps(body_data).encode("utf-8") if body_data else raw_body

    if path == "logout" and request.method == "POST":
        if "refresh_token" not in body_data:
            refresh_token = request.cookies.get(_REFRESH_COOKIE)
            if refresh_token:
                body_data["refresh_token"] = refresh_token
        if "access_token" not in body_data:
            access_token = request.cookies.get(_ACCESS_COOKIE)
            if access_token:
                body_data["access_token"] = access_token
        raw_body = json.dumps(body_data).encode("utf-8") if body_data else raw_body

    try:
        response = await _http_client.request(
            method=request.method,
            url=f"{settings.auth_service_url}{auth_path}",
            params=query_params,
            content=raw_body if request.method in _BODY_METHODS else None,
            headers=headers,
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend service unavailable",
        )
    except Exception:
        # Generic message — never leak internal exception details to clients.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )

    content: dict[str, Any] = response.json() if response.content else {}
    if not isinstance(content, dict):
        content = {}

    client_response = JSONResponse(
        content=_sanitized_auth_content(path, content),
        status_code=response.status_code,
    )

    if response.status_code == 200 and path == "login":
        access_token = content.get("access_token")
        refresh_token = content.get("refresh_token")
        if isinstance(access_token, str) and access_token:
            _set_cookie(
                client_response,
                request,
                _ACCESS_COOKIE,
                access_token,
                max_age=settings.access_token_expire_minutes * 60,
            )
        if isinstance(refresh_token, str) and refresh_token:
            _set_cookie(
                client_response,
                request,
                _REFRESH_COOKIE,
                refresh_token,
                max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
            )

    if response.status_code == 200 and path == "refresh":
        access_token = content.get("access_token")
        refresh_token = content.get("refresh_token")
        if isinstance(access_token, str) and access_token:
            _set_cookie(
                client_response,
                request,
                _ACCESS_COOKIE,
                access_token,
                max_age=settings.access_token_expire_minutes * 60,
            )
        if isinstance(refresh_token, str) and refresh_token:
            _set_cookie(
                client_response,
                request,
                _REFRESH_COOKIE,
                refresh_token,
                max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
            )

    if response.status_code == 200 and path == "impersonate":
        current_access = request.cookies.get(_ACCESS_COOKIE)
        current_refresh = request.cookies.get(_REFRESH_COOKIE)
        impersonated_access = content.get("access_token")

        if isinstance(current_access, str) and current_access:
            _set_cookie(
                client_response,
                request,
                _ADMIN_ORIGINAL_ACCESS_COOKIE,
                current_access,
                max_age=settings.access_token_expire_minutes * 60,
            )
        if isinstance(current_refresh, str) and current_refresh:
            _set_cookie(
                client_response,
                request,
                _ADMIN_ORIGINAL_REFRESH_COOKIE,
                current_refresh,
                max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
            )

        if isinstance(impersonated_access, str) and impersonated_access:
            _set_cookie(
                client_response,
                request,
                _ACCESS_COOKIE,
                impersonated_access,
                max_age=settings.access_token_expire_minutes * 60,
            )
            # Impersonation tokens have no refresh contract; force explicit
            # return-to-admin rather than silent refresh.
            _delete_cookie(client_response, request, _REFRESH_COOKIE)

    if response.status_code == 200 and path == "logout":
        _delete_cookie(client_response, request, _ACCESS_COOKIE)
        _delete_cookie(client_response, request, _REFRESH_COOKIE)
        _delete_cookie(client_response, request, _ADMIN_ORIGINAL_ACCESS_COOKIE)
        _delete_cookie(client_response, request, _ADMIN_ORIGINAL_REFRESH_COOKIE)

    return client_response


@router.post("/auth/impersonation/return")
async def return_from_impersonation(request: Request) -> JSONResponse:
    """Restore the original superadmin session after impersonation."""
    original_access = request.cookies.get(_ADMIN_ORIGINAL_ACCESS_COOKIE)
    original_refresh = request.cookies.get(_ADMIN_ORIGINAL_REFRESH_COOKIE)

    response = JSONResponse(content={"ok": True}, status_code=status.HTTP_200_OK)

    if not original_access:
        response = JSONResponse(
            content={"detail": "No stored admin session"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        _delete_cookie(response, request, _ADMIN_ORIGINAL_ACCESS_COOKIE)
        _delete_cookie(response, request, _ADMIN_ORIGINAL_REFRESH_COOKIE)
        return response

    _set_cookie(
        response,
        request,
        _ACCESS_COOKIE,
        original_access,
        max_age=settings.access_token_expire_minutes * 60,
    )
    if original_refresh:
        _set_cookie(
            response,
            request,
            _REFRESH_COOKIE,
            original_refresh,
            max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        )

    _delete_cookie(response, request, _ADMIN_ORIGINAL_ACCESS_COOKIE)
    _delete_cookie(response, request, _ADMIN_ORIGINAL_REFRESH_COOKIE)

    return response


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


# -- Company & Permissions (user-bl-service) -----------------------------------


@router.api_route("/company", methods=["GET", "PUT"])
@router.api_route("/company/{path:path}", methods=["GET", "PUT"])
async def proxy_company_service(request: Request, path: str = "") -> JSONResponse:
    """Forward company requests to **user-bl-service** (:8004).

    Maps ``/api/company`` → ``/api/v1/company`` on user-bl-service.
    """
    target = f"/api/v1/company/{path}" if path else "/api/v1/company"
    return await proxy_request(
        settings.user_bl_service_url,
        target,
        request,
        request.method,
    )


@router.api_route("/permissions/{path:path}", methods=["GET"])
async def proxy_permissions_service(path: str, request: Request) -> JSONResponse:
    """Forward permission catalog requests to **user-bl-service** (:8004).

    Maps ``/api/permissions/catalog`` → ``/api/v1/permissions/catalog``
    on user-bl-service.
    """
    return await proxy_request(
        settings.user_bl_service_url,
        f"/api/v1/permissions/{path}" if path else "/api/v1/permissions",
        request,
        request.method,
    )


@router.api_route("/audit-logs", methods=["GET"])
@router.api_route("/audit-logs/{path:path}", methods=["GET"])
async def proxy_audit_logs_service(request: Request, path: str = "") -> JSONResponse:
    """Forward tenant audit-log requests to **user-bl-service** (:8004)."""
    target = f"/api/v1/audit-logs/{path}" if path else "/api/v1/audit-logs"
    return await proxy_request(
        settings.user_bl_service_url,
        target,
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


# -- Notification Service  (/api/notifications/*) ------------------------------


@router.api_route(
    "/notifications/{path:path}", methods=["GET", "POST", "PUT", "DELETE"]
)
async def proxy_notification_service(path: str, request: Request) -> JSONResponse:
    """Forward notification requests to **notification-service** (:8011)."""
    return await proxy_request(
        settings.notification_service_url,
        f"/api/v1/notifications/{path}" if path else "/api/v1/notifications",
        request,
        request.method,
    )


# -- Maps Service  (/api/maps/*) -----------------------------------------------


@router.api_route("/maps/{path:path}", methods=["GET", "POST"])
async def proxy_maps_service(path: str, request: Request) -> JSONResponse:
    """Forward geocoding/eircode requests to **maps-access-service** (:8009)."""
    return await proxy_request(
        settings.maps_service_url,
        f"/api/v1/maps/{path}" if path else "/api/v1/maps",
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


@router.api_route(
    "/jobs/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"]
)
async def proxy_job_service(path: str, request: Request) -> JSONResponse:
    """Forward general job requests to **job-bl-service** (:8006)."""
    return await proxy_request(
        settings.job_bl_service_url,
        f"/api/v1/jobs/{path}" if path else "/api/v1/jobs",
        request,
        request.method,
    )
