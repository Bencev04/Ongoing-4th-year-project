"""Tests for the background scheduler logic.

These tests mock Redis and verify lock behaviour, loop structure, and
graceful cancellation without needing a live Redis instance.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.logic.scheduler import (
    ANONYMIZATION_INTERVAL,
    ANONYMIZATION_KEY,
    POLL_INTERVAL,
    SCHEDULER_LOCK_KEY,
    SCHEDULER_LOCK_TTL,
    TOKEN_CLEANUP_INTERVAL,
    TOKEN_CLEANUP_KEY,
    _maybe_cleanup_tokens,
    _maybe_process_anonymizations,
    _process_reminders,
    _process_retries,
    scheduler_loop,
)


class TestSchedulerConstants:
    """Verify the scheduler is configured correctly."""

    def test_lock_ttl_exceeds_poll(self):
        assert SCHEDULER_LOCK_TTL > POLL_INTERVAL

    def test_lock_key_format(self):
        assert "notification" in SCHEDULER_LOCK_KEY


class TestProcessReminders:
    """Tests for _process_reminders."""

    @pytest.mark.asyncio
    async def test_process_reminders_no_jobs_is_noop(self):
        """When no jobs fall in the reminder windows, nothing is sent."""
        mock_redis = AsyncMock()

        with patch(
            "app.logic.scheduler._fetch_jobs_in_window",
            new_callable=AsyncMock,
            return_value=[],
        ):
            await _process_reminders(mock_redis)  # should not raise

    @pytest.mark.asyncio
    async def test_process_reminders_skips_no_consent(self):
        """Jobs for customers without data_processing_consent are skipped."""
        mock_redis = AsyncMock()

        job = {"id": 1, "customer_id": 10, "owner_id": 5, "title": "Test"}
        customer = {
            "data_processing_consent": False,
            "email": "a@b.com",
            "notify_email": True,
        }

        with patch(
            "app.logic.scheduler._fetch_jobs_in_window",
            new_callable=AsyncMock,
            return_value=[job],
        ):
            with patch(
                "app.logic.scheduler._fetch_customer",
                new_callable=AsyncMock,
                return_value=customer,
            ):
                with patch(
                    "app.logic.scheduler._send_reminder_channels",
                    new_callable=AsyncMock,
                ) as mock_send:
                    await _process_reminders(mock_redis)
                    mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_reminders_sends_when_consent_given(self):
        """Jobs for customers with consent trigger channel sends."""
        mock_redis = AsyncMock()

        job = {"id": 1, "customer_id": 10, "owner_id": 5, "title": "Test"}
        customer = {
            "data_processing_consent": True,
            "email": "a@b.com",
            "notify_email": True,
        }

        with patch(
            "app.logic.scheduler._fetch_jobs_in_window",
            new_callable=AsyncMock,
            return_value=[job],
        ):
            with patch(
                "app.logic.scheduler._fetch_customer",
                new_callable=AsyncMock,
                return_value=customer,
            ):
                with patch(
                    "app.logic.scheduler._send_reminder_channels",
                    new_callable=AsyncMock,
                ) as mock_send:
                    await _process_reminders(mock_redis)
                    # Called twice — once for each window (24h and 1h)
                    assert mock_send.await_count == 2


class TestProcessRetries:
    """Tests for _process_retries."""

    @pytest.mark.asyncio
    async def test_process_retries_no_retryable_is_noop(self):
        """When there are no retryable notifications, nothing happens."""
        mock_redis = AsyncMock()
        mock_session = AsyncMock()

        with patch("app.logic.scheduler.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "app.logic.scheduler.get_retryable_notifications",
                new_callable=AsyncMock,
                return_value=[],
            ) as mock_get:
                await _process_retries(mock_redis)
                mock_get.assert_awaited_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_process_retries_sends_and_marks_sent(self):
        """A retryable notification should be re-sent and marked sent on success."""
        mock_redis = AsyncMock()
        mock_session = AsyncMock()

        # Fake notification log entry
        mock_log = AsyncMock()
        mock_log.id = 1
        mock_log.channel = "whatsapp"
        mock_log.recipient = "+353831234567"
        mock_log.message_body = "Test retry"
        mock_log.retry_count = 1

        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.message_id = "retry_id_123"

        with patch("app.logic.scheduler.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "app.logic.scheduler.get_retryable_notifications",
                new_callable=AsyncMock,
                return_value=[mock_log],
            ):
                with patch("app.logic.scheduler.get_adapter") as mock_get_adapter:
                    mock_adapter = AsyncMock()
                    mock_adapter.send.return_value = mock_result
                    mock_get_adapter.return_value = mock_adapter
                    with patch(
                        "app.logic.scheduler.mark_sent",
                        new_callable=AsyncMock,
                    ) as mock_mark_sent:
                        await _process_retries(mock_redis)
                        mock_mark_sent.assert_awaited_once_with(
                            mock_session, mock_log, "retry_id_123"
                        )

    @pytest.mark.asyncio
    async def test_process_retries_marks_failed_on_failure(self):
        """A failed retry should be marked failed."""
        mock_redis = AsyncMock()
        mock_session = AsyncMock()

        mock_log = AsyncMock()
        mock_log.id = 2
        mock_log.channel = "email"
        mock_log.recipient = "user@example.com"
        mock_log.message_body = "Test retry"
        mock_log.retry_count = 0

        mock_result = AsyncMock()
        mock_result.success = False
        mock_result.error = "SMTP timeout"

        with patch("app.logic.scheduler.AsyncSessionLocal") as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            with patch(
                "app.logic.scheduler.get_retryable_notifications",
                new_callable=AsyncMock,
                return_value=[mock_log],
            ):
                with patch("app.logic.scheduler.get_adapter") as mock_get_adapter:
                    mock_adapter = AsyncMock()
                    mock_adapter.send.return_value = mock_result
                    mock_get_adapter.return_value = mock_adapter
                    with patch(
                        "app.logic.scheduler.mark_failed",
                        new_callable=AsyncMock,
                    ) as mock_mark_failed:
                        with patch("app.logic.scheduler.app_settings") as mock_settings:
                            mock_settings.smtp_host = "localhost"
                            mock_settings.smtp_port = 1025
                            mock_settings.smtp_username = ""
                            mock_settings.smtp_password = ""
                            mock_settings.smtp_from_email = "test@example.com"
                            mock_settings.smtp_from_name = "CRM"
                            mock_settings.smtp_use_tls = False
                            await _process_retries(mock_redis)
                            mock_mark_failed.assert_awaited_once()


class TestSchedulerLoop:
    """Tests for scheduler_loop() behaviour."""

    @pytest.mark.asyncio
    async def test_acquires_lock_and_processes(self):
        """When lock IS acquired, _process_* functions should run."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True  # lock acquired
        mock_redis.delete = AsyncMock()

        with patch("app.logic.scheduler.get_redis", return_value=mock_redis):
            with patch(
                "app.logic.scheduler._process_reminders", new_callable=AsyncMock
            ) as mock_rem:
                with patch(
                    "app.logic.scheduler._process_retries", new_callable=AsyncMock
                ) as mock_ret:
                    with patch(
                        "app.logic.scheduler._maybe_process_anonymizations",
                        new_callable=AsyncMock,
                    ) as mock_anon:
                        with patch(
                            "app.logic.scheduler._maybe_cleanup_tokens",
                            new_callable=AsyncMock,
                        ) as mock_tok:
                            with patch(
                                "app.logic.scheduler.asyncio.sleep",
                                new_callable=AsyncMock,
                            ) as mock_sleep:
                                # Cancel after first iteration
                                call_count = 0

                                async def controlled_sleep(seconds):
                                    nonlocal call_count
                                    call_count += 1
                                    if call_count >= 2:
                                        raise asyncio.CancelledError()

                                mock_sleep.side_effect = controlled_sleep

                                await scheduler_loop()

                                mock_rem.assert_awaited_once()
                                mock_ret.assert_awaited_once()
                                mock_anon.assert_awaited_once()
                                mock_tok.assert_awaited_once()
                                mock_redis.delete.assert_awaited_once_with(
                                    SCHEDULER_LOCK_KEY
                                )

    @pytest.mark.asyncio
    async def test_skips_when_lock_not_acquired(self):
        """When lock is NOT acquired, processing should be skipped."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = False  # lock NOT acquired

        with patch("app.logic.scheduler.get_redis", return_value=mock_redis):
            with patch(
                "app.logic.scheduler._process_reminders", new_callable=AsyncMock
            ) as mock_rem:
                with patch(
                    "app.logic.scheduler._process_retries", new_callable=AsyncMock
                ) as mock_ret:
                    with patch(
                        "app.logic.scheduler.asyncio.sleep", new_callable=AsyncMock
                    ) as mock_sleep:
                        call_count = 0

                        async def controlled_sleep(seconds):
                            nonlocal call_count
                            call_count += 1
                            if call_count >= 2:
                                raise asyncio.CancelledError()

                        mock_sleep.side_effect = controlled_sleep

                        await scheduler_loop()

                        mock_rem.assert_not_awaited()
                        mock_ret.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_redis_connection_error(self):
        """Redis errors should be caught, not crash the loop."""
        import redis.asyncio as aioredis

        mock_redis = AsyncMock()
        mock_redis.set.side_effect = aioredis.RedisError("Connection lost")

        with patch("app.logic.scheduler.get_redis", return_value=mock_redis):
            with patch(
                "app.logic.scheduler.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep:
                call_count = 0

                async def controlled_sleep(seconds):
                    nonlocal call_count
                    call_count += 1
                    if call_count >= 2:
                        raise asyncio.CancelledError()

                mock_sleep.side_effect = controlled_sleep

                # Should not raise — error is caught internally
                await scheduler_loop()

    @pytest.mark.asyncio
    async def test_exception_in_processing_releases_lock(self):
        """If _process_reminders raises, lock should still be released."""
        mock_redis = AsyncMock()
        mock_redis.set.return_value = True
        mock_redis.delete = AsyncMock()

        with patch("app.logic.scheduler.get_redis", return_value=mock_redis):
            with patch(
                "app.logic.scheduler._process_reminders",
                side_effect=RuntimeError("boom"),
            ):
                with patch(
                    "app.logic.scheduler.asyncio.sleep", new_callable=AsyncMock
                ) as mock_sleep:
                    call_count = 0

                    async def controlled_sleep(seconds):
                        nonlocal call_count
                        call_count += 1
                        if call_count >= 2:
                            raise asyncio.CancelledError()

                    mock_sleep.side_effect = controlled_sleep

                    await scheduler_loop()

                    # Lock MUST be released even after an error
                    mock_redis.delete.assert_awaited_with(SCHEDULER_LOCK_KEY)


class TestMaybeProcessAnonymizations:
    """Tests for _maybe_process_anonymizations."""

    @pytest.mark.asyncio
    async def test_skips_if_already_ran(self):
        """Should skip when Redis key exists (already ran this interval)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"1"  # already ran

        with patch("app.logic.scheduler.app_settings") as mock_settings:
            mock_settings.user_service_url = "http://user-db-access-service:8001"
            with patch("app.logic.scheduler.httpx.AsyncClient") as mock_client_cls:
                await _maybe_process_anonymizations(mock_redis)
                mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_endpoint_and_sets_key(self):
        """When key is absent, should call the anonymization endpoint and set the key."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # hasn't run yet

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"processed_count": 3}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("app.logic.scheduler.app_settings") as mock_settings:
            mock_settings.user_service_url = "http://user-db-access-service:8001"
            with patch("app.logic.scheduler.httpx.AsyncClient") as mock_client_cls:
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await _maybe_process_anonymizations(mock_redis)

                mock_client.post.assert_awaited_once()
                mock_redis.set.assert_awaited_once_with(
                    ANONYMIZATION_KEY, "1", ex=ANONYMIZATION_INTERVAL
                )

    @pytest.mark.asyncio
    async def test_handles_endpoint_failure_gracefully(self):
        """Network errors should be caught, not crash the scheduler."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")

        with patch("app.logic.scheduler.app_settings") as mock_settings:
            mock_settings.user_service_url = "http://user-db-access-service:8001"
            with patch("app.logic.scheduler.httpx.AsyncClient") as mock_client_cls:
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                # Should not raise
                await _maybe_process_anonymizations(mock_redis)

                # Key should still be set to avoid hammering a broken endpoint
                mock_redis.set.assert_awaited_once()


