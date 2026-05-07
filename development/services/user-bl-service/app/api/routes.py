"""
API routes for User Service (Business Logic Layer).

All endpoints enforce multi-tenant isolation: users can only
see / modify resources belonging to their ``owner_id`` (tenant).

Route summary
-------------
GET    /api/v1/users                – List users in tenant.
POST   /api/v1/users                – Create a user under tenant.
GET    /api/v1/users/{id}           – Get user by ID.
PUT    /api/v1/users/{id}           – Update user.
DELETE /api/v1/users/{id}           – Deactivate user.
POST   /api/v1/users/invite         – Invite employee (user + details).
GET    /api/v1/employees            – List employees in tenant.
POST   /api/v1/employees            – Add employee details.
GET    /api/v1/employees/{id}       – Get employee details.
PUT    /api/v1/employees/{id}       – Update employee details.
DELETE /api/v1/employees/{id}       – Deactivate employee (soft-delete user).
GET    /api/v1/health               – Health check.
"""

import logging
import sys

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

logger = logging.getLogger(__name__)

sys.path.append("../../../shared")
from common.audit import log_action
from common.health import HealthChecker
from common.schemas import HealthResponse

from .. import service_client
from ..dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
    require_role,
    verify_tenant_access,
)
from ..schemas import (
    AuditLogListResponse,
    CompanyResponse,
    CompanyUpdateRequest,
    EmployeeCreateRequest,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdateRequest,
    InviteEmployeeRequest,
    PermissionUpdateRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
    UserWithEmployeeResponse,
)

router = APIRouter(prefix="/api/v1", tags=["users"])


def _audit_scope_id(current_user: CurrentUser) -> int | None:
    """Resolve the tenant audit-scope identifier for the current user."""
    return current_user.organization_id or current_user.company_id


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("user-service", "1.0.0")


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
    Checks dependent services (auth, user-db-access, and optionally Redis).
    """
    return await _health_checker.readiness_probe(
        db=None,  # User BL doesn't touch DB directly
        check_redis=True,
        check_services={
            "user-db-access": "http://user-db-access-service:8001",
        },
    )


# ==============================================================================
# User Endpoints (Tenant-Scoped)
# ==============================================================================


@router.get("/users", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: bool | None = Query(None),
    role: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List all users belonging to the current tenant.

    The ``owner_id`` filter is automatically applied from the JWT.
    """
    return await service_client.get_users(
        skip=skip,
        limit=limit,
        owner_id=current_user.owner_id,
        is_active=is_active,
        role=role,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    current_user: CurrentUser = Depends(require_permission("users.invite")),
) -> dict:
    """
    Create a new user under the current tenant.

    Only owners and admins may create users.
    The ``owner_id`` is set to the caller's tenant automatically.
    """
    payload = body.model_dump()
    payload["owner_id"] = current_user.effective_owner_id
    payload["company_id"] = current_user.company_id
    user_data = await service_client.create_user(payload)

    # Seed role-based default permissions for the new user
    try:
        await service_client.seed_user_permissions(
            owner_id=current_user.effective_owner_id,
            user_id=user_data["id"],
            role=payload.get("role", "employee"),
        )
    except Exception:
        # Non-critical — user is created even if seeding fails.
        # Permissions can be set later via the Settings page.
        logger.warning("Failed to seed permissions for user %s", user_data["id"])

    return user_data


