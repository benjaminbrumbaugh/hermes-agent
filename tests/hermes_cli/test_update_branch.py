"""Update targets follow the checkout's nominated origin branch."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace


def _git(repo, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo_with_update_branch(tmp_path, branch: str = "main_plus_our_prs"):
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-b", branch)
    _git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "--allow-empty", "-m", "initial")
    _git(repo, "remote", "add", "origin", "https://github.com/example/hermes-agent.git")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{branch}")
    return repo


def test_implicit_update_branch_follows_origin_head_and_explicit_branch_wins(tmp_path, monkeypatch):
    from hermes_cli import main
    from hermes_cli.main_install_repair import _resolve_update_branch

    repo = _repo_with_update_branch(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", repo)

    assert _resolve_update_branch(SimpleNamespace(branch=None)) == "main_plus_our_prs"
    assert _resolve_update_branch(SimpleNamespace(branch=" release/test ")) == "release/test"


def test_passive_check_queries_fork_update_branch_and_keys_cache_by_it(tmp_path, monkeypatch):
    import hermes_cli.banner as banner

    repo = _repo_with_update_branch(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_REVISION", raising=False)
    monkeypatch.setattr(banner, "_resolve_repo_dir", lambda: repo)
    monkeypatch.setattr("hermes_cli.config.detect_install_method", lambda root: "git")
    monkeypatch.setattr("hermes_cli.config.get_project_root", lambda: repo)

    tip = "b" * 40
    branch_tip_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        banner,
        "_github_branch_tip",
        lambda slug, branch: branch_tip_calls.append((slug, branch)) or tip,
    )
    monkeypatch.setattr(banner, "_github_compare_behind", lambda current, target: 4)

    assert banner.check_for_updates() == 4
    assert branch_tip_calls == [("example/hermes-agent", "main_plus_our_prs")]

    cached = banner._read_json(home / ".update_check")
    assert cached is not None
    assert cached["branch"] == "main_plus_our_prs"
    assert cached["target"] == tip
