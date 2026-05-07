"""Tier 2 WhatsApp adapter — sends via Twilio WhatsApp API.

Uses the ``twilio`` Python SDK with Content Templates for
business-initiated messages.
"""

import asyncio
import json
import logging

from pydantic import BaseModel, Field
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from ..phone import normalize_phone_e164
from ..schemas import SendResult
from .base import MessageAdapter

logger = logging.getLogger(__name__)


class TwilioConfig(BaseModel):
    """Validated Twilio WhatsApp configuration."""

    account_sid: str = Field(..., min_length=1)
    auth_token: str = Field(..., min_length=1)
    phone_number: str = Field(..., min_length=1)
    status_callback_url: str | None = None


class WhatsAppTwilioAdapter(MessageAdapter):
    """Sends WhatsApp messages through the Twilio API (Tier 2).

    Accepts a ``TwilioConfig`` or a plain dict (validated at init time).
    """

    def __init__(self, config: dict | TwilioConfig) -> None:
        if not isinstance(config, TwilioConfig):
            config = TwilioConfig(**config)
        self.client = Client(config.account_sid, config.auth_token)
        self.from_number = config.phone_number
        self.status_callback_url = config.status_callback_url

    async def send(
        self,
        to: str,
        subject: str | None,
        body: str,
        template_vars: dict | None = None,
        template_name: str | None = None,
    ) -> SendResult:
        phone = normalize_phone_e164(to)
        if not phone:
            return SendResult(
                success=False,
                action="failed",
                error=f"Invalid phone number: {to}",
            )

        try:
            kwargs: dict = {
                "to": f"whatsapp:{phone}",
                "from_": f"whatsapp:{self.from_number}",
            }

            # Use Content Template if available, otherwise send plain body
            if template_name:
                kwargs["content_sid"] = template_name
                if template_vars:
                    kwargs["content_variables"] = json.dumps(template_vars)
            else:
                kwargs["body"] = body

            if self.status_callback_url:
                kwargs["status_callback"] = self.status_callback_url

            # Twilio SDK is synchronous — run in thread to avoid blocking
            message = await asyncio.to_thread(self.client.messages.create, **kwargs)

            logger.info("Twilio message sent: SID=%s to=%s", message.sid, phone)
            return SendResult(
                success=True,
                action="sent",
                message_id=message.sid,
            )
        except TwilioRestException as exc:
            logger.error("Twilio send failed: %s (code=%s)", exc.msg, exc.code)
            return SendResult(
                success=False,
                action="failed",
                error=f"Twilio error {exc.code}: {exc.msg}",
            )

    def get_channel_name(self) -> str:
        return "whatsapp"
