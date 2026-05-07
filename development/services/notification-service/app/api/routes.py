"""Notification service API routes.

All endpoints (except the webhook) require JWT auth and are scoped
by ``owner_id`` for tenant isolation.

Config resolution follows a 3-tier hierarchy:
  1. Organization-level overrides (``notification_settings`` on org)
  2. Platform settings (generic key/value settings managed by superadmin)
  3. Environment variables (hard-coded fallback via ``common.config``)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from common.auth import CurrentUser
from common.database import get_async_db

from .. import service_client
from ..adapters.factory import get_adapter
from ..crud.notification import (
    create_notification_log,
    get_notification_log,
)
from ..dependencies import get_current_user
from ..schemas import (
    MarkSentRequest,
    NotificationLogListResponse,
    NotificationLogResponse,
    SendResult,
    SendTestRequest,
    SendWelcomeRequest,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 3-tier configuration resolution helpers
# ---------------------------------------------------------------------------


def _ps_val(settings: dict, key: str, prop: str = "value", default: Any = "") -> Any:
    """Extract a property from a platform-settings dict entry."""
    val = settings.get(key, {})
    return val.get(prop, default) if isinstance(val, dict) else default


def _ps_bool(settings: dict, key: str, prop: str = "enabled") -> bool:
    """Extract a boolean flag from a platform-settings dict entry."""
    val = settings.get(key, {})
    return isinstance(val, dict) and bool(val.get(prop, False))


async def _resolve_smtp_config(
    token: str,
    org_id: int | None,
) -> dict[str, Any] | None:
    """Resolve SMTP config using the 3-tier hierarchy.

    Returns a config dict ready for ``get_adapter("email_smtp", config)``,
    or ``None`` if SMTP is not enabled at any tier.
    """
    # --- Tier 1: Organization overrides ---
    if org_id:
        org = await service_client.get_organization(token, org_id)
        if org:
            ns = org.get("notification_settings") or {}
            if ns.get("use_custom_smtp") and ns.get("smtp", {}).get("host"):
                smtp = ns["smtp"]
                logger.info("SMTP config resolved from org %s", org_id)
                return {
                    "smtp_host": smtp["host"],
                    "smtp_port": int(smtp.get("port", 587)),
                    "smtp_username": smtp.get("username", ""),
                    "smtp_password": smtp.get("password", ""),
                    "from_email": smtp.get("from_email", "noreply@example.com"),
                    "from_name": smtp.get("from_name", "CRM Calendar"),
                    "use_tls": smtp.get("use_tls", False),
                }

    # --- Tier 2: Platform settings ---
    platform = await service_client.get_platform_settings_bulk(token, "smtp.")
    if _ps_bool(platform, "smtp.enabled") and _ps_val(platform, "smtp.host"):
        logger.info("SMTP config resolved from platform settings")
        return {
            "smtp_host": _ps_val(platform, "smtp.host"),
            "smtp_port": int(_ps_val(platform, "smtp.port", default=587)),
            "smtp_username": _ps_val(platform, "smtp.username"),
            "smtp_password": _ps_val(platform, "smtp.password"),
            "from_email": _ps_val(platform, "smtp.from_email") or "noreply@example.com",
            "from_name": _ps_val(platform, "smtp.from_name") or "CRM Calendar",
            "use_tls": _ps_bool(platform, "smtp.use_tls"),
        }

    # --- Tier 3: Environment / config fallback ---
    from common.config import settings as app_settings

    host = getattr(app_settings, "smtp_host", "")
    if host:
        logger.info("SMTP config resolved from environment variables")
        return {
            "smtp_host": host,
            "smtp_port": getattr(app_settings, "smtp_port", 1025),
            "smtp_username": getattr(app_settings, "smtp_username", ""),
            "smtp_password": getattr(app_settings, "smtp_password", ""),
            "from_email": getattr(
                app_settings, "smtp_from_email", "noreply@example.com"
            ),
            "from_name": getattr(app_settings, "smtp_from_name", "CRM Calendar"),
            "use_tls": getattr(app_settings, "smtp_use_tls", False),
        }

    return None


async def _resolve_whatsapp_adapter(
    token: str,
    org_id: int | None,
):
    """Resolve the WhatsApp adapter using the 3-tier hierarchy.

    Returns an adapter instance (either Twilio or link).
    """
    # --- Tier 1: Organization overrides ---
    if org_id:
        org = await service_client.get_organization(token, org_id)
        if org:
            ns = org.get("notification_settings") or {}
            wa = ns.get("whatsapp", {})
            if ns.get("use_custom_whatsapp") and wa.get("account_sid"):
                logger.info("WhatsApp config resolved from org %s", org_id)
                return get_adapter(
                    "whatsapp_twilio",
                    {
                        "account_sid": wa["account_sid"],
                        "auth_token": wa.get("auth_token", ""),
                        "phone_number": wa.get("phone_number", ""),
                    },
                )

    # --- Tier 2: Platform settings ---
    wa_settings = await service_client.get_platform_settings_bulk(token, "whatsapp.")
    if _ps_bool(wa_settings, "whatsapp.tier2_enabled"):
        sid = _ps_val(wa_settings, "whatsapp.twilio_account_sid")
        tok = _ps_val(wa_settings, "whatsapp.twilio_auth_token")
        phone = _ps_val(wa_settings, "whatsapp.twilio_phone_number")
        if sid and tok and phone:
            logger.info("WhatsApp config resolved from platform settings")
            return get_adapter(
                "whatsapp_twilio",
                {
                    "account_sid": sid,
                    "auth_token": tok,
                    "phone_number": phone,
                },
            )
        else:
            missing = [
                k
                for k, v in [
                    ("account_sid", sid),
                    ("auth_token", tok),
                    ("phone_number", phone),
                ]
                if not v
            ]
            logger.warning(
                "Twilio Tier 2 enabled but missing: %s — falling back to wa.me links",
                ", ".join(missing),
            )

    # --- Tier 3: Fallback to wa.me links ---
    logger.info("WhatsApp using wa.me link fallback (Tier 1)")
    return get_adapter("whatsapp_link")


router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/pending", response_model=dict)
async def list_pending_reminders(
    user: CurrentUser = Depends(get_current_user),
):
    """List jobs needing manual WhatsApp send (Tier 1 dashboard).

    In a full implementation this would query upcoming jobs and cross-check
    the notification log. Returns a placeholder structure for now.
    """
    return {"items": [], "total": 0}


@router.post("/{job_id}/mark-sent", response_model=NotificationLogResponse)
async def mark_notification_sent(
    job_id: int,
    body: MarkSentRequest,
    db: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Mark a Tier 1 notification as manually sent by the employee."""
    log = await create_notification_log(
        db,
        owner_id=user.owner_id,
        job_id=job_id,
        channel=body.channel.value,
        notification_type="manual",
        status="sent",
        recipient="manual",
        message_body="Manually marked as sent via Tier 1 click-to-chat",
    )
    return log