@router.get("/users/{user_id}", response_model=UserWithEmployeeResponse)
async def get_user(
    user_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a user by ID.

    Enforces tenant isolation — the requested user must belong
    to the caller's tenant.  Superadmins bypass this check.
    """
    user_data = await service_client.get_user(user_id)

    # Security: tenant isolation — verify the resource belongs to the
    # caller's tenant.  Uses effective_owner_id to handle impersonation.
    resource_owner_id = user_data.get("owner_id") or user_data.get("id")
    if not verify_tenant_access(current_user, resource_owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    return user_data


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update a user's information.

    Regular employees can only update their own profile.
    Owners and admins can update any user in their tenant.
    Superadmins can update any user system-wide.
    """
    # Security: fetch target user and verify tenant boundary BEFORE mutation
    target_user = await service_client.get_user(user_id)
    resource_owner_id = target_user.get("owner_id") or target_user.get("id")

    if not verify_tenant_access(current_user, resource_owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    # Self-update is always allowed; otherwise require owner/admin role
    if current_user.user_id != user_id and not current_user.is_superadmin:
        if current_user.role not in ("owner", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own profile",
            )

    payload = body.model_dump(exclude_unset=True, mode="json")
    return await service_client.update_user(user_id, payload)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_permission("users.deactivate")),
) -> None:
    """
    Deactivate a user.  Only owners/admins may do this.

    Superadmins can deactivate any user system-wide.
    """
    # Prevent self-deletion
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    # Security: verify tenant boundary before mutation
    target_user = await service_client.get_user(user_id)
    resource_owner_id = target_user.get("owner_id") or target_user.get("id")
    if not verify_tenant_access(current_user, resource_owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    await service_client.delete_user(user_id)


# ==============================================================================
# Company Endpoints
# ==============================================================================


@router.get("/company", response_model=CompanyResponse)
async def get_company(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get the current user's company details.

    Uses the ``company_id`` from the JWT to fetch company metadata.
    Merges notification_preferences from the parent organization.
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company associated with this account",
        )
    company = await service_client.get_company(current_user.company_id)

    # Merge notification preferences from the organization
    if current_user.organization_id:
        try:
            org = await service_client.get_organization(current_user.organization_id)
            company["notification_preferences"] = org.get("notification_settings")
        except Exception:
            company["notification_preferences"] = None

    return company


@router.put("/company", response_model=CompanyResponse)
async def update_company(
    body: CompanyUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("company.update")),
    request: Request = None,
) -> dict:
    """
    Update the current user's company details.

    Only owners and admins may update company information.
    If notification_preferences is included, it is saved to the
    parent organization's notification_settings column.
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company associated with this account",
        )
    payload = body.model_dump(exclude_unset=True)

    # Extract notification_preferences — these go to the organization, not company
    notif_prefs = payload.pop("notification_preferences", None)

    # Update company fields (if any remain)
    if payload:
        company = await service_client.update_company(current_user.company_id, payload)
    else:
        company = await service_client.get_company(current_user.company_id)

    # Save notification preferences to the organization
    if notif_prefs is not None and current_user.organization_id:
        await service_client.update_organization(
            current_user.organization_id,
            {"notification_settings": notif_prefs},
        )
        company["notification_preferences"] = notif_prefs

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="company.update",
        resource_type="company",
        resource_id=str(current_user.company_id),
        details={"updated_fields": sorted(body.model_dump(exclude_unset=True).keys())},
        ip_address=request.client.host if request and request.client else None,
    )

    return company


# ==============================================================================
# Employee Invite (Convenience)
# ==============================================================================


@router.post(
    "/users/invite",
    response_model=UserWithEmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_employee(
    body: InviteEmployeeRequest,
    current_user: CurrentUser = Depends(require_permission("users.invite")),
    request: Request = None,
) -> dict:
    """
    Create a user **and** their employee details in one request.

    This is a convenience endpoint that orchestrates two calls
    to user-db-access-service.
    """
    # Step 1 — Create the user
    user_payload = {
        "email": body.email,
        "password": body.password,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "phone": body.phone,
        "role": "employee",
        "owner_id": current_user.effective_owner_id,
        "company_id": current_user.company_id,
    }
    user_data = await service_client.create_user(user_payload)

    # Seed role-based default permissions for the new employee user
    try:
        await service_client.seed_user_permissions(
            owner_id=current_user.effective_owner_id,
            user_id=user_data["id"],
            role="employee",
        )
    except Exception:
        # Non-critical — employee is created even if seeding fails.
        logger.warning(
            "Failed to seed permissions for employee user %s", user_data["id"]
        )

    # Step 2 — Create employee details
    emp_payload = {
        "user_id": user_data["id"],
        "owner_id": current_user.effective_owner_id,
        "position": body.position,
        "hourly_rate": body.hourly_rate,
        "skills": body.skills,
    }
    emp_data = await service_client.create_employee(emp_payload)

    # Enrich employee data with user fields for the BL response
    emp_data["first_name"] = user_data["first_name"]
    emp_data["last_name"] = user_data["last_name"]
    emp_data["email"] = user_data["email"]

    user_data["employee_details"] = emp_data

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="employee.invite",
        resource_type="employee",
        resource_id=str(emp_data["id"]),
        details={
            "user_id": user_data["id"],
            "email": user_data["email"],
            "role": user_data.get("role"),
        },
        ip_address=request.client.host if request and request.client else None,
    )

    return user_data


# ==============================================================================
# Employee Endpoints
# ==============================================================================


@router.get("/employees", response_model=EmployeeListResponse)
async def list_employees(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List all employees in the current tenant.
    """
    return await service_client.get_employees_by_owner(
        owner_id=current_user.owner_id,
        skip=skip,
        limit=limit,
        search=search,
    )


