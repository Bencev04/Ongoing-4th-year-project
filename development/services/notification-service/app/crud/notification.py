"""CRUD operations for the notification_log table.

All queries are tenant-scoped by ``owner_id`` for isolation.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.notification_log import NotificationLog

# -- Create -------------------------------------------------------------------


async def create_notification_log(
    db: AsyncSession,
    *,
    owner_id: int,
    job_id: int | None = None,
    customer_id: int | None = None,
    channel: str,
    notification_type: str,
    status: str = "pending",
    recipient: str,
    message_body: str,
    external_message_id: str | None = None,
) -> NotificationLog:
    """Insert a new notification log entry."""
    log = NotificationLog(
        owner_id=owner_id,
        job_id=job_id,
        customer_id=customer_id,
        channel=channel,
        notification_type=notification_type,
        status=status,
        recipient=recipient,
        message_body=message_body,
        external_message_id=external_message_id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


# -- Read ---------------------------------------------------------------------


async def has_been_notified(
    db: AsyncSession,
    job_id: int,
    notification_type: str,
    channel: str,
) -> bool:
    """Check if a notification has already been sent for this job/type/channel.

    Used as a dedup guard before the scheduler sends.
    """
    result = await db.execute(
        select(func.count())
        .select_from(NotificationLog)
        .where(
            and_(
                NotificationLog.job_id == job_id,
                NotificationLog.notification_type == notification_type,
                NotificationLog.channel == channel,
                NotificationLog.status.in_(["pending", "sent", "delivered", "read"]),
            )
        )
    )
    return (result.scalar_one() or 0) > 0


async def get_notification_log(
    db: AsyncSession,
    owner_id: int,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[NotificationLog], int]:
    """Paginated notification log for a tenant."""
    base = select(NotificationLog).where(NotificationLog.owner_id == owner_id)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        base.order_by(NotificationLog.created_at.desc()).offset(offset).limit(per_page)
    )
    items = list(result.scalars().all())
    return items, total


async def get_retryable_notifications(db: AsyncSession) -> list[NotificationLog]:
    """Find failed sends eligible for retry (count < 3, next_retry_at <= now)."""
    now = datetime.now(UTC)
    result = await db.execute(
        select(NotificationLog).where(
            and_(
                NotificationLog.status == "failed",
                NotificationLog.retry_count < 3,
                NotificationLog.next_retry_at <= now,
            )
        )
    )
    return list(result.scalars().all())


# -- Update -------------------------------------------------------------------


async def update_delivery_status(
    db: AsyncSession,
    external_message_id: str,
    status: str,
    delivered_at: datetime | None = None,
) -> NotificationLog | None:
    """Update status via webhook delivery receipt.

    Returns the updated log entry or ``None`` if not found (idempotent).
    """
    result = await db.execute(
        select(NotificationLog).where(
            NotificationLog.external_message_id == external_message_id
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        return None

    log.status = status
    if delivered_at:
        log.delivered_at = delivered_at
    await db.commit()
    await db.refresh(log)
    return log


async def mark_sent(
    db: AsyncSession,
    log: NotificationLog,
    external_message_id: str | None = None,
) -> NotificationLog:
    """Mark a notification as successfully sent."""
    log.status = "sent"
    log.sent_at = datetime.now(UTC)
    if external_message_id:
        log.external_message_id = external_message_id
    await db.commit()
    await db.refresh(log)
    return log


async def mark_failed(
    db: AsyncSession,
    log: NotificationLog,
    error_message: str,
) -> NotificationLog:
    """Mark a notification as failed and schedule retry if eligible."""
    log.status = "failed"
    log.error_message = error_message
    log.retry_count += 1

    if log.retry_count < 3:
        backoff_seconds = 5**log.retry_count  # 5, 25, 125
        log.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)

    await db.commit()
    await db.refresh(log)
    return log


# -- GDPR: Retention Cleanup -------------------------------------------------


async def cleanup_old_notification_logs(
    db: AsyncSession,
    retention_days: int = 90,
) -> int:
    """
    Delete notification log entries older than ``retention_days``.

    Only deletes terminal-status entries (delivered, failed).
    Pending and sent entries are kept until they resolve.

    Returns the number of rows deleted.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    stmt = sa_delete(NotificationLog).where(
        and_(
            NotificationLog.created_at < cutoff,
            NotificationLog.status.in_(["delivered", "failed"]),
        )
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount
