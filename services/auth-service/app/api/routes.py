"""
API routes for Auth Service.

Defines all HTTP endpoints for authentication, token management,
and session control.  This is the single source of truth for
identity in the CRM Calendar platform.

All route handlers are fully **async** — database operations use
``AsyncSession`` and the token blacklist leverages Redis.

Endpoint summary
----------------
POST /api/v1/auth/login           – Exchange credentials for tokens.
POST /api/v1/auth/refresh         – Obtain a new access token.
POST /api/v1/auth/verify          – Validate a token (service-to-service).
POST /api/v1/auth/logout          – Revoke a single session.
POST /api/v1/auth/revoke-all      – Revoke every session for a user.
POST /api/v1/auth/change-password – Change the user's password.
POST /api/v1/auth/reset-password  – Reset another user's password (admin).
GET  /api/v1/auth/me              – Return the current user's context.
GET  /api/v1/health               – Health check for load balancers.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.append("../../../shared")
from common.database import get_async_db
from common.config import settings
from common.schemas import HealthResponse
from common.audit import log_action

from ..schemas.auth import (
    ImpersonateRequest,
    ImpersonateResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    PasswordChangeRequest,
    PasswordResetRequest,
    RevokeAllRequest,
    TokenPayload,
    TokenRefreshRequest,
    TokenRefreshResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
)
from ..crud.auth import (
    create_access_token,
    create_impersonation_token,
    create_refresh_token,
    decode_access_token,
    store_refresh_token,
    verify_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    blacklist_access_token,
    is_token_blacklisted,
    cleanup_expired_tokens,
)
from .dependencies import get_current_user, get_client_ip, require_role

logger = logging.getLogger(__name__)

# Create router with prefix
router = APIRouter(prefix="/api/v1", tags=["auth"])

# Async HTTP client for calling user-db-access-service
_http_client = httpx.AsyncClient(timeout=10.0)


# ==============================================================================
# Health Check
# ==============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns service health status for monitoring and load balancers.
    """
    return HealthResponse(
        status="healthy",
        service="auth-service",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc),
    )


# ==============================================================================
# Login
# ==============================================================================