@router.post(
    "/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee(
    body: EmployeeCreateRequest,
    current_user: CurrentUser = Depends(require_permission("employees.create")),
) -> dict:
    """
    Create employee details for an existing user.

    Security: the ``owner_id`` is injected from the caller's tenant
    context — never accepted from the request body.
    """
    payload = body.model_dump()
    # Security: inject owner_id from authenticated context to prevent
    # cross-tenant employee creation
    payload["owner_id"] = current_user.effective_owner_id
    return await service_client.create_employee(payload)


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get employee details by ID.

    Enforces tenant isolation — the employee must belong
    to the caller's tenant.
    """
    employee_data = await service_client.get_employee(employee_id)

    # Security: tenant check on the employee resource
    if not verify_tenant_access(current_user, employee_data.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: employee belongs to a different tenant",
        )

    return employee_data


@router.put("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    body: EmployeeUpdateRequest,
    current_user: CurrentUser = Depends(require_permission("employees.edit")),
    request: Request = None,
) -> dict:
    """
    Update employee details.

    Enforces tenant isolation — the employee must belong
    to the caller's tenant before mutation is allowed.
    """
    # Security: verify tenant boundary before allowing update
    employee_data = await service_client.get_employee(employee_id)
    if not verify_tenant_access(current_user, employee_data.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: employee belongs to a different tenant",
        )

    payload = body.model_dump(exclude_unset=True)
    employee = await service_client.update_employee(employee_id, payload)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="employee.update",
        resource_type="employee",
        resource_id=str(employee_id),
        details={"updated_fields": sorted(payload.keys())},
        ip_address=request.client.host if request and request.client else None,
    )

    return employee


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: int,
    current_user: CurrentUser = Depends(require_permission("employees.delete")),
    request: Request = None,
) -> None:
    """
    Deactivate the user account linked to an employee.

    Fetches the employee to obtain its ``user_id``, verifies tenant
    isolation, then soft-deletes the underlying user record
    (``is_active = False``).
    """
    employee_data = await service_client.get_employee(employee_id)
    if not verify_tenant_access(current_user, employee_data.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: employee belongs to a different tenant",
        )

    user_id = employee_data.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee has no linked user account",
        )

    # Prevent deleting yourself
    if current_user.user_id == int(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    await service_client.delete_user(user_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="employee.deactivate",
        resource_type="employee",
        resource_id=str(employee_id),
        details={
            "user_id": user_id,
            "email": employee_data.get("email"),
        },
        ip_address=request.client.host if request and request.client else None,
    )


# ==============================================================================
# GDPR Endpoints (Data Export & Anonymization)
# ==============================================================================


@router.get("/users/me/consent-status")
async def get_my_consent_status(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return the privacy consent and anonymization status for the authenticated user."""
    user_data = await service_client.get_user(current_user.user_id)
    return {
        "privacy_consent_at": user_data.get("privacy_consent_at"),
        "privacy_consent_version": user_data.get("privacy_consent_version"),
        "anonymize_scheduled_at": user_data.get("anonymize_scheduled_at"),
    }


