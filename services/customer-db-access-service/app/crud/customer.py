"""
CRUD operations for Customer service.

Provides **async** database access functions for customers and notes.
"""

from typing import Optional, List, Tuple

from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.customer import Customer, CustomerNote
from ..schemas.customer import (
    CustomerCreate, CustomerUpdate,
    CustomerNoteCreate, CustomerNoteUpdate
)


# ==============================================================================
# Customer CRUD Operations
# ==============================================================================

async def get_customer(db: AsyncSession, customer_id: int) -> Optional[Customer]:
    """
    Retrieve a customer by ID.

    Args:
        db: Async database session
        customer_id: Customer's primary key

    Returns:
        Optional[Customer]: Customer if found, None otherwise
    """
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    return result.scalar_one_or_none()


async def get_customer_by_email(
    db: AsyncSession,
    email: str,
    owner_id: int,
) -> Optional[Customer]:
    """
    Retrieve a customer by email within an owner's customers.

    Args:
        db: Async database session
        email: Customer's email address
        owner_id: Owner's user ID

    Returns:
        Optional[Customer]: Customer if found, None otherwise
    """
    result = await db.execute(
        select(Customer).filter(
            Customer.email == email,
            Customer.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def get_customers(
    db: AsyncSession,
    owner_id: int,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Tuple[List[Customer], int]:
    """
    Retrieve customers with optional filtering and pagination.

    Args:
        db: Async database session
        owner_id: Owner's user ID (required for tenant isolation)
        skip: Number of records to skip (offset)
        limit: Maximum number of records to return
        search: Search term for name, email, or phone
        is_active: Filter by active status

    Returns:
        Tuple[List[Customer], int]: List of customers and total count
    """
    stmt = select(Customer).filter(Customer.owner_id == owner_id)

    # Apply search filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.filter(
            or_(
                Customer.name.ilike(search_term),
                Customer.email.ilike(search_term),
                Customer.phone.ilike(search_term),
                Customer.company_name.ilike(search_term),
            )
        )

    # Apply status filter
    if is_active is not None:
        stmt = stmt.filter(Customer.is_active == is_active)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Apply pagination and ordering
    result = await db.execute(
        stmt.order_by(Customer.name).offset(skip).limit(limit)
    )
    customers = list(result.scalars().all())

    return customers, total


async def create_customer(db: AsyncSession, customer_data: CustomerCreate) -> Customer:
    """
    Create a new customer.

    Args:
        db: Async database session
        customer_data: Customer creation data

    Returns:
        Customer: Newly created customer
    """
    db_customer = Customer(
        owner_id=customer_data.owner_id,
        name=customer_data.name,
        email=customer_data.email,
        phone=customer_data.phone,
        address=customer_data.address,
        eircode=customer_data.eircode,
        company_name=customer_data.company_name,
    )

    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)

    return db_customer


async def update_customer(
    db: AsyncSession,
    customer_id: int,
    customer_data: CustomerUpdate,
) -> Optional[Customer]:
    """
    Update an existing customer.

    Args:
        db: Async database session
        customer_id: Customer's primary key
        customer_data: Fields to update

    Returns:
        Optional[Customer]: Updated customer if found, None otherwise
    """
    db_customer = await get_customer(db, customer_id)
    if not db_customer:
        return None

    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_customer, field, value)

    await db.commit()
    await db.refresh(db_customer)

    return db_customer


async def delete_customer(db: AsyncSession, customer_id: int) -> bool:
    """
    Delete a customer (soft delete by deactivating).

    Args:
        db: Async database session
        customer_id: Customer's primary key

    Returns:
        bool: True if customer was deleted, False if not found
    """
    db_customer = await get_customer(db, customer_id)
    if not db_customer:
        return False

    db_customer.is_active = False
    await db.commit()

    return True


# ==============================================================================
# Customer Note CRUD Operations
# ==============================================================================

async def get_note(db: AsyncSession, note_id: int) -> Optional[CustomerNote]:
    """
    Retrieve a customer note by ID.

    Args:
        db: Async database session
        note_id: Note's primary key

    Returns:
        Optional[CustomerNote]: Note if found, None otherwise
    """
    result = await db.execute(select(CustomerNote).filter(CustomerNote.id == note_id))
    return result.scalar_one_or_none()


async def get_customer_notes(
    db: AsyncSession,
    customer_id: int,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[CustomerNote], int]:
    """
    Retrieve notes for a customer.

    Args:
        db: Async database session
        customer_id: Customer's primary key
        skip: Pagination offset
        limit: Maximum results

    Returns:
        Tuple[List[CustomerNote], int]: Notes and total count
    """
    stmt = select(CustomerNote).filter(CustomerNote.customer_id == customer_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Order by creation date (newest first)
    result = await db.execute(
        stmt.order_by(
            CustomerNote.created_at.desc(),
        ).offset(skip).limit(limit)
    )
    notes = list(result.scalars().all())

    return notes, total


async def create_note(db: AsyncSession, note_data: CustomerNoteCreate) -> CustomerNote:
    """
    Create a new customer note.

    Args:
        db: Async database session
        note_data: Note creation data

    Returns:
        CustomerNote: Newly created note
    """
    db_note = CustomerNote(
        customer_id=note_data.customer_id,
        created_by_id=note_data.created_by_id,
        content=note_data.content,
    )

    db.add(db_note)
    await db.commit()
    await db.refresh(db_note)

    return db_note


async def update_note(
    db: AsyncSession,
    note_id: int,
    note_data: CustomerNoteUpdate,
) -> Optional[CustomerNote]:
    """
    Update a customer note.

    Args:
        db: Async database session
        note_id: Note's primary key
        note_data: Fields to update

    Returns:
        Optional[CustomerNote]: Updated note if found, None otherwise
    """
    db_note = await get_note(db, note_id)
    if not db_note:
        return None

    update_data = note_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_note, field, value)

    await db.commit()
    await db.refresh(db_note)

    return db_note


async def delete_note(db: AsyncSession, note_id: int) -> bool:
    """
    Delete a customer note (hard delete).

    Args:
        db: Async database session
        note_id: Note's primary key

    Returns:
        bool: True if note was deleted, False if not found
    """
    db_note = await get_note(db, note_id)
    if not db_note:
        return False

    await db.delete(db_note)
    await db.commit()

    return True