@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> LoginResponse:
    """
    Authenticate a user and return access + refresh tokens.

    Delegates credential verification to the user-db-access-service
    so this service never touches the users table directly.

    Raises:
        HTTPException 401 if credentials are invalid.
        HTTPException 503 if user-db-access-service is unreachable.
    """
    # ---- Call user-db-access-service to validate credentials ----
    user_svc_url: str = settings.user_service_url

    try:
        auth_resp = await _http_client.post(
            f"{user_svc_url}/api/v1/internal/authenticate",
            json={"email": body.email, "password": body.password},
        )
    except httpx.RequestError:
        logger.error("User service unreachable at %s", user_svc_url)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service is unavailable",
        )

    if auth_resp.status_code != 200:
        logger.warning("User service returned %d during login", auth_resp.status_code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service returned an unexpected status",
        )

    user_data: dict = auth_resp.json()

    # The /internal/authenticate endpoint ALWAYS returns 200.
    # A failed login is indicated by authenticated=False.
    if not user_data.get("authenticated"):
        logger.info("Failed login attempt for %s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    user_id: int = user_data["user_id"]
    email: str = user_data["email"]
    role: str = user_data["role"]
    # For an owner, owner_id is their own ID.
    # For employees, owner_id is the owner they belong to.
    # For superadmins, owner_id is None (they sit outside tenants).
    raw_owner_id = user_data.get("owner_id")
    if raw_owner_id is None:
        # DB returned NULL — set based on role
        owner_id: Optional[int] = user_id if role != "superadmin" else None
    else:
        # DB returned an actual owner_id value
        owner_id = raw_owner_id
    company_id: Optional[int] = user_data.get("company_id")
    organization_id: Optional[int] = user_data.get("organization_id")

    # ---- Create tokens ----
    access_token, jti, expires_at = create_access_token(
        user_id=user_id,
        email=email,
        role=role,
        owner_id=owner_id,
        company_id=company_id,
        organization_id=organization_id,
    )

    raw_refresh: str = create_refresh_token()
    client_ip: Optional[str] = get_client_ip(request)

    await store_refresh_token(
        db=db,
        user_id=user_id,
        owner_id=owner_id or 0,
        raw_token=raw_refresh,
        device_info=body.device_info,
        ip_address=client_ip,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        user_id=user_id,
        owner_id=owner_id,
        company_id=company_id,
        organization_id=organization_id,
        role=role,
    )


# ==============================================================================
# Refresh
# ==============================================================================

@router.post("/auth/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    body: TokenRefreshRequest,
    db: AsyncSession = Depends(get_async_db),
) -> TokenRefreshResponse:
    """
    Exchange a valid refresh token for a new access token.

    The refresh token itself is **not** rotated in this implementation;
    rotation can be added for higher security if required.

    Raises:
        HTTPException 401 if the refresh token is invalid or revoked.
    """
    db_token = await verify_refresh_token(db, body.refresh_token)

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    # Fetch the user's current email and role from user-db-access-service
    # so the new access token contains accurate claims.
    user_svc_url: str = settings.user_service_url
    email: str = ""
    role: str = ""
    company_id: Optional[int] = None
    organization_id: Optional[int] = None

    try:
        user_resp = await _http_client.get(
            f"{user_svc_url}/api/v1/users/{db_token.user_id}",
        )
        if user_resp.status_code == 200:
            user_info: dict = user_resp.json()
            email = user_info.get("email", "")
            role = user_info.get("role", "")
            company_id = user_info.get("company_id")
            organization_id = user_info.get("organization_id")
        else:
            logger.warning(
                "Could not fetch user %d for refresh (status %d)",
                db_token.user_id,
                user_resp.status_code,
            )
    except httpx.RequestError:
        logger.error(
            "User service unreachable during token refresh for user %d",
            db_token.user_id,
        )

    access_token, _jti, _expires = create_access_token(
        user_id=db_token.user_id,
        email=email,
        role=role,
        owner_id=db_token.owner_id,
        company_id=company_id,
        organization_id=organization_id,
    )

    return TokenRefreshResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


# ==============================================================================
# Verify (Service-to-Service)
# ==============================================================================

@router.post("/auth/verify", response_model=TokenVerifyResponse)
async def verify_token(
    body: TokenVerifyRequest,
    db: AsyncSession = Depends(get_async_db),
) -> TokenVerifyResponse:
    """
    Validate an access token and return tenant context.

    This endpoint is called by other microservices to validate tokens
    without needing to share the JWT signing secret.

    Returns a ``TokenVerifyResponse`` with ``valid=False`` if the
    token fails any check rather than raising an HTTP error.
    """
    payload: Optional[TokenPayload] = decode_access_token(body.access_token)

    if payload is None:
        return TokenVerifyResponse(
            valid=False,
            message="Invalid or expired token",
        )

    if await is_token_blacklisted(payload.jti, db):
        return TokenVerifyResponse(
            valid=False,
            message="Token has been revoked",
        )

    return TokenVerifyResponse(
        valid=True,
        user_id=int(payload.sub),
        email=payload.email,
        role=payload.role,
        owner_id=payload.owner_id,
        company_id=payload.company_id,
        organization_id=payload.organization_id,
        acting_as=payload.acting_as,
        impersonator_id=payload.impersonator_id,
        message="Token is valid",
    )


# ==============================================================================
# Logout
# ==============================================================================

@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    Revoke the refresh token (and optionally blacklist the access token).

    Raises:
        HTTPException 401 if the refresh token is already invalid.
    """
    revoked: bool = await revoke_refresh_token(db, body.refresh_token)

    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or already revoked",
        )

    # Optionally blacklist the access token so it cannot be used
    # for the remainder of its TTL.
    if body.access_token:
        payload = decode_access_token(body.access_token)
        if payload:
            await blacklist_access_token(
                db=db,
                jti=payload.jti,
                user_id=int(payload.sub),
                expires_at=datetime.fromtimestamp(payload.exp, tz=timezone.utc),
            )


# ==============================================================================
# Revoke All Sessions
# ==============================================================================

@router.post("/auth/revoke-all", status_code=status.HTTP_200_OK)
async def revoke_all_sessions(
    body: RevokeAllRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Revoke every refresh token for a user (logout everywhere).

    Only the user themselves or an owner/admin of their tenant
    may perform this action.  Superadmins can revoke for any user.

    Security:
        Cross-tenant revocation is blocked — owners/admins can only
        revoke tokens for users within their own tenant.  The
        ``owner_id`` check ensures tenant boundary enforcement.

    Returns:
        JSON with ``revoked_count``.
    """
    is_superadmin: bool = current_user.role == "superadmin"

    # Security: regular users can only revoke their own tokens
    if (
        not is_superadmin
        and current_user.role not in ("owner", "admin")
        and int(current_user.sub) != body.user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only revoke your own sessions",
        )

    # Security: cross-tenant protection — verify the target user
    # belongs to the same tenant (unless superadmin)
    if not is_superadmin and int(current_user.sub) != body.user_id:
        user_svc_url: str = settings.user_service_url
        try:
            user_resp = await _http_client.get(
                f"{user_svc_url}/api/v1/users/{body.user_id}",
            )
            if user_resp.status_code == 200:
                target_user: dict = user_resp.json()
                target_owner_id = target_user.get("owner_id") or target_user.get("id")
                if target_owner_id != current_user.owner_id:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cannot revoke sessions for users in a different tenant",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target user not found",
                )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User service is unavailable",
            )

    count: int = await revoke_all_user_tokens(db, body.user_id)
    return {"revoked_count": count}


