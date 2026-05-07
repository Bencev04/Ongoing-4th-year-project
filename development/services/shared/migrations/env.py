"""
Alembic environment configuration for CRM Calendar Platform.

Reads DATABASE_URL from the environment, imports all ORM models via
``common.all_models`` so that ``Base.metadata`` is fully populated,
and configures online/offline migration runners.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# Ensure the shared library is importable (already on PYTHONPATH in Docker,
# but this helps when running locally too).
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# Import ALL models so Base.metadata knows about every table.
# This is the single integration point between Alembic and the services.
# ---------------------------------------------------------------------------
import common.all_models  # noqa: F401, E402
from common.database import Base  # noqa: E402

# Alembic Config object — provides access to alembic.ini values.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_url() -> str:
    """
    Return a synchronous database URL for Alembic.

    Reads ``DATABASE_URL`` from the environment, strips any async driver
    suffix (``+asyncpg``), and returns a plain ``postgresql://`` URL
    suitable for the synchronous ``psycopg2`` driver that Alembic uses.
    """
    url = os.environ.get(
        "DATABASE_URL",
        config.get_main_option("sqlalchemy.url", ""),
    )
    # Convert async URL to sync
    return url.replace("+asyncpg", "").replace("+aiopg", "")


# Objects that exist only in raw SQL (triggers, functions, extensions)
# and should be ignored by autogenerate so it doesn't try to drop them.
_EXCLUDE_TABLES: set[str] = set()  # add table names here to skip entirely


def include_object(obj, name, type_, reflected, compare_to):
    """
    Filter callback for ``--autogenerate``.

    Excludes database objects that are managed by raw SQL in migrations
    rather than by SQLAlchemy ORM metadata (e.g., triggers, PL/pgSQL
    functions). Tables listed in ``_EXCLUDE_TABLES`` are also skipped.
    """
    if type_ == "table" and name in _EXCLUDE_TABLES:
        return False
    return True


# ---------------------------------------------------------------------------
# Offline migrations (generate SQL script without connecting to DB)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL to stdout."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (connect to DB and apply changes)
# ---------------------------------------------------------------------------


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connect to the database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
