"""
API routes for User service.

Defines all **async** HTTP endpoints for user and employee operations.
"""

import sys
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append("../../../shared")

from common.database import get_async_db
from common.exceptions import ConflictError, NotFoundError
from common.health import HealthChecker
from common.schemas import HealthResponse

from ..crud import (
    anonymize_user,
    cancel_user_anonymization,
    check_user_permission,
    cleanup_old_audit_logs,
    create_audit_log,
    create_company,
    create_employee,
    create_organization,
    create_user,
    delete_organization,
    delete_user,
    export_user_data,
    get_audit_logs,
    get_company,
    get_employee,
    get_employee_by_user_id,
    get_employees_by_owner,
    get_organization,
    get_organizations,
    get_password_hash,
    get_platform_setting,
    get_platform_settings,
    get_user,
    get_user_by_email,
    get_user_permissions,
    get_users,
    process_scheduled_anonymizations,
    schedule_user_anonymization,
    seed_default_permissions,
    set_user_permissions,
    suspend_organization,
    unsuspend_organization,
    update_company,
    update_employee,
    update_organization,
    update_user,
    upsert_platform_setting,
)
from ..models.permission import DEFAULT_ROLE_PERMISSIONS, PERMISSION_CATALOG
from ..models.user import UserRole
from ..schemas import (
    AuditLogCreate,
    AuditLogListResponse,
    AuditLogResponse,
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    EmployeeCreate,
    EmployeeListResponse,
    EmployeeResponse,
    EmployeeUpdate,
    EmployeeWithUserResponse,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    PasswordUpdate,
    PermissionCatalogResponse,
    PermissionCheck,
    PermissionUpdate,
    PlatformSettingListResponse,
    PlatformSettingResponse,
    PlatformSettingUpdate,
    UserCreate,
    UserListResponse,
    UserPermissionsResponse,
    UserResponse,
    UserUpdate,
    UserWithEmployeeResponse,
)

# Create router with prefix
router = APIRouter(prefix="/api/v1", tags=["users"])


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("user-db-access-service", "1.0.0")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness probe — is the service running?

    K8s uses this to determine if the container should be restarted.
    Returns quickly without checking external dependencies.
    """
    return await _health_checker.liveness_probe()


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(
    db: AsyncSession = Depends(get_async_db),
) -> HealthResponse:
    """
    Readiness probe — can the service handle traffic?

    K8s uses this to determine if the pod should receive traffic.
    Checks database connectivity.
    """
    return await _health_checker.readiness_probe(db=db, check_redis=False)


# ==============================================================================
# User Endpoints
# ==============================================================================


@router.get("/users", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    page: int | None = Query(None, ge=1, description="Page number (overrides skip)"),
    per_page: int | None = Query(
        None, ge=1, le=1000, description="Items per page (overrides limit)"
    ),
    owner_id: int | None = Query(None, description="Filter by owner ID"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    role: UserRole | None = Query(None, description="Filter by role"),
    db: AsyncSession = Depends(get_async_db),
) -> UserListResponse:
    """
    List users with optional filtering and pagination.

    Supports both ``skip``/``limit`` and ``page``/``per_page`` pagination
    styles.  When ``page`` and ``per_page`` are provided they take
    precedence over ``skip`` and ``limit``.

    Args:
        skip:     Pagination offset (default style).
        limit:    Maximum results per page (default style).
        page:     Page number — overrides ``skip`` when provided.
        per_page: Items per page — overrides ``limit`` when provided.
        owner_id: Filter employees by owner.
        is_active: Filter by active/inactive status.
        role:     Filter by user role.
        db:       Async database session.

    Returns:
        UserListResponse: Paginated list of users.
    """
    # Allow page/per_page to override skip/limit
    effective_limit = per_page if per_page is not None else limit
    if page is not None:
        effective_skip = (page - 1) * effective_limit
    else:
        effective_skip = skip

    users, total = await get_users(
        db,
        skip=effective_skip,
        limit=effective_limit,
        owner_id=owner_id,
        is_active=is_active,
        role=role,
    )

    pages = (
        (total + effective_limit - 1) // effective_limit if effective_limit > 0 else 0
    )
    current_page = (effective_skip // effective_limit) + 1 if effective_limit > 0 else 1

    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=current_page,
        per_page=effective_limit,
        pages=pages,
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_new_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_async_db),
) -> UserResponse:
    """
    Create a new user.

    Args:
        user_data: User creation payload
        db: Async database session

    Returns:
        UserResponse: Created user data

    Raises:
        HTTPException: 409 if email already exists
    """
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    user = await create_user(db, user_data)
    return UserResponse.model_validate(user)


@router.get("/users/{user_id}", response_model=UserWithEmployeeResponse)
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> UserWithEmployeeResponse:
    """
    Get a specific user by ID.

    Args:
        user_id: User's primary key
        db: Async database session

    Returns:
        UserWithEmployeeResponse: User data with employee details if available

    Raises:
        HTTPException: 404 if user not found
    """
    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    employee = await get_employee_by_user_id(db, user_id)

    # Build from base response to avoid lazy-loading relationships
    base = UserResponse.model_validate(user)
    response = UserWithEmployeeResponse(**base.model_dump())
    if employee:
        response.employee_details = EmployeeResponse.model_validate(employee)

    return response


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_existing_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> UserResponse:
    """
    Update a user's information.

    Args:
        user_id: User's primary key
        user_data: Fields to update
        db: Async database session

    Returns:
        UserResponse: Updated user data

    Raises:
        HTTPException: 404 if user not found, 409 if email conflict
    """
    if user_data.email:
        existing = await get_user_by_email(db, user_data.email)
        if existing and existing.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already in use",
            )

    user = await update_user(db, user_id, user_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    Delete (deactivate) a user.

    Args:
        user_id: User's primary key
        db: Async database session

    Raises:
        HTTPException: 404 if user not found
    """
    success = await delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