@router.get("/log", response_model=NotificationLogListResponse)
async def list_notification_log(
    db: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(get_current_user),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """Paginated notification history for the tenant."""
    items, total = await get_notification_log(
        db,
        owner_id=user.owner_id,
        page=page,
        per_page=per_page,
    )
    return NotificationLogListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/send-test", response_model=SendResult)
async def send_test_notification(
    body: SendTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Send a test notification (email or WhatsApp) to verify configuration.

    Test notifications are always platform-level (no org override) since
    they are triggered from the superadmin settings page.
    """
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""

    if body.channel.value == "whatsapp":
        adapter = await _resolve_whatsapp_adapter(token, org_id=None)
        result = await adapter.send(
            to=body.recipient,
            subject=None,
            body="This is a test message from CRM Calendar notifications.",
        )
    elif body.channel.value == "email":
        config = await _resolve_smtp_config(token, org_id=None)
        if not config:
            raise HTTPException(
                status_code=400,
                detail="SMTP not configured. Set up SMTP in Platform Settings first.",
            )
        adapter = get_adapter("email_smtp", config)
        result = await adapter.send(
            to=body.recipient,
            subject="Test Notification — CRM Calendar",
            body="<p>This is a test email from CRM Calendar notifications.</p>",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown channel: {body.channel}")

    await create_notification_log(
        db,
        owner_id=user.owner_id or 0,
        channel=body.channel.value,
        notification_type="test",
        status="sent" if result.success else "failed",
        recipient=body.recipient,
        message_body="Test notification",
        external_message_id=result.message_id,
    )

    return result


def _build_welcome_email(customer: dict, job: dict) -> str:
    """Build a welcome/confirmation HTML email body."""
    name = customer.get("first_name", "Customer")
    title = job.get("title", "your job")
    start = job.get("start_time", "")
    address = job.get("address", "")

    date_str = ""
    if start:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            date_str = dt.strftime("%A %d %B %Y at %H:%M")
        except (ValueError, AttributeError):
            date_str = str(start)

    lines = [
        "<h2 style='color:#0d9488'>Job Confirmation</h2>",
        f"<p>Hi {name},</p>",
        "<p>Thank you for choosing us! Here are the details of your upcoming job:</p>",
        "<table style='border-collapse:collapse;margin:16px 0'>",
        f"<tr><td style='padding:6px 12px;font-weight:600'>Job</td><td style='padding:6px 12px'>{title}</td></tr>",
    ]
    if date_str:
        lines.append(
            f"<tr><td style='padding:6px 12px;font-weight:600'>Scheduled</td><td style='padding:6px 12px'>{date_str}</td></tr>"
        )
    if address:
        lines.append(
            f"<tr><td style='padding:6px 12px;font-weight:600'>Location</td><td style='padding:6px 12px'>{address}</td></tr>"
        )
    lines += [
        "</table>",
        "<p>If you have any questions, please don't hesitate to get in touch.</p>",
        "<p>Kind regards,<br><strong>The Team</strong></p>",
    ]
    return "\n".join(lines)


def _build_welcome_whatsapp(customer: dict, job: dict) -> str:
    """Build a plain-text WhatsApp welcome message."""
    name = customer.get("first_name", "Customer")
    title = job.get("title", "your job")
    start = job.get("start_time", "")
    address = job.get("address", "")

    date_str = ""
    if start:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            date_str = dt.strftime("%A %d %B %Y at %H:%M")
        except (ValueError, AttributeError):
            date_str = str(start)

    parts = [
        f"Hi {name}! 👋",
        f"Your job *{title}* has been booked.",
    ]
    if date_str:
        parts.append(f"📅 {date_str}")
    if address:
        parts.append(f"📍 {address}")
    parts.append("We'll be in touch with any updates. Thanks for choosing us!")
    return "\n".join(parts)


@router.post("/send-welcome", response_model=list[SendResult])
async def send_welcome_message(
    body: SendWelcomeRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: CurrentUser = Depends(get_current_user),
):
    """Send a welcome/confirmation message to a customer after job creation.

    Sends via the channels requested (email and/or WhatsApp) using
    the customer's contact details and job information.

    Config is resolved per the 3-tier hierarchy using the caller's
    organisation context (``user.organization_id``).
    """
    auth_header = request.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip() if auth_header else ""

    customer = await service_client.get_customer(token, body.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # GDPR: refuse to send if the customer hasn't given data-processing consent
    if not customer.get("data_processing_consent"):
        raise HTTPException(
            status_code=403,
            detail="Customer has not given data processing consent. Cannot send notifications.",
        )

    job = await service_client.get_job(token, body.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    org_id = getattr(user, "organization_id", None)
    results: list[SendResult] = []

    # --- Email channel ---
    if body.send_email and customer.get("email"):
        config = await _resolve_smtp_config(token, org_id)
        if not config:
            logger.warning("SMTP not configured at any tier — skipping email")
        else:
            adapter = get_adapter("email_smtp", config)
            html_body = _build_welcome_email(customer, job)
            result = await adapter.send(
                to=customer["email"],
                subject=f"Job Confirmation — {job.get('title', 'Your Job')}",
                body=html_body,
            )
            await create_notification_log(
                db,
                owner_id=user.owner_id,
                job_id=body.job_id,
                customer_id=body.customer_id,
                channel="email",
                notification_type="welcome",
                status="sent" if result.success else "failed",
                recipient=customer["email"],
                message_body="Welcome message — job confirmation email",
                external_message_id=result.message_id,
            )
            results.append(result)

    # --- WhatsApp channel ---
    if body.send_whatsapp and customer.get("phone"):
        adapter = await _resolve_whatsapp_adapter(token, org_id)
        wa_body = _build_welcome_whatsapp(customer, job)
        result = await adapter.send(
            to=customer["phone"],
            subject=None,
            body=wa_body,
        )
        await create_notification_log(
            db,
            owner_id=user.owner_id,
            job_id=body.job_id,
            customer_id=body.customer_id,
            channel="whatsapp",
            notification_type="welcome",
            status="sent" if result.success else "failed",
            recipient=customer["phone"],
            message_body="Welcome message — job confirmation WhatsApp",
            external_message_id=result.message_id,
        )
        results.append(result)

    return results
