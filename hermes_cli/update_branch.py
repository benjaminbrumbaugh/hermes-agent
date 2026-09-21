"""Resolve the implicit Git branch used by Hermes update surfaces."""

from __future__ import annotations

import subprocess
from pathlib import Path


def default_update_branch(repo_dir: Path | str, fallback: str = "main") -> str:
    """Return the branch nominated by ``origin/HEAD``, or *fallback* when unavailable.

    Install checkouts normally point ``origin/HEAD`` at ``origin/main``. Forks may
    deliberately point it at a maintained distribution branch; honoring that
    symbolic ref keeps update checks and applies aligned without treating an
    arbitrary checked-out feature branch as the update target.
    """
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return fallback

    prefix = "refs/remotes/origin/"
    ref = result.stdout.strip()
    branch = ref[len(prefix):] if result.returncode == 0 and ref.startswith(prefix) else ""
    return branch or fallback
