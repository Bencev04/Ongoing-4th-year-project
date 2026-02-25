"""
CRUD operations for User service.

Provides **async** database access functions for users and employees.
All database operations should go through these functions.
"""

from typing import Optional, List, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from passlib.context import CryptContext

from ..models.user import User, Employee, Company, UserRole, Organization, AuditLog, PlatformSetting
from ..schemas.user import (
    UserCreate, UserUpdate, EmployeeCreate, EmployeeUpdate, 
    CompanyCreate, CompanyUpdate, OrganizationCreate, OrganizationUpdate,
    AuditLogCreate, PlatformSettingCreate, PlatformSettingUpdate,
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """
    Hash a plain text password.

    Args:
        password: Plain text password

    Returns:
        str: Bcrypt hashed password
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Stored hashed password

    Returns:
        bool: True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


# ==============================================================================
# User CRUD Operations
# ==============================================================================

async def get_user(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Retrieve a user by ID.

    Args:
        db: Async database session
        user_id: User's primary key

    Returns:
        Optional[User]: User if found, None otherwise
    """
    result = await db.execute(select(User).filter(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Retrieve a user by email address.

    Args:
        db: Async database session
        email: User's email address

    Returns:
        Optional[User]: User if found, None otherwise
    """
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    owner_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    role: Optional[UserRole] = None,
) -> Tuple[List[User], int]:
    """
    Retrieve users with optional filtering and pagination.

    Args:
        db: Async database session
        skip: Number of records to skip (offset)
        limit: Maximum number of records to return
        owner_id: Filter by owner (for employees)
        is_active: Filter by active status
        role: Filter by user role

    Returns:
        Tuple[List[User], int]: List of users and total count
    """
    stmt = select(User)

    # Apply filters
    if owner_id is not None:
        stmt = stmt.filter(User.owner_id == owner_id)
    if is_active is not None:
        stmt = stmt.filter(User.is_active == is_active)
    if role is not None:
        stmt = stmt.filter(User.role == role)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Apply pagination
    result = await db.execute(stmt.offset(skip).limit(limit))
    users = list(result.scalars().all())

    return users, total


async def create_user(db: AsyncSession, user_data: UserCreate) -> User:
    """
    Create a new user.

    Args:
        db: Async database session
        user_data: User creation data

    Returns:
        User: Newly created user
    """
    hashed_password = get_password_hash(user_data.password)

    db_user = User(
        email=user_data.email,
        hashed_password=hashed_password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        role=user_data.role,
        owner_id=user_data.owner_id,
        company_id=user_data.company_id,
    )

    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)

    return db_user


async def update_user(
    db: AsyncSession,
    user_id: int,
    user_data: UserUpdate,
) -> Optional[User]:
    """
    Update an existing user.

    Args:
        db: Async database session
        user_id: User's primary key
        user_data: Fields to update

    Returns:
        Optional[User]: Updated user if found, None otherwise
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return None

    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)

    await db.commit()
    await db.refresh(db_user)

    return db_user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    """
    Delete a user (soft delete by deactivating).

    Args:
        db: Async database session
        user_id: User's primary key

    Returns:
        bool: True if user was deleted, False if not found
    """
    db_user = await get_user(db, user_id)
    if not db_user:
        return False

    db_user.is_active = False
    await db.commit()

    return True


async def authenticate_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Optional[User]:
    """
    Authenticate a user with email and password.

    Args:
        db: Async database session
        email: User's email
        password: Plain text password

    Returns:
        Optional[User]: Authenticated user or None if authentication fails
    """
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    if not user.is_active:
        return None
    return user


# ==============================================================================
# Employee CRUD Operations
# ==============================================================================

async def get_employee(db: AsyncSession, employee_id: int) -> Optional[Employee]:
    """
    Retrieve an employee by ID with user data eagerly loaded.

    Args:
        db: Async database session
        employee_id: Employee's primary key

    Returns:
        Optional[Employee]: Employee if found, None otherwise
    """
    result = await db.execute(
        select(Employee)
        .options(selectinload(Employee.user))
        .filter(Employee.id == employee_id)
    )
    return result.scalar_one_or_none()


async def get_employee_by_user_id(db: AsyncSession, user_id: int) -> Optional[Employee]:
    """
    Retrieve employee details by user ID.

    Args:
        db: Async database session
        user_id: User's primary key

    Returns:
        Optional[Employee]: Employee if found, None otherwise
    """
    result = await db.execute(select(Employee).filter(Employee.user_id == user_id))
    return result.scalar_one_or_none()


async def get_employees_by_owner(
    db: AsyncSession,
    owner_id: int,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[Employee], int]:
    """
    Retrieve all employees under a specific owner with user data.

    Args:
        db: Async database session
        owner_id: Owner's user ID
        skip: Pagination offset
        limit: Maximum results

    Returns:
        Tuple[List[Employee], int]: Employees (with user eager-loaded) and total count
    """
    stmt = (
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .options(selectinload(Employee.user))
        .filter(Employee.owner_id == owner_id)
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    result = await db.execute(stmt.offset(skip).limit(limit))
    employees = list(result.scalars().all())

    return employees, total


async def create_employee(db: AsyncSession, employee_data: EmployeeCreate) -> Employee:
    """
    Create employee details for a user.

    Args:
        db: Async database session
        employee_data: Employee creation data

    Returns:
        Employee: Newly created employee record
    """
    db_employee = Employee(
        user_id=employee_data.user_id,
        owner_id=employee_data.owner_id,
        department=employee_data.department,
        position=employee_data.position,
        phone=employee_data.phone,
        hire_date=employee_data.hire_date,
        hourly_rate=employee_data.hourly_rate,
        skills=employee_data.skills,
        notes=employee_data.notes,
        is_active=employee_data.is_active,
    )

    db.add(db_employee)
    await db.commit()
    await db.refresh(db_employee)

    return db_employee


async def update_employee(
    db: AsyncSession,
    employee_id: int,
    employee_data: EmployeeUpdate,
) -> Optional[Employee]:
    """
    Update employee details.

    Args:
        db: Async database session
        employee_id: Employee's primary key
        employee_data: Fields to update

    Returns:
        Optional[Employee]: Updated employee if found, None otherwise
    """
    db_employee = await get_employee(db, employee_id)
    if not db_employee:
        return None

    update_data = employee_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_employee, field, value)

    await db.commit()
    await db.refresh(db_employee)

    return db_employee


# ==============================================================================
# Company CRUD Operations
# ==============================================================================

async def get_company(db: AsyncSession, company_id: int) -> Optional[Company]:
    """
    Retrieve a company by ID.

    Args:
        db: Async database session
        company_id: Company's primary key

    Returns:
        Optional[Company]: Company if found, None otherwise
    """
    result = await db.execute(select(Company).filter(Company.id == company_id))
    return result.scalar_one_or_none()


async def create_company(db: AsyncSession, company_data: CompanyCreate) -> Company:
    """
    Create a new company.

    Args:
        db: Async database session
        company_data: Company creation data

    Returns:
        Company: Newly created company
    """
    db_company = Company(
        name=company_data.name,
        address=company_data.address,
        phone=company_data.phone,
        email=company_data.email,
        eircode=company_data.eircode,
        logo_url=company_data.logo_url,
    )

    db.add(db_company)
    await db.commit()
    await db.refresh(db_company)

    return db_company


async def update_company(
    db: AsyncSession,
    company_id: int,
    company_data: CompanyUpdate,
) -> Optional[Company]:
    """
    Update an existing company.

    Args:
        db: Async database session
        company_id: Company's primary key
        company_data: Fields to update

    Returns:
        Optional[Company]: Updated company if found, None otherwise
    """
    db_company = await get_company(db, company_id)
    if not db_company:
        return None

    update_data = company_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_company, field, value)

    await db.commit()
    await db.refresh(db_company)

    return db_company


# ==============================================================================
# Organization CRUD Operations
# ==============================================================================

async def get_organizations(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    is_active: Optional[bool] = None,
) -> Tuple[List[Organization], int]:
    """
    Fetch all organizations with pagination and optional filtering.

    Args:
        db: Async database session
        skip: Number of records to skip
        limit: Maximum records to return
        is_active: Optional filter by active status

    Returns:
        Tuple of (organizations list, total count)
    """
    stmt = select(Organization)
    
    if is_active is not None:
        stmt = stmt.filter(Organization.is_active == is_active)
    
    # Get total count
    count_stmt = select(func.count()).select_from(Organization)
    if is_active is not None:
        count_stmt = count_stmt.filter(Organization.is_active == is_active)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()
    
    # Get paginated results
    stmt = stmt.offset(skip).limit(limit).order_by(Organization.created_at.desc())
    result = await db.execute(stmt)
    organizations = result.scalars().all()
    
    return list(organizations), total


async def get_organization(db: AsyncSession, org_id: int) -> Optional[Organization]:
    """
    Retrieve a single organization by ID.

    Args:
        db: Async database session
        org_id: Organization's primary key

    Returns:
        Optional[Organization]: Organization if found, None otherwise
    """
    result = await db.execute(select(Organization).filter(Organization.id == org_id))
    return result.scalar_one_or_none()


async def get_organization_by_slug(db: AsyncSession, slug: str) -> Optional[Organization]:
    """
    Retrieve an organization by its unique slug.

    Args:
        db: Async database session
        slug: URL-safe unique identifier

    Returns:
        Optional[Organization]: Organization if found, None otherwise
    """
    result = await db.execute(select(Organization).filter(Organization.slug == slug))
    return result.scalar_one_or_none()


async def create_organization(
    db: AsyncSession,
    organization_data: OrganizationCreate,
) -> Organization:
    """
    Create a new organization.

    Args:
        db: Async database session
        organization_data: Organization creation payload

    Returns:
        Organization: Newly created organization
    """
    new_org = Organization(**organization_data.model_dump())
    db.add(new_org)
    await db.commit()
    await db.refresh(new_org)
    return new_org


async def update_organization(
    db: AsyncSession,
    org_id: int,
    organization_data: OrganizationUpdate,
) -> Optional[Organization]:
    """
    Update an existing organization.

    Args:
        db: Async database session
        org_id: Organization's primary key
        organization_data: Fields to update

    Returns:
        Optional[Organization]: Updated organization if found, None otherwise
    """
    db_org = await get_organization(db, org_id)
    if not db_org:
        return None

    update_data = organization_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_org, field, value)

    await db.commit()
    await db.refresh(db_org)

    return db_org


