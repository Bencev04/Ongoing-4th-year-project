"""
Authentication dependencies for Admin BL Service.

Thin wrapper around ``common.auth`` — the shared auth module
provides the heavy lifting; this module just wires it to the
admin service's settings and re-exports the public API.

All admin endpoints should use ``require_superadmin`` to enforce
that only platform-level administrators can access them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from common.auth import (  # noqa: F401 — re-exported
    CurrentUser,
    ROLE_HIERARCHY,
    create_auth_dependencies,
    verify_tenant_access,
)
from common.config import settings

# ---- Create dependency instances bound to this service's config ----
get_current_user, require_role, require_superadmin = create_auth_dependencies(
    settings.auth_service_url
)

__all__ = [
    "CurrentUser",
    "ROLE_HIERARCHY",
    "get_current_user",
    "require_role",
    "require_superadmin",
    "verify_tenant_access",
]
