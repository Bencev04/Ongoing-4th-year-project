"""
Shared authorization module for all business-logic services.

Provides a single source of truth for authentication dependencies,
role-based access control, and tenant isolation utilities used by
every BL service (user-bl, job-bl, customer-bl, admin-bl).

Architecture
------------
BL services **never** decode JWTs locally.  Instead, each request's
Bearer token is forwarded to the auth-service via ``POST /api/v1/auth/verify``.
The auth-service validates the signature, checks the blacklist, and returns
a ``TokenVerifyResponse`` payload.  This module converts that payload into
a ``CurrentUser`` context object consumed by route handlers.

Security notes
--------------
* **Role hierarchy** — roles are ranked numerically (superadmin=100 …
  viewer=10).  ``require_role`` passes when the caller's level is ≥
  the minimum level among the requested roles.  Superadmin implicitly
  passes every check.
* **Tenant isolation** — every tenant-facing route must call
  ``verify_tenant_access()`` before returning data.  Superadmins
  bypass tenant checks.  Impersonating users use ``effective_owner_id``
  which resolves to the impersonation target.
* **Impersonation** — a superadmin can obtain a shadow token whose
  ``acting_as`` claim sets the ``effective_owner_id`` to the target
  tenant.  The original superadmin's ``user_id`` is preserved in
  ``impersonator_id`` for full audit traceability.
"""

from collections.abc import Callable

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ==============================================================================
# Role Hierarchy
# ==============================================================================

# Numeric ranking for role-based access control.
# Higher number = more privilege.  Superadmin is the highest.
ROLE_HIERARCHY: dict[str, int] = {
    "superadmin": 100,
    "owner": 80,
    "admin": 60,
    "manager": 40,
    "employee": 20,
    "viewer": 10,
}


# ==============================================================================
# CurrentUser Value Object
# ==============================================================================


