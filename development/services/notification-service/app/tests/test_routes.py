"""Tests for notification service API routes.

Uses FastAPI TestClient with mocked auth and database dependencies.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestPendingEndpoint:
    """GET /api/v1/notifications/pending."""

    def test_returns_empty_list(self, test_client: TestClient):
        resp = test_client.get("/api/v1/notifications/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


class TestMarkSentEndpoint:
    """POST /api/v1/notifications/{job_id}/mark-sent."""

    @patch("app.api.routes.create_notification_log", new_callable=AsyncMock)
    def test_mark_sent_creates_log(self, mock_create, test_client: TestClient):
        log_obj = MagicMock()
        log_obj.id = 1
        log_obj.owner_id = 10
        log_obj.job_id = 42
        log_obj.customer_id = None
        log_obj.channel = "whatsapp"
        log_obj.notification_type = "manual"
        log_obj.status = "sent"
        log_obj.recipient = "manual"
        log_obj.message_body = "Manually marked as sent via Tier 1 click-to-chat"
        log_obj.external_message_id = None
        log_obj.error_message = None
        log_obj.retry_count = 0
        log_obj.sent_at = None
        log_obj.delivered_at = None
        log_obj.created_at = datetime.now(UTC)
        mock_create.return_value = log_obj

        resp = test_client.post(
            "/api/v1/notifications/42/mark-sent",
            json={"channel": "whatsapp"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == 42
        assert data["status"] == "sent"
        assert data["notification_type"] == "manual"

        # Verify CRUD was called correctly
        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["owner_id"] == 10
        assert call_kwargs["job_id"] == 42
        assert call_kwargs["channel"] == "whatsapp"


class TestNotificationLogEndpoint:
    """GET /api/v1/notifications/log."""

    @patch("app.api.routes.get_notification_log", new_callable=AsyncMock)
    def test_returns_paginated_log(self, mock_get_log, test_client: TestClient):
        log1 = MagicMock()
        log1.id = 1
        log1.owner_id = 10
        log1.job_id = 42
        log1.customer_id = 7
        log1.channel = "whatsapp"
        log1.notification_type = "reminder_24h"
        log1.status = "sent"
        log1.recipient = "+353831234567"
        log1.message_body = "Reminder about your appointment"
        log1.external_message_id = "SM123"
        log1.error_message = None
        log1.retry_count = 0
        log1.sent_at = datetime.now(UTC)
        log1.delivered_at = None
        log1.created_at = datetime.now(UTC)
        mock_get_log.return_value = ([log1], 1)

        resp = test_client.get("/api/v1/notifications/log?page=1&per_page=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert len(data["items"]) == 1
        assert data["items"][0]["channel"] == "whatsapp"

    @patch("app.api.routes.get_notification_log", new_callable=AsyncMock)
    def test_empty_log(self, mock_get_log, test_client: TestClient):
        mock_get_log.return_value = ([], 0)
        resp = test_client.get("/api/v1/notifications/log")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestSendTestEndpoint:
    """POST /api/v1/notifications/send-test."""

    @patch("app.api.routes.create_notification_log", new_callable=AsyncMock)
    @patch("app.api.routes._resolve_whatsapp_adapter", new_callable=AsyncMock)
    def test_send_whatsapp_test(
        self, mock_resolve_wa, mock_create, test_client: TestClient
    ):
        from app.schemas import SendResult

        mock_adapter = AsyncMock()
        mock_adapter.send.return_value = SendResult(
            success=True,
            action="open_link",
            link="https://wa.me/353831234567?text=This+is+a+test",
        )
        mock_adapter.get_channel_name.return_value = "whatsapp"
        mock_resolve_wa.return_value = mock_adapter

        mock_log = MagicMock()
        mock_create.return_value = mock_log

        resp = test_client.post(
            "/api/v1/notifications/send-test",
            json={"channel": "whatsapp", "recipient": "+353831234567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "open_link"
        assert "wa.me" in data["link"]

    @patch("app.api.routes.create_notification_log", new_callable=AsyncMock)
    @patch("app.api.routes.get_adapter")
    @patch("app.api.routes._resolve_smtp_config", new_callable=AsyncMock)
    def test_send_email_test(
        self, mock_resolve_smtp, mock_get_adapter, mock_create, test_client: TestClient
    ):
        from app.schemas import SendResult

        mock_resolve_smtp.return_value = {
            "smtp_host": "localhost",
            "smtp_port": 1025,
            "smtp_username": "",
            "smtp_password": "",
            "from_email": "noreply@example.com",
            "from_name": "CRM Calendar",
            "use_tls": False,
        }

        mock_adapter = AsyncMock()
        mock_adapter.send.return_value = SendResult(
            success=True,
            action="sent",
            message_id="<test-msg-id@example.com>",
        )
        mock_get_adapter.return_value = mock_adapter

        mock_log = MagicMock()
        mock_create.return_value = mock_log

        resp = test_client.post(
            "/api/v1/notifications/send-test",
            json={"channel": "email", "recipient": "user@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "sent"
        assert data["message_id"] is not None

    def test_send_test_missing_recipient(self, test_client: TestClient):
        resp = test_client.post(
            "/api/v1/notifications/send-test",
            json={"channel": "whatsapp"},
        )
        assert resp.status_code == 422  # validation error

    def test_send_test_invalid_channel(self, test_client: TestClient):
        resp = test_client.post(
            "/api/v1/notifications/send-test",
            json={"channel": "sms", "recipient": "+353831234567"},
        )
        assert resp.status_code == 422


class TestRootAndHealth:
    """Service root and health check."""

    def test_root(self, test_client: TestClient):
        resp = test_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "notification-service"
        assert data["status"] == "running"

    def test_health(self, test_client: TestClient):
        resp = test_client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestSendWelcomeConsent:
    """POST /api/v1/notifications/send-welcome — data_processing_consent checks."""

    @patch("app.api.routes.service_client.get_customer", new_callable=AsyncMock)
    def test_rejects_when_no_consent(self, mock_get_customer, test_client: TestClient):
        """Should return 403 when the customer hasn't given data processing consent."""
        mock_get_customer.return_value = {
            "id": 10,
            "first_name": "John",
            "email": "john@example.com",
            "phone": "+353831234567",
            "data_processing_consent": False,
            "notify_email": True,
            "notify_whatsapp": True,
        }

        resp = test_client.post(
            "/api/v1/notifications/send-welcome",
            json={
                "customer_id": 10,
                "job_id": 42,
                "send_email": True,
                "send_whatsapp": False,
            },
        )
        assert resp.status_code == 403
        assert "consent" in resp.json()["detail"].lower()

    @patch("app.api.routes.service_client.get_customer", new_callable=AsyncMock)
    def test_rejects_when_consent_missing(
        self, mock_get_customer, test_client: TestClient
    ):
        """Should return 403 when data_processing_consent key is absent."""
        mock_get_customer.return_value = {
            "id": 10,
            "first_name": "John",
            "email": "john@example.com",
        }

        resp = test_client.post(
            "/api/v1/notifications/send-welcome",
            json={
                "customer_id": 10,
                "job_id": 42,
                "send_email": True,
                "send_whatsapp": False,
            },
        )
        assert resp.status_code == 403

    @patch("app.api.routes.create_notification_log", new_callable=AsyncMock)
    @patch("app.api.routes._resolve_smtp_config", new_callable=AsyncMock)
    @patch("app.api.routes.get_adapter")
    @patch("app.api.routes.service_client.get_job", new_callable=AsyncMock)
    @patch("app.api.routes.service_client.get_customer", new_callable=AsyncMock)
    def test_allows_when_consent_given(
        self,
        mock_get_customer,
        mock_get_job,
        mock_get_adapter,
        mock_resolve_smtp,
        mock_create_log,
        test_client: TestClient,
    ):
        """Should proceed to send when data_processing_consent is True."""
        mock_get_customer.return_value = {
            "id": 10,
            "first_name": "John",
            "email": "john@example.com",
            "data_processing_consent": True,
            "notify_email": True,
        }
        mock_get_job.return_value = {
            "id": 42,
            "title": "Window Cleaning",
            "start_time": "2025-07-01T10:00:00Z",
        }
        mock_resolve_smtp.return_value = {
            "smtp_host": "localhost",
            "smtp_port": 1025,
            "smtp_username": "",
            "smtp_password": "",
            "from_email": "noreply@example.com",
            "from_name": "CRM",
            "use_tls": False,
        }

        from app.schemas import SendResult

        mock_adapter = AsyncMock()
        mock_adapter.send.return_value = SendResult(
            success=True, action="sent", message_id="<id>"
        )
        mock_get_adapter.return_value = mock_adapter

        mock_log = MagicMock()
        mock_create_log.return_value = mock_log

        resp = test_client.post(
            "/api/v1/notifications/send-welcome",
            json={
                "customer_id": 10,
                "job_id": 42,
                "send_email": True,
                "send_whatsapp": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["success"] is True
