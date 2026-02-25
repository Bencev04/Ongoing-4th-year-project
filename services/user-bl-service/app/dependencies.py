"""
Auth dependencies for the User BL Service.

Delegates all authentication, role-based access control, and tenant
isolation logic to the shared ``common.auth`` module.  This thin
wrapper exists so that route modules can continue importing from
``..dependencies`` without knowing about the shared library path.

Re-exports
----------
* ``CurrentUser``         — authenticated user context value object.
* ``get_current_user``    — FastAPI dependency (validates token via auth-service).
* ``require_role``        — FastAPI dependency factory (role hierarchy check).
* ``require_superadmin``  — FastAPI dependency (superadmin-only access).
* ``verify_tenant_access``— helper to enforce tenant isolation boundaries.
* ``ROLE_HIERARCHY``      — numeric role ranking dict.

See Also:
    ``services/shared/common/auth.py`` for the full implementation.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup: ensure the shared library is importable regardless of
# the working directory (Docker sets PYTHONPATH, but local dev may not).
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared"))

from common.config import settings
from common.auth import (                       # noqa: E402
    CurrentUser,
    ROLE_HIERARCHY,
    create_auth_dependencies,
    verify_tenant_access,
)

# ---------------------------------------------------------------------------
# Instantiate service-specific auth dependencies by binding to the
# auth-service URL from centralised config.  The factory returns a
# tuple of three callables ready for use in ``Depends()``.
# ---------------------------------------------------------------------------
_auth_url: str = getattr(settings, "auth_service_url", "http://auth-service:8005")

get_current_user, require_role, require_superadmin = create_auth_dependencies(
    auth_service_url=_auth_url,
)

# ---------------------------------------------------------------------------
# Public API — everything route modules need is re-exported here.
# ---------------------------------------------------------------------------
__all__ = [
    "CurrentUser",
    "ROLE_HIERARCHY",
    "get_current_user",
    "require_role",
    "require_superadmin",
    "verify_tenant_access",
]
