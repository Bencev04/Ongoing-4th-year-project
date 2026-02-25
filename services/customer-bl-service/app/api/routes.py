"""
API routes for Customer Service (Business Logic Layer).

All endpoints enforce multi-tenant isolation.

Route summary
-------------
GET    /api/v1/customers                   – List/search customers.
POST   /api/v1/customers                   – Create customer.
GET    /api/v1/customers/{id}              – Get customer with enrichment.
PUT    /api/v1/customers/{id}              – Update customer.
DELETE /api/v1/customers/{id}              – Soft-delete customer.
GET    /api/v1/notes/{customer_id}         – List customer notes.
POST   /api/v1/notes/{customer_id}         – Add customer note.
PUT    /api/v1/notes/{id}                  – Update a note.
DELETE /api/v1/notes/{id}                  – Delete a note.
GET    /api/v1/customers/search            – Search customers.
GET    /api/v1/health                      – Health check.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

import sys
sys.path.append("../../../shared")
from common.schemas import HealthResponse

from ..dependencies import CurrentUser, get_current_user, require_role, verify_tenant_access
from ..schemas import (
    CustomerCreateRequest,
    CustomerListResponse,
    CustomerNoteCreateRequest,
    CustomerNoteResponse,
    CustomerNoteUpdateRequest,
    CustomerResponse,
    CustomerUpdateRequest,
    CustomerWithHistoryResponse,
    JobSummary,
)
from .. import service_client

router = APIRouter(prefix="/api/v1", tags=["customers"])


# ==============================================================================
# Health Check
# ==============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="customer-service",
        version="1.0.0",
        timestamp=datetime.utcnow(),
    )


# ==============================================================================
# Customer CRUD
# ==============================================================================

@router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    is_active: Optional[bool] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List customers belonging to the current tenant.

    Supports search by name, email, or company via the ``search``
    query parameter.
    """
    return await service_client.get_customers(
        skip=skip,
        limit=limit,
        owner_id=current_user.owner_id,
        search=search,
        is_active=is_active,
    )


@router.get("/customers/search", response_model=CustomerListResponse)
async def search_customers(
    q: str = Query(..., min_length=1, max_length=200),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Dedicated search endpoint for customer lookups.

    Useful for autocomplete and HTMX-powered search fields.
    """
    return await service_client.get_customers(
        skip=skip,
        limit=limit,
        owner_id=current_user.owner_id,
        search=q,
    )


@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    body: CustomerCreateRequest,
    current_user: CurrentUser = Depends(require_role("owner", "admin", "manager", "employee")),
) -> dict:
    """
    Create a new customer under the current tenant.

    Any authenticated user except viewers can create customers.
    The ``owner_id`` is injected from the JWT context — never from
    the request body.
    """
    payload = body.model_dump()
    # Security: inject owner_id from authenticated context
    payload["owner_id"] = current_user.effective_owner_id
    return await service_client.create_customer(payload)


@router.get("/customers/{customer_id}", response_model=CustomerWithHistoryResponse)
async def get_customer(
    customer_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Get a customer with enriched data (recent jobs, notes).

    Enforces tenant isolation.
    """
    customer = await service_client.get_customer(customer_id)

    # Tenant check (verify_tenant_access handles superadmin bypass)
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: customer belongs to a different tenant",
        )

    # Enrich with recent jobs (graceful degradation)
    jobs = await service_client.get_jobs_for_customer(
        customer_id=customer_id,
        owner_id=current_user.owner_id,
        limit=10,
    )
    customer["recent_jobs"] = [
        {
            "id": j["id"],
            "title": j.get("title", ""),
            "status": j.get("status", ""),
            "start_time": j.get("start_time"),
        }
        for j in jobs
    ]
    customer["total_jobs"] = len(jobs)

    # Enrich with notes
    try:
        notes = await service_client.get_customer_notes(customer_id)
        customer["customer_notes"] = notes
    except Exception:
        customer["customer_notes"] = []

    return customer


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    body: CustomerUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Update a customer's information."""
    # Verify ownership first
    existing = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    payload = body.model_dump(exclude_unset=True)
    return await service_client.update_customer(customer_id, payload)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> None:
    """
    Soft-delete a customer. Only owners and admins may do this.
    """
    existing = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    await service_client.delete_customer(customer_id)


# ==============================================================================
# Customer Notes
# ==============================================================================

@router.get(
    "/notes/{customer_id}",
    response_model=list[CustomerNoteResponse],
)
async def list_customer_notes(
    customer_id: int,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    """List all notes for a customer."""
    # Verify customer belongs to tenant
    customer = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    return await service_client.get_customer_notes(customer_id)


@router.post(
    "/notes/{customer_id}",
    response_model=CustomerNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_note(
    customer_id: int,
    body: CustomerNoteCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Add a note to a customer."""
    customer = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    payload = {
        "content": body.content,
        "created_by_id": current_user.user_id,
    }
    return await service_client.create_customer_note(customer_id, payload)


@router.put("/notes/{note_id}", response_model=CustomerNoteResponse)
async def update_note(
    note_id: int,
    body: CustomerNoteUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Update a customer note.

    Security: verifies tenant isolation by tracing the note back
    to its parent customer's ``owner_id`` before allowing mutation.
    """
    # Security: fetch note → get customer_id → verify customer's owner_id
    note_data = await service_client.get_customer_note(note_id)
    customer = await service_client.get_customer(note_data["customer_id"])
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: note belongs to a different tenant",
        )

    return await service_client.update_customer_note(
        note_id, {"content": body.content},
    )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: int,
    current_user: CurrentUser = Depends(require_role("owner", "admin")),
) -> None:
    """
    Delete a customer note. Only owners and admins may do this.

    Security: verifies tenant isolation by tracing the note back
    to its parent customer's ``owner_id`` before deletion.
    """
    # Security: fetch note → get customer_id → verify customer's owner_id
    note_data = await service_client.get_customer_note(note_id)
    customer = await service_client.get_customer(note_data["customer_id"])
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: note belongs to a different tenant",
        )

    await service_client.delete_customer_note(note_id)