# ==============================================================================
# Current User Context
# ==============================================================================

@router.get("/auth/me", response_model=TokenVerifyResponse)
async def get_me(
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenVerifyResponse:
    """
    Return the authenticated user's context from the access token.

    Useful for the frontend to verify who is logged in without
    a round-trip to the user service.
    """
    return TokenVerifyResponse(
        valid=True,
        user_id=int(current_user.sub),
        email=current_user.email,
        role=current_user.role,
        owner_id=current_user.owner_id,
        company_id=current_user.company_id,
        organization_id=current_user.organization_id,
        acting_as=current_user.acting_as,
        impersonator_id=current_user.impersonator_id,
        message="Authenticated",
    )


# ==============================================================================
# Password Change
# ==============================================================================

@router.post("/auth/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    body: PasswordChangeRequest,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """
    Change the authenticated user's password.

    Validates the current password and updates to the new password.
    Delegates the actual password verification and update to the
    user-db-access-service.

    Returns:
        Success message on password change.

    Raises:
        HTTPException 401: If current password is incorrect.
        HTTPException 400: If new password is invalid.
        HTTPException 503: If user service is unavailable.
    """
    user_id = int(current_user.sub)
    user_svc_url: str = settings.user_service_url

    # Verify current password by calling the internal authenticate endpoint
    try:
        auth_resp = await _http_client.post(
            f"{user_svc_url}/api/v1/internal/authenticate",
            json={"email": current_user.email, "password": body.current_password},
            timeout=5.0,
        )
        
        if auth_resp.status_code == 200:
            auth_data = auth_resp.json()
            if not auth_data.get("authenticated"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Current password is incorrect",
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect",
            )
    except httpx.RequestError:
        logger.error("User service unavailable during password verification")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service is unavailable",
        )

    # Update to new password
    try:
        update_resp = await _http_client.put(
            f"{user_svc_url}/api/v1/users/{user_id}/password",
            json={"new_password": body.new_password},
            timeout=5.0,
        )
        
        if update_resp.status_code != 200:
            error_data = update_resp.json() if update_resp.status_code < 500 else {}
            raise HTTPException(
                status_code=update_resp.status_code,
                detail=error_data.get("detail", "Failed to update password"),
            )
    except httpx.RequestError:
        logger.error("User service unavailable during password update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service is unavailable",
        )

    logger.info(f"Password changed successfully for user_id={user_id}")
    return {"message": "Password changed successfully"}


# ==============================================================================
# Password Reset (Admin/Owner/Superadmin)
# ==============================================================================

@router.post(
    "/auth/reset-password",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_role("owner", "admin"))],
)
async def reset_password(
    body: PasswordResetRequest,
    current_user: TokenPayload = Depends(get_current_user),
) -> dict:
    """
    Reset another user's password (admin/owner/superadmin only).

    This endpoint allows administrators to set a new password for a user
    without requiring the current password. Useful for password recovery
    or account setup.

    Authorization rules:
    - Superadmin: Can reset any user's password
    - Owner/Admin: Can only reset passwords for users in their organization

    Returns:
        Success message on password reset.

    Raises:
        HTTPException 403: If trying to reset password outside tenant.
        HTTPException 404: If user not found.
        HTTPException 503: If user service is unavailable.
    """
    user_svc_url: str = settings.user_service_url
    is_superadmin = current_user.role == "superadmin"

    # Fetch target user to verify permissions
    try:
        user_resp = await _http_client.get(
            f"{user_svc_url}/api/v1/users/{body.user_id}",
            timeout=5.0,
        )
        
        if user_resp.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        
        if user_resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="User service is unavailable",
            )
        
        target_user = user_resp.json()
        
        # Authorization check: non-superadmins can only reset passwords in their org
        if not is_superadmin:
            target_owner_id = target_user.get("owner_id") or target_user.get("id")
            if target_owner_id != current_user.owner_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot reset password for users in a different organization",
                )
    except httpx.RequestError:
        logger.error("User service unavailable during password reset")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service is unavailable",
        )

    # Update password
    try:
        update_resp = await _http_client.put(
            f"{user_svc_url}/api/v1/users/{body.user_id}/password",
            json={"new_password": body.new_password},
            timeout=5.0,
        )
        
        if update_resp.status_code != 200:
            error_data = update_resp.json() if update_resp.status_code < 500 else {}
            raise HTTPException(
                status_code=update_resp.status_code,
                detail=error_data.get("detail", "Failed to reset password"),
            )
    except httpx.RequestError:
        logger.error("User service unavailable during password update")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service is unavailable",
        )

    logger.info(
        f"Password reset for user_id={body.user_id} by {current_user.role} user_id={current_user.sub}"
    )
    return {"message": "Password reset successfully"}


# ==============================================================================
# Impersonation (Superadmin Only)
# ==============================================================================

@router.post("/auth/impersonate", response_model=ImpersonateResponse)
async def impersonate_user(
    body: ImpersonateRequest,
    current_user: TokenPayload = Depends(get_current_user),
) -> ImpersonateResponse:
    """
    Create a shadow access token for impersonating another user.

    **Superadmin only.**  The shadow token behaves like a normal
    access token for the target user but carries an ``impersonator_id``
    claim so every downstream action is attributed to the superadmin
    in the audit trail.

    Security:
        - Only the ``superadmin`` role may call this endpoint.
        - A superadmin cannot impersonate another superadmin.
        - Shadow tokens have a deliberately short lifetime (15 min).
        - The original superadmin’s user ID is always preserved in
          ``impersonator_id`` for traceability.

    Raises:
        HTTPException 403 if the caller is not a superadmin.
        HTTPException 403 if attempting to impersonate a superadmin.
        HTTPException 404 if the target user does not exist.
        HTTPException 503 if user service is unreachable.
    """
    # ---- Authorisation: superadmin only ----
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmins can impersonate users",
        )

    # ---- Fetch the target user from user-db-access-service ----
    user_svc_url: str = settings.user_service_url
    try:
        resp = await _http_client.get(
            f"{user_svc_url}/api/v1/users/{body.target_user_id}",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service is unavailable",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {body.target_user_id} not found",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service returned an unexpected status",
        )

    target: dict = resp.json()

    # ---- Prevent superadmin-to-superadmin impersonation ----
    if target.get("role") == "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot impersonate another superadmin",
        )

    # ---- Build the shadow token ----
    target_owner_id: Optional[int] = target.get("owner_id") or target.get("id")

    shadow_token, jti, expires_at = create_impersonation_token(
        target_user_id=body.target_user_id,
        target_email=target["email"],
        target_role=target["role"],
        target_owner_id=target_owner_id,
        target_company_id=target.get("company_id"),
        target_organization_id=target.get("organization_id"),
        impersonator_id=int(current_user.sub),
    )

    logger.info(
        "Superadmin %s (id=%s) impersonating user %d (%s). Reason: %s",
        current_user.email,
        current_user.sub,
        body.target_user_id,
        target["email"],
        body.reason or "(none given)",
    )

    # ---- Audit trail: record impersonation in immutable log ----
    class _AuditActor:
        """Lightweight actor adapter for audit logging."""
        def __init__(self, payload: TokenPayload) -> None:
            self.user_id = int(payload.sub)
            self.email = payload.email
            self.role = payload.role
            self.impersonator_id = None

    await log_action(
        actor=_AuditActor(current_user),
        action="auth.impersonate",
        resource_type="user",
        resource_id=str(body.target_user_id),
        details={
            "target_email": target["email"],
            "target_role": target["role"],
            "reason": body.reason or "(none given)",
        },
    )

    return ImpersonateResponse(
        access_token=shadow_token,
        token_type="bearer",
        expires_in=15 * 60,  # 15-minute shadow tokens
        impersonating=body.target_user_id,
        impersonator_id=int(current_user.sub),
    )


# ==============================================================================
# Maintenance (Admin Only)
# ==============================================================================

@router.post(
    "/auth/cleanup",
    dependencies=[Depends(require_role("owner", "admin"))],
    status_code=status.HTTP_200_OK,
)
async def run_token_cleanup(
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Prune expired tokens from the database.

    Security: restricted to owner, admin, and superadmin roles.
    Superadmins pass via the role hierarchy in ``require_role``.

    In production this would be triggered by a scheduler, but
    exposing it as an endpoint simplifies manual maintenance.
    """
    result: dict[str, int] = await cleanup_expired_tokens(db)
    return result
