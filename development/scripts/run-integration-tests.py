"""Run the integration test suite from a portable project-root location."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def find_python(project_root: Path) -> str:
    """Return the project virtualenv Python when present, otherwise this Python."""
    windows_python = project_root / ".venv" / "Scripts" / "python.exe"
    posix_python = project_root / ".venv" / "bin" / "python"

    if windows_python.exists():
        return str(windows_python)
    if posix_python.exists():
        return str(posix_python)
    return sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://localhost:8088",
        help="Base URL for the running app stack.",
    )
    parser.add_argument(
        "--user-db-url",
        default="http://localhost:8001",
        help="Direct user DB service URL used by some integration tests.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("test-results/integration-results.txt"),
        help="File to write combined stdout/stderr test output to.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Extra arguments passed to pytest after --.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    python = find_python(project_root)
    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    env = {
        **os.environ,
        "INTEGRATION_BASE_URL": args.base_url,
        "USER_DB_SERVICE_URL": args.user_db_url,
    }

    command = [python, "-m", "pytest", "tests/integration/", "--tb=short", "-v"]
    command.extend(pytest_args)

    result = subprocess.run(  # noqa: S603
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    output_path = project_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        result.stdout
        + ("\n--- STDERR ---\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )

    print(f"Exit code: {result.returncode}")
    print(f"Output written to: {output_path.relative_to(project_root)}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())