@router.get("/users/me/export")
async def export_my_data(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Download all personal data held for the authenticated user (GDPR Article 15/20).

    Any authenticated user can export their own data.
    """
    return await service_client.export_user_data(current_user.user_id)


@router.post("/users/me/anonymize/schedule")
async def schedule_my_anonymization(
    current_user: CurrentUser = Depends(get_current_user),
    request: Request = None,
) -> dict:
    """
    Request anonymization of your own account (72-hour grace period).

    The user can cancel within the grace period by calling the cancel endpoint.
    """
    data = await service_client.schedule_user_anonymization(current_user.user_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="user.anonymize_scheduled",
        resource_type="user",
        resource_id=str(current_user.user_id),
        details={"scheduled_at": data.get("anonymize_scheduled_at")},
        ip_address=request.client.host if request and request.client else None,
    )

    return data


@router.post("/users/me/anonymize/cancel")
async def cancel_my_anonymization(
    current_user: CurrentUser = Depends(get_current_user),
    request: Request = None,
) -> dict:
    """Cancel a pending anonymization request for the authenticated user."""
    data = await service_client.cancel_user_anonymization(current_user.user_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="user.anonymize_cancelled",
        resource_type="user",
        resource_id=str(current_user.user_id),
        ip_address=request.client.host if request and request.client else None,
    )

    return data


@router.post("/users/{user_id}/anonymize")
async def anonymize_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    request: Request = None,
) -> dict:
    """
    Immediately anonymize a user's data (owner/admin only).

    Superadmins can also anonymize any user system-wide.
    """
    # Verify tenant boundary
    target_user = await service_client.get_user(user_id)
    resource_owner_id = target_user.get("owner_id") or target_user.get("id")
    if not verify_tenant_access(current_user, resource_owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    data = await service_client.anonymize_user(user_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="user.anonymized",
        resource_type="user",
        resource_id=str(user_id),
        ip_address=request.client.host if request and request.client else None,
    )

    return data


@router.get("/users/{user_id}/export")
async def export_user_data(
    user_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """
    Export all personal data for a user (owner/admin only).

    Regular users should use ``/users/me/export`` instead.
    """
    target_user = await service_client.get_user(user_id)
    resource_owner_id = target_user.get("owner_id") or target_user.get("id")
    if not verify_tenant_access(current_user, resource_owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    return await service_client.export_user_data(user_id)


# ==============================================================================
# Permission Management (Tenant-Scoped)
# ==============================================================================


@router.get("/permissions/catalog")
async def get_permission_catalog(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Return the full permission catalog with per-role defaults."""
    return await service_client.get_permission_catalog()


@router.get("/users/{user_id}/permissions")
async def get_user_permissions(
    user_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """
    Get permission grants for a specific user in the tenant.

    Only owners and admins may view another user's permissions.
    """
    target = await service_client.get_user(user_id)
    if not verify_tenant_access(current_user, target.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    return await service_client.get_user_permissions(
        current_user.effective_owner_id, user_id
    )


@router.put("/users/{user_id}/permissions")
async def update_user_permissions(
    user_id: int,
    body: PermissionUpdateRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
    request: Request = None,
) -> dict:
    """
    Bulk upsert permission grants for a specific user.

    Only owners and admins may modify permissions.
    Prevents modifying your own permissions.
    """
    if current_user.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot modify your own permissions",
        )

    target = await service_client.get_user(user_id)
    if not verify_tenant_access(current_user, target.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: user belongs to a different tenant",
        )

    permissions = await service_client.update_user_permissions(
        current_user.effective_owner_id, user_id, body.permissions
    )

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="permissions.update",
        resource_type="user",
        resource_id=str(user_id),
        details={
            "target_email": target.get("email"),
            "permissions": body.permissions,
        },
        ip_address=request.client.host if request and request.client else None,
    )

    return permissions


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    actor_id: int | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    search: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """Return tenant-scoped audit log entries for owner/admin settings views."""
    scope_id = _audit_scope_id(current_user)
    if scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No audit scope associated with this account",
        )

    return await service_client.get_audit_logs(
        organization_id=scope_id,
        page=page,
        per_page=per_page,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
