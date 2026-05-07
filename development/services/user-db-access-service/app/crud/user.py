"""
CRUD operations for User service.

Provides **async** database access functions for users and employees.
All database operations should go through these functions.
"""

import secrets
from datetime import UTC, datetime, timedelta

from passlib.context import CryptContext
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.user import (
    AuditLog,
    Company,
    Employee,
    Organization,
    PlatformSetting,
    User,
    UserRole,
)
from ..schemas.user import (
    AuditLogCreate,
    CompanyCreate,
    CompanyUpdate,
    EmployeeCreate,
    EmployeeUpdate,
    OrganizationCreate,
    OrganizationUpdate,
    PlatformSettingUpdate,
    UserCreate,
    UserUpdate,
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


async def get_user(db: AsyncSession, user_id: int) -> User | None:
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


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
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
    owner_id: int | None = None,
    is_active: bool | None = None,
    role: UserRole | None = None,
) -> tuple[list[User], int]:
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

    # Deterministic ordering prevents unstable pagination under writes.
    stmt = stmt.order_by(User.created_at.desc(), User.id.asc())

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
) -> User | None:
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
) -> User | None:
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


async def get_employee(db: AsyncSession, employee_id: int) -> Employee | None:
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


async def get_employee_by_user_id(db: AsyncSession, user_id: int) -> Employee | None:
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
    search: str | None = None,
) -> tuple[list[Employee], int]:
    """
    Retrieve all employees under a specific owner with user data.

    Args:
        db: Async database session
        owner_id: Owner's user ID
        skip: Pagination offset
        limit: Maximum results
        search: Optional search query across employee/user fields

    Returns:
        Tuple[List[Employee], int]: Employees (with user eager-loaded) and total count
    """
    stmt = (
        select(Employee)
        .join(User, Employee.user_id == User.id)
        .options(selectinload(Employee.user))
        .filter(Employee.owner_id == owner_id)
    )

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.filter(
            or_(
                User.first_name.ilike(term),
                User.last_name.ilike(term),
                User.email.ilike(term),
                Employee.position.ilike(term),
                Employee.skills.ilike(term),
            )
        )

    # Deterministic ordering for stable pagination.
    stmt = stmt.order_by(User.last_name.asc(), User.first_name.asc(), Employee.id.asc())

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
) -> Employee | None:
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


async def get_company(db: AsyncSession, company_id: int) -> Company | None:
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
) -> Company | None:
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
    is_active: bool | None = None,
) -> tuple[list[Organization], int]:
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


async def get_organization(db: AsyncSession, org_id: int) -> Organization | None:
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


async def get_organization_by_slug(db: AsyncSession, slug: str) -> Organization | None:
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
) -> Organization | None:
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
    reason: str | None = None,
) -> Organization | None:
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
) -> Organization | None:
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


async def delete_organization(db: AsyncSession, org_id: int) -> bool:
    """
    Delete an organization by ID.

    Args:
        db: Async database session
        org_id: Organization's primary key

    Returns:
        True if the organization was deleted, False if not found.
    """
    db_org = await get_organization(db, org_id)
    if not db_org:
        return False

    await db.delete(db_org)
    await db.commit()
    return True


# ==============================================================================
# Audit Log CRUD Operations
# ==============================================================================


async def get_audit_logs(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    organization_id: int | None = None,
    actor_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    search: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[AuditLog], int]:
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
        search:          Free-text search across actor_email, action,
                         resource_type, and resource_id.
        date_from:       Only return entries on or after this timestamp.
        date_to:         Only return entries on or before this timestamp.

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
    if search:
        pattern = f"%{search}%"
        stmt = stmt.filter(
            or_(
                AuditLog.actor_email.ilike(pattern),
                AuditLog.action.ilike(pattern),
                AuditLog.resource_type.ilike(pattern),
                AuditLog.resource_id.ilike(pattern),
            )
        )
    if date_from is not None:
        stmt = stmt.filter(AuditLog.timestamp >= date_from)
    if date_to is not None:
        stmt = stmt.filter(AuditLog.timestamp <= date_to)

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
) -> list[PlatformSetting]:
    """
    Retrieve all platform settings.

    Args:
        db: Async database session.

    Returns:
        List of all platform setting records.
    """
    result = await db.execute(select(PlatformSetting).order_by(PlatformSetting.key))
    return list(result.scalars().all())


async def get_platform_setting(
    db: AsyncSession,
    key: str,
) -> PlatformSetting | None:
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
    updated_by: int | None = None,
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


# ==============================================================================
# GDPR: Data Export & Anonymization
# ==============================================================================


