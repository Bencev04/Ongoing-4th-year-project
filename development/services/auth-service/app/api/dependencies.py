"""
Dependencies for Auth Service routes.

Provides reusable FastAPI dependency functions for token
extraction, validation, and tenant context injection.

All database interactions are fully async.
The token blacklist is checked via Redis for sub-millisecond
lookups, with a Postgres fallback when Redis is unavailable.
"""

import sys

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append("../../../shared")
from common.database import get_async_db

from ..crud.auth import decode_access_token, is_token_blacklisted
from ..schemas.auth import TokenPayload

# Reusable HTTP Bearer scheme (auto-populates OpenAPI security)
_bearer_scheme = HTTPBearer(auto_error=False)


def get_token_from_request(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """
    Extract the Bearer token string from the ``Authorization`` header.

    Raises:
        HTTPException 401 if the header is missing or malformed.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def get_current_user(
    token: str = Depends(get_token_from_request),
    db: AsyncSession = Depends(get_async_db),
) -> TokenPayload:
    """
    Validate the access token and return the decoded payload.

    Steps:
        1. Decode the JWT (checks signature + expiry).
        2. Verify the ``jti`` is not in the blacklist (Redis → Postgres).

    Returns:
        ``TokenPayload`` with user / tenant context.

    Raises:
        HTTPException 401 if the token is invalid, expired, or blacklisted.
    """
    payload: TokenPayload | None = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check blacklist (Redis first, Postgres fallback)
    if await is_token_blacklisted(payload.jti, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def require_role(*allowed_roles: str):
    """
    Factory that returns a dependency enforcing role-based access.

    Usage::

        @router.get("/admin-only", dependencies=[Depends(require_role("owner", "admin"))])
        async def admin_endpoint(): ...

    Args:
        allowed_roles: One or more role strings that are permitted.

    Returns:
        A FastAPI dependency callable.
    """

    # Pre-compute the minimum required level so superadmins always pass
    role_hierarchy: dict[str, int] = {
        "superadmin": 100,
        "owner": 80,
        "admin": 60,
        "manager": 40,
        "employee": 20,
        "viewer": 10,
    }
    min_level: int = min(role_hierarchy.get(r, 0) for r in allowed_roles)

    async def _role_checker(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        user_level: int = role_hierarchy.get(current_user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action",
            )
        return current_user

    return _role_checker


def get_client_ip(request: Request) -> str | None:
    """
    Best-effort extraction of the client's IP address.

    Checks ``X-Forwarded-For`` first (for reverse-proxy setups),
    then falls back to the direct connection address.
    """
    forwarded: str | None = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
