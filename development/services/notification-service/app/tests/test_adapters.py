"""Tests for notification adapters — WhatsApp link, WhatsApp Twilio, Email SMTP."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.base import MessageAdapter
from app.adapters.email_smtp import EmailSmtpAdapter
from app.adapters.factory import ADAPTER_REGISTRY, get_adapter
from app.adapters.whatsapp_link import WhatsAppLinkAdapter
from app.adapters.whatsapp_twilio import WhatsAppTwilioAdapter

# =============================================================================
# Adapter Factory
# =============================================================================


class TestAdapterFactory:
    """Tests for get_adapter() factory and registry."""

    def test_registry_has_all_adapters(self):
        assert "whatsapp_link" in ADAPTER_REGISTRY
        assert "whatsapp_twilio" in ADAPTER_REGISTRY
        assert "email_smtp" in ADAPTER_REGISTRY

    def test_get_adapter_whatsapp_link(self):
        adapter = get_adapter("whatsapp_link")
        assert isinstance(adapter, WhatsAppLinkAdapter)
        assert isinstance(adapter, MessageAdapter)

    def test_get_adapter_whatsapp_twilio(self):
        config = {
            "account_sid": "ACtest",
            "auth_token": "test_token",
            "phone_number": "+14155238886",
        }
        adapter = get_adapter("whatsapp_twilio", config)
        assert isinstance(adapter, WhatsAppTwilioAdapter)
        assert isinstance(adapter, MessageAdapter)

    def test_get_adapter_email_smtp(self):
        config = {"smtp_host": "localhost", "smtp_port": 1025}
        adapter = get_adapter("email_smtp", config)
        assert isinstance(adapter, EmailSmtpAdapter)
        assert isinstance(adapter, MessageAdapter)

    def test_get_adapter_unknown_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown adapter 'nonexistent'"):
            get_adapter("nonexistent")

    def test_get_adapter_twilio_missing_config_raises_value_error(self):
        """Twilio adapter requires account_sid, auth_token, phone_number."""
        with pytest.raises(ValueError, match="Invalid config"):
            get_adapter("whatsapp_twilio", {})

    def test_get_adapter_email_missing_host_raises_value_error(self):
        """Email adapter requires smtp_host."""
        with pytest.raises(ValueError, match="Invalid config"):
            get_adapter("email_smtp", {})

    def test_all_adapters_implement_interface(self):
        """Every registered adapter must be a MessageAdapter subclass."""
        for key, cls in ADAPTER_REGISTRY.items():
            assert issubclass(cls, MessageAdapter), (
                f"{key} does not subclass MessageAdapter"
            )


# =============================================================================
# WhatsApp Link Adapter (Tier 1)
# =============================================================================


class TestWhatsAppLinkAdapter:
    """Tests for click-to-chat wa.me link generation."""

    @pytest.fixture
    def adapter(self):
        return WhatsAppLinkAdapter()

    @pytest.mark.asyncio
    async def test_send_generates_link(self, adapter):
        result = await adapter.send(
            to="+353831234567",
            subject=None,
            body="Hello from CRM",
        )
        assert result.success is True
        assert result.action == "open_link"
        assert result.link is not None
        assert "wa.me/353831234567" in result.link
        assert "Hello" in result.link

    @pytest.mark.asyncio
    async def test_send_normalises_irish_number(self, adapter):
        result = await adapter.send(to="083 123 4567", subject=None, body="Test")
        assert result.success is True
        assert "wa.me/353831234567" in result.link

    @pytest.mark.asyncio
    async def test_send_invalid_phone_returns_failure(self, adapter):
        result = await adapter.send(to="invalid", subject=None, body="Test")
        assert result.success is False
        assert result.action == "failed"
        assert "Invalid phone" in result.error

    @pytest.mark.asyncio
    async def test_send_empty_phone_returns_failure(self, adapter):
        result = await adapter.send(to="", subject=None, body="Test")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_none_phone_returns_failure(self, adapter):
        result = await adapter.send(to=None, subject=None, body="Test")
        assert result.success is False

    def test_channel_name(self, adapter):
        assert adapter.get_channel_name() == "whatsapp"


# =============================================================================
# WhatsApp Twilio Adapter (Tier 2)
# =============================================================================


class TestWhatsAppTwilioAdapter:
    """Tests for Twilio WhatsApp API adapter."""

    @pytest.fixture
    def twilio_config(self):
        return {
            "account_sid": "ACtest123",
            "auth_token": "test_auth_token",
            "phone_number": "+14155238886",
            "status_callback_url": "https://example.com/api/v1/notifications/webhooks/twilio",
        }

    @pytest.fixture
    def adapter(self, twilio_config):
        with patch("app.adapters.whatsapp_twilio.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            a = WhatsAppTwilioAdapter(twilio_config)
            a.client = mock_client
            return a

    @pytest.mark.asyncio
    async def test_send_with_content_template(self, adapter):
        mock_message = MagicMock()
        mock_message.sid = "SM1234567890"
        adapter.client.messages.create.return_value = mock_message

        with patch(
            "app.adapters.whatsapp_twilio.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            mock_thread.return_value = mock_message

            result = await adapter.send(
                to="+353831234567",
                subject=None,
                body="Fallback text",
                template_name="HXtest123",
                template_vars={"1": "John", "2": "Plumbing"},
            )

        assert result.success is True
        assert result.action == "sent"
        assert result.message_id == "SM1234567890"

        # Verify asyncio.to_thread was used (not direct sync call)
        mock_thread.assert_awaited_once()
        call_args = mock_thread.call_args
        call_kwargs = call_args.kwargs
        assert call_kwargs["to"] == "whatsapp:+353831234567"
        assert call_kwargs["from_"] == "whatsapp:+14155238886"
        assert call_kwargs["content_sid"] == "HXtest123"
        # Verify content_variables is valid JSON with correct values
        parsed = json.loads(call_kwargs["content_variables"])
        assert parsed == {"1": "John", "2": "Plumbing"}
        assert (
            call_kwargs["status_callback"]
            == "https://example.com/api/v1/notifications/webhooks/twilio"
        )

    @pytest.mark.asyncio
    async def test_send_plain_body_without_template(self, adapter):
        mock_message = MagicMock()
        mock_message.sid = "SM9876543210"
        adapter.client.messages.create.return_value = mock_message

        with patch(
            "app.adapters.whatsapp_twilio.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            mock_thread.return_value = mock_message

            result = await adapter.send(
                to="+353831234567",
                subject=None,
                body="Plain message text",
            )

        assert result.success is True
        call_kwargs = mock_thread.call_args.kwargs
        assert call_kwargs["body"] == "Plain message text"
        assert "content_sid" not in call_kwargs

    @pytest.mark.asyncio
    async def test_send_invalid_phone(self, adapter):
        result = await adapter.send(to="bad", subject=None, body="Test")
        assert result.success is False
        assert "Invalid phone" in result.error

    @pytest.mark.asyncio
    async def test_send_twilio_error(self, adapter):
        from twilio.base.exceptions import TwilioRestException

        exc = TwilioRestException(status=400, uri="/test", msg="Invalid To number")

        with patch(
            "app.adapters.whatsapp_twilio.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            mock_thread.side_effect = exc

            result = await adapter.send(to="+353831234567", subject=None, body="Test")
        assert result.success is False
        assert result.action == "failed"
        assert "Twilio error" in result.error

    @pytest.mark.asyncio
    async def test_send_without_status_callback(self, twilio_config):
        """When status_callback_url is omitted, no callback kwarg is passed."""
        config_no_cb = {
            k: v for k, v in twilio_config.items() if k != "status_callback_url"
        }
        with patch("app.adapters.whatsapp_twilio.Client") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value = mock_client
            adapter = WhatsAppTwilioAdapter(config_no_cb)
            adapter.client = mock_client

        mock_message = MagicMock()
        mock_message.sid = "SM_NO_CB"

        with patch(
            "app.adapters.whatsapp_twilio.asyncio.to_thread", new_callable=AsyncMock
        ) as mock_thread:
            mock_thread.return_value = mock_message
            result = await adapter.send(to="+353831234567", subject=None, body="Hi")

        assert result.success is True
        assert "status_callback" not in mock_thread.call_args.kwargs

    def test_channel_name(self, twilio_config):
        with patch("app.adapters.whatsapp_twilio.Client"):
            adapter = WhatsAppTwilioAdapter(twilio_config)
        assert adapter.get_channel_name() == "whatsapp"


# =============================================================================
# Email SMTP Adapter
# =============================================================================


class TestEmailSmtpAdapter:
    """Tests for async SMTP email adapter."""

    @pytest.fixture
    def smtp_config(self):
        return {
            "smtp_host": "localhost",
            "smtp_port": 1025,
            "smtp_username": "",
            "smtp_password": "",
            "from_email": "test@example.com",
            "from_name": "Test CRM",
            "use_tls": False,
        }

    @pytest.fixture
    def adapter(self, smtp_config):
        return EmailSmtpAdapter(smtp_config)

    @pytest.mark.asyncio
    async def test_send_success(self, adapter):
        with patch("app.adapters.email_smtp.aiosmtplib.SMTP") as MockSMTP:
            mock_smtp = AsyncMock()
            MockSMTP.return_value = mock_smtp
            mock_smtp.connect = AsyncMock()
            mock_smtp.send_message = AsyncMock(return_value=({}, "OK"))
            mock_smtp.quit = AsyncMock()

            result = await adapter.send(
                to="user@example.com",
                subject="Test Subject",
                body="<p>Hello World</p>",
            )

            assert result.success is True
            assert result.action == "sent"
            mock_smtp.connect.assert_awaited_once()
            mock_smtp.send_message.assert_awaited_once()
            mock_smtp.quit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_with_tls(self, smtp_config):
        smtp_config["use_tls"] = True
        smtp_config["smtp_username"] = "user@example.com"
        smtp_config["smtp_password"] = "secret"
        adapter = EmailSmtpAdapter(smtp_config)

        with patch("app.adapters.email_smtp.aiosmtplib.SMTP") as MockSMTP:
            mock_smtp = AsyncMock()
            MockSMTP.return_value = mock_smtp
            mock_smtp.connect = AsyncMock()
            mock_smtp.login = AsyncMock()
            mock_smtp.send_message = AsyncMock(return_value=({}, "OK"))
            mock_smtp.quit = AsyncMock()

            result = await adapter.send(
                to="user@example.com", subject="TLS Test", body="Body"
            )

            assert result.success is True
            # TLS is configured via constructor args (start_tls=True for port 587)
            MockSMTP.assert_called_once()
            call_kwargs = MockSMTP.call_args[1] if MockSMTP.call_args[1] else {}
            assert (
                call_kwargs.get("start_tls") is True
                or call_kwargs.get("use_tls") is True
            )
            mock_smtp.login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_bare_at_sign_rejected(self, adapter):
        """A bare '@' should be rejected by tightened email validation."""
        result = await adapter.send(to="@", subject="Test", body="Body")
        assert result.success is False
        assert "Invalid email" in result.error

    @pytest.mark.asyncio
    async def test_send_at_only_prefix_rejected(self, adapter):
        result = await adapter.send(to="@bar", subject="Test", body="Body")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_at_only_suffix_rejected(self, adapter):
        result = await adapter.send(to="foo@", subject="Test", body="Body")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_invalid_email(self, adapter):
        result = await adapter.send(to="not-an-email", subject="Test", body="Body")
        assert result.success is False
        assert "Invalid email" in result.error

    @pytest.mark.asyncio
    async def test_send_empty_email(self, adapter):
        result = await adapter.send(to="", subject="Test", body="Body")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_send_smtp_connection_error(self, adapter):
        with patch("app.adapters.email_smtp.aiosmtplib.SMTP") as MockSMTP:
            mock_smtp = AsyncMock()
            MockSMTP.return_value = mock_smtp
            mock_smtp.connect = AsyncMock(side_effect=OSError("Connection refused"))

            result = await adapter.send(
                to="user@example.com", subject="Test", body="Body"
            )

            assert result.success is False
            assert result.action == "failed"
            assert "Connection refused" in result.error

    def test_channel_name(self, adapter):
        assert adapter.get_channel_name() == "email"