# ==============================================================================
# GDPR Endpoints (Data Export & Anonymization)
# ==============================================================================


@router.get("/users/{user_id}/export")
async def export_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Export all personal data for a user (GDPR Article 15/20).

    Returns a JSON document containing all PII held for this user,
    suitable for data portability.
    """
    data = await export_user_data(db, user_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return data


@router.post("/users/{user_id}/anonymize")
async def anonymize_user_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Immediately anonymize a user's personal data (GDPR Article 17).

    Replaces all PII with anonymized placeholders. This is irreversible.
    """
    user = await anonymize_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {"status": "anonymized", "user_id": user_id}


@router.post("/users/{user_id}/anonymize/schedule")
async def schedule_anonymize_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Schedule user anonymization after a 72-hour grace period.

    The user can cancel within the grace period.
    """
    scheduled_at = datetime.now(UTC) + timedelta(hours=72)
    user = await schedule_user_anonymization(db, user_id, scheduled_at)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {
        "status": "scheduled",
        "user_id": user_id,
        "anonymize_scheduled_at": user.anonymize_scheduled_at.isoformat(),
    }


@router.post("/users/{user_id}/anonymize/cancel")
async def cancel_anonymize_user(
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Cancel a pending anonymization request."""
    user = await cancel_user_anonymization(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return {"status": "cancelled", "user_id": user_id}


@router.post("/users/anonymize/process-scheduled")
async def process_scheduled_anonymizations_endpoint(
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """Process all users whose anonymization grace period has expired.

    Called by the notification-service scheduler.  Finds users where
    ``anonymize_scheduled_at <= now()`` and anonymizes them.

    Returns the count of users anonymized.
    """
    count = await process_scheduled_anonymizations(db)
    return {"processed_count": count}


# ==============================================================================
# Employee Endpoints
# ==============================================================================


@router.put("/users/{user_id}/password", response_model=UserResponse)
async def update_user_password(
    user_id: int,
    body: PasswordUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> UserResponse:
    """
    Update a user's password.

    Hashes the new password and persists it.

    Args:
        user_id: User's primary key
        body: Current and new password
        db: Async database session

    Returns:
        UserResponse: Updated user data

    Raises:
        HTTPException: 404 if user not found
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db_user.hashed_password = get_password_hash(body.new_password)
    await db.commit()
    await db.refresh(db_user)

    return UserResponse.model_validate(db_user)


@router.post(
    "/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED
)
async def create_employee_details(
    employee_data: EmployeeCreate,
    db: AsyncSession = Depends(get_async_db),
) -> EmployeeResponse:
    """
    Create employee details for a user.

    Args:
        employee_data: Employee creation payload
        db: Async database session

    Returns:
        EmployeeResponse: Created employee data

    Raises:
        HTTPException: 404 if user not found, 409 if already has employee details
    """
    user = await get_user(db, employee_data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    existing = await get_employee_by_user_id(db, employee_data.user_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee details already exist for this user",
        )

    employee = await create_employee(db, employee_data)
    return EmployeeResponse.model_validate(employee)


@router.get("/employees/{employee_id}", response_model=EmployeeWithUserResponse)
async def get_employee_details(
    employee_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> EmployeeWithUserResponse:
    """
    Get employee details by ID, enriched with user information.

    Args:
        employee_id: Employee's primary key
        db: Async database session

    Returns:
        EmployeeWithUserResponse: Employee data with user fields

    Raises:
        HTTPException: 404 if employee not found
    """
    employee = await get_employee(db, employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    return EmployeeWithUserResponse(
        **EmployeeResponse.model_validate(employee).model_dump(),
        first_name=employee.user.first_name,
        last_name=employee.user.last_name,
        email=employee.user.email,
    )


@router.put("/employees/{employee_id}", response_model=EmployeeWithUserResponse)
async def update_employee_details(
    employee_id: int,
    employee_data: EmployeeUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> EmployeeWithUserResponse:
    """
    Update employee details.

    Args:
        employee_id: Employee's primary key
        employee_data: Fields to update
        db: Async database session

    Returns:
        EmployeeResponse: Updated employee data

    Raises:
        HTTPException: 404 if employee not found
    """
    employee = await update_employee(db, employee_id, employee_data)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )

    # Reload with user relationship for enriched response
    employee = await get_employee(db, employee_id)

    return EmployeeWithUserResponse(
        **EmployeeResponse.model_validate(employee).model_dump(),
        first_name=employee.user.first_name,
        last_name=employee.user.last_name,
        email=employee.user.email,
    )


@router.get("/users/{user_id}/employees", response_model=EmployeeListResponse)
async def list_user_employees(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_async_db),
) -> EmployeeListResponse:
    """
    List all employees under a specific owner with user information.

    Args:
        user_id: Owner's user ID
        skip: Pagination offset
        limit: Maximum results
        db: Async database session

    Returns:
        list[EmployeeWithUserResponse]: List of employees with associated user data
    """
    employees, total = await get_employees_by_owner(db, user_id, skip, limit, search)

    # Build enriched response with user data
    items = [
        EmployeeWithUserResponse(
            **EmployeeResponse.model_validate(e).model_dump(),
            first_name=e.user.first_name,
            last_name=e.user.last_name,
            email=e.user.email,
        )
        for e in employees
    ]

    page = (skip // limit) + 1
    pages = (total + limit - 1) // limit if total > 0 else 0
    return EmployeeListResponse(
        items=items,
        total=total,
        page=page,
        per_page=limit,
        pages=pages,
    )


# ==============================================================================
# Company Endpoints
# ==============================================================================


@router.post(
    "/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED
)
async def create_new_company(
    company_data: CompanyCreate,
    db: AsyncSession = Depends(get_async_db),
) -> CompanyResponse:
    """
    Create a new company.

    Args:
        company_data: Company creation payload
        db: Async database session

    Returns:
        CompanyResponse: Created company data
    """
    company = await create_company(db, company_data)
    return CompanyResponse.model_validate(company)


@router.get("/companies/{company_id}", response_model=CompanyResponse)
async def get_company_by_id(
    company_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> CompanyResponse:
    """
    Get a specific company by ID.

    Args:
        company_id: Company's primary key
        db: Async database session

    Returns:
        CompanyResponse: Company data

    Raises:
        HTTPException: 404 if company not found
    """
    company = await get_company(db, company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    return CompanyResponse.model_validate(company)


@router.put("/companies/{company_id}", response_model=CompanyResponse)
async def update_existing_company(
    company_id: int,
    company_data: CompanyUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> CompanyResponse:
    """
    Update a company's information.

    Args:
        company_id: Company's primary key
        company_data: Fields to update
        db: Async database session

    Returns:
        CompanyResponse: Updated company data

    Raises:
        HTTPException: 404 if company not found
    """
    company = await update_company(db, company_id, company_data)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found",
        )
    return CompanyResponse.model_validate(company)


# ==============================================================================
# Internal Endpoints (service-to-service only)
# ==============================================================================

from pydantic import BaseModel


class AuthenticateRequest(BaseModel):
    """Internal request body for credential verification."""

    email: str
    password: str


class AuthenticateResponse(BaseModel):
    """Internal response for credential verification."""

    authenticated: bool
    user_id: int | None = None
    email: str | None = None
    role: str | None = None
    owner_id: int | None = None
    company_id: int | None = None
    is_active: bool | None = None


@router.post("/internal/authenticate", response_model=AuthenticateResponse)
async def internal_authenticate(
    body: AuthenticateRequest,
    db: AsyncSession = Depends(get_async_db),
) -> AuthenticateResponse:
    """
    Internal endpoint for auth-service to verify credentials.

    This is NOT exposed to end users — only called service-to-service
    by the auth-service during login.

    Args:
        body: Email and plain-text password.
        db: Async database session.

    Returns:
        AuthenticateResponse with ``authenticated=True`` and user info,
        or ``authenticated=False`` on failure.
    """
    from ..crud import authenticate_user

    user = await authenticate_user(db, body.email, body.password)
    if not user:
        return AuthenticateResponse(authenticated=False)

    # Determine owner_id: employee -> actual owner, owner -> self, superadmin -> None
    if user.owner_id is not None:
        # Employee with explicit owner_id
        owner_id_value = user.owner_id
    elif user.role == "superadmin":
        # Superadmins sit outside tenants
        owner_id_value = None
    else:
        # Owner users — self-referential
        owner_id_value = user.id

    return AuthenticateResponse(
        authenticated=True,
        user_id=user.id,
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        owner_id=owner_id_value,
        company_id=user.company_id,
        is_active=user.is_active,
    )


# ==============================================================================
# Organization Endpoints
# ==============================================================================


@router.get("/organizations", response_model=dict)
async def list_organizations(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    List all organizations with pagination.

    Used by admin-bl-service for platform administration.
    """
    skip = (page - 1) * per_page
    organizations, total = await get_organizations(
        db, skip=skip, limit=per_page, is_active=is_active
    )

    pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    return {
        "items": [OrganizationResponse.model_validate(org) for org in organizations],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_new_organization(
    organization_data: OrganizationCreate,
    db: AsyncSession = Depends(get_async_db),
) -> OrganizationResponse:
    """
    Create a new organization.

    Used by admin-bl-service when superadmins create organizations.
    """
    # Check for duplicate slug
    from ..crud import get_organization_by_slug

    existing = await get_organization_by_slug(db, organization_data.slug)
    if existing:
        raise ConflictError(
            f"Organization with slug '{organization_data.slug}' already exists"
        )

    organization = await create_organization(db, organization_data)
    return OrganizationResponse.model_validate(organization)


@router.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization_by_id(
    org_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> OrganizationResponse:
    """
    Retrieve a single organization by ID.

    Used by admin-bl-service for organization details.
    """
    organization = await get_organization(db, org_id)
    if not organization:
        raise NotFoundError(f"Organization {org_id} not found")

    return OrganizationResponse.model_validate(organization)


@router.put("/organizations/{org_id}", response_model=OrganizationResponse)
async def update_organization_by_id(
    org_id: int,
    organization_data: OrganizationUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> OrganizationResponse:
    """
    Update an existing organization.

    Used by admin-bl-service when superadmins modify organizations.
    """
    organization = await update_organization(db, org_id, organization_data)
    if not organization:
        raise NotFoundError(f"Organization {org_id} not found")

    return OrganizationResponse.model_validate(organization)


@router.post("/organizations/{org_id}/suspend", response_model=OrganizationResponse)
async def suspend_organization_by_id(
    org_id: int,
    db: AsyncSession = Depends(get_async_db),
    reason: str | None = Query(None, description="Reason for suspension"),
) -> OrganizationResponse:
    """
    Suspend an organization.

    Used by admin-bl-service when superadmins suspend organizations.
    """
    organization = await suspend_organization(db, org_id, reason)
    if not organization:
        raise NotFoundError(f"Organization {org_id} not found")

    return OrganizationResponse.model_validate(organization)


@router.post("/organizations/{org_id}/unsuspend", response_model=OrganizationResponse)
async def unsuspend_organization_by_id(
    org_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> OrganizationResponse:
    """
    Reactivate a suspended organization.

    Used by admin-bl-service when superadmins reactivate organizations.
    """
    organization = await unsuspend_organization(db, org_id)
    if not organization:
        raise NotFoundError(f"Organization {org_id} not found")

    return OrganizationResponse.model_validate(organization)


@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_by_id(
    org_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    Delete an organization by ID.

    Used by admin-bl-service when superadmins delete organizations.
    """
    deleted = await delete_organization(db, org_id)
    if not deleted:
        raise NotFoundError(f"Organization {org_id} not found")


# ==============================================================================
# Audit Log Endpoints
# ==============================================================================


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    organization_id: int | None = Query(None, description="Filter by organization"),
    actor_id: int | None = Query(None, description="Filter by acting user"),
    action: str | None = Query(None, description="Filter by action string"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    search: str | None = Query(None, description="Free-text search"),
    date_from: datetime | None = Query(None, description="Start of date range"),
    date_to: datetime | None = Query(None, description="End of date range"),
    db: AsyncSession = Depends(get_async_db),
) -> AuditLogListResponse:
    """
    List audit log entries with optional filtering and pagination.

    Results are returned in reverse chronological order (newest first).
    Used by admin-bl-service for the superadmin audit trail view.

    Args:
        page:            Page number (1-based).
        per_page:        Items per page (max 200).
        organization_id: Filter by organization context.
        actor_id:        Filter by acting user.
        action:          Filter by action string (e.g. ``"org.create"``).
        resource_type:   Filter by affected resource type.
        search:          Free-text search across actor email, action, etc.
        date_from:       Only return entries on or after this timestamp.
        date_to:         Only return entries on or before this timestamp.
        db:              Async database session.

    Returns:
        AuditLogListResponse: Paginated list of audit log entries.
    """
    skip = (page - 1) * per_page
    logs, total = await get_audit_logs(
        db,
        skip=skip,
        limit=per_page,
        organization_id=organization_id,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )

    pages = (total + per_page - 1) // per_page if per_page > 0 else 0

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.post(
    "/audit-logs",
    response_model=AuditLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_audit_log_entry(
    log_data: AuditLogCreate,
    db: AsyncSession = Depends(get_async_db),
) -> AuditLogResponse:
    """
    Create a new audit log entry.

    Called by admin-bl-service to record superadmin actions.
    Audit log entries are immutable once written.

    Args:
        log_data: Audit log creation payload.
        db:       Async database session.

    Returns:
        AuditLogResponse: The newly created audit log entry.
    """
    log = await create_audit_log(db, log_data)
    return AuditLogResponse.model_validate(log)


@router.post("/audit-logs/cleanup")
async def cleanup_audit_logs(
    retention_days: int = 730,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Delete audit log entries older than retention_days (GDPR data minimization).

    Internal endpoint called by the scheduler. Defaults to 730 days (2 years).
    """
    deleted = await cleanup_old_audit_logs(db, retention_days)
    return {"deleted_count": deleted, "retention_days": retention_days}


# ==============================================================================
# Platform Settings Endpoints
# ==============================================================================


@router.get("/platform-settings", response_model=PlatformSettingListResponse)
async def list_platform_settings_endpoint(
    db: AsyncSession = Depends(get_async_db),
) -> PlatformSettingListResponse:
    """
    Retrieve all platform settings.

    Platform settings are global key-value pairs managed by superadmins.
    The dataset is expected to be small, so no pagination is needed.

    Args:
        db: Async database session.

    Returns:
        PlatformSettingListResponse: All platform settings.
    """
    settings_list = await get_platform_settings(db)
    return PlatformSettingListResponse(
        items=[PlatformSettingResponse.model_validate(s) for s in settings_list],
        total=len(settings_list),
    )


@router.get("/platform-settings/{key}", response_model=PlatformSettingResponse)
async def get_platform_setting_endpoint(
    key: str,
    db: AsyncSession = Depends(get_async_db),
) -> PlatformSettingResponse:
    """
    Retrieve a single platform setting by key.

    Args:
        key: Unique setting key (e.g. ``"maintenance_mode"``).
        db:  Async database session.

    Returns:
        PlatformSettingResponse: The requested setting.

    Raises:
        HTTPException: 404 if key does not exist.
    """
    setting = await get_platform_setting(db, key)
    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting '{key}' not found",
        )
    return PlatformSettingResponse.model_validate(setting)


@router.put("/platform-settings/{key}", response_model=PlatformSettingResponse)
async def update_platform_setting_endpoint(
    key: str,
    setting_data: PlatformSettingUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> PlatformSettingResponse:
    """
    Create or update a platform setting.

    If the key already exists, the value and description are updated.
    If it does not exist, a new row is inserted (upsert behaviour).

    Args:
        key:          Setting key.
        setting_data: New value and optional description.
        db:           Async database session.

    Returns:
        PlatformSettingResponse: The created or updated setting.
    """
    setting = await upsert_platform_setting(db, key, setting_data)
    return PlatformSettingResponse.model_validate(setting)


# ==============================================================================
# Permission Endpoints
# ==============================================================================


@router.get("/permissions/catalog", response_model=PermissionCatalogResponse)
async def get_permission_catalog() -> PermissionCatalogResponse:
    """
    Return the full permission catalog and per-role defaults.

    No database access needed — the catalog is defined in code.
    Used by user-bl-service for the settings UI.
    """
    return PermissionCatalogResponse(
        permissions=list(PERMISSION_CATALOG),
        defaults={
            role: sorted(perms) for role, perms in DEFAULT_ROLE_PERMISSIONS.items()
        },
    )


@router.get(
    "/permissions/{owner_id}/{user_id}",
    response_model=UserPermissionsResponse,
)
async def get_permissions_for_user(
    owner_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> UserPermissionsResponse:
    """
    Get all permissions for a specific user within a tenant.

    Args:
        owner_id: Tenant isolation key.
        user_id:  Target user.
        db:       Async database session.

    Returns:
        UserPermissionsResponse with permission map.
    """
    perms = await get_user_permissions(db, user_id=user_id, owner_id=owner_id)
    return UserPermissionsResponse(
        user_id=user_id,
        owner_id=owner_id,
        permissions=perms,
    )


@router.put(
    "/permissions/{owner_id}/{user_id}",
    response_model=UserPermissionsResponse,
)
async def update_permissions_for_user(
    owner_id: int,
    user_id: int,
    payload: PermissionUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> UserPermissionsResponse:
    """
    Bulk-upsert permissions for a user.

    Unknown permission names are silently ignored.

    Args:
        owner_id: Tenant isolation key.
        user_id:  Target user.
        payload:  Map of permission name → granted flag.
        db:       Async database session.

    Returns:
        UserPermissionsResponse with the full permission map after upsert.
    """
    perms = await set_user_permissions(
        db,
        user_id=user_id,
        owner_id=owner_id,
        permissions=payload.permissions,
    )
    return UserPermissionsResponse(
        user_id=user_id,
        owner_id=owner_id,
        permissions=perms,
    )


@router.get(
    "/permissions/{owner_id}/{user_id}/check/{permission}",
    response_model=PermissionCheck,
)
async def check_permission_for_user(
    owner_id: int,
    user_id: int,
    permission: str,
    db: AsyncSession = Depends(get_async_db),
) -> PermissionCheck:
    """
    Check whether a single permission is granted for a user.

    Called by BL services at request-time to enforce fine-grained
    permission checks for subordinate users.

    Args:
        owner_id:   Tenant isolation key.
        user_id:    Target user.
        permission: Permission name to check.
        db:         Async database session.

    Returns:
        PermissionCheck indicating whether the permission is granted.
    """
    granted = await check_user_permission(
        db,
        user_id=user_id,
        owner_id=owner_id,
        permission=permission,
    )
    return PermissionCheck(
        user_id=user_id,
        permission=permission,
        granted=granted,
    )


@router.post(
    "/permissions/{owner_id}/{user_id}/seed",
    response_model=UserPermissionsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def seed_permissions_for_user(
    owner_id: int,
    user_id: int,
    role: str = Query(..., description="User role for default permissions"),
    db: AsyncSession = Depends(get_async_db),
) -> UserPermissionsResponse:
    """
    Seed default permissions for a newly created subordinate user.

    Idempotent — existing rows are not overwritten.

    Args:
        owner_id: Tenant isolation key.
        user_id:  The new subordinate user.
        role:     User role (manager, employee, viewer).
        db:       Async database session.

    Returns:
        UserPermissionsResponse with the full permission map.
    """
    perms = await seed_default_permissions(
        db,
        user_id=user_id,
        owner_id=owner_id,
        role=role,
    )
    return UserPermissionsResponse(
        user_id=user_id,
        owner_id=owner_id,
        permissions=perms,
    )
