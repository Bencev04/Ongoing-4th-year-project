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
GET    /api/v1/health               – Health check.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

import sys
sys.path.append("../../../shared")
from common.schemas import HealthResponse

from ..dependencies import CurrentUser, get_current_user, require_role, verify_tenant_access
from ..schemas import (
    EmployeeCreateRequest,
    EmployeeResponse,
    EmployeeUpdateRequest,
    InviteEmployeeRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
    UserWithEmployeeResponse,
    CompanyCreateRequest,
    CompanyUpdateRequest,
    CompanyResponse,
)
from .. import service_client

router = APIRouter(prefix="/api/v1", tags=["users"])


# ==============================================================================
# Health Check
# ==============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint for monitoring and load balancers."""
    return HealthResponse(
        status="healthy",
        service="user-service",
        version="1.0.0",
        timestamp=datetime.utcnow(),
    )


# ==============================================================================
# User Endpoints (Tenant-Scoped)
# ==============================================================================

@router.get("/users", response_model=UserListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = Query(None),
    role: Optional[str] = Query(None),
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
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """
    Create a new user under the current tenant.

    Only owners and admins may create users.
    The ``owner_id`` is set to the caller's tenant automatically.
    """
    payload = body.model_dump()
    payload["owner_id"] = current_user.owner_id
    payload["company_id"] = current_user.company_id
    return await service_client.create_user(payload)


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

    payload = body.model_dump(exclude_unset=True)
    return await service_client.update_user(user_id, payload)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
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
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company associated with this account",
        )
    return await service_client.get_company(current_user.company_id)


@router.put("/company", response_model=CompanyResponse)
async def update_company(
    body: CompanyUpdateRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> dict:
    """
    Update the current user's company details.

    Only owners and admins may update company information.
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company associated with this account",
        )
    payload = body.model_dump(exclude_unset=True)
    return await service_client.update_company(current_user.company_id, payload)


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
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
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
        "owner_id": current_user.owner_id,
        "company_id": current_user.company_id,
    }
    user_data = await service_client.create_user(user_payload)

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
    return user_data


# ==============================================================================
# Employee Endpoints
# ==============================================================================

@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """
    List all employees in the current tenant.
    """
    return await service_client.get_employees_by_owner(
        owner_id=current_user.owner_id,
        skip=skip,
        limit=limit,
    )


@router.post(
    "/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_employee(
    body: EmployeeCreateRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
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
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
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
    return await service_client.update_employee(employee_id, payload)
