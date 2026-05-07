"""
Pydantic schemas for the permission subsystem.

Defines request/response models for permission assignment CRUD
in the user-db-access-service.  These schemas are consumed by
the user-bl-service when managing subordinate user permissions.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PermissionResponse(BaseModel):
    """Single permission assignment returned by the API."""

    id: int
    owner_id: int
    user_id: int
    permission: str
    granted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserPermissionsResponse(BaseModel):
    """All permissions for a single user within a tenant."""

    user_id: int
    owner_id: int
    permissions: dict[str, bool] = Field(
        default_factory=dict,
        description="Map of permission name → granted flag",
    )


class PermissionUpdate(BaseModel):
    """
    Bulk update payload for a user's permissions.

    The ``permissions`` dict maps permission names to their desired
    granted/denied state.  Only permissions present in the dict are
    upserted; absent permissions remain unchanged.
    """

    permissions: dict[str, bool] = Field(
        ...,
        description="Map of permission name → granted flag to upsert",
    )


class PermissionCheck(BaseModel):
    """Result of a single permission check."""

    user_id: int
    permission: str
    granted: bool


class PermissionCatalogResponse(BaseModel):
    """Full permission catalog with per-role defaults."""

    permissions: list[str]
    defaults: dict[str, list[str]] = Field(
        description="Map of role → list of default permissions",
    )
