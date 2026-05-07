"""
Admin BL Service — Audit Logging Tests.

Verifies that admin endpoints call ``service_client.create_audit_log``
with the correct action and resource metadata.
"""

from datetime import UTC, datetime

import httpx
import pytest
from httpx import AsyncClient


def _full_org(*, id: int = 10, name: str = "Acme", slug: str = "acme") -> dict:
    """Return a complete organization payload that satisfies OrganizationResponse."""
    now = datetime.now(UTC).isoformat()
    return {
        "id": id,
        "name": name,
        "slug": slug,
        "billing_email": None,
        "billing_plan": "free",
        "max_users": 50,
        "max_customers": 500,
        "is_active": True,
        "suspended_at": None,
        "suspended_reason": None,
        "created_at": now,
        "updated_at": now,
    }


class TestAuditLogOnOrganizationCreate:
    """POST /admin/organizations should write an audit log on success."""

    @pytest.mark.asyncio
    async def test_create_org_writes_audit_log(
        self,
        client: AsyncClient,
        mock_http_client,
    ) -> None:
        """Successful org creation triggers create_audit_log with correct fields."""
        # post is called twice: create-org then audit-log
        mock_http_client.post.return_value = httpx.Response(201, json=_full_org())

        response = await client.post(
            "/api/v1/admin/organizations",
            json={"name": "Acme", "slug": "acme"},
        )

        assert response.status_code == 201
        audit_calls = [
            c for c in mock_http_client.post.call_args_list if "audit-logs" in str(c)
        ]
        assert len(audit_calls) >= 1
        audit_body = audit_calls[0].kwargs.get(
            "json", audit_calls[0][1] if len(audit_calls[0]) > 1 else {}
        )
        assert audit_body.get("action") == "organization.create"
        assert audit_body.get("resource_type") == "organization"


class TestAuditLogOnOrganizationSuspend:
    """POST /admin/organizations/{id}/suspend should audit the suspension."""

    @pytest.mark.asyncio
    async def test_suspend_org_writes_audit_log(
        self,
        client: AsyncClient,
        mock_http_client,
    ) -> None:
        """Suspending an org triggers audit with 'organization.suspend' action."""
        # suspend calls PUT (update_organization) then POST (audit-log)
        mock_http_client.put.return_value = httpx.Response(
            200, json=_full_org(id=3, name="Old Corp")
        )
        mock_http_client.post.return_value = httpx.Response(201, json={"id": 1})

        response = await client.post(
            "/api/v1/admin/organizations/3/suspend",
            json={"reason": "Policy violation"},
        )

        assert response.status_code == 200
        audit_calls = [
            c for c in mock_http_client.post.call_args_list if "audit-logs" in str(c)
        ]
        assert len(audit_calls) >= 1
        audit_body = audit_calls[0].kwargs.get(
            "json", audit_calls[0][1] if len(audit_calls[0]) > 1 else {}
        )
        assert audit_body.get("action") == "organization.suspend"


class TestAuditLogFireAndForget:
    """Audit log failures must not break the admin operation."""

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_break_create(
        self,
        client: AsyncClient,
        mock_http_client,
    ) -> None:
        """If the audit-log POST fails, org creation still returns 201."""
        call_count = 0
        org_data = _full_org(id=11, name="NewCo", slug="newco")

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(201, json=org_data)
            # Second post = audit → service error
            return httpx.Response(500, json={"detail": "audit DB down"})

        mock_http_client.post.side_effect = _side_effect

        response = await client.post(
            "/api/v1/admin/organizations",
            json={"name": "NewCo", "slug": "newco"},
        )

        assert response.status_code == 201
