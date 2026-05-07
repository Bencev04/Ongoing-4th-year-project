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

import sys

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

sys.path.append("../../../shared")
from common.audit import log_action
from common.health import HealthChecker
from common.schemas import HealthResponse

from .. import service_client
from ..dependencies import (
    CurrentUser,
    get_current_user,
    require_permission,
    verify_tenant_access,
)
from ..schemas import (
    CustomerCreateRequest,
    CustomerListResponse,
    CustomerNoteCreateRequest,
    CustomerNoteResponse,
    CustomerNoteUpdateRequest,
    CustomerResponse,
    CustomerUpdateRequest,
    CustomerWithHistoryResponse,
)

router = APIRouter(prefix="/api/v1", tags=["customers"])


def _audit_scope_id(current_user: CurrentUser) -> int | None:
    """Resolve the tenant audit-scope identifier for the current user."""
    return current_user.organization_id or current_user.company_id


# ==============================================================================
# Health Check (Kubernetes Probes)
# ==============================================================================

_health_checker = HealthChecker("customer-service", "1.0.0")


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
        db=None,  # Customer BL doesn't touch DB directly
        check_redis=True,
        check_services={
            "customer-db-access": "http://customer-db-access-service:8002",
        },
    )


# ==============================================================================
# Customer CRUD
# ==============================================================================


@router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    page: int | None = Query(None, ge=1),
    per_page: int | None = Query(None, ge=1, le=1000),
    search: str | None = Query(None, min_length=1, max_length=200),
    is_active: bool | None = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    List customers belonging to the current tenant.

    Supports search by name, email, or company via the ``search``
    query parameter.  Pagination via ``page``/``per_page`` or
    ``skip``/``limit``.
    """
    if page is not None and per_page is not None:
        skip = (page - 1) * per_page
        limit = per_page
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
    current_user: CurrentUser = Depends(require_permission("customers.create")),
    request: Request = None,
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
    customer = await service_client.create_customer(payload)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.create",
        resource_type="customer",
        resource_id=str(customer["id"]),
        details={
            "name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
            "email": customer.get("email"),
            "company": customer.get("company"),
        },
        ip_address=request.client.host if request and request.client else None,
    )

    return customer


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
    request: Request = None,
) -> dict:
    """Update a customer's information."""
    # Verify ownership first
    existing = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    payload = body.model_dump(exclude_unset=True)
    customer = await service_client.update_customer(customer_id, payload)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.update",
        resource_type="customer",
        resource_id=str(customer_id),
        details={"updated_fields": sorted(payload.keys())},
        ip_address=request.client.host if request and request.client else None,
    )

    return customer


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    current_user: CurrentUser = Depends(require_permission("customers.delete")),
    request: Request = None,
) -> None:
    """
    Soft-delete a customer. Only owners and admins may do this.
    """
    existing = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, existing.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    await service_client.delete_customer(customer_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.delete",
        resource_type="customer",
        resource_id=str(customer_id),
        details={
            "name": f"{existing.get('first_name', '')} {existing.get('last_name', '')}".strip(),
            "email": existing.get("email"),
        },
        ip_address=request.client.host if request and request.client else None,
    )


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
    request: Request = None,
) -> dict:
    """Add a note to a customer."""
    customer = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(status_code=403, detail="Access denied")

    payload = {
        "content": body.content,
        "created_by_id": current_user.user_id,
    }
    note = await service_client.create_customer_note(customer_id, payload)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.note.create",
        resource_type="customer_note",
        resource_id=str(note["id"]),
        details={"customer_id": customer_id},
        ip_address=request.client.host if request and request.client else None,
    )

    return note


@router.put("/notes/{note_id}", response_model=CustomerNoteResponse)
async def update_note(
    note_id: int,
    body: CustomerNoteUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    request: Request = None,
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

    note = await service_client.update_customer_note(
        note_id,
        {"content": body.content},
    )

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.note.update",
        resource_type="customer_note",
        resource_id=str(note_id),
        details={"customer_id": note_data["customer_id"]},
        ip_address=request.client.host if request and request.client else None,
    )

    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: int,
    current_user: CurrentUser = Depends(require_permission("notes.delete")),
    request: Request = None,
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

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.note.delete",
        resource_type="customer_note",
        resource_id=str(note_id),
        details={"customer_id": note_data["customer_id"]},
        ip_address=request.client.host if request and request.client else None,
    )


# ==============================================================================
# GDPR Endpoints (Data Export & Anonymization)
# ==============================================================================


@router.get("/customers/{customer_id}/export")
async def export_customer_data(
    customer_id: int,
    current_user: CurrentUser = Depends(require_permission("customers.view")),
) -> dict:
    """
    Export all personal data for a customer (GDPR Article 15/20).

    Owner/admin exports data on behalf of the customer and provides
    it to them outside the application.
    """
    customer = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: customer belongs to a different tenant",
        )

    return await service_client.export_customer_data(customer_id)


@router.post("/customers/{customer_id}/anonymize")
async def anonymize_customer(
    customer_id: int,
    current_user: CurrentUser = Depends(require_permission("customers.delete")),
    request: Request = None,
) -> dict:
    """
    Anonymize a customer's personal data (GDPR Article 17).

    This is irreversible. Only owner/admin can trigger this.
    No grace period — the action is immediate upon confirmation.
    """
    customer = await service_client.get_customer(customer_id)
    if not verify_tenant_access(current_user, customer.get("owner_id")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: customer belongs to a different tenant",
        )

    data = await service_client.anonymize_customer(customer_id)

    await log_action(
        actor=current_user,
        organization_id=_audit_scope_id(current_user),
        action="customer.anonymized",
        resource_type="customer",
        resource_id=str(customer_id),
        ip_address=request.client.host if request and request.client else None,
    )

    return data
