"""
API routes for Admin BL Service.

**All endpoints require the ``superadmin`` role.**

This service is the single entry point for platform-level
administration.  It delegates data operations to
``user-db-access-service`` and writes audit log entries
for every state-changing action.

Endpoint summary
----------------
GET    /api/v1/admin/organizations          – List all organizations.
POST   /api/v1/admin/organizations          – Create an organization.
GET    /api/v1/admin/organizations/{id}     – Get a single organization.
PUT    /api/v1/admin/organizations/{id}     – Update an organization.
DELETE /api/v1/admin/organizations/{id}     – Delete an organization.
POST   /api/v1/admin/organizations/{id}/suspend   – Suspend an org.
POST   /api/v1/admin/organizations/{id}/unsuspend – Reactivate an org.

GET    /api/v1/admin/audit-logs             – Query audit logs.

GET    /api/v1/admin/settings               – List platform settings.
GET    /api/v1/admin/settings/{key}         – Get a single setting.
PUT    /api/v1/admin/settings/{key}         – Update a setting.

GET    /api/v1/admin/users                  – Cross-tenant user list.
GET    /api/v1/admin/users/{id}             – Get any user by ID.

GET    /api/v1/health                       – Health check.
"""

import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from common.health import HealthChecker
from common.schemas import HealthResponse

from .. import service_client
from ..dependencies import CurrentUser, require_superadmin
from ..schemas import (
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
    AuditLogListResponse,
    MessageResponse,
    OrganizationCreateRequest,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
    PlatformSettingResponse,
    PlatformSettingsListResponse,
    PlatformSettingUpdateRequest,
    SuspendRequest,
)

logger = logging.getLogger(__name__)

