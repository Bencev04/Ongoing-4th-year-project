"""
Audit trail helper for all BL services.

Provides a lightweight async function to write audit log entries
to the ``user-db-access-service`` without blocking the caller.

Usage
-----
::

    from common.audit import log_action

    await log_action(
        actor=current_user,
        action="job.create",
        resource_type="job",
        resource_id=str(job_id),
        details={"title": "Fix boiler"},
        ip_address=request.client.host,
    )

Design decisions
----------------
- **Fire-and-forget** style — audit log failures are logged but
  do **not** raise exceptions or block the primary operation.
- Uses a module-level ``httpx.AsyncClient`` that is lazily created
  on first call and reused for connection pooling.
- The ``CurrentUser`` protocol (duck-typed) keeps this module
  decoupled from ``common.auth`` — any object with ``user_id``,
  ``email``, ``role``, and ``impersonator_id`` attributes works.

Security
--------
Audit log entries are **immutable** — once written they cannot be
updated or deleted through the API.  The ``impersonator_id`` field
ensures that actions performed via impersonation are always
traceable to the originating superadmin.
"""

import logging
from typing import Any, Protocol, runtime_checkable

import httpx

from common.config import settings

logger = logging.getLogger(__name__)

# Lazily initialised — avoids import-time side effects in tests
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """
    Return the module-level async HTTP client, creating it on first use.

    Returns:
        Shared ``httpx.AsyncClient`` instance.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=5.0)
    return _http_client


# ==============================================================================
# Actor Protocol (duck-typed CurrentUser)
# ==============================================================================


@runtime_checkable
class AuditActor(Protocol):
    """
    Minimal interface for the actor field in audit logs.

    Any object satisfying this protocol can be passed to
    ``log_action``.  The ``CurrentUser`` class from
    ``common.auth`` implements this protocol.
    """

    user_id: int
    email: str
    role: str
    impersonator_id: int | None


# ==============================================================================
# Public API
# ==============================================================================


async def log_action(
    *,
    actor: AuditActor,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    organization_id: int | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Write an audit log entry to the user-db-access-service.

    This function is **fire-and-forget** — it suppresses all
    exceptions so that audit failures never block the primary
    business operation.

    Args:
        actor:           The user performing the action.  Must
                         satisfy the ``AuditActor`` protocol.
        action:          Machine-readable action identifier,
                         e.g. ``"user.create"``, ``"org.suspend"``.
        resource_type:   Type of resource affected (e.g. ``"user"``).
        resource_id:     Primary key of the affected resource.
        organization_id: Organization context (optional).
        details:         Free-form JSON metadata for the entry.
        ip_address:      Client IP from the request.

    Example::

        await log_action(
            actor=current_user,
            action="job.delete",
            resource_type="job",
            resource_id="42",
            details={"reason": "Duplicate entry"},
        )
    """
    entry: dict[str, Any] = {
        "actor_id": actor.user_id,
        "actor_email": actor.email,
        "actor_role": actor.role,
        "impersonator_id": actor.impersonator_id,
        "organization_id": organization_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "details": details,
        "ip_address": ip_address,
    }

    try:
        client = _get_client()
        resp = await client.post(
            f"{settings.user_service_url}/api/v1/audit-logs",
            json=entry,
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                "Audit log write returned %d for action '%s'",
                resp.status_code,
                action,
            )
    except Exception:
        # Fire-and-forget — never block the primary operation
        logger.warning(
            "Failed to write audit log for action '%s' (suppressed)",
            action,
            exc_info=True,
        )
