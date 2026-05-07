"""Unit tests for the migration runner entrypoint."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

sys.modules.setdefault("psycopg2", SimpleNamespace(connect=MagicMock()))

import run_migrations


class TestGetSyncUrl:
    """Tests for database URL normalization."""

    def test_strips_asyncpg_driver_suffix(self) -> None:
        """Asyncpg URLs should be converted to sync PostgreSQL URLs."""
        with patch.dict(
            "run_migrations.os.environ",
            {"DATABASE_URL": "postgresql+asyncpg://user:pass@db:5432/app"},
            clear=True,
        ):
            assert (
                run_migrations._get_sync_url() == "postgresql://user:pass@db:5432/app"
            )

    def test_strips_aiopg_driver_suffix(self) -> None:
        """Aiopg URLs should be converted to sync PostgreSQL URLs."""
        with patch.dict(
            "run_migrations.os.environ",
            {"DATABASE_URL": "postgresql+aiopg://user:pass@db:5432/app"},
            clear=True,
        ):
            assert (
                run_migrations._get_sync_url() == "postgresql://user:pass@db:5432/app"
            )


class TestRunAlembic:
    """Tests for Alembic invocation."""

    @patch("run_migrations.subprocess.run")
    def test_run_alembic_success(self, mock_run: MagicMock) -> None:
        """Successful Alembic runs should not exit the process."""
        mock_run.return_value = MagicMock(returncode=0)

        run_migrations.run_alembic()

        mock_run.assert_called_once_with(
            ["alembic", "upgrade", "head"],
            cwd="/app/shared",
            capture_output=False,
        )

    @patch("run_migrations.subprocess.run")
    def test_run_alembic_failure_exits(self, mock_run: MagicMock) -> None:
        """Failed Alembic runs should propagate the exit code."""
        mock_run.return_value = MagicMock(returncode=3)

        with pytest.raises(SystemExit) as exc_info:
            run_migrations.run_alembic()

        assert exc_info.value.code == 3


class TestRunSeedSql:
    """Tests for optional seed execution."""

    @patch("run_migrations.os.path.isfile", return_value=False)
    @patch("run_migrations.psycopg2.connect")
    def test_skips_when_seed_file_missing(
        self,
        mock_connect: MagicMock,
        mock_isfile: MagicMock,
    ) -> None:
        """Missing seed files should be treated as a non-error."""
        run_migrations.run_seed_sql()

        mock_isfile.assert_called_once_with("/app/seed-demo-data.sql")
        mock_connect.assert_not_called()

    @patch("run_migrations.os.path.isfile", return_value=True)
    @patch("run_migrations.open", new_callable=mock_open, read_data="SELECT 1;")
    @patch("run_migrations.psycopg2.connect")
    def test_executes_seed_file_when_present(
        self,
        mock_connect: MagicMock,
        mock_open_file: MagicMock,
        mock_isfile: MagicMock,
    ) -> None:
        """Present seed files should be executed against the sync connection."""
        mock_cursor = MagicMock()
        mock_connection = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_connection

        with patch.dict(
            "run_migrations.os.environ",
            {"DATABASE_URL": "postgresql+asyncpg://user:pass@db:5432/app"},
            clear=True,
        ):
            run_migrations.run_seed_sql()

        mock_isfile.assert_called_once_with("/app/seed-demo-data.sql")
        mock_open_file.assert_called_once_with("/app/seed-demo-data.sql")
        mock_connect.assert_called_once_with(
            host="db",
            port=5432,
            user="user",
            password="pass",
            dbname="app",
        )
        mock_cursor.execute.assert_called_once_with("SELECT 1;")
        mock_connection.close.assert_called_once()