# All routes require superadmin — enforced via dependency
router = APIRouter(prefix="/api/v1", tags=["admin"])


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("admin-bl-service", "1.0.0")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness probe — is the service running?

    K8s uses this to determine if the container should be restarted.
    Returns quickly without checking external dependencies.
    """
    return await _health_checker.liveness_probe()


@router.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """
    Readiness probe — can the service handle traffic?

    K8s uses this to determine if the pod should receive traffic.
    Checks dependent services and Redis.
    """
    return await _health_checker.readiness_probe(
        db=None,  # Admin BL doesn't touch DB directly
        check_redis=True,
        check_services={
            "user-db-access": "http://user-db-access-service:8001",
        },
    )


# ==============================================================================
# Organization Management
# ==============================================================================


@router.get("/admin/organizations", response_model=OrganizationListResponse)
async def list_organizations(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_user: CurrentUser = Depends(require_superadmin),
) -> OrganizationListResponse:
    """
    List all organizations on the platform.

    Supports pagination and optional filtering by active status.
    **Superadmin only.**

    Args:
        page:      Page number (1-based).
        per_page:  Number of items per page (max 100).
        is_active: Optional filter for active/inactive organizations.

    Returns:
        Paginated list of organizations.
    """
    data = await service_client.list_organizations(
        page=page, per_page=per_page, is_active=is_active
    )
    return OrganizationListResponse(**data)


@router.post(
    "/admin/organizations",
    response_model=OrganizationResponse,
    status_code=201,
)
async def create_organization(
    body: OrganizationCreateRequest,
    current_user: CurrentUser = Depends(require_superadmin),
) -> OrganizationResponse:
    """
    Create a new organization.

    **Superadmin only.**  Writes an audit log entry on success.

    Args:
        body: Organization creation payload.

    Returns:
        The newly created organization.
    """
    org_data = await service_client.create_organization(
        body.model_dump(exclude_unset=True)
    )

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "action": "organization.create",
            "resource_type": "organization",
            "resource_id": str(org_data.get("id")),
            "details": {
                "name": body.name,
                "slug": body.slug,
                "plan": body.billing_plan,
            },
        }
    )

    return OrganizationResponse(**org_data)


@router.get("/admin/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: int,
    current_user: CurrentUser = Depends(require_superadmin),
) -> OrganizationResponse:
    """
    Get a single organization by ID.

    **Superadmin only.**

    Args:
        org_id: Organization primary key.

    Returns:
        Organization details.
    """
    data = await service_client.get_organization(org_id)
    return OrganizationResponse(**data)


@router.put("/admin/organizations/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: int,
    body: OrganizationUpdateRequest,
    current_user: CurrentUser = Depends(require_superadmin),
) -> OrganizationResponse:
    """
    Update an existing organization.

    **Superadmin only.**  Only provided fields are updated.
    Writes an audit log entry on success.

    Args:
        org_id: Organization primary key.
        body:   Fields to update.

    Returns:
        Updated organization details.
    """
    update_data = body.model_dump(exclude_unset=True)
    org_data = await service_client.update_organization(org_id, update_data)

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "organization_id": org_id,
            "action": "organization.update",
            "resource_type": "organization",
            "resource_id": str(org_id),
            "details": {"updated_fields": list(update_data.keys())},
        }
    )

    return OrganizationResponse(**org_data)


@router.post(
    "/admin/organizations/{org_id}/suspend",
    response_model=MessageResponse,
)
async def suspend_organization(
    org_id: int,
    body: SuspendRequest,
    current_user: CurrentUser = Depends(require_superadmin),
) -> MessageResponse:
    """
    Suspend an organization.

    Sets ``is_active = false`` and records the suspension reason
    and timestamp.  All users under this organization will be
    unable to authenticate until the org is unsuspended.

    **Superadmin only.**

    Args:
        org_id: Organization primary key.
        body:   Suspension reason.

    Returns:
        Confirmation message.
    """
    await service_client.update_organization(
        org_id,
        {
            "is_active": False,
            "suspended_reason": body.reason,
        },
    )

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "organization_id": org_id,
            "action": "organization.suspend",
            "resource_type": "organization",
            "resource_id": str(org_id),
            "details": {"reason": body.reason},
        }
    )

    return MessageResponse(
        message=f"Organization {org_id} has been suspended",
        detail=body.reason,
    )


@router.post(
    "/admin/organizations/{org_id}/unsuspend",
    response_model=MessageResponse,
)
async def unsuspend_organization(
    org_id: int,
    current_user: CurrentUser = Depends(require_superadmin),
) -> MessageResponse:
    """
    Reactivate a suspended organization.

    Clears the suspension reason and sets ``is_active = true``.

    **Superadmin only.**

    Args:
        org_id: Organization primary key.

    Returns:
        Confirmation message.
    """
    await service_client.update_organization(
        org_id,
        {
            "is_active": True,
            "suspended_reason": None,
        },
    )

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "organization_id": org_id,
            "action": "organization.unsuspend",
            "resource_type": "organization",
            "resource_id": str(org_id),
        }
    )

    return MessageResponse(message=f"Organization {org_id} has been reactivated")


@router.delete(
    "/admin/organizations/{org_id}",
    response_model=MessageResponse,
)
async def delete_organization(
    org_id: int,
    current_user: CurrentUser = Depends(require_superadmin),
) -> MessageResponse:
    """
    Delete an organization.

    **Superadmin only.**  Writes an audit log entry on success.

    Args:
        org_id: Organization primary key.

    Returns:
        Confirmation message.
    """
    await service_client.delete_organization(org_id)

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "organization_id": org_id,
            "action": "organization.delete",
            "resource_type": "organization",
            "resource_id": str(org_id),
        }
    )

    return MessageResponse(message=f"Organization {org_id} has been deleted")


# ==============================================================================
# Audit Logs (Read-Only)
# ==============================================================================


@router.get("/admin/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    organization_id: int | None = Query(None, description="Filter by org"),
    actor_id: int | None = Query(None, description="Filter by actor"),
    action: str | None = Query(None, description="Filter by action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    current_user: CurrentUser = Depends(require_superadmin),
) -> AuditLogListResponse:
    """
    Query the platform-wide audit log.

    Supports filtering by organization, actor, action type, and
    resource type.  Results are ordered newest-first.

    **Superadmin only.**

    Args:
        page:            Page number (1-based).
        per_page:        Items per page (max 100).
        organization_id: Filter by organization ID.
        actor_id:        Filter by acting user ID.
        action:          Filter by action string.
        resource_type:   Filter by resource type.

    Returns:
        Paginated list of audit log entries.
    """
    data = await service_client.list_audit_logs(
        page=page,
        per_page=per_page,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
    )
    return AuditLogListResponse(**data)


# ==============================================================================
# Platform Settings
# ==============================================================================


@router.get("/admin/settings", response_model=PlatformSettingsListResponse)
async def list_settings(
    current_user: CurrentUser = Depends(require_superadmin),
) -> PlatformSettingsListResponse:
    """
    List all platform settings.

    **Superadmin only.**

    Returns:
        All platform settings with their current values.
    """
    items = await service_client.list_platform_settings()
    return PlatformSettingsListResponse(items=items, total=len(items))


@router.get("/admin/settings/{key}", response_model=PlatformSettingResponse)
async def get_setting(
    key: str,
    current_user: CurrentUser = Depends(require_superadmin),
) -> PlatformSettingResponse:
    """
    Get a single platform setting by key.

    **Superadmin only.**

    Args:
        key: Setting key (e.g. ``"maintenance_mode"``).

    Returns:
        Setting value and metadata.
    """
    data = await service_client.get_platform_setting(key)
    return PlatformSettingResponse(**data)


@router.put("/admin/settings/{key}", response_model=PlatformSettingResponse)
async def update_setting(
    key: str,
    body: PlatformSettingUpdateRequest,
    current_user: CurrentUser = Depends(require_superadmin),
) -> PlatformSettingResponse:
    """
    Update a platform setting value.

    **Superadmin only.**  Writes an audit log entry.

    Args:
        key:  Setting key.
        body: New value and optional description.

    Returns:
        Updated setting.
    """
    payload = body.model_dump(exclude_unset=True)
    payload["updated_by"] = current_user.user_id

    data = await service_client.update_platform_setting(key, payload)

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "action": "platform_setting.update",
            "resource_type": "platform_setting",
            "resource_id": key,
            "details": {"new_value": body.value},
        }
    )

    return PlatformSettingResponse(**data)


# ==============================================================================
# Cross-Tenant User Management
# ==============================================================================


@router.get("/admin/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    organization_id: int | None = Query(None, description="Filter by org"),
    role: str | None = Query(None, description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active"),
    current_user: CurrentUser = Depends(require_superadmin),
) -> AdminUserListResponse:
    """
    List all users across all tenants.

    **Superadmin only.**  Supports filtering by organization,
    role, and active status.

    Args:
        page:            Page number (1-based).
        per_page:        Items per page (max 100).
        organization_id: Filter by organization.
        role:            Filter by user role.
        is_active:       Filter by active status.

    Returns:
        Paginated list of all users.
    """
    data = await service_client.list_all_users(
        page=page,
        per_page=per_page,
        organization_id=organization_id,
        role=role,
        is_active=is_active,
    )
    return AdminUserListResponse(**data)


@router.get("/admin/users/{user_id}", response_model=AdminUserResponse)
async def get_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_superadmin),
) -> AdminUserResponse:
    """
    Get any user by ID (cross-tenant).

    **Superadmin only.**

    Args:
        user_id: User primary key.

    Returns:
        User details including tenant context.
    """
    data = await service_client.get_user(user_id)
    return AdminUserResponse(**data)


@router.put("/admin/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: int,
    body: AdminUserUpdateRequest,
    current_user: CurrentUser = Depends(require_superadmin),
) -> AdminUserResponse:
    """
    Update a user's role (cross-tenant).

    **Superadmin only.** Writes an audit log entry.

    Args:
        user_id: User primary key.
        body:    Fields to update.

    Returns:
        Updated user details.
    """
    update_data = body.model_dump(exclude_unset=True)
    data = await service_client.update_user(user_id, update_data)

    # Audit trail
    await service_client.create_audit_log(
        {
            "actor_id": current_user.user_id,
            "actor_email": current_user.email,
            "actor_role": current_user.role,
            "impersonator_id": current_user.impersonator_id,
            "action": "user.update_role",
            "resource_type": "user",
            "resource_id": str(user_id),
            "details": {"updated_fields": list(update_data.keys())},
        }
    )

    return AdminUserResponse(**data)