async def suspend_organization(
    db: AsyncSession,
    org_id: int,
    reason: Optional[str] = None,
) -> Optional[Organization]:
    """
    Suspend an organization.

    Args:
        db: Async database session
        org_id: Organization's primary key
        reason: Optional reason for suspension

    Returns:
        Optional[Organization]: Suspended organization if found, None otherwise
    """
    from datetime import datetime
    
    db_org = await get_organization(db, org_id)
    if not db_org:
        return None

    db_org.is_active = False
    db_org.suspended_at = datetime.utcnow()
    db_org.suspended_reason = reason

    await db.commit()
    await db.refresh(db_org)

    return db_org


async def unsuspend_organization(
    db: AsyncSession,
    org_id: int,
) -> Optional[Organization]:
    """
    Reactivate a suspended organization.

    Args:
        db: Async database session
        org_id: Organization's primary key

    Returns:
        Optional[Organization]: Reactivated organization if found, None otherwise
    """
    db_org = await get_organization(db, org_id)
    if not db_org:
        return None

    db_org.is_active = True
    db_org.suspended_at = None
    db_org.suspended_reason = None

    await db.commit()
    await db.refresh(db_org)

    return db_org


# ==============================================================================
# Audit Log CRUD Operations
# ==============================================================================

async def get_audit_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    organization_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
) -> Tuple[List[AuditLog], int]:
    """
    Retrieve audit log entries with optional filtering and pagination.

    Results are returned in reverse chronological order (newest first).

    Args:
        db:              Async database session.
        skip:            Pagination offset.
        limit:           Maximum records to return.
        organization_id: Filter by organization.
        actor_id:        Filter by acting user.
        action:          Filter by action string (exact match).
        resource_type:   Filter by resource type (exact match).

    Returns:
        Tuple of (audit_log list, total count).
    """
    stmt = select(AuditLog)

    if organization_id is not None:
        stmt = stmt.filter(AuditLog.organization_id == organization_id)
    if actor_id is not None:
        stmt = stmt.filter(AuditLog.actor_id == actor_id)
    if action is not None:
        stmt = stmt.filter(AuditLog.action == action)
    if resource_type is not None:
        stmt = stmt.filter(AuditLog.resource_type == resource_type)

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Paginated results, newest first
    stmt = stmt.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    logs = list(result.scalars().all())

    return logs, total


