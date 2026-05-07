"""Background scheduler for automated notifications.

Runs as an ``asyncio`` background task inside the notification-service.
Uses a Redis distributed lock (``SET NX EX``) so that only **one**
replica processes reminders at a time — safe for Kubernetes.

Flow:
1. Acquire Redis lock (120 s TTL)
2. Find jobs due for 24-hour / 1-hour reminders
3. For each job: dedup check → consent check → send via adapter → log result
4. Process retryable failed notifications
5. Process scheduled GDPR anonymizations (72-hour grace period)
6. Cleanup expired auth tokens, notification logs, and audit logs
7. Release lock, sleep, repeat
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
import redis.asyncio as aioredis

from common.config import settings as app_settings
from common.database import AsyncSessionLocal
from common.redis import get_redis

from ..adapters.factory import get_adapter
from ..crud.notification import (
    cleanup_old_notification_logs,
    create_notification_log,
    get_retryable_notifications,
    has_been_notified,
    mark_failed,
    mark_sent,
)

logger = logging.getLogger(__name__)

SCHEDULER_LOCK_KEY = "notification:scheduler:lock"
SCHEDULER_LOCK_TTL = 120  # seconds — must exceed one full loop cycle
POLL_INTERVAL = 60  # seconds between scheduler runs
MAX_RETRIES = 3
BACKOFF_BASE = 5  # seconds: 5^1=5, 5^2=25, 5^3=125

# GDPR: retention cleanup runs once per day (tracked via Redis key)
RETENTION_CLEANUP_KEY = "notification:retention:last_run"
RETENTION_CLEANUP_INTERVAL = 86400  # 24 hours in seconds

# Token cleanup runs once per day (tracked via Redis key)
TOKEN_CLEANUP_KEY = "notification:token_cleanup:last_run"
TOKEN_CLEANUP_INTERVAL = 86400  # 24 hours in seconds

# GDPR anonymization processor runs once per hour (tracked via Redis key)
ANONYMIZATION_KEY = "notification:anonymization:last_run"
ANONYMIZATION_INTERVAL = 3600  # 1 hour in seconds

# Channel → (adapter_key, needs_config) mapping for retry resolution
_CHANNEL_ADAPTER_MAP: dict[str, str] = {
    "email": "email_smtp",
    "whatsapp": "whatsapp_link",  # fallback — Twilio retries need stored config
}


async def scheduler_loop() -> None:
    """Main scheduler loop — runs forever as a background task.

    Acquires a Redis distributed lock before processing to prevent
    duplicate sends when multiple notification-service replicas exist.
    """
    # Wait a few seconds on startup to let other services become ready
    await asyncio.sleep(5)

    while True:
        try:
            try:
                redis = await get_redis()
                acquired = await redis.set(
                    SCHEDULER_LOCK_KEY, "1", nx=True, ex=SCHEDULER_LOCK_TTL
                )
                if acquired:
                    try:
                        await _process_reminders(redis)
                        await _process_retries(redis)
                        await _maybe_process_anonymizations(redis)
                        await _maybe_cleanup_tokens(redis)
                        await _maybe_cleanup_retention(redis)
                    except Exception:
                        logger.exception("Scheduler loop error")
                    finally:
                        await redis.delete(SCHEDULER_LOCK_KEY)
                else:
                    logger.debug("Scheduler lock held by another instance — skipping")
            except (aioredis.RedisError, ConnectionError):
                logger.exception("Redis connection error in scheduler")

            await asyncio.sleep(POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled — shutting down")
            return


# ---------------------------------------------------------------------------
# Internal HTTP helpers
# ---------------------------------------------------------------------------


def _get_job_db_url() -> str:
    """Base URL for the job-db-access-service (internal, no auth)."""
    return getattr(
        app_settings, "job_db_service_url", "http://job-db-access-service:8002"
    )


def _get_customer_db_url() -> str:
    """Base URL for the customer-db-access-service (internal, no auth)."""
    return getattr(
        app_settings,
        "customer_db_service_url",
        "http://customer-db-access-service:8003",
    )


async def _process_reminders(redis: aioredis.Redis) -> None:
    """Find and send due reminders (24h and 1h).

    Queries the job-db-access-service for jobs with ``start_time`` in
    the next 24 hours or 1 hour, fetches the customer, checks consent
    and notification preferences, deduplicates, and sends via the
    appropriate adapter.
    """
    logger.debug("Processing reminders...")

    now = datetime.now(UTC)
    # Define windows: (notification_type, window_start, window_end)
    windows = [
        ("reminder_24h", now + timedelta(hours=23), now + timedelta(hours=25)),
        ("reminder_1h", now + timedelta(minutes=50), now + timedelta(minutes=70)),
    ]

    for notif_type, window_start, window_end in windows:
        try:
            jobs = await _fetch_jobs_in_window(window_start, window_end)
        except Exception:
            logger.exception("Failed to fetch jobs for %s window", notif_type)
            continue

        for job in jobs:
            customer_id = job.get("customer_id")
            owner_id = job.get("owner_id")
            job_id = job.get("id")
            if not customer_id or not owner_id or not job_id:
                continue

            try:
                customer = await _fetch_customer(customer_id)
            except Exception:
                logger.warning(
                    "Failed to fetch customer %s for job %s", customer_id, job_id
                )
                continue

            if not customer:
                continue

            # GDPR: skip if customer has not given data processing consent
            if not customer.get("data_processing_consent"):
                logger.debug(
                    "Skipping reminder for customer %s — no data_processing_consent",
                    customer_id,
                )
                continue

            await _send_reminder_channels(
                notif_type, job, customer, owner_id, job_id, customer_id
            )


async def _fetch_jobs_in_window(
    window_start: datetime, window_end: datetime
) -> list[dict]:
    """Query job-db-access-service for scheduled jobs in a time window."""
    url = f"{_get_job_db_url()}/api/v1/jobs"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url,
            params={
                "start_date": window_start.isoformat(),
                "end_date": window_end.isoformat(),
                "status": ["scheduled", "pending"],
                "limit": 500,
            },
        )
        if resp.status_code != 200:
            logger.warning("Job query returned %d", resp.status_code)
            return []
        data = resp.json()
        return data.get("items", [])


async def _fetch_customer(customer_id: int) -> dict | None:
    """Fetch a customer from customer-db-access-service (internal, no auth)."""
    url = f"{_get_customer_db_url()}/api/v1/customers/{customer_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None


async def _send_reminder_channels(
    notif_type: str,
    job: dict,
    customer: dict,
    owner_id: int,
    job_id: int,
    customer_id: int,
) -> None:
    """Send reminders on all opted-in channels for a single job/customer."""
    channels: list[tuple[str, str, str | None]] = []
    # (channel_name, adapter_key, recipient)

    if customer.get("notify_email") and customer.get("email"):
        channels.append(("email", "email_smtp", customer["email"]))
    if customer.get("notify_whatsapp") and customer.get("phone"):
        channels.append(("whatsapp", "whatsapp_link", customer["phone"]))

    for channel, adapter_key, recipient in channels:
        async with AsyncSessionLocal() as db:
            # Dedup: skip if already sent for this job/type/channel
            if await has_been_notified(db, job_id, notif_type, channel):
                continue

            body = _build_reminder_message(notif_type, job, customer)

            try:
                config = _build_adapter_config(adapter_key)
                adapter = get_adapter(adapter_key, config)
                result = await adapter.send(to=recipient, subject=None, body=body)

                await create_notification_log(
                    db,
                    owner_id=owner_id,
                    job_id=job_id,
                    customer_id=customer_id,
                    channel=channel,
                    notification_type=notif_type,
                    status="sent" if result.success else "failed",
                    recipient=recipient,
                    message_body=body,
                    external_message_id=result.message_id,
                )

                if result.success:
                    logger.info(
                        "Sent %s %s to %s for job %s",
                        notif_type,
                        channel,
                        recipient,
                        job_id,
                    )
                else:
                    logger.warning(
                        "Failed %s %s to %s: %s",
                        notif_type,
                        channel,
                        recipient,
                        result.error,
                    )
            except Exception:
                logger.exception(
                    "Error sending %s %s for job %s", notif_type, channel, job_id
                )


def _build_reminder_message(notif_type: str, job: dict, customer: dict) -> str:
    """Build a human-readable reminder message body."""
    title = job.get("title", "Your upcoming job")
    customer_name = customer.get("name", "Customer")
    location = job.get("location") or job.get("address") or ""
    start_time = job.get("start_time", "")

    if notif_type == "reminder_24h":
        intro = f"Hi {customer_name}, this is a reminder that your job is scheduled for tomorrow."
    else:
        intro = f"Hi {customer_name}, your job is starting in about 1 hour."

    parts = [intro, f"Job: {title}"]
    if start_time:
        parts.append(f"Scheduled: {start_time}")
    if location:
        parts.append(f"Location: {location}")
    parts.append("If you need to reschedule, please contact us. Thank you!")
    return "\n".join(parts)


def _build_adapter_config(adapter_key: str) -> dict | None:
    """Build adapter config from environment (Tier 3 fallback)."""
    if adapter_key == "email_smtp":
        host = getattr(app_settings, "smtp_host", "")
        if not host:
            return None
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
    # whatsapp_link requires no config
    return None


async def _process_retries(redis: aioredis.Redis) -> None:
    """Re-send failed notifications that are eligible for retry.

    Picks up records where ``retry_count < 3`` and
    ``next_retry_at <= now()``, re-sends via the adapter,
    and updates the log accordingly.
    """
    async with AsyncSessionLocal() as db:
        retryable = await get_retryable_notifications(db)
        if not retryable:
            return

        logger.info("Processing %d retryable notifications", len(retryable))

        for log_entry in retryable:
            adapter_key = _CHANNEL_ADAPTER_MAP.get(log_entry.channel)
            if not adapter_key:
                logger.warning(
                    "No adapter mapping for channel %r — skipping retry for log %s",
                    log_entry.channel,
                    log_entry.id,
                )
                await mark_failed(
                    db, log_entry, f"No adapter for channel: {log_entry.channel}"
                )
                continue

            try:
                # For retries we use env-var config (Tier 3). Full org-level
                # retry would need stored credentials — a future enhancement.
                config = None
                if adapter_key == "email_smtp":
                    host = getattr(app_settings, "smtp_host", "")
                    if not host:
                        logger.warning(
                            "SMTP not configured — cannot retry email log %s",
                            log_entry.id,
                        )
                        await mark_failed(
                            db, log_entry, "SMTP not configured for retry"
                        )
                        continue
                    config = {
                        "smtp_host": host,
                        "smtp_port": getattr(app_settings, "smtp_port", 1025),
                        "smtp_username": getattr(app_settings, "smtp_username", ""),
                        "smtp_password": getattr(app_settings, "smtp_password", ""),
                        "from_email": getattr(
                            app_settings, "smtp_from_email", "noreply@example.com"
                        ),
                        "from_name": getattr(
                            app_settings, "smtp_from_name", "CRM Calendar"
                        ),
                        "use_tls": getattr(app_settings, "smtp_use_tls", False),
                    }
                adapter = get_adapter(adapter_key, config)
            except (KeyError, ValueError) as exc:
                logger.error("Failed to create adapter for retry: %s", exc)
                await mark_failed(db, log_entry, str(exc))
                continue

            try:
                result = await adapter.send(
                    to=log_entry.recipient,
                    subject=None,
                    body=log_entry.message_body,
                )

                if result.success:
                    await mark_sent(db, log_entry, result.message_id)
                    logger.info(
                        "Retry succeeded for log %s (attempt %d)",
                        log_entry.id,
                        log_entry.retry_count + 1,
                    )
                else:
                    await mark_failed(db, log_entry, result.error or "Send failed")
                    logger.warning(
                        "Retry failed for log %s (attempt %d): %s",
                        log_entry.id,
                        log_entry.retry_count + 1,
                        result.error,
                    )
            except Exception:
                logger.exception("Unexpected error retrying log %s", log_entry.id)
                await mark_failed(db, log_entry, "Unexpected error during retry")


async def _maybe_cleanup_retention(redis: aioredis.Redis) -> None:
    """Run retention cleanup at most once per day (GDPR data minimisation).

    Uses a Redis key to track the last run time so that
    only one cleanup per 24 hours happens, even across restarts.
    """
    last_run = await redis.get(RETENTION_CLEANUP_KEY)
    if last_run is not None:
        return  # Already ran today

    logger.info("Running GDPR notification log retention cleanup")
    async with AsyncSessionLocal() as db:
        # Default 90 days; configurable via platform_settings
        deleted = await cleanup_old_notification_logs(db, retention_days=90)
        logger.info(
            "Retention cleanup: deleted %d old notification log entries", deleted
        )

    # Also clean up old audit logs via user-db-access-service (730 days / 2 years)
    try:
        user_svc_url = app_settings.user_service_url
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{user_svc_url}/api/v1/audit-logs/cleanup",
                params={"retention_days": 730},
            )
            if resp.status_code == 200:
                result = resp.json()
                logger.info(
                    "Audit log cleanup: deleted %d entries (retention=%d days)",
                    result.get("deleted_count", 0),
                    result.get("retention_days", 730),
                )
    except Exception:
        logger.warning(
            "Failed to trigger audit log cleanup (suppressed)", exc_info=True
        )

    # Mark as done for the next 24 hours
    await redis.set(RETENTION_CLEANUP_KEY, "1", ex=RETENTION_CLEANUP_INTERVAL)


async def _maybe_process_anonymizations(redis: aioredis.Redis) -> None:
    """Process users whose ``anonymize_scheduled_at`` has passed (hourly).

    Calls the user-db-access-service endpoint that finds users due for
    anonymization and anonymizes them in bulk.
    """
    last_run = await redis.get(ANONYMIZATION_KEY)
    if last_run is not None:
        return  # Already ran this hour

    logger.info("Processing scheduled anonymizations")
    try:
        user_svc_url = app_settings.user_service_url
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{user_svc_url}/api/v1/users/anonymize/process-scheduled"
            )
            if resp.status_code == 200:
                result = resp.json()
                count = result.get("processed_count", 0)
                if count:
                    logger.info("Anonymized %d users whose grace period expired", count)
            else:
                logger.warning("Anonymization endpoint returned %d", resp.status_code)
    except Exception:
        logger.warning("Failed to process scheduled anonymizations", exc_info=True)

    await redis.set(ANONYMIZATION_KEY, "1", ex=ANONYMIZATION_INTERVAL)


async def _maybe_cleanup_tokens(redis: aioredis.Redis) -> None:
    """Clean up expired auth tokens once per day.

    Calls the auth-service internal cleanup endpoint (no auth required,
    blocked at nginx for external access).
    """
    last_run = await redis.get(TOKEN_CLEANUP_KEY)
    if last_run is not None:
        return  # Already ran today

    logger.info("Running expired token cleanup")
    try:
        auth_svc_url = app_settings.auth_service_url
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(f"{auth_svc_url}/api/v1/auth/internal/cleanup")
            if resp.status_code == 200:
                result = resp.json()
                logger.info(
                    "Token cleanup: removed %d expired tokens",
                    result.get("deleted_count", 0),
                )
            else:
                logger.warning("Token cleanup endpoint returned %d", resp.status_code)
    except Exception:
        logger.warning("Failed to clean up expired tokens", exc_info=True)

    await redis.set(TOKEN_CLEANUP_KEY, "1", ex=TOKEN_CLEANUP_INTERVAL)
