"""
Database configuration and session management.

Provides both synchronous and asynchronous SQLAlchemy engines,
session factories, and FastAPI dependency injectors for all
microservices.

Usage:
    - DB-access services that talk directly to Postgres should
      import ``get_async_db`` (preferred) or ``get_db`` (legacy sync).
    - Business-logic services that have no direct DB access
      do not need this module.
"""

import os
import re
import time
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from .config import settings

try:
    from .metrics_config import record_db_query, update_db_pool_status
except ModuleNotFoundError as exc:
    if exc.name != "starlette":
        raise

    def record_db_query(*args, **kwargs):
        return None

    def update_db_pool_status(*args, **kwargs):
        return None


# ── Declarative base (shared by both sync & async models) ────────────────────
Base = declarative_base()


# ==============================================================================
# Synchronous engine (legacy — kept for migration scripts / tests)
# Lazy-initialised so services without psycopg2 are not affected.
# ==============================================================================


def _sync_url(url: str) -> str:
    """Ensure the URL uses a synchronous driver."""
    return url.replace("+asyncpg", "").replace("+aiopg", "")


_engine = None
_SessionLocal = None
_instrumented_engine_ids: set[int] = set()

_QUERY_TABLE_PATTERN = re.compile(
    r"\b(?:from|join|into|update)\s+([\w.\"`\[\]]+)",
    re.IGNORECASE,
)
_QUERY_TYPES = {"SELECT", "INSERT", "UPDATE", "DELETE"}


def _service_name() -> str:
    return os.environ.get("SERVICE_NAME", "unknown-service")


def _query_metadata(statement: str) -> tuple[str, str]:
    stripped = statement.lstrip()
    query_type = stripped.split(None, 1)[0].upper() if stripped else "UNKNOWN"
    if query_type not in _QUERY_TYPES:
        query_type = "OTHER"

    table_match = _QUERY_TABLE_PATTERN.search(statement)
    if table_match is None:
        return query_type, "unknown"

    table_name = table_match.group(1).strip('"`[]')
    table_name = table_name.rsplit(".", 1)[-1].strip('"`[]')
    if not table_name or len(table_name) > 64:
        return query_type, "unknown"
    return query_type, table_name.lower()


def _update_pool_metrics(sqlalchemy_engine) -> None:
    pool = sqlalchemy_engine.pool
    size = getattr(pool, "size", None)
    checked_in = getattr(pool, "checkedin", None)
    if not callable(size) or not callable(checked_in):
        return
    try:
        update_db_pool_status(size(), checked_in(), _service_name())
    except Exception:
        return


def _instrument_engine(sqlalchemy_engine) -> None:
    engine_id = id(sqlalchemy_engine)
    if engine_id in _instrumented_engine_ids:
        return
    _instrumented_engine_ids.add(engine_id)

    @event.listens_for(sqlalchemy_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        context._query_start_time = time.perf_counter()

    @event.listens_for(sqlalchemy_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        started_at = getattr(context, "_query_start_time", None)
        if started_at is None:
            return
        query_type, table_name = _query_metadata(statement)
        record_db_query(
            query_type=query_type,
            table=table_name,
            duration=time.perf_counter() - started_at,
            service_name=_service_name(),
        )
        _update_pool_metrics(sqlalchemy_engine)


def _get_sync_engine():
    """Return the sync engine, creating it lazily on first call."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _sync_url(settings.database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            echo=settings.debug,
        )
        _instrument_engine(_engine)
    return _engine


def _get_sync_session_factory():
    """Return the sync session factory, creating it lazily on first call."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=_get_sync_engine(),
        )
    return _SessionLocal


# Backward-compatible aliases (evaluated lazily via property-like access)
class _EngineProxy:
    """Proxy that defers engine creation until attribute access."""

    def __getattr__(self, name):
        return getattr(_get_sync_engine(), name)


engine = _EngineProxy()


def get_db() -> Generator[Session, None, None]:
    """
    Synchronous database session dependency (legacy).

    Yields a database session and ensures it's closed after use.
    Use ``get_async_db`` for new code.

    Yields:
        Session: SQLAlchemy database session
    """
    factory = _get_sync_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()


# ==============================================================================
# Asynchronous engine (preferred for all new services)
# ==============================================================================


def _async_url(url: str) -> str:
    """Ensure the URL uses the asyncpg driver."""
    if "+asyncpg" in url:
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async_engine = create_async_engine(
    _async_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.debug,
)
_instrument_engine(async_engine.sync_engine)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session dependency for FastAPI ``Depends()``.

    Yields an ``AsyncSession`` and ensures it is closed after use.

    Yields:
        AsyncSession: SQLAlchemy async database session

    Example:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ==============================================================================
# Utilities
# ==============================================================================


def get_test_db_engine():
    """
    Create a test database engine (synchronous).

    Returns:
        Engine: SQLAlchemy engine connected to test database
    """
    test_url = getattr(settings, "test_database_url", None)
    if test_url is None:
        test_url = "sqlite:///:memory:"
    return create_engine(
        _sync_url(test_url),
        pool_pre_ping=True,
        echo=True,
    )


def init_db() -> None:
    """
    Initialize database tables (synchronous).

    Creates all tables defined in the models.
    Should be called on application startup.
    """
    Base.metadata.create_all(bind=_get_sync_engine())


async def async_init_db() -> None:
    """
    Initialize database tables (asynchronous).

    .. deprecated::
        Schema is now managed by Alembic migrations via the migration-runner
        container. This function is kept for backward compatibility with
        unit tests that use in-memory SQLite. Application services should
        NOT call this on startup.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
