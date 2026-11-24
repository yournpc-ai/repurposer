"""Pytest launcher that safely loads the repository .env (tolerating unquoted angle brackets)
across both main checkouts and git worktrees, then invokes pytest in-process."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]


def _find_env_file() -> Path | None:
    for candidate in (REPO_ROOT / ".env", API_ROOT / ".env"):
        if candidate.is_file():
            return candidate
    # Support git worktrees where .env lives beside the common .git directory
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if common:
            common_root = (REPO_ROOT / common).resolve().parent
            env_file = common_root / ".env"
            if env_file.is_file():
                return env_file
    except Exception:
        pass
    return None


def main(argv: list[str] | None = None) -> int:
    env_file = _find_env_file()
    if env_file is not None:
        for key, value in dotenv_values(env_file).items():
            if value is not None:
                os.environ.setdefault(key, value)

    import pytest

    args = sys.argv[1:] if argv is None else argv
    return int(pytest.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
