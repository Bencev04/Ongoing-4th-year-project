"""Tier 1 WhatsApp adapter — click-to-chat via wa.me links.

No API keys required. Generates a link that the employee opens
manually to send a pre-filled WhatsApp message.
"""

import urllib.parse

from ..phone import normalize_phone_e164
from ..schemas import SendResult
from .base import MessageAdapter


class WhatsAppLinkAdapter(MessageAdapter):
    """Generates ``wa.me`` click-to-chat links (Tier 1)."""

    def __init__(self, config: dict | None = None) -> None:
        # No config needed for wa.me links
        pass

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

        # Strip the leading + for wa.me
        phone_digits = phone.lstrip("+")
        encoded_body = urllib.parse.quote(body)
        link = f"https://wa.me/{phone_digits}?text={encoded_body}"

        return SendResult(
            success=True,
            action="open_link",
            link=link,
        )

    def get_channel_name(self) -> str:
        return "whatsapp"
