"""Twilio StatusCallback webhook receiver.

Receives delivery status updates from Twilio and updates the
notification_log accordingly. Validates the request signature
using Twilio's ``RequestValidator``.

This endpoint is **public** (no JWT auth) — authentication is
performed by verifying the ``X-Twilio-Signature`` header.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_async_db

from ..crud.notification import update_delivery_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

# Twilio status → our status mapping
_STATUS_MAP: dict[str, str] = {
    "queued": "pending",
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
    "undelivered": "failed",
}


def _validate_twilio_signature(request: Request, form_data: dict) -> bool:
    """Validate the X-Twilio-Signature header.

    Returns True if signature is valid, False otherwise.
    Requires TWILIO_AUTH_TOKEN env var to be set.
    """
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        logger.error(
            "TWILIO_AUTH_TOKEN not set — rejecting webhook. "
            "Configure the auth token to receive Twilio callbacks."
        )
        return False

    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(auth_token)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        return validator.validate(url, form_data, signature)
    except Exception:
        logger.exception("Twilio signature validation failed")
        return False


@router.post("/api/v1/notifications/webhooks/twilio")
async def twilio_status_callback(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Receive delivery status updates from Twilio.

    Twilio POSTs form-encoded data with fields:
    - ``MessageSid``: The Twilio message SID (``SM...``)
    - ``MessageStatus``: One of queued, sent, delivered, read, failed, undelivered
    - ``ErrorCode``: Present if status is failed/undelivered
    """
    form = await request.form()
    form_data = dict(form)

    if not _validate_twilio_signature(request, form_data):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    message_sid = form_data.get("MessageSid", "")
    message_status = form_data.get("MessageStatus", "")

    if not message_sid or not message_status:
        raise HTTPException(
            status_code=400, detail="Missing MessageSid or MessageStatus"
        )

    our_status = _STATUS_MAP.get(message_status, message_status)

    from datetime import UTC, datetime

    delivered_at = datetime.now(UTC) if our_status in ("delivered", "read") else None

    log = await update_delivery_status(
        db,
        external_message_id=message_sid,
        status=our_status,
        delivered_at=delivered_at,
    )

    if log:
        logger.info(
            "Webhook: Updated %s → status=%s (Twilio status=%s)",
            message_sid,
            our_status,
            message_status,
        )
    else:
        # Unknown message SID — ignore (idempotent)
        logger.debug("Webhook: Unknown MessageSid %s — ignored", message_sid)

    return {"status": "ok"}
