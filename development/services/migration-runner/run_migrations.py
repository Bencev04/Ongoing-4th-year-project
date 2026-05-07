#!/usr/bin/env python3
"""
Migration runner entrypoint.

1. Runs ``alembic upgrade head`` to apply all pending migrations.
2. If a seed SQL file is present, executes it against the database.

The seed file is optional and only mounted in dev/CI environments.
"""

import os
import subprocess
import sys

import psycopg2


def _get_sync_url() -> str:
    """Return a sync database URL from DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL", "")
    return url.replace("+asyncpg", "").replace("+aiopg", "")


def run_alembic() -> None:
    """Run alembic upgrade head."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],  # noqa: S607
        cwd="/app/shared",
        capture_output=False,
    )
    if result.returncode != 0:
        print("ERROR: Alembic migration failed!", file=sys.stderr)
        sys.exit(result.returncode)
    print("Alembic migrations applied successfully.")


def run_seed_sql() -> None:
    """Execute the seed SQL file if present."""
    seed_file = "/app/seed-demo-data.sql"
    if not os.path.isfile(seed_file):
        print("No seed file found — skipping seed step.")
        return

    print(f"Running seed file: {seed_file}")
    url = _get_sync_url()

    # Parse the URL into connection params for psycopg2
    # Format: postgresql://user:password@host:port/dbname
    from urllib.parse import urlparse

    parsed = urlparse(url)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        dbname=parsed.path.lstrip("/"),
    )
    conn.autocommit = True

    with open(seed_file) as f:
        sql = f.read()

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        print("Seed data loaded successfully.")
    except Exception as e:
        # Seed failures are non-fatal (e.g., data already exists)
        print(f"WARNING: Seed script encountered an issue: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    run_alembic()
    run_seed_sql()