async def create_audit_log(
    db: AsyncSession,
    log_data: AuditLogCreate,
) -> AuditLog:
    """
    Write a new audit log entry.

    Audit log entries are immutable — once written they cannot be
    updated or deleted.

    Args:
        db:       Async database session.
        log_data: Audit log creation payload.

    Returns:
        The newly created ``AuditLog`` instance.
    """
    db_log = AuditLog(**log_data.model_dump())
    db.add(db_log)
    await db.commit()
    await db.refresh(db_log)
    return db_log


# ==============================================================================
# Platform Settings CRUD Operations
# ==============================================================================

async def get_platform_settings(
    db: AsyncSession,
) -> List[PlatformSetting]:
    """
    Retrieve all platform settings.

    Args:
        db: Async database session.

    Returns:
        List of all platform setting records.
    """
    result = await db.execute(
        select(PlatformSetting).order_by(PlatformSetting.key)
    )
    return list(result.scalars().all())


async def get_platform_setting(
    db: AsyncSession,
    key: str,
) -> Optional[PlatformSetting]:
    """
    Retrieve a single platform setting by key.

    Args:
        db:  Async database session.
        key: Unique setting key.

    Returns:
        ``PlatformSetting`` if found, ``None`` otherwise.
    """
    result = await db.execute(
        select(PlatformSetting).filter(PlatformSetting.key == key)
    )
    return result.scalar_one_or_none()


async def upsert_platform_setting(
    db: AsyncSession,
    key: str,
    setting_data: PlatformSettingUpdate,
    updated_by: Optional[int] = None,
) -> PlatformSetting:
    """
    Create or update a platform setting.

    If the key already exists, the value and description are updated.
    If it does not exist, a new row is inserted.

    Args:
        db:           Async database session.
        key:          Setting key.
        setting_data: New value/description payload.
        updated_by:   User ID of the updater (superadmin).

    Returns:
        The created or updated ``PlatformSetting``.
    """
    existing = await get_platform_setting(db, key)

    if existing:
        update_data = setting_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(existing, field, value)
        if updated_by is not None:
            existing.updated_by = updated_by
        await db.commit()
        await db.refresh(existing)
        return existing

    # Create new setting
    new_setting = PlatformSetting(
        key=key,
        value=setting_data.value,
        description=setting_data.description,
        updated_by=updated_by,
    )
    db.add(new_setting)
    await db.commit()
    await db.refresh(new_setting)
    return new_setting