async def export_user_data(db: AsyncSession, user_id: int) -> dict | None:
    """
    Export all personal data for a user (GDPR Article 15 / 20).

    Returns a structured dict with the user's profile, employee record,
    and audit log entries.  Returns ``None`` if the user does not exist.
    """
    user = await get_user(db, user_id)
    if not user:
        return None

    employee = await get_employee_by_user_id(db, user_id)

    # Audit log entries where the user was the actor
    audit_stmt = (
        select(AuditLog)
        .filter(AuditLog.actor_id == user_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(500)
    )
    audit_result = await db.execute(audit_stmt)
    audit_logs = list(audit_result.scalars().all())

    export = {
        "profile": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": user.role,
            "is_active": user.is_active,
            "owner_id": user.owner_id,
            "company_id": user.company_id,
            "organization_id": user.organization_id,
            "privacy_consent_at": user.privacy_consent_at.isoformat()
            if user.privacy_consent_at
            else None,
            "privacy_consent_version": user.privacy_consent_version,
            "created_at": user.created_at.isoformat(),
            "updated_at": user.updated_at.isoformat(),
        },
        "employee": None,
        "audit_log_entries": [],
    }

    if employee:
        export["employee"] = {
            "id": employee.id,
            "department": employee.department,
            "position": employee.position,
            "phone": employee.phone,
            "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
            "hourly_rate": float(employee.hourly_rate)
            if employee.hourly_rate
            else None,
            "skills": employee.skills,
            "notes": employee.notes,
            "is_active": employee.is_active,
            "created_at": employee.created_at.isoformat(),
        }

    for log in audit_logs:
        export["audit_log_entries"].append(
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "ip_address": log.ip_address,
            }
        )

    return export


async def anonymize_user(db: AsyncSession, user_id: int) -> User | None:
    """
    Anonymize a user's personal data (GDPR Article 17 — right to erasure).

    Replaces PII with anonymized placeholders while preserving referential
    integrity.  Also anonymizes the linked employee record and scrubs
    ``actor_email`` from audit logs authored by this user.

    Returns the anonymized ``User`` or ``None`` if not found.
    """
    user = await get_user(db, user_id)
    if not user:
        return None

    # Anonymize user PII
    user.email = f"deleted_user_{user_id}@anonymized.local"
    user.first_name = "Deleted"
    user.last_name = "User"
    user.phone = None
    user.hashed_password = f"!anonymized_{secrets.token_hex(16)}"
    user.is_active = False
    user.anonymize_scheduled_at = None

    # Anonymize linked employee record
    employee = await get_employee_by_user_id(db, user_id)
    if employee:
        employee.phone = None
        employee.skills = None
        employee.notes = None
        employee.hourly_rate = None
        employee.is_active = False

    # Scrub actor_email from audit logs authored by this user
    await db.execute(
        sa_update(AuditLog)
        .where(AuditLog.actor_id == user_id)
        .values(actor_email="anonymized")
    )

    # Record the anonymization in the audit log (no PII in details)
    anon_log = AuditLog(
        actor_id=user_id,
        actor_email="anonymized",
        actor_role=user.role,
        action="user.anonymized",
        resource_type="user",
        resource_id=str(user_id),
        details={"note": "User data anonymized per GDPR request"},
    )
    db.add(anon_log)

    await db.commit()
    await db.refresh(user)
    return user


async def schedule_user_anonymization(
    db: AsyncSession, user_id: int, scheduled_at: datetime
) -> User | None:
    """
    Schedule a user for anonymization after a 72-hour grace period.

    Sets ``anonymize_scheduled_at`` — the actual anonymization is
    performed by a scheduled task after the grace period expires.
    """
    user = await get_user(db, user_id)
    if not user:
        return None

    user.anonymize_scheduled_at = scheduled_at
    await db.commit()
    await db.refresh(user)
    return user


async def cancel_user_anonymization(db: AsyncSession, user_id: int) -> User | None:
    """Cancel a pending anonymization request."""
    user = await get_user(db, user_id)
    if not user:
        return None

    user.anonymize_scheduled_at = None
    await db.commit()
    await db.refresh(user)
    return user


async def get_users_due_for_anonymization(db: AsyncSession) -> list[User]:
    """Return users whose ``anonymize_scheduled_at`` has passed.

    These users requested account deletion and their 72-hour grace
    period has expired.  The scheduler calls this to find accounts
    that should be anonymized.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        select(User).where(
            User.anonymize_scheduled_at.isnot(None),
            User.anonymize_scheduled_at <= now,
            User.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


async def process_scheduled_anonymizations(db: AsyncSession) -> int:
    """Find and anonymize all users whose grace period has expired.

    Returns the number of users anonymized.
    """
    users = await get_users_due_for_anonymization(db)
    count = 0
    for user in users:
        await anonymize_user(db, user.id)
        count += 1
    return count


async def cleanup_old_audit_logs(db: AsyncSession, retention_days: int = 730) -> int:
    """
    Delete audit log entries older than ``retention_days`` (GDPR data minimization).

    Defaults to 730 days (2 years).  Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = await db.execute(sa_delete(AuditLog).where(AuditLog.timestamp < cutoff))
    await db.commit()
    return result.rowcount
