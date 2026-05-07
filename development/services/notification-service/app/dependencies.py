import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "shared"))

from common.auth import (
    ROLE_HIERARCHY,
    CurrentUser,
    create_auth_dependencies,
    verify_tenant_access,
)
from common.config import settings

_auth_url = getattr(settings, "auth_service_url", "http://auth-service:8005")
_user_svc_url = getattr(
    settings, "user_service_url", "http://user-db-access-service:8001"
)

get_current_user, require_role, require_superadmin, require_permission = (
    create_auth_dependencies(auth_service_url=_auth_url, user_service_url=_user_svc_url)
)

__all__ = [
    "CurrentUser",
    "ROLE_HIERARCHY",
    "get_current_user",
    "require_permission",
    "require_role",
    "require_superadmin",
    "verify_tenant_access",
]
