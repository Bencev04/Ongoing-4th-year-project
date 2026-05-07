"""Pydantic schemas for the notification service."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class NotificationChannel(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class NotificationType(StrEnum):
    REMINDER_24H = "reminder_24h"
    REMINDER_1H = "reminder_1h"
    ON_THE_WAY = "on_the_way"
    COMPLETED = "completed"
    WELCOME = "welcome"
    TEST = "test"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# -- Responses ----------------------------------------------------------------


class NotificationLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    job_id: int | None = None
    customer_id: int | None = None
    channel: str
    notification_type: str
    status: str
    recipient: str
    message_body: str
    external_message_id: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    created_at: datetime


class NotificationLogListResponse(BaseModel):
    items: list[NotificationLogResponse]
    total: int
    page: int
    per_page: int


class PendingReminderResponse(BaseModel):
    """A job that needs a manual WhatsApp reminder (Tier 1)."""

    job_id: int
    job_title: str
    customer_name: str
    customer_phone: str
    start_time: datetime
    whatsapp_link: str


class PendingReminderListResponse(BaseModel):
    items: list[PendingReminderResponse]
    total: int


# -- Requests -----------------------------------------------------------------


class SendTestRequest(BaseModel):
    channel: NotificationChannel
    recipient: str = Field(..., min_length=1, max_length=255)


class MarkSentRequest(BaseModel):
    channel: NotificationChannel = NotificationChannel.WHATSAPP


class SendWelcomeRequest(BaseModel):
    """Request to send a welcome/confirmation message after job creation."""

    job_id: int
    customer_id: int
    send_email: bool = False
    send_whatsapp: bool = False


# -- Adapter result -----------------------------------------------------------


class SendResult(BaseModel):
    """Returned by every adapter after a send attempt."""

    success: bool
    action: str  # "sent", "open_link", "failed"
    message_id: str | None = None
    link: str | None = None
    error: str | None = None
