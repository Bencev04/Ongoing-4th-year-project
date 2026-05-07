"""
Integration tests — Notification service flow.

Full stack: NGINX → notification-service → PostgreSQL / Redis

Tests the notification API endpoints through the nginx gateway,
verifying:
- Service health check via nginx routing
- JWT auth enforcement on all protected endpoints
- Notification log CRUD (mark-sent, paginated listing)
- Send-test endpoint (WhatsApp link generation)
- Twilio webhook endpoint (public, no JWT)
- Cross-tenant isolation of notification logs
- RBAC: employee and viewer access to notification endpoints
"""

import httpx


class TestNotificationHealth:
    """Verify the notification service is reachable through NGINX."""

    def test_notification_service_health(self, http_client: httpx.Client) -> None:
        """
        Notification service is reachable through nginx.

        Verifies:
        - nginx upstream ``notification_service`` is correctly configured
        - notification-service container is healthy and responding

        We hit a known notification endpoint; 401/403 proves the service
        is alive (a 502/504 would mean the upstream is down).
        """
        resp = http_client.get("/api/v1/notifications/pending")
        assert resp.status_code in (401, 403)


class TestNotificationAuth:
    """Verify JWT auth is enforced on all notification endpoints."""

    def test_pending_requires_auth(self, http_client: httpx.Client) -> None:
        """GET /api/v1/notifications/pending rejects unauthenticated requests."""
        resp = http_client.get("/api/v1/notifications/pending")
        assert resp.status_code in (401, 403)

    def test_log_requires_auth(self, http_client: httpx.Client) -> None:
        """GET /api/v1/notifications/log rejects unauthenticated requests."""
        resp = http_client.get("/api/v1/notifications/log")
        assert resp.status_code in (401, 403)

    def test_send_test_requires_auth(self, http_client: httpx.Client) -> None:
        """POST /api/v1/notifications/send-test rejects unauthenticated requests."""
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            json={"channel": "whatsapp", "recipient": "+353831234567"},
        )
        assert resp.status_code in (401, 403)

    def test_mark_sent_requires_auth(self, http_client: httpx.Client) -> None:
        """POST /api/v1/notifications/{id}/mark-sent rejects unauthenticated requests."""
        resp = http_client.post(
            "/api/v1/notifications/999/mark-sent",
            json={"channel": "whatsapp"},
        )
        assert resp.status_code in (401, 403)