class TestMaybeCleanupTokens:
    """Tests for _maybe_cleanup_tokens."""

    @pytest.mark.asyncio
    async def test_skips_if_already_ran(self):
        """Should skip when Redis key exists (already ran today)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"1"

        with patch("app.logic.scheduler.app_settings") as mock_settings:
            mock_settings.auth_service_url = "http://auth-service:8005"
            with patch("app.logic.scheduler.httpx.AsyncClient") as mock_client_cls:
                await _maybe_cleanup_tokens(mock_redis)
                mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_cleanup_endpoint_and_sets_key(self):
        """When key is absent, should call auth internal cleanup and set the key."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted_count": 15}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch("app.logic.scheduler.app_settings") as mock_settings:
            mock_settings.auth_service_url = "http://auth-service:8005"
            with patch("app.logic.scheduler.httpx.AsyncClient") as mock_client_cls:
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await _maybe_cleanup_tokens(mock_redis)

                mock_client.post.assert_awaited_once()
                call_url = mock_client.post.call_args[0][0]
                assert "/auth/internal/cleanup" in call_url
                mock_redis.set.assert_awaited_once_with(
                    TOKEN_CLEANUP_KEY, "1", ex=TOKEN_CLEANUP_INTERVAL
                )

    @pytest.mark.asyncio
    async def test_handles_endpoint_failure_gracefully(self):
        """Network errors should be caught, not crash the scheduler."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Connection refused")

        with patch("app.logic.scheduler.app_settings") as mock_settings:
            mock_settings.auth_service_url = "http://auth-service:8005"
            with patch("app.logic.scheduler.httpx.AsyncClient") as mock_client_cls:
                mock_client_cls.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

                await _maybe_cleanup_tokens(mock_redis)
                mock_redis.set.assert_awaited_once()
