"""Tests for Pydantic schemas (enums, validation boundaries, serialization)."""

from datetime import UTC

import pytest
from pydantic import ValidationError

from app.schemas import (
    MarkSentRequest,
    NotificationChannel,
    NotificationLogResponse,
    NotificationStatus,
    NotificationType,
    SendResult,
    SendTestRequest,
)

# =============================================================================
# Enum coverage
# =============================================================================


class TestNotificationChannel:
    def test_whatsapp(self):
        assert NotificationChannel.WHATSAPP == "whatsapp"

    def test_email(self):
        assert NotificationChannel.EMAIL == "email"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            NotificationChannel("sms")


class TestNotificationType:
    def test_all_values(self):
        expected = {
            "reminder_24h",
            "reminder_1h",
            "on_the_way",
            "completed",
            "welcome",
            "test",
        }
        assert {t.value for t in NotificationType} == expected

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            NotificationType("custom")


class TestNotificationStatus:
    def test_all_values(self):
        expected = {"pending", "sent", "delivered", "read", "failed"}
        assert {s.value for s in NotificationStatus} == expected


# =============================================================================
# SendTestRequest validation
# =============================================================================


class TestSendTestRequest:
    def test_valid_whatsapp(self):
        r = SendTestRequest(channel="whatsapp", recipient="+353831234567")
        assert r.channel == NotificationChannel.WHATSAPP

    def test_valid_email(self):
        r = SendTestRequest(channel="email", recipient="user@example.com")
        assert r.channel == NotificationChannel.EMAIL

    def test_empty_recipient_rejected(self):
        with pytest.raises(ValidationError):
            SendTestRequest(channel="whatsapp", recipient="")

    def test_recipient_max_length(self):
        """255 chars should be accepted."""
        r = SendTestRequest(channel="whatsapp", recipient="a" * 255)
        assert len(r.recipient) == 255

    def test_recipient_over_max_rejected(self):
        with pytest.raises(ValidationError):
            SendTestRequest(channel="whatsapp", recipient="a" * 256)

    def test_invalid_channel(self):
        with pytest.raises(ValidationError):
            SendTestRequest(channel="sms", recipient="123")

    def test_missing_channel(self):
        with pytest.raises(ValidationError):
            SendTestRequest(recipient="123")

    def test_missing_recipient(self):
        with pytest.raises(ValidationError):
            SendTestRequest(channel="whatsapp")


# =============================================================================
# MarkSentRequest
# =============================================================================


class TestMarkSentRequest:
    def test_defaults_to_whatsapp(self):
        r = MarkSentRequest()
        assert r.channel == NotificationChannel.WHATSAPP

    def test_explicit_email(self):
        r = MarkSentRequest(channel="email")
        assert r.channel == NotificationChannel.EMAIL

    def test_invalid_channel_rejected(self):
        with pytest.raises(ValidationError):
            MarkSentRequest(channel="sms")


# =============================================================================
# SendResult
# =============================================================================


class TestSendResult:
    def test_successful_send(self):
        r = SendResult(success=True, action="sent", message_id="SM123")
        assert r.success is True
        assert r.link is None
        assert r.error is None

    def test_link_action(self):
        r = SendResult(success=True, action="open_link", link="https://wa.me/123")
        assert r.action == "open_link"
        assert r.link == "https://wa.me/123"

    def test_failed_action(self):
        r = SendResult(success=False, action="failed", error="Timeout")
        assert r.error == "Timeout"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            SendResult(success=True)  # missing action


# =============================================================================
# NotificationLogResponse (from_attributes)
# =============================================================================


class TestNotificationLogResponse:
    def test_from_mock_object(self, sample_notification_log):
        """Should serialize from an ORM-like object via from_attributes."""
        resp = NotificationLogResponse.model_validate(
            sample_notification_log, from_attributes=True
        )
        assert resp.id == 1
        assert resp.owner_id == 10
        assert resp.channel == "whatsapp"
        assert resp.status == "sent"

    def test_optional_fields_none(self):
        from datetime import datetime

        resp = NotificationLogResponse(
            id=1,
            owner_id=10,
            channel="whatsapp",
            notification_type="test",
            status="pending",
            recipient="+353831234567",
            message_body="Hello",
            created_at=datetime.now(UTC),
        )
        assert resp.job_id is None
        assert resp.customer_id is None
        assert resp.external_message_id is None
        assert resp.error_message is None
        assert resp.delivered_at is None
        assert resp.retry_count == 0