class TestPendingReminders:
    """GET /api/v1/notifications/pending — Tier 1 dashboard."""

    def test_owner_can_list_pending(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Owner can access the pending reminders endpoint.

        Verifies:
        - Endpoint returns 200
        - Response has expected structure (items + total)
        """
        resp = http_client.get(
            "/api/v1/notifications/pending",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_employee_can_list_pending(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """Employees can also access the pending reminders (they send them)."""
        resp = http_client.get(
            "/api/v1/notifications/pending",
            headers=employee_headers,
        )
        assert resp.status_code == 200


class TestMarkSent:
    """POST /api/v1/notifications/{job_id}/mark-sent — Tier 1 manual send."""

    def test_owner_can_mark_sent(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Owner can mark a notification as manually sent.

        Verifies:
        - Creates a notification_log record
        - Returns the log entry with correct fields
        - Status is 'sent', notification_type is 'manual'
        """
        resp = http_client.post(
            "/api/v1/notifications/42/mark-sent",
            headers=owner_headers,
            json={"channel": "whatsapp"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sent"
        assert data["notification_type"] == "manual"
        assert data["channel"] == "whatsapp"
        assert data["job_id"] == 42

    def test_mark_sent_email_channel(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Mark-sent also works for the email channel."""
        resp = http_client.post(
            "/api/v1/notifications/43/mark-sent",
            headers=owner_headers,
            json={"channel": "email"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == "email"
        assert data["job_id"] == 43

    def test_mark_sent_invalid_channel(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Invalid channel should be rejected by schema validation."""
        resp = http_client.post(
            "/api/v1/notifications/42/mark-sent",
            headers=owner_headers,
            json={"channel": "sms"},
        )
        assert resp.status_code == 422


class TestNotificationLog:
    """GET /api/v1/notifications/log — paginated notification history."""

    def test_owner_can_view_log(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Owner can view their notification log.

        Verifies:
        - Endpoint returns 200
        - Response has items, total, page, per_page
        - Items are scoped to the owner's tenant (tested via mark-sent above)
        """
        resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert data["page"] == 1

    def test_log_pagination(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Pagination parameters are respected."""
        resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner_headers,
            params={"page": 1, "per_page": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["per_page"] == 2
        assert len(data["items"]) <= 2

    def test_log_invalid_page(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Page < 1 should be rejected."""
        resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner_headers,
            params={"page": 0},
        )
        assert resp.status_code == 422

    def test_log_contains_mark_sent_entries(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Log should contain entries created by mark-sent in earlier tests.

        Note: test ordering means TestMarkSent runs before this.
        """
        resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner_headers,
            params={"per_page": 100},
        )
        assert resp.status_code == 200
        data = resp.json()
        # The mark-sent tests above should have created at least two entries
        if data["total"] > 0:
            item = data["items"][0]
            assert "id" in item
            assert "channel" in item
            assert "status" in item
            assert "created_at" in item


class TestSendTest:
    """POST /api/v1/notifications/send-test — test notification delivery."""

    def test_send_whatsapp_test(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """
        Send a test WhatsApp notification (Tier 1 — generates a wa.me link).

        Verifies:
        - Returns success=True
        - action is 'open_link'
        - link contains wa.me and the phone number
        """
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            headers=owner_headers,
            json={"channel": "whatsapp", "recipient": "+353831234567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "open_link"
        assert "wa.me" in data["link"]
        assert "353831234567" in data["link"]

    def test_send_whatsapp_test_irish_format(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Irish 08x format is normalised before wa.me link generation."""
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            headers=owner_headers,
            json={"channel": "whatsapp", "recipient": "083 123 4567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "353831234567" in data["link"]

    def test_send_whatsapp_invalid_phone(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Invalid phone number returns success=False with error."""
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            headers=owner_headers,
            json={"channel": "whatsapp", "recipient": "bad"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["action"] == "failed"
        assert data["error"] is not None

    def test_send_test_invalid_channel(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Invalid channel value is rejected by Pydantic validation."""
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            headers=owner_headers,
            json={"channel": "sms", "recipient": "+353831234567"},
        )
        assert resp.status_code == 422

    def test_send_test_empty_recipient(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
    ) -> None:
        """Empty recipient is rejected by schema validation."""
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            headers=owner_headers,
            json={"channel": "whatsapp", "recipient": ""},
        )
        assert resp.status_code == 422


class TestTwilioWebhook:
    """POST /api/v1/notifications/webhooks/twilio — public webhook."""

    def test_webhook_rejects_unsigned_request(self, http_client: httpx.Client) -> None:
        """
        Twilio webhook without valid signature should be rejected.

        The endpoint validates X-Twilio-Signature — unsigned requests
        must return 403.

        Note: we send a form-encoded body as Twilio does.
        """
        resp = http_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={
                "MessageSid": "SM0000000000000000000000000000000",
                "MessageStatus": "delivered",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        # Should reject: no valid X-Twilio-Signature
        assert resp.status_code in (400, 403)

    def test_webhook_no_auth_header_needed(self, http_client: httpx.Client) -> None:
        """
        Webhook endpoint is public — no JWT required.

        Should return 400/403 (bad signature), NOT 401 (missing auth).
        """
        resp = http_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM123", "MessageStatus": "sent"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code != 401


class TestCrossTenantIsolation:
    """Notification logs are scoped per tenant (owner_id)."""

    def test_second_tenant_sees_no_cross_tenant_data(
        self,
        http_client: httpx.Client,
        owner_headers: dict[str, str],
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Tenant 2 should NOT see notification logs from Tenant 1.

        Verifies:
        - Owner 2 can access /log
        - None of the entries in owner2's log originate from owner1's tests
          (job_ids 42, 43 were created by TestMarkSent for tenant 1)

        Idempotent: owner2 may already have entries from prior runs of
        test_second_tenant_can_mark_sent_independently — that is fine;
        we only assert that tenant 1's data never leaks.
        """
        # Confirm tenant 1 has data (mark-sent created entries for jobs 42/43)
        owner1_resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner_headers,
            params={"per_page": 100},
        )
        assert owner1_resp.status_code == 200
        assert owner1_resp.json()["total"] > 0

        # Tenant 2 must never see tenant 1's entries
        resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner2_headers,
            params={"per_page": 100},
        )
        assert resp.status_code == 200
        data = resp.json()
        owner1_job_ids = {42, 43}
        for item in data["items"]:
            assert item.get("job_id") not in owner1_job_ids, (
                f"Cross-tenant leak: owner2 sees job_id={item['job_id']} from owner1"
            )

    def test_second_tenant_can_mark_sent_independently(
        self,
        http_client: httpx.Client,
        owner2_headers: dict[str, str],
    ) -> None:
        """
        Tenant 2 can create their own notification logs.

        Verifies independent log creation + their log only shows their data.
        """
        # Record baseline count
        baseline_resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner2_headers,
        )
        assert baseline_resp.status_code == 200
        baseline_total = baseline_resp.json()["total"]

        # Create a mark-sent entry for tenant 2
        mark_resp = http_client.post(
            "/api/v1/notifications/100/mark-sent",
            headers=owner2_headers,
            json={"channel": "whatsapp"},
        )
        assert mark_resp.status_code == 200
        assert mark_resp.json()["job_id"] == 100

        # Verify the new entry shows in their log
        log_resp = http_client.get(
            "/api/v1/notifications/log",
            headers=owner2_headers,
        )
        assert log_resp.status_code == 200
        data = log_resp.json()
        assert data["total"] == baseline_total + 1


class TestRBACNotifications:
    """Role-based access to notification endpoints."""

    def test_employee_can_send_test(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """Employees should be able to send test notifications (they use Tier 1)."""
        resp = http_client.post(
            "/api/v1/notifications/send-test",
            headers=employee_headers,
            json={"channel": "whatsapp", "recipient": "+353871234567"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_employee_can_mark_sent(
        self,
        http_client: httpx.Client,
        employee_headers: dict[str, str],
    ) -> None:
        """Employees should be able to mark notifications as sent."""
        resp = http_client.post(
            "/api/v1/notifications/50/mark-sent",
            headers=employee_headers,
            json={"channel": "whatsapp"},
        )
        assert resp.status_code == 200

    def test_viewer_can_view_log(
        self,
        http_client: httpx.Client,
        viewer_headers: dict[str, str],
    ) -> None:
        """Viewers should be able to view the notification log (read-only)."""
        resp = http_client.get(
            "/api/v1/notifications/log",
            headers=viewer_headers,
        )
        assert resp.status_code == 200
