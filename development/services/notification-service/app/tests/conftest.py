"""Shared test fixtures for the notification service."""

import sys
from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure shared module is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = 1
    user.owner_id = 10
    user.role = "owner"
    user.email = "test@example.com"
    return user


@pytest.fixture
def test_client(mock_current_user):
    """FastAPI test client with mocked auth and DB.

    Mocks startup/shutdown events so no Redis/external connection is needed.
    """
    from app.dependencies import get_current_user
    from app.main import app
    from common.database import get_async_db

    # Mock the async DB session
    mock_session = AsyncMock()

    async def override_db():
        yield mock_session

    app.dependency_overrides[get_current_user] = lambda: mock_current_user
    app.dependency_overrides[get_async_db] = override_db

    # Patch startup/shutdown to avoid needing Redis and HTTP clients
    with patch("app.main.init_http_client", new_callable=AsyncMock):
        with patch("app.main.scheduler_loop", new_callable=AsyncMock):
            with patch("app.main.close_http_client", new_callable=AsyncMock):
                with patch("app.main.close_redis", new_callable=AsyncMock):
                    client = TestClient(app)
                    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_notification_log():
    """Mock notification log object matching NotificationLogResponse."""
    from datetime import datetime

    log = MagicMock()
    log.id = 1
    log.owner_id = 10
    log.job_id = 42
    log.customer_id = 7
    log.channel = "whatsapp"
    log.notification_type = "reminder_24h"
    log.status = "sent"
    log.recipient = "+353831234567"
    log.message_body = "Hi John, reminder about your appointment tomorrow."
    log.external_message_id = None
    log.error_message = None
    log.retry_count = 0
    log.sent_at = datetime.now(UTC)
    log.delivered_at = None
    log.created_at = datetime.now(UTC)
    return log
