"""
CRUD operations for tenant-scoped user permissions.

All queries are scoped by ``owner_id`` for multi-tenant isolation.
Owner/admin users bypass permission checks at the BL layer, so
these functions only manage *subordinate* user permission rows.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.permission import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_CATALOG,
    UserPermission,
)


async def get_user_permissions(
    db: AsyncSession,
    *,
    user_id: int,
    owner_id: int,
) -> dict[str, bool]:
    """
    Return all permission assignments for a user as {name: granted}.

    Args:
        db:       Async database session.
        user_id:  The subordinate user whose permissions to fetch.
        owner_id: Tenant isolation key.

    Returns:
        Dict mapping permission names to their granted flag.
    """
    result = await db.execute(
        select(UserPermission.permission, UserPermission.granted).where(
            UserPermission.user_id == user_id,
            UserPermission.owner_id == owner_id,
        )
    )
    return {row.permission: row.granted for row in result.all()}


async def check_user_permission(
    db: AsyncSession,
    *,
    user_id: int,
    owner_id: int,
    permission: str,
) -> bool:
    """
    Check whether a specific permission is granted.

    Args:
        db:         Async database session.
        user_id:    The subordinate user to check.
        owner_id:   Tenant isolation key.
        permission: Permission name to check.

    Returns:
        True if an explicit grant exists, False otherwise.
    """
    result = await db.execute(
        select(UserPermission.granted).where(
            UserPermission.user_id == user_id,
            UserPermission.owner_id == owner_id,
            UserPermission.permission == permission,
        )
    )
    row = result.scalar_one_or_none()
    return bool(row) if row is not None else False


async def set_user_permissions(
    db: AsyncSession,
    *,
    user_id: int,
    owner_id: int,
    permissions: dict[str, bool],
) -> dict[str, bool]:
    """
    Upsert multiple permissions for a user in a single transaction.

    Only permissions listed in the catalog are accepted; unknown
    names are silently ignored.

    Args:
        db:          Async database session.
        user_id:     The subordinate user whose permissions to set.
        owner_id:    Tenant isolation key.
        permissions: Map of permission name → granted flag.

    Returns:
        The full permission map after the operation.
    """
    valid_perms = {k: v for k, v in permissions.items() if k in PERMISSION_CATALOG}

    for perm_name, granted in valid_perms.items():
        existing = await db.execute(
            select(UserPermission).where(
                UserPermission.user_id == user_id,
                UserPermission.owner_id == owner_id,
                UserPermission.permission == perm_name,
            )
        )
        row = existing.scalar_one_or_none()

        if row is not None:
            row.granted = granted
        else:
            db.add(
                UserPermission(
                    owner_id=owner_id,
                    user_id=user_id,
                    permission=perm_name,
                    granted=granted,
                )
            )

    await db.commit()
    return await get_user_permissions(db, user_id=user_id, owner_id=owner_id)


async def seed_default_permissions(
    db: AsyncSession,
    *,
    user_id: int,
    owner_id: int,
    role: str,
) -> dict[str, bool]:
    """
    Seed default permissions for a newly created subordinate user.

    Idempotent — existing rows are not overwritten.

    Args:
        db:       Async database session.
        user_id:  The new subordinate user.
        owner_id: Tenant isolation key.
        role:     The user's role (manager, employee, viewer).

    Returns:
        The full permission map after seeding.
    """
    defaults = DEFAULT_ROLE_PERMISSIONS.get(role, set())
    existing = await get_user_permissions(db, user_id=user_id, owner_id=owner_id)

    for perm_name in PERMISSION_CATALOG:
        if perm_name not in existing:
            db.add(
                UserPermission(
                    owner_id=owner_id,
                    user_id=user_id,
                    permission=perm_name,
                    granted=perm_name in defaults,
                )
            )

    await db.commit()
    return await get_user_permissions(db, user_id=user_id, owner_id=owner_id)


async def delete_user_permissions(
    db: AsyncSession,
    *,
    user_id: int,
    owner_id: int,
) -> int:
    """
    Delete all permission rows for a user (e.g. on user deactivation).

    Args:
        db:       Async database session.
        user_id:  The user whose permissions to delete.
        owner_id: Tenant isolation key.

    Returns:
        Number of rows deleted.
    """
    result = await db.execute(
        delete(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.owner_id == owner_id,
        )
    )
    await db.commit()
    return result.rowcount
