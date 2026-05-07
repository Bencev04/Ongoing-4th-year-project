"""Email adapter — sends via async SMTP.

Uses ``aiosmtplib`` for non-blocking SMTP delivery with TLS support.
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from pydantic import BaseModel, Field

from ..schemas import SendResult
from .base import MessageAdapter

logger = logging.getLogger(__name__)


class SmtpConfig(BaseModel):
    """Validated SMTP configuration."""

    smtp_host: str = Field(..., min_length=1)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    from_email: str = Field(default="noreply@example.com")
    from_name: str = Field(default="CRM Calendar")
    use_tls: bool = False


class EmailSmtpAdapter(MessageAdapter):
    """Sends email via SMTP (async).

    Accepts a ``SmtpConfig`` or a plain dict (validated at init time).
    """

    def __init__(self, config: dict | SmtpConfig) -> None:
        if not isinstance(config, SmtpConfig):
            config = SmtpConfig(**config)
        self.host = config.smtp_host
        self.port = config.smtp_port
        self.username = config.smtp_username
        self.password = config.smtp_password
        self.from_email = config.from_email
        self.from_name = config.from_name
        self.use_tls = config.use_tls

    async def send(
        self,
        to: str,
        subject: str | None,
        body: str,
        template_vars: dict | None = None,
        template_name: str | None = None,
    ) -> SendResult:
        if (
            not to
            or "@" not in to
            or len(to) < 5
            or to.startswith("@")
            or to.endswith("@")
        ):
            return SendResult(
                success=False,
                action="failed",
                error=f"Invalid email address: {to}",
            )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject or "Notification"
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to

        # Plain-text fallback
        msg.attach(MIMEText(body, "plain"))
        # HTML version (body is expected to contain HTML when templates are used)
        msg.attach(MIMEText(body, "html"))

        try:
            # Port 465 uses implicit TLS (encrypted from the start).
            # Port 587 (and others) use STARTTLS to upgrade a plain connection.
            # aiosmtplib handles both modes natively via use_tls / start_tls.
            implicit_tls = self.use_tls and self.port == 465
            smtp = aiosmtplib.SMTP(
                hostname=self.host,
                port=self.port,
                use_tls=implicit_tls,
                start_tls=self.use_tls if not implicit_tls else False,
            )
            await smtp.connect()
            if self.username:
                await smtp.login(self.username, self.password)

            await smtp.send_message(msg)
            await smtp.quit()

            # Extract message ID from SMTP response
            message_id = msg.get("Message-ID", "")

            logger.info("Email sent to %s (message_id=%s)", to, message_id)
            return SendResult(
                success=True,
                action="sent",
                message_id=message_id,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            logger.error("SMTP send failed to %s: %s", to, exc)
            return SendResult(
                success=False,
                action="failed",
                error=str(exc),
            )

    def get_channel_name(self) -> str:
        return "email"
