"""
Unit tests for permission CRUD operations and API endpoints.

Covers the UserPermission model, CRUD functions, and REST routes
used for tenant-scoped permission management in user-db-access-service.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.permissions import (
    check_user_permission,
    delete_user_permissions,
    get_user_permissions,
    seed_default_permissions,
    set_user_permissions,
)
from app.crud.user import create_user
from app.models.permission import (
    DEFAULT_ROLE_PERMISSIONS,
    PERMISSION_CATALOG,
)
from app.schemas import UserCreate

# ==============================================================================
# Helpers
# ==============================================================================


async def _create_owner(db: AsyncSession) -> int:
    """Create an owner user and return its id."""
    owner = await create_user(
        db,
        UserCreate(
            email="owner@test.com",
            password="password123",
            first_name="Owner",
            last_name="User",
            role="owner",
        ),
    )
    return owner.id


async def _create_employee(db: AsyncSession, owner_id: int) -> int:
    """Create an employee user under the given owner and return its id."""
    emp = await create_user(
        db,
        UserCreate(
            email="emp@test.com",
            password="password123",
            first_name="Employee",
            last_name="User",
            role="employee",
            owner_id=owner_id,
        ),
    )
    return emp.id


# ==============================================================================
# CRUD: get_user_permissions
# ==============================================================================


class TestGetUserPermissions:
    """Tests for the get_user_permissions CRUD function."""

    async def test_returns_empty_dict_for_new_user(
        self, db_session: AsyncSession
    ) -> None:
        """A user with no seeded permissions returns an empty map."""
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await get_user_permissions(db_session, user_id=uid, owner_id=oid)
        assert result == {}

    async def test_returns_permissions_after_seeding(
        self, db_session: AsyncSession
    ) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        result = await get_user_permissions(db_session, user_id=uid, owner_id=oid)
        assert len(result) == len(PERMISSION_CATALOG)
        # Employee defaults should be granted
        for perm in DEFAULT_ROLE_PERMISSIONS["employee"]:
            assert result[perm] is True


# ==============================================================================
# CRUD: check_user_permission
# ==============================================================================


class TestCheckUserPermission:
    """Tests for the check_user_permission CRUD function."""

    async def test_returns_false_for_unseeded_user(
        self, db_session: AsyncSession
    ) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        assert (
            await check_user_permission(
                db_session, user_id=uid, owner_id=oid, permission="jobs.create"
            )
            is False
        )

    async def test_returns_true_for_granted_permission(
        self, db_session: AsyncSession
    ) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        # jobs.create is in the employee default set
        assert (
            await check_user_permission(
                db_session, user_id=uid, owner_id=oid, permission="jobs.create"
            )
            is True
        )

    async def test_returns_false_for_denied_permission(
        self, db_session: AsyncSession
    ) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        # jobs.delete is NOT in the employee default set
        assert (
            await check_user_permission(
                db_session, user_id=uid, owner_id=oid, permission="jobs.delete"
            )
            is False
        )


# ==============================================================================
# CRUD: set_user_permissions
# ==============================================================================


class TestSetUserPermissions:
    """Tests for the set_user_permissions CRUD function."""

    async def test_creates_new_permission_rows(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await set_user_permissions(
            db_session,
            user_id=uid,
            owner_id=oid,
            permissions={"jobs.create": True, "jobs.delete": False},
        )
        assert result["jobs.create"] is True
        assert result["jobs.delete"] is False

    async def test_updates_existing_permission(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        await set_user_permissions(
            db_session,
            user_id=uid,
            owner_id=oid,
            permissions={"jobs.create": True},
        )
        # Flip it
        result = await set_user_permissions(
            db_session,
            user_id=uid,
            owner_id=oid,
            permissions={"jobs.create": False},
        )
        assert result["jobs.create"] is False

    async def test_ignores_invalid_permission_names(
        self, db_session: AsyncSession
    ) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await set_user_permissions(
            db_session,
            user_id=uid,
            owner_id=oid,
            permissions={"not.a.real.perm": True, "jobs.create": True},
        )
        assert "not.a.real.perm" not in result
        assert result["jobs.create"] is True


# ==============================================================================
# CRUD: seed_default_permissions
# ==============================================================================


class TestSeedDefaultPermissions:
    """Tests for the seed_default_permissions CRUD function."""

    async def test_seeds_employee_defaults(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        assert len(result) == len(PERMISSION_CATALOG)
        for perm in DEFAULT_ROLE_PERMISSIONS["employee"]:
            assert result[perm] is True
        # Non-employee perms should be denied
        for perm in PERMISSION_CATALOG:
            if perm not in DEFAULT_ROLE_PERMISSIONS["employee"]:
                assert result[perm] is False

    async def test_seeds_manager_defaults(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="manager"
        )
        for perm in DEFAULT_ROLE_PERMISSIONS["manager"]:
            assert result[perm] is True

    async def test_seeds_viewer_defaults(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="viewer"
        )
        assert result["company.view"] is True
        denied = [p for p in PERMISSION_CATALOG if p != "company.view"]
        for perm in denied:
            assert result[perm] is False

    async def test_idempotent_does_not_overwrite(
        self, db_session: AsyncSession
    ) -> None:
        """Seeding twice should not overwrite a manual change."""
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        # Manually revoke a permission
        await set_user_permissions(
            db_session, user_id=uid, owner_id=oid, permissions={"jobs.create": False}
        )
        # Re-seed — should NOT overwrite the manual change
        result = await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        assert result["jobs.create"] is False

    async def test_unknown_role_gets_no_grants(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        result = await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="unknown"
        )
        assert all(v is False for v in result.values())


# ==============================================================================
# CRUD: delete_user_permissions
# ==============================================================================


class TestDeleteUserPermissions:
    """Tests for the delete_user_permissions CRUD function."""

    async def test_deletes_all_permission_rows(self, db_session: AsyncSession) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        await seed_default_permissions(
            db_session, user_id=uid, owner_id=oid, role="employee"
        )
        count = await delete_user_permissions(db_session, user_id=uid, owner_id=oid)
        assert count == len(PERMISSION_CATALOG)
        # Verify all gone
        result = await get_user_permissions(db_session, user_id=uid, owner_id=oid)
        assert result == {}

    async def test_delete_returns_zero_when_none_exist(
        self, db_session: AsyncSession
    ) -> None:
        oid = await _create_owner(db_session)
        uid = await _create_employee(db_session, oid)
        count = await delete_user_permissions(db_session, user_id=uid, owner_id=oid)
        assert count == 0


# ==============================================================================
# API Route Tests
# ==============================================================================


class TestPermissionCatalogRoute:
    """Tests for GET /api/v1/permissions/catalog."""

    async def test_returns_catalog_and_defaults(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/permissions/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert "permissions" in data
        assert set(data["permissions"]) == set(PERMISSION_CATALOG)
        assert "defaults" in data
        for role in ("manager", "employee", "viewer"):
            assert role in data["defaults"]


class TestGetPermissionsRoute:
    """Tests for GET /api/v1/permissions/{owner_id}/{user_id}."""

    async def test_returns_empty_for_new_user(self, client: AsyncClient) -> None:
        # Create owner + employee first
        owner_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "owner@route.com",
                "password": "password123",
                "first_name": "Owner",
                "last_name": "R",
                "role": "owner",
            },
        )
        oid = owner_resp.json()["id"]

        emp_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "emp@route.com",
                "password": "password123",
                "first_name": "Emp",
                "last_name": "R",
                "role": "employee",
                "owner_id": oid,
            },
        )
        uid = emp_resp.json()["id"]

        resp = await client.get(f"/api/v1/permissions/{oid}/{uid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == uid
        assert data["owner_id"] == oid
        assert data["permissions"] == {}


class TestUpdatePermissionsRoute:
    """Tests for PUT /api/v1/permissions/{owner_id}/{user_id}."""

    async def test_upserts_permissions(self, client: AsyncClient) -> None:
        owner_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "owner@upsert.com",
                "password": "password123",
                "first_name": "O",
                "last_name": "U",
                "role": "owner",
            },
        )
        oid = owner_resp.json()["id"]

        emp_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "emp@upsert.com",
                "password": "password123",
                "first_name": "E",
                "last_name": "U",
                "role": "employee",
                "owner_id": oid,
            },
        )
        uid = emp_resp.json()["id"]

        resp = await client.put(
            f"/api/v1/permissions/{oid}/{uid}",
            json={"permissions": {"jobs.create": True, "jobs.delete": False}},
        )
        assert resp.status_code == 200
        perms = resp.json()["permissions"]
        assert perms["jobs.create"] is True
        assert perms["jobs.delete"] is False


class TestCheckPermissionRoute:
    """Tests for GET /api/v1/permissions/{owner_id}/{user_id}/check/{permission}."""

    async def test_granted_permission_returns_true(self, client: AsyncClient) -> None:
        owner_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "owner@check.com",
                "password": "password123",
                "first_name": "O",
                "last_name": "C",
                "role": "owner",
            },
        )
        oid = owner_resp.json()["id"]

        emp_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "emp@check.com",
                "password": "password123",
                "first_name": "E",
                "last_name": "C",
                "role": "employee",
                "owner_id": oid,
            },
        )
        uid = emp_resp.json()["id"]

        # Grant the permission
        await client.put(
            f"/api/v1/permissions/{oid}/{uid}",
            json={"permissions": {"jobs.create": True}},
        )

        resp = await client.get(f"/api/v1/permissions/{oid}/{uid}/check/jobs.create")
        assert resp.status_code == 200
        assert resp.json()["granted"] is True

    async def test_denied_permission_returns_false(self, client: AsyncClient) -> None:
        owner_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "owner@check2.com",
                "password": "password123",
                "first_name": "O",
                "last_name": "C2",
                "role": "owner",
            },
        )
        oid = owner_resp.json()["id"]

        emp_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "emp@check2.com",
                "password": "password123",
                "first_name": "E",
                "last_name": "C2",
                "role": "employee",
                "owner_id": oid,
            },
        )
        uid = emp_resp.json()["id"]

        resp = await client.get(f"/api/v1/permissions/{oid}/{uid}/check/jobs.create")
        assert resp.status_code == 200
        assert resp.json()["granted"] is False


class TestSeedPermissionsRoute:
    """Tests for POST /api/v1/permissions/{owner_id}/{user_id}/seed."""

    async def test_seeds_defaults_for_role(self, client: AsyncClient) -> None:
        owner_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "owner@seed.com",
                "password": "password123",
                "first_name": "O",
                "last_name": "S",
                "role": "owner",
            },
        )
        oid = owner_resp.json()["id"]

        emp_resp = await client.post(
            "/api/v1/users",
            json={
                "email": "emp@seed.com",
                "password": "password123",
                "first_name": "E",
                "last_name": "S",
                "role": "employee",
                "owner_id": oid,
            },
        )
        uid = emp_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/permissions/{oid}/{uid}/seed?role=employee",
        )
        assert resp.status_code == 201
        perms = resp.json()["permissions"]
        assert len(perms) == len(PERMISSION_CATALOG)
        for perm in DEFAULT_ROLE_PERMISSIONS["employee"]:
            assert perms[perm] is True
