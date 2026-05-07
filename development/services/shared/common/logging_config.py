"""
Structured logging configuration for container and AWS log ingestion.

Provides centralized, JSON-formatted logging across all services.
Logs include timestamp, service name, level, message, trace_id, user_id, and more.
"""

import logging
import logging.config
import os
import sys
import traceback
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

from pythonjsonlogger import jsonlogger

_log_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "log_context", default=None
)


class StructuredFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """
        Add custom fields to log records for downstream log ingestion.

        Args:
            log_record: The log record dictionary to be formatted
            record: The logging.LogRecord object
            message_dict: The message dictionary
        """
        super().add_fields(log_record, record, message_dict)

        # Add timestamp in ISO 8601 format
        log_record["timestamp"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        # Add service name from environment
        log_record["service_name"] = os.environ.get("SERVICE_NAME", "unknown-service")

        # Set logging level from the record (not from log_record which may be missing it)
        log_record["logging_level"] = record.levelname

        # Add environment
        log_record["environment"] = os.environ.get("ENVIRONMENT", "development")

        # Add service version if available
        if version := os.environ.get("SERVICE_VERSION"):
            log_record["service_version"] = version

        # Add correlation/trace ID if available (e.g., from request context)
        if trace_id := getattr(record, "trace_id", None):
            log_record["trace_id"] = trace_id

        if request_id := getattr(record, "request_id", None):
            log_record["request_id"] = request_id

        # Add user ID if available (e.g., from request context)
        if user_id := getattr(record, "user_id", None):
            log_record["user_id"] = user_id

        if tenant_id := getattr(record, "tenant_id", None):
            log_record["tenant_id"] = tenant_id

        # Add execution time for performance tracking
        if duration_ms := getattr(record, "duration_ms", None):
            log_record["duration_ms"] = duration_ms

        # Add full traceback for exceptions
        if record.exc_info:
            log_record["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        # Remove redundant fields
        log_record.pop("name", None)  # Covered by service_name and module
        log_record.pop("filename", None)
        log_record.pop("funcName", None)
        log_record.pop("lineno", None)
        log_record.pop("levelname", None)  # We've renamed it to logging_level


class ResilientStdoutHandler(logging.StreamHandler):
    """Stream logs to the current stdout, recovering if test capture closes it."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout if not sys.stdout.closed else sys.__stdout__
        try:
            super().emit(record)
        except ValueError:
            self.stream = sys.__stdout__
            super().emit(record)


class ContextFilter(logging.Filter):
    """
    Adds context information (trace_id, user_id, tenant_id) to log records.

    Uses contextvars so concurrent async requests do not leak context into each
    other's logs.
    """

    @staticmethod
    def set_context(**context: Any) -> Token[dict[str, Any]]:
        """Set context variables for the current request/task."""
        current_context = (_log_context.get() or {}).copy()
        current_context.update(
            {key: value for key, value in context.items() if value is not None}
        )
        return _log_context.set(current_context)

    @staticmethod
    def clear_context(token: Token[dict[str, Any]] | None = None) -> None:
        """Clear context variables for the current request/task."""
        if token is None:
            _log_context.set({})
            return
        _log_context.reset(token)

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context to log record."""
        for key, value in (_log_context.get() or {}).items():
            setattr(record, key, value)
        return True


def configure_logging(
    service_name: str,
    level: str = "INFO",
    environment: str = "development",
    version: str | None = None,
    log_to_stdout: bool = True,
    log_to_file: str | None = None,
) -> logging.Logger:
    """
    Configure structured JSON logging for a service.

    IMPORTANT: Call this BEFORE importing FastAPI/Uvicorn to properly
    suppress their default logging handlers.

    Args:
        service_name: Name of the service (e.g., 'auth-service')
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Environment name (development, staging, production)
        version: Service version
        log_to_stdout: Whether to log to stdout
        log_to_file: Optional file path to log to

    Returns:
        Configured root logger

    Example:
        >>> logger = configure_logging("auth-service", level="DEBUG")
        >>> logger.info("Service started")
    """
    # Set environment variables (accessible to formatter)
    os.environ["SERVICE_NAME"] = service_name
    os.environ["ENVIRONMENT"] = environment
    if version:
        os.environ["SERVICE_VERSION"] = version

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove ALL existing handlers (critical to prevent Uvicorn/duplicates)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Add context filter to all handlers
    context_filter = ContextFilter()

    # Create formatter
    log_format = "%(timestamp)s %(service_name)s %(logging_level)s %(message)s"
    formatter = StructuredFormatter(log_format)

    # stdout handler
    if log_to_stdout:
        stdout_handler = ResilientStdoutHandler(sys.stdout)
        stdout_handler.setLevel(level)
        stdout_handler.setFormatter(formatter)
        stdout_handler.addFilter(context_filter)
        root_logger.addHandler(stdout_handler)

    # file handler (optional)
    if log_to_file:
        file_handler = logging.FileHandler(log_to_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        root_logger.addHandler(file_handler)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("This is a structured log")
    """
    return logging.getLogger(name)


def set_correlation_context(
    trace_id: str,
    user_id: str | None = None,
    tenant_id: str | None = None,
) -> Token[dict[str, Any]]:
    """
    Set correlation context for request tracing across services.

    Args:
        trace_id: Unique request/trace ID
        user_id: User ID if applicable
        tenant_id: Tenant ID for multi-tenant tracking
    """
    context_data = {"trace_id": trace_id}
    if user_id:
        context_data["user_id"] = user_id
    if tenant_id:
        context_data["tenant_id"] = tenant_id
    context_data["request_id"] = trace_id
    return ContextFilter.set_context(**context_data)


def clear_correlation_context(token: Token[dict[str, Any]] | None = None) -> None:
    """Clear correlation context after request completes."""
    ContextFilter.clear_context(token)


def get_correlation_context() -> dict[str, Any]:
    """Return a copy of the current request correlation context."""
    return (_log_context.get() or {}).copy()
