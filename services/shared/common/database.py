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

from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings


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

    Creates all tables defined in the models using the async engine.
    Preferred for services that only have asyncpg installed.
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
