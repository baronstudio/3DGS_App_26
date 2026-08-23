"""Application identity: name, version, commit.

The version number is derived from the repository itself — the date of the
commit the app is running, `YYYY.MM.DD`, which is what the GitHub history
shows for that commit. Deriving it from the local clone rather than querying
github.com keeps it honest: it describes the code actually running, not the
tip of the remote, and it works with no network.

Read once per process: the metadata cannot change under a running server
without a restart, and a subprocess per page load would be pure waste.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

APP_NAME = "3DGS Pipeline App"

# backend/api/routes/version.py -> the app root, which is inside the repo.
_APP_ROOT = Path(__file__).resolve().parents[3]

_cache: dict | None = None


def _git(*args: str) -> str | None:
    """Run a git command in the app directory, or None if git/the repo is absent."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=_APP_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _commit_url(remote: str | None, sha: str | None) -> str | None:
    """https URL of the commit on GitHub, from whatever form `origin` takes."""
    if not remote or not sha:
        return None
    m = re.match(r"^(?:https://github\.com/|git@github\.com:)(.+?)(?:\.git)?/?$", remote)
    if not m:
        return None
    return f"https://github.com/{m.group(1)}/commit/{sha}"


def _read_version() -> dict:
    sha = _git("rev-parse", "HEAD")
    short = _git("rev-parse", "--short=8", "HEAD")
    date = _git("log", "-1", "--date=format:%Y.%m.%d", "--format=%cd")
    iso = _git("log", "-1", "--format=%cI")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    remote = _git("config", "--get", "remote.origin.url")

    return {
        "name": APP_NAME,
        # No git, no version: saying "0.0.0" would be inventing one.
        "version": date,
        "commit": sha,
        "commit_short": short,
        "commit_date": iso,
        "branch": branch,
        "commit_url": _commit_url(remote, sha),
    }


@router.get("/")
def read_version() -> dict:
    global _cache
    if _cache is None:
        _cache = _read_version()
    return _cache
