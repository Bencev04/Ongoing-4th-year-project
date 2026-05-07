"""Tests for the Twilio StatusCallback webhook receiver.

Covers signature validation, status mapping, missing fields,
delivered_at timestamp logic, and unknown MessageSid handling.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.webhooks import _STATUS_MAP, _validate_twilio_signature

# =============================================================================
# Twilio Signature Validation
# =============================================================================


class TestTwilioSignatureValidation:
    """Tests for _validate_twilio_signature helper."""

    def test_missing_auth_token_always_rejects(self, monkeypatch):
        """Missing TWILIO_AUTH_TOKEN should always return False."""
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("DEBUG", "true")
        request = MagicMock()
        assert _validate_twilio_signature(request, {}) is False

    def test_missing_auth_token_production_rejects(self, monkeypatch):
        """Without DEBUG, missing TWILIO_AUTH_TOKEN should return False."""
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setenv("DEBUG", "false")
        request = MagicMock()
        assert _validate_twilio_signature(request, {}) is False

    def test_invalid_signature_returns_false(self, monkeypatch):
        """Valid auth token but bad signature should return False."""
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real_token_value")
        monkeypatch.delenv("DEBUG", raising=False)

        request = MagicMock()
        request.headers = {"X-Twilio-Signature": "bad_sig"}
        request.url = "https://example.com/api/v1/notifications/webhooks/twilio"

        with patch("twilio.request_validator.RequestValidator") as MockValidator:
            mock_val = MagicMock()
            mock_val.validate.return_value = False
            MockValidator.return_value = mock_val

            result = _validate_twilio_signature(request, {"MessageSid": "SM123"})
            assert result is False
            mock_val.validate.assert_called_once()

    def test_valid_signature_returns_true(self, monkeypatch):
        """Correct signature should return True."""
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real_token_value")
        monkeypatch.delenv("DEBUG", raising=False)

        request = MagicMock()
        request.headers = {"X-Twilio-Signature": "valid_sig"}
        request.url = "https://example.com/webhooks/twilio"

        with patch("twilio.request_validator.RequestValidator") as MockValidator:
            mock_val = MagicMock()
            mock_val.validate.return_value = True
            MockValidator.return_value = mock_val

            result = _validate_twilio_signature(request, {"MessageSid": "SM123"})
            assert result is True

    def test_exception_during_validation_returns_false(self, monkeypatch):
        """If the Twilio SDK throws, treat it as invalid."""
        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "real_token_value")
        monkeypatch.delenv("DEBUG", raising=False)

        request = MagicMock()
        request.headers = {}
        request.url = "https://example.com/webhooks/twilio"

        with patch(
            "twilio.request_validator.RequestValidator",
            side_effect=RuntimeError("boom"),
        ):
            result = _validate_twilio_signature(request, {})
            assert result is False


# =============================================================================
# Status Mapping
# =============================================================================


class TestStatusMapping:
    """Tests for the Twilio → internal status map."""

    def test_all_twilio_statuses_mapped(self):
        """Every documented Twilio status should have a mapping."""
        expected = {"queued", "sent", "delivered", "read", "failed", "undelivered"}
        assert expected == set(_STATUS_MAP.keys())

    def test_queued_maps_to_pending(self):
        assert _STATUS_MAP["queued"] == "pending"

    def test_sent_maps_to_sent(self):
        assert _STATUS_MAP["sent"] == "sent"

    def test_delivered_maps_to_delivered(self):
        assert _STATUS_MAP["delivered"] == "delivered"

    def test_read_maps_to_read(self):
        assert _STATUS_MAP["read"] == "read"

    def test_failed_maps_to_failed(self):
        assert _STATUS_MAP["failed"] == "failed"

    def test_undelivered_maps_to_failed(self):
        assert _STATUS_MAP["undelivered"] == "failed"


# =============================================================================
# Webhook Endpoint (through TestClient)
# =============================================================================


class TestTwilioWebhookEndpoint:
    """Integration-style tests for the webhook route via TestClient."""

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    @patch("app.api.webhooks.update_delivery_status", new_callable=AsyncMock)
    def test_successful_delivery_update(
        self, mock_update, mock_validate, test_client: TestClient
    ):
        """Valid webhook call updates delivery status."""
        mock_log = MagicMock()
        mock_log.id = 1
        mock_update.return_value = mock_log

        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM123456", "MessageStatus": "delivered"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        mock_update.assert_awaited_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["external_message_id"] == "SM123456"
        assert call_kwargs["status"] == "delivered"
        assert call_kwargs["delivered_at"] is not None

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    @patch("app.api.webhooks.update_delivery_status", new_callable=AsyncMock)
    def test_sent_status_no_delivered_at(
        self, mock_update, mock_validate, test_client: TestClient
    ):
        """'sent' status should NOT set delivered_at."""
        mock_update.return_value = MagicMock()

        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM999", "MessageStatus": "sent"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["status"] == "sent"
        assert call_kwargs["delivered_at"] is None

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    @patch("app.api.webhooks.update_delivery_status", new_callable=AsyncMock)
    def test_read_status_sets_delivered_at(
        self, mock_update, mock_validate, test_client: TestClient
    ):
        """'read' should also set delivered_at."""
        mock_update.return_value = MagicMock()

        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM_READ", "MessageStatus": "read"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["status"] == "read"
        assert call_kwargs["delivered_at"] is not None

    @patch("app.api.webhooks._validate_twilio_signature", return_value=False)
    def test_invalid_signature_returns_403(
        self, mock_validate, test_client: TestClient
    ):
        """Request with invalid signature should be rejected."""
        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM123", "MessageStatus": "sent"},
        )
        assert resp.status_code == 403

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    def test_missing_message_sid_returns_400(
        self, mock_validate, test_client: TestClient
    ):
        """Missing MessageSid should return 400."""
        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageStatus": "sent"},
        )
        assert resp.status_code == 400

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    def test_missing_message_status_returns_400(
        self, mock_validate, test_client: TestClient
    ):
        """Missing MessageStatus should return 400."""
        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM123"},
        )
        assert resp.status_code == 400

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    @patch("app.api.webhooks.update_delivery_status", new_callable=AsyncMock)
    def test_unknown_sid_returns_ok(
        self, mock_update, mock_validate, test_client: TestClient
    ):
        """Unknown MessageSid should still return 200 (idempotent)."""
        mock_update.return_value = None  # no matching log found

        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM_UNKNOWN", "MessageStatus": "delivered"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @patch("app.api.webhooks._validate_twilio_signature", return_value=True)
    @patch("app.api.webhooks.update_delivery_status", new_callable=AsyncMock)
    def test_unmapped_status_passes_through(
        self, mock_update, mock_validate, test_client: TestClient
    ):
        """Unknown Twilio status falls through to raw string."""
        mock_update.return_value = MagicMock()

        resp = test_client.post(
            "/api/v1/notifications/webhooks/twilio",
            data={"MessageSid": "SM_CUSTOM", "MessageStatus": "some_new_status"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_update.call_args.kwargs
        # Falls through _STATUS_MAP.get() to the raw value
        assert call_kwargs["status"] == "some_new_status"
