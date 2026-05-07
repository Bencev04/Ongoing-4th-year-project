"""
API routes for Customer service.

Defines all **async** HTTP endpoints for customer operations.
"""

import sys

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append("../../../shared")
from common.database import get_async_db
from common.health import HealthChecker
from common.schemas import HealthResponse

from ..crud import (
    anonymize_customer,
    create_customer,
    create_note,
    delete_customer,
    delete_note,
    export_customer_data,
    get_customer,
    get_customer_notes,
    get_customers,
    get_note,
    update_customer,
    update_note,
)
from ..schemas import (
    CustomerCreate,
    CustomerListResponse,
    CustomerNoteCreate,
    CustomerNoteResponse,
    CustomerNoteUpdate,
    CustomerResponse,
    CustomerUpdate,
    CustomerWithNotesResponse,
)

# Create router with prefix
router = APIRouter(prefix="/api/v1", tags=["customers"])


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("customer-db-access-service", "1.0.0")


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
# Customer Endpoints
# ==============================================================================


@router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    owner_id: int = Query(..., description="Owner's user ID (required)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
    search: str | None = Query(None, description="Search in name, email, phone"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_async_db),
) -> CustomerListResponse:
    """
    List customers for an owner with optional filtering and pagination.

    Args:
        owner_id: Owner's user ID (required for tenant isolation)
        skip: Pagination offset
        limit: Maximum results per page
        search: Search term
        is_active: Filter by active status
        db: Async database session

    Returns:
        CustomerListResponse: Paginated list of customers
    """
    customers, total = await get_customers(
        db,
        owner_id=owner_id,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
    )

    pages = (total + limit - 1) // limit if limit > 0 else 0
    page = (skip // limit) + 1 if limit > 0 else 1

    return CustomerListResponse(
        items=[CustomerResponse.model_validate(c) for c in customers],
        total=total,
        page=page,
        per_page=limit,
        pages=pages,
    )


@router.post(
    "/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED
)
async def create_new_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_async_db),
) -> CustomerResponse:
    """
    Create a new customer.

    Args:
        customer_data: Customer creation payload
        db: Async database session

    Returns:
        CustomerResponse: Created customer data
    """
    customer = await create_customer(db, customer_data)
    return CustomerResponse.model_validate(customer)


@router.get("/customers/{customer_id}", response_model=CustomerWithNotesResponse)
async def get_customer_by_id(
    customer_id: int,
    include_notes: bool = Query(False, description="Include customer notes"),
    db: AsyncSession = Depends(get_async_db),
) -> CustomerWithNotesResponse:
    """
    Get a specific customer by ID.

    Args:
        customer_id: Customer's primary key
        include_notes: Whether to include notes in response
        db: Async database session

    Returns:
        CustomerWithNotesResponse: Customer data with optional notes

    Raises:
        HTTPException: 404 if customer not found
    """
    customer = await get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Build from base response to avoid lazy-loading the notes relationship
    base = CustomerResponse.model_validate(customer)
    notes_list: list[CustomerNoteResponse] = []

    if include_notes:
        notes, _ = await get_customer_notes(db, customer_id)
        notes_list = [CustomerNoteResponse.model_validate(n) for n in notes]

    return CustomerWithNotesResponse(**base.model_dump(), notes=notes_list)


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_existing_customer(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> CustomerResponse:
    """
    Update a customer's information.

    Args:
        customer_id: Customer's primary key
        customer_data: Fields to update
        db: Async database session

    Returns:
        CustomerResponse: Updated customer data

    Raises:
        HTTPException: 404 if customer not found
    """
    customer = await update_customer(db, customer_id, customer_data)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return CustomerResponse.model_validate(customer)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    Delete (deactivate) a customer.

    Args:
        customer_id: Customer's primary key
        db: Async database session

    Raises:
        HTTPException: 404 if customer not found
    """
    success = await delete_customer(db, customer_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )


# ==============================================================================
# GDPR Endpoints (Data Export & Anonymization)
# ==============================================================================


@router.get("/customers/{customer_id}/export")
async def export_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Export all personal data for a customer (GDPR Article 15/20).

    Returns a JSON document containing all PII held for this customer,
    suitable for data portability.
    """
    data = await export_customer_data(db, customer_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return data


@router.post("/customers/{customer_id}/anonymize")
async def anonymize_customer_endpoint(
    customer_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> dict:
    """
    Anonymize a customer's personal data (GDPR Article 17).

    Replaces all PII with anonymized placeholders, scrubs all notes.
    This is irreversible — only owner/admin should call this.
    """
    customer = await anonymize_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return {"status": "anonymized", "customer_id": customer_id}


# ==============================================================================
# Customer Note Endpoints
# ==============================================================================


@router.get("/customer-notes/{customer_id}", response_model=list[CustomerNoteResponse])
async def list_customer_notes(
    customer_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
) -> list[CustomerNoteResponse]:
    """
    List notes for a customer.

    Args:
        customer_id: Customer's primary key
        skip: Pagination offset
        limit: Maximum results
        db: Async database session

    Returns:
        list[CustomerNoteResponse]: List of notes
    """
    customer = await get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    notes, _ = await get_customer_notes(db, customer_id, skip, limit)
    return [CustomerNoteResponse.model_validate(n) for n in notes]


@router.post(
    "/customer-notes/",
    response_model=CustomerNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_note(
    note_data: CustomerNoteCreate,
    db: AsyncSession = Depends(get_async_db),
) -> CustomerNoteResponse:
    """
    Create a note for a customer.

    The ``customer_id`` is provided in the request body.

    Args:
        note_data: Note creation payload (includes customer_id)
        db: Async database session

    Returns:
        CustomerNoteResponse: Created note data
    """
    customer = await get_customer(db, note_data.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    note = await create_note(db, note_data)
    return CustomerNoteResponse.model_validate(note)


@router.get("/customer-notes/note/{note_id}", response_model=CustomerNoteResponse)
async def get_customer_note_by_id(
    note_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> CustomerNoteResponse:
    """
    Get a single customer note by its primary key.

    This endpoint supports tenant isolation checks in the BL layer
    by allowing it to fetch note metadata (including ``customer_id``)
    before performing mutations.

    Args:
        note_id: Note's primary key.
        db: Async database session.

    Returns:
        CustomerNoteResponse: Note data including ``customer_id``.

    Raises:
        HTTPException: 404 if note not found.
    """
    note = await get_note(db, note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
    return CustomerNoteResponse.model_validate(note)


@router.put("/customer-notes/{note_id}", response_model=CustomerNoteResponse)
async def update_customer_note(
    note_id: int,
    note_data: CustomerNoteUpdate,
    db: AsyncSession = Depends(get_async_db),
) -> CustomerNoteResponse:
    """
    Update a customer note.

    Args:
        note_id: Note's primary key
        note_data: Fields to update
        db: Async database session

    Returns:
        CustomerNoteResponse: Updated note data
    """
    note = await update_note(db, note_id, note_data)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    return CustomerNoteResponse.model_validate(note)


@router.delete("/customer-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer_note(
    note_id: int,
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """
    Delete a customer note.

    Args:
        note_id: Note's primary key
        db: Async database session
    """
    success = await delete_note(db, note_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )
