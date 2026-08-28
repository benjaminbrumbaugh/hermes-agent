from __future__ import annotations

from pathlib import Path

from agent.delegation_resource_scope import (
    DelegationResourceScope,
    build_resource_scope,
    evaluate_tool_call,
)
from agent.tool_executor import _delegation_resource_scope_block
from tools.delegate_tool import _prepare_task_resource_scopes


def _scope(tmp_path: Path) -> DelegationResourceScope:
    root = tmp_path / "repository"
    root.mkdir()
    return DelegationResourceScope(
        allowed_roots=(root.resolve(),),
        allowed_repositories=("example/repository",),
    )


def test_direct_file_target_outside_allowed_root_is_blocked(tmp_path: Path) -> None:
    scope = _scope(tmp_path)

    decision = evaluate_tool_call(
        scope,
        "search_files",
        {"path": str(tmp_path / "other")},
        cwd=scope.allowed_roots[0],
    )

    assert decision is not None
    assert "outside delegated allowed roots" in decision


def test_terminal_broad_home_walk_is_blocked(tmp_path: Path) -> None:
    scope = _scope(tmp_path)

    decision = evaluate_tool_call(
        scope,
        "terminal",
        {
            "command": "python3 -c \"import os; list(os.walk('/Users/example'))\"",
            "workdir": str(scope.allowed_roots[0]),
        },
        cwd=scope.allowed_roots[0],
    )

    assert decision is not None
    assert "absolute path outside delegated allowed roots" in decision


def test_terminal_command_scoped_to_allowed_root_is_allowed(tmp_path: Path) -> None:
    scope = _scope(tmp_path)
    target = scope.allowed_roots[0] / "src"

    decision = evaluate_tool_call(
        scope,
        "terminal",
        {"command": f"git -C '{target}' status --short", "workdir": str(scope.allowed_roots[0])},
        cwd=scope.allowed_roots[0],
    )

    assert decision is None


def test_terminal_relative_cd_cannot_escape_allowed_root(tmp_path: Path) -> None:
    scope = _scope(tmp_path)

    decision = evaluate_tool_call(
        scope,
        "terminal",
        {"command": "cd .. && find . -type f", "workdir": str(scope.allowed_roots[0])},
        cwd=scope.allowed_roots[0],
    )

    assert decision is not None
    assert "shell path outside delegated allowed roots" in decision


def test_account_wide_repository_discovery_is_blocked(tmp_path: Path) -> None:
    scope = _scope(tmp_path)

    decision = evaluate_tool_call(
        scope,
        "terminal",
        {"command": "gh repo list example --limit 100", "workdir": str(scope.allowed_roots[0])},
        cwd=scope.allowed_roots[0],
    )

    assert decision is not None
    assert "account-wide repository discovery" in decision


def test_tool_executor_applies_child_resource_scope(monkeypatch, tmp_path: Path) -> None:
    scope = _scope(tmp_path)
    agent = type("Agent", (), {"_delegation_resource_scope": scope})()
    monkeypatch.setattr(
        "tools.terminal_tool.get_session_cwd",
        lambda _task_id: str(scope.allowed_roots[0]),
    )

    decision = _delegation_resource_scope_block(
        agent,
        "search_files",
        {"path": str(tmp_path / "other")},
        "child-task",
    )

    assert decision is not None
    assert "outside delegated allowed roots" in decision


def test_resource_scope_preflight_binds_git_root_remote_and_ref(tmp_path: Path) -> None:
    import subprocess

    root = tmp_path / "repository"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    remote = "https://github.com/example/repository.git"
    subprocess.run(["git", "-C", str(root), "remote", "add", "origin", remote], check=True)
    oid = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()

    scope = build_resource_scope(
        {
            "workspace_root": str(root),
            "repository_remote": remote,
            "required_refs": {"HEAD": oid},
            "allowed_repositories": ["example/repository"],
        },
        fallback_root=tmp_path,
    )

    assert scope.allowed_roots == (root.resolve(),)
    assert scope.allowed_repositories == ("example/repository",)


def test_required_child_scope_rejects_task_without_lease(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HERMES_REQUIRE_DELEGATION_RESOURCE_SCOPE", "1")

    scopes, error = _prepare_task_resource_scopes(
        [{"goal": "Inspect the repository"}],
        fallback_root=str(tmp_path / "repository"),
    )

    assert scopes == []
    assert error is not None
    assert "resource_scope is required" in error
