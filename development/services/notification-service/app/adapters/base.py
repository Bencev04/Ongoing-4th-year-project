"""Abstract base class for all notification adapters."""

from abc import ABC, abstractmethod

from ..schemas import SendResult


class MessageAdapter(ABC):
    """Interface that every notification channel adapter must implement.

    Adapters are instantiated with a ``config`` dict containing
    provider-specific credentials and settings.
    """

    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str | None,
        body: str,
        template_vars: dict | None = None,
        template_name: str | None = None,
    ) -> SendResult:
        """Send a notification and return a ``SendResult``.

        Args:
            to: Recipient (phone number or email address).
            subject: Email subject line (ignored by WhatsApp adapters).
            body: Message body or fallback text.
            template_vars: Template variable mapping (for Content Templates).
            template_name: Content Template SID / template identifier.

        Returns:
            A ``SendResult`` indicating success/failure and provider metadata.
        """
        ...

    @abstractmethod
    def get_channel_name(self) -> str:
        """Return the channel identifier (``"whatsapp"`` or ``"email"``)."""
        ...
