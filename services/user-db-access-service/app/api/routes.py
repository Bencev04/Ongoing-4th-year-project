"""
API routes for User service.

Defines all **async** HTTP endpoints for user and employee operations.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

import sys
sys.path.append("../../../shared")
from common.database import get_async_db
from common.schemas import HealthResponse
from common.exceptions import NotFoundError, ConflictError

from ..schemas import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    EmployeeCreate, EmployeeUpdate, EmployeeResponse,
    UserWithEmployeeResponse, EmployeeWithUserResponse,
    CompanyCreate, CompanyUpdate, CompanyResponse,
    OrganizationCreate, OrganizationUpdate, OrganizationResponse,
    AuditLogCreate, AuditLogResponse, AuditLogListResponse,
    PlatformSettingUpdate, PlatformSettingResponse,
    PlatformSettingListResponse,
    PasswordUpdate,
)
from ..crud import (
    get_user, get_user_by_email, get_users, create_user,
    update_user, delete_user, get_employee, get_employee_by_user_id,
    get_employees_by_owner, create_employee, update_employee,
    get_company, create_company, update_company,
    get_organizations, get_organization, create_organization,
    update_organization, suspend_organization, unsuspend_organization,
    get_audit_logs, create_audit_log,
    get_platform_settings, get_platform_setting,
    upsert_platform_setting,
    get_password_hash,
)
from ..models.user import UserRole

from datetime import datetime

# Create router with prefix
router = APIRouter(prefix="/api/v1", tags=["users"])


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
        service="user-service",
        version="1.0.0",
        timestamp=datetime.utcnow()
    )


# ==============================================================================
# User Endpoints
# ==============================================================================

@router.get("/users", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    page: Optional[int] = Query(None, ge=1, description="Page number (overrides skip)"),
    per_page: Optional[int] = Query(None, ge=1, le=1000, description="Items per page (overrides limit)"),
    owner_id: Optional[int] = Query(None, description="Filter by owner ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    role: Optional[UserRole] = Query(None, description="Filter by role"),
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

    pages = (total + effective_limit - 1) // effective_limit if effective_limit > 0 else 0
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


@router.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("/users/{user_id}/employees", response_model=list[EmployeeWithUserResponse])
async def list_user_employees(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_async_db),
) -> list[EmployeeWithUserResponse]:
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
    employees, _ = await get_employees_by_owner(db, user_id, skip, limit)
    
    # Build enriched response with user data
    return [
        EmployeeWithUserResponse(
            **EmployeeResponse.model_validate(e).model_dump(),
            first_name=e.user.first_name,
            last_name=e.user.last_name,
            email=e.user.email,
        )
        for e in employees
    ]


# ==============================================================================
# Company Endpoints
# ==============================================================================

@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
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
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    List all organizations with pagination.

    Used by admin-bl-service for platform administration.
    """
    skip = (page - 1) * per_page
    organizations, total = await get_organizations(db, skip=skip, limit=per_page, is_active=is_active)
    
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    
    return {
        "items": [OrganizationResponse.model_validate(org) for org in organizations],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
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
        raise ConflictError(f"Organization with slug '{organization_data.slug}' already exists")
    
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
    reason: Optional[str] = Query(None, description="Reason for suspension"),
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


# ==============================================================================
# Audit Log Endpoints
# ==============================================================================

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    organization_id: Optional[int] = Query(None, description="Filter by organization"),
    actor_id: Optional[int] = Query(None, description="Filter by acting user"),
    action: Optional[str] = Query(None, description="Filter by action string"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
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
