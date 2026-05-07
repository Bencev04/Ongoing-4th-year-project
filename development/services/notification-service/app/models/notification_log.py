"""SQLAlchemy model for the notification_log table.

This model is used within the notification-service for CRUD operations.
The table itself is created by an Alembic migration in the shared layer.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from common.database import Base


class NotificationLog(Base):
    """Notification log entry — tracks every send attempt."""

    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    message_body: Mapped[str] = mapped_column(Text, nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # GDPR: hashed recipient for post-delivery data minimisation
    recipient_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="SHA-256 hash of recipient after delivery — replaces plaintext",
    )

    def __repr__(self) -> str:
        return (
            f"<NotificationLog(id={self.id}, channel={self.channel!r}, "
            f"status={self.status!r}, recipient={self.recipient!r})>"
        )