class CurrentUser:
    """
    Authenticated user context populated from auth-service verification.

    Every route handler receives an instance of this class via FastAPI
    dependency injection.  It carries all the claims extracted from the
    JWT by the auth-service plus convenience properties for tenant
    isolation and impersonation checks.

    Attributes:
        user_id:            Authenticated user's primary key.
        email:              User email address.
        role:               Role string (superadmin | owner | admin |
                            manager | employee | viewer).
        owner_id:           Tenant (business-owner) ID — the multi-tenancy
                            key.  ``None`` for superadmins who are not
                            impersonating.
        company_id:         Company identifier for tenant metadata.
        organization_id:    Organization identifier (superadmin context).
        acting_as_owner_id: If impersonating, the target tenant's owner_id.
        impersonator_id:    Original superadmin user_id during impersonation.
    """

    __slots__ = (
        "user_id",
        "email",
        "role",
        "owner_id",
        "company_id",
        "organization_id",
        "acting_as_owner_id",
        "impersonator_id",
    )

    def __init__(
        self,
        user_id: int,
        email: str,
        role: str,
        owner_id: int | None = None,
        company_id: int | None = None,
        organization_id: int | None = None,
        acting_as_owner_id: int | None = None,
        impersonator_id: int | None = None,
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role
        self.owner_id = owner_id
        self.company_id = company_id
        self.organization_id = organization_id
        self.acting_as_owner_id = acting_as_owner_id
        self.impersonator_id = impersonator_id

    # ------------------------------------------------------------------
    # Computed Properties
    # ------------------------------------------------------------------

    @property
    def is_superadmin(self) -> bool:
        """Whether this user has system-wide superadmin privileges."""
        return self.role == "superadmin"

    @property
    def effective_owner_id(self) -> int | None:
        """
        The owner_id to use for tenant-scoped queries.

        During impersonation this returns the *target* tenant's
        owner_id (``acting_as_owner_id``).  Otherwise it returns
        the user's own ``owner_id``.

        Returns ``None`` for superadmins who are not impersonating,
        which signals that tenant filtering should be skipped (only
        valid in admin-portal endpoints).
        """
        if self.acting_as_owner_id is not None:
            return self.acting_as_owner_id
        return self.owner_id

    @property
    def is_impersonating(self) -> bool:
        """
        Whether this session is an impersonation session.

        True when a superadmin is operating with a shadow token
        that has an ``acting_as`` claim.  All actions during
        impersonation carry the ``impersonator_id`` for audit.
        """
        return self.impersonator_id is not None

    def __repr__(self) -> str:
        """Human-readable representation for logging and debugging."""
        parts: list[str] = [
            f"user_id={self.user_id}",
            f"role='{self.role}'",
            f"owner_id={self.owner_id}",
        ]
        if self.is_impersonating:
            parts.append(f"acting_as={self.acting_as_owner_id}")
            parts.append(f"impersonator={self.impersonator_id}")
        return f"CurrentUser({', '.join(parts)})"


# ==============================================================================
# Tenant Isolation Helper
# ==============================================================================


def verify_tenant_access(
    current_user: CurrentUser,
    resource_owner_id: int | None,
) -> bool:
    """
    Check whether the current user may access a resource in a given tenant.

    This is the **single point of truth** for tenant boundary enforcement.
    Every BL route that reads or mutates a tenant-scoped resource must
    call this function before proceeding.

    Security:
        * Superadmins always pass (they operate above the tenant level).
        * Impersonating users pass if ``effective_owner_id`` matches.
        * Regular users pass only if their ``owner_id`` matches exactly.

    Args:
        current_user:       The authenticated user context.
        resource_owner_id:  The ``owner_id`` of the resource being accessed.
                            May be ``None`` for resources without tenant scope
                            (e.g. superadmin-only entities).

    Returns:
        ``True`` if access is permitted, ``False`` otherwise.
    """
    # Security: superadmins bypass tenant checks entirely
    if current_user.is_superadmin:
        return True

    # Security: resource without owner scope — deny non-superadmins
    if resource_owner_id is None:
        return False

    # Security: compare effective_owner_id (handles impersonation)
    return current_user.effective_owner_id == resource_owner_id


# ==============================================================================
# Dependency Factory
# ==============================================================================


def create_auth_dependencies(
    auth_service_url: str,
    user_service_url: str | None = None,
) -> tuple[Callable, Callable, Callable, Callable]:
    """
    Factory that creates FastAPI auth dependencies bound to a specific
    auth-service URL.

    Each BL service calls this once at import time to obtain its own
    ``get_current_user``, ``require_role``, ``require_superadmin``, and
    ``require_permission`` dependency callables.

    Args:
        auth_service_url:  Base URL of the auth-service instance
                           (e.g. ``"http://auth-service:8005"``).
        user_service_url:  Base URL of the user-db-access-service
                           (e.g. ``"http://user-db-access-service:8001"``).
                           Required for ``require_permission`` to work.

    Returns:
        A tuple of ``(get_current_user, require_role, require_superadmin,
        require_permission)`` dependency callables ready for use in
        FastAPI ``Depends()``.

    Example::

        from common.auth import create_auth_dependencies
        get_current_user, require_role, require_superadmin, require_permission = (
            create_auth_dependencies(
                "http://auth-service:8005",
                "http://user-db-access-service:8001",
            )
        )
    """

    # Security: auto_error=False so we return a custom 401 message
    # instead of FastAPI's default "Not authenticated" response.
    _bearer_scheme = HTTPBearer(auto_error=False)

    # Security: 5-second timeout prevents BL services from hanging
    # when the auth-service is slow or unreachable.
    _auth_client: httpx.AsyncClient = httpx.AsyncClient(timeout=5.0)

    def _extract_token(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> str:
        """
        Extract the Bearer token from the Authorization header.

        Security:
            Raises HTTP 401 with a ``WWW-Authenticate`` header if
            the Authorization header is missing or malformed.

        Args:
            credentials: The parsed HTTP Bearer credentials (injected
                         by FastAPI from the Authorization header).

        Returns:
            The raw JWT string.

        Raises:
            HTTPException: 401 if credentials are missing.
        """
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return credentials.credentials

    async def get_current_user(
        token: str = Depends(_extract_token),
    ) -> CurrentUser:
        """
        Validate the access token via auth-service and return a
        ``CurrentUser`` context object.

        Security:
            Token validation is delegated to the auth-service via HTTP
            rather than decoding locally.  This ensures BL services
            never need the JWT signing secret and that the blacklist
            check is always authoritative.

        Args:
            token: The raw JWT string extracted from the Authorization
                   header by ``_extract_token``.

        Returns:
            A ``CurrentUser`` instance populated from the auth-service
            verification response.

        Raises:
            HTTPException: 401 if the token is invalid or revoked.
            HTTPException: 503 if the auth-service is unreachable.
        """
        try:
            resp: httpx.Response = await _auth_client.post(
                f"{auth_service_url}/api/v1/auth/verify",
                json={"access_token": token},
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Auth service is unavailable",
            )

        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
            )

        data: dict = resp.json()

        # Security: auth-service returns valid=true/false rather than
        # using HTTP status codes, so we must check the body.
        if not data.get("valid"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=data.get("message", "Invalid token"),
            )

        return CurrentUser(
            user_id=data["user_id"],
            email=data.get("email", ""),
            role=data.get("role", ""),
            owner_id=data.get("owner_id"),
            company_id=data.get("company_id"),
            organization_id=data.get("organization_id"),
            acting_as_owner_id=data.get("acting_as"),
            impersonator_id=data.get("impersonator_id"),
        )

    def require_role(*allowed_roles: str) -> Callable:
        """
        Dependency factory that enforces role-based access control
        using the role hierarchy.

        A user passes if their role's hierarchy level is **≥** the
        *minimum* level among ``allowed_roles``.  Superadmin always
        passes regardless of the requested roles.

        Security:
            The hierarchy approach means ``require_role("employee")``
            permits owner, admin, manager, and employee — but not viewer.
            Superadmin (level 100) always passes every check.

        Args:
            allowed_roles: One or more role strings that define the
                           minimum permission level.

        Returns:
            A FastAPI dependency callable that returns ``CurrentUser``
            or raises ``HTTPException 403``.

        Raises:
            HTTPException: 403 if the user's role level is too low.

        Example::

            @router.delete("/jobs/{id}")
            async def delete_job(
                current_user: CurrentUser = Depends(require_role("owner", "admin")),
            ) -> None:
                ...
        """
        # Pre-compute the minimum required level at definition time
        if not allowed_roles:
            raise ValueError("require_role() requires at least one role argument")
        min_level: int = min(ROLE_HIERARCHY.get(r, 0) for r in allowed_roles)

        async def _checker(
            current_user: CurrentUser = Depends(get_current_user),
        ) -> CurrentUser:
            """Inner dependency that performs the actual role check."""
            user_level: int = ROLE_HIERARCHY.get(current_user.role, 0)
            if user_level < min_level:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{current_user.role}' is not permitted",
                )
            return current_user

        return _checker

    async def require_superadmin(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        """
        Dependency that restricts access to superadmin users **only**.

        Security:
            This is stricter than ``require_role("superadmin")`` because it
            checks the role string directly rather than relying on hierarchy.
            Used exclusively for admin-portal endpoints where no other role
            should ever have access.

        Returns:
            ``CurrentUser`` if the user is a superadmin.

        Raises:
            HTTPException: 403 if the user is not a superadmin.
        """
        # Security: explicit role check — hierarchy not used here
        if not current_user.is_superadmin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin access required",
            )
        return current_user

    # Security: roles that always have all permissions (bypass check)
    _PRIVILEGED_ROLES: frozenset[str] = frozenset({"superadmin", "owner", "admin"})

    def require_permission(*permissions: str) -> Callable:
        """
        Dependency factory that enforces fine-grained permission checks
        for subordinate users (manager, employee, viewer).

        Privileged roles (superadmin, owner, admin) automatically pass
        without a database lookup.  For all other roles the permission
        is checked by calling the user-db-access-service.

        Security:
            Requires ``user_service_url`` to be configured.  If it was
            not provided to ``create_auth_dependencies``, the first call
            to the returned dependency will raise a 500 error.

        Args:
            permissions: One or more permission names.  The user must
                         have **all** of them granted.

        Returns:
            A FastAPI dependency callable that returns ``CurrentUser``
            or raises ``HTTPException 403``.

        Example::

            @router.post("/jobs")
            async def create_job(
                current_user: CurrentUser = Depends(
                    require_permission("jobs.create")
                ),
            ) -> dict:
                ...
        """
        if not permissions:
            raise ValueError("require_permission() requires at least one permission")

        async def _checker(
            current_user: CurrentUser = Depends(get_current_user),
        ) -> CurrentUser:
            """Inner dependency that performs the permission check."""
            # Security: privileged roles bypass permission table
            if current_user.role in _PRIVILEGED_ROLES:
                return current_user

            if user_service_url is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Permission checking is not configured",
                )

            effective_oid = current_user.effective_owner_id
            if effective_oid is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot determine tenant context",
                )

            for perm in permissions:
                try:
                    resp = await _auth_client.get(
                        f"{user_service_url}/api/v1/permissions"
                        f"/{effective_oid}/{current_user.user_id}"
                        f"/check/{perm}",
                    )
                except httpx.RequestError:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Permission service is unavailable",
                    )

                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission '{perm}' denied",
                    )

                data = resp.json()
                if not data.get("granted"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Permission '{perm}' denied",
                    )

            return current_user

        return _checker

    return get_current_user, require_role, require_superadmin, require_permission
