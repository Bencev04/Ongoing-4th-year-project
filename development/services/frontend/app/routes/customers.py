"""
Customers page routes.

Serves the main customers list page and HTMX partial templates
for customer CRUD operations, detail views, and note management.
All data is fetched client-side via the /api/customers proxy.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.template_config import get_templates

# Configure Jinja2 templates relative to this file
templates: Jinja2Templates = get_templates()

router: APIRouter = APIRouter(tags=["customers"])


# ==============================================================================
# Full-page routes
# ==============================================================================


@router.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request) -> HTMLResponse:
    """
    Render the main customers list page.

    Customer data is loaded client-side via the Alpine.js ``customersApp``
    component, which calls ``/api/customers`` (proxied to customer-bl-service).
    """
    return templates.TemplateResponse(
        request,
        "pages/customers.html",
        {
            "title": "Customers",
        },
    )


# ==============================================================================
# HTMX partial routes
# ==============================================================================


@router.get("/customers/create-modal", response_class=HTMLResponse)
async def customer_create_modal(request: Request) -> HTMLResponse:
    """
    Render the *Create Customer* modal form (HTMX partial).

    Returned HTML is injected into ``#modal-container`` via hx-target.
    """
    return templates.TemplateResponse(
        request,
        "partials/customer_modal.html",
        {
            "customer": None,
            "is_edit": False,
        },
    )


@router.get("/customers/edit-modal/{customer_id}", response_class=HTMLResponse)
async def customer_edit_modal(
    request: Request,
    customer_id: int,
) -> HTMLResponse:
    """
    Render the *Edit Customer* modal form (HTMX partial).

    The actual customer data is fetched client-side; this template
    is pre-loaded with the ``customer_id`` so Alpine.js can populate
    the fields on mount.

    Args:
        request: Incoming FastAPI request.
        customer_id: Primary key of the customer to edit.
    """
    return templates.TemplateResponse(
        request,
        "partials/customer_modal.html",
        {
            "customer": None,  # Data loaded client-side via Alpine
            "customer_id": customer_id,
            "is_edit": True,
        },
    )


@router.get("/customers/detail/{customer_id}", response_class=HTMLResponse)
async def customer_detail_panel(
    request: Request,
    customer_id: int,
) -> HTMLResponse:
    """
    Render the customer detail side-panel (HTMX partial).

    Shows enriched customer info (contact details, recent jobs,
    notes) fetched client-side from ``/api/customers/<id>``.

    Args:
        request: Incoming FastAPI request.
        customer_id: Primary key of the customer.
    """
    return templates.TemplateResponse(
        request,
        "partials/customer_detail.html",
        {
            "customer_id": customer_id,
        },
    )


@router.get("/customers/delete-confirm/{customer_id}", response_class=HTMLResponse)
async def customer_delete_confirm(
    request: Request,
    customer_id: int,
) -> HTMLResponse:
    """
    Render the *Delete Customer* confirmation dialog (HTMX partial).

    Args:
        request: Incoming FastAPI request.
        customer_id: Primary key of the customer to delete.
    """
    return templates.TemplateResponse(
        request,
        "partials/customer_delete_confirm.html",
        {
            "customer_id": customer_id,
        },
    )
