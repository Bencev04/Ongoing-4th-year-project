"""
Shared common library for CRM Calendar microservices.

This module contains shared utilities, database configurations,
base models, and common schemas used across all microservices.

Database utilities (get_db, get_async_db, async_init_db, Base) are
imported lazily so that services which do not need SQLAlchemy
(e.g. business-logic services, frontend) can still use config and
exceptions without installing database drivers.
"""

from .config import settings


def __getattr__(name: str):
    """Lazy-load database and logging symbols only when they are actually accessed."""
    _db_exports = {"get_db", "get_async_db", "async_init_db", "Base"}
    _logging_exports = {
        "configure_logging",
        "get_logger",
        "set_correlation_context",
        "clear_correlation_context",
    }

    if name in _db_exports:
        from .database import Base, async_init_db, get_async_db, get_db  # noqa: F811

        # Cache them on the module so __getattr__ is only called once
        globals().update(
            {
                "get_db": get_db,
                "get_async_db": get_async_db,
                "async_init_db": async_init_db,
                "Base": Base,
            }
        )
        return globals()[name]
    elif name in _logging_exports:
        from .logging_config import (  # noqa: F401
            clear_correlation_context,
            configure_logging,
            get_logger,
            set_correlation_context,
        )

        # Cache them on the module so __getattr__ is only called once
        globals().update(
            {
                "configure_logging": configure_logging,
                "get_logger": get_logger,
                "set_correlation_context": set_correlation_context,
                "clear_correlation_context": clear_correlation_context,
            }
        )
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "settings",
    "get_db",
    "get_async_db",
    "async_init_db",
    "Base",
    "configure_logging",
    "get_logger",
    "set_correlation_context",
    "clear_correlation_context",
]
