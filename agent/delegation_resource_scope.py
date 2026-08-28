"""Fail-closed filesystem and forge scope for delegated child tool calls."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_DIRECT_PATH_KEYS = frozenset(
    {
        "cwd",
        "destination_path",
        "directory",
        "dst",
        "file_path",
        "new_path",
        "old_path",
        "path",
        "source_path",
        "src",
        "target_path",
        "workdir",
    }
)
_ABSOLUTE_PATH_RE = re.compile(r"(?<![:/])/(?!/)[^\s'\"`;|&<>)]*")
_ACCOUNT_WIDE_GH_RE = re.compile(
    r"(?:^|[;&|]\s*|\s)gh\s+(?:repo\s+list|search\s+repos|api\s+(?:--method\s+GET\s+)?(?:/)?(?:user/)?repos\b)"
)
_GH_REPOSITORY_RE = re.compile(r"(?:^|\s)--repo(?:sitory)?(?:=|\s+)(?P<repo>[^\s'\"]+)")
_PARENT_PATH_RE = re.compile(r"(?<![A-Za-z0-9_.])\.\.(?:/[A-Za-z0-9._-]+)*")
_SYSTEM_EXECUTABLE_PREFIXES = (Path("/bin"), Path("/sbin"), Path("/usr/bin"), Path("/usr/sbin"))
_ALWAYS_ALLOWED_PATHS = frozenset({Path("/dev/null")})


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _canonical(path: str | os.PathLike[str], cwd: Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve(strict=False)


def _is_prohibited_broad_root(path: Path) -> bool:
    home = Path.home().resolve()
    return path in {
        Path("/"),
        Path("/Users"),
        Path("/Volumes"),
        Path("/tmp"),
        Path("/private/tmp"),
        home,
    }


@dataclass(frozen=True)
class DelegationResourceScope:
    """Exact local roots and forge repositories admitted to one child."""

    allowed_roots: tuple[Path, ...]
    allowed_repositories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        roots = tuple(Path(root).expanduser().resolve(strict=False) for root in self.allowed_roots)
        if not roots:
            raise ValueError("delegation resource scope requires at least one allowed root")
        if any(_is_prohibited_broad_root(root) for root in roots):
            raise ValueError("delegation resource scope cannot admit a broad system or home root")
        repositories = tuple(repository.strip() for repository in self.allowed_repositories)
        if any(not repository or repository.count("/") != 1 for repository in repositories):
            raise ValueError("allowed repository identities must use owner/name form")
        object.__setattr__(self, "allowed_roots", roots)
        object.__setattr__(self, "allowed_repositories", repositories)


def _git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"repository preflight failed: git {' '.join(arguments)}: {detail}")
    return completed.stdout.strip()


def build_resource_scope(
    specification: Mapping[str, Any] | None,
    *,
    fallback_root: str | os.PathLike[str],
) -> DelegationResourceScope:
    """Validate an optional child lease against the live Git repository."""
    fallback = Path(fallback_root).expanduser().resolve(strict=False)
    if not specification:
        return DelegationResourceScope(allowed_roots=(fallback,))
    if not isinstance(specification, Mapping):
        raise ValueError("resource_scope must be an object")
    root_value = specification.get("workspace_root")
    if not isinstance(root_value, str) or not root_value.strip():
        raise ValueError("resource_scope.workspace_root is required")
    root = Path(root_value).expanduser().resolve(strict=False)
    if not root.is_dir():
        raise ValueError(f"resource_scope.workspace_root is not a directory: {root}")

    expected_remote = specification.get("repository_remote")
    required_refs = specification.get("required_refs") or {}
    if expected_remote is not None or required_refs:
        top_level = Path(_git_output(root, "rev-parse", "--show-toplevel")).resolve()
        if top_level != root:
            raise ValueError(
                f"resource_scope.workspace_root must be the canonical Git root: {top_level}"
            )
    if expected_remote is not None:
        if not isinstance(expected_remote, str) or not expected_remote.strip():
            raise ValueError("resource_scope.repository_remote must be a non-empty string")
        observed_remote = _git_output(root, "remote", "get-url", "origin")
        if observed_remote != expected_remote:
            raise ValueError(
                "resource_scope repository remote mismatch: "
                f"expected {expected_remote!r}, observed {observed_remote!r}"
            )
    if not isinstance(required_refs, Mapping):
        raise ValueError("resource_scope.required_refs must be an object of ref to commit OID")
    for ref, expected_oid in required_refs.items():
        if not isinstance(ref, str) or not ref or not isinstance(expected_oid, str):
            raise ValueError("resource_scope.required_refs must map non-empty refs to commit OIDs")
        observed_oid = _git_output(root, "rev-parse", f"{ref}^{{commit}}")
        if observed_oid != expected_oid:
            raise ValueError(
                f"resource_scope ref mismatch for {ref}: expected {expected_oid}, observed {observed_oid}"
            )

    raw_repositories = specification.get("allowed_repositories") or ()
    if not isinstance(raw_repositories, (list, tuple)):
        raise ValueError("resource_scope.allowed_repositories must be a list")
    return DelegationResourceScope(
        allowed_roots=(root,),
        allowed_repositories=tuple(str(item) for item in raw_repositories),
    )


def _path_block(scope: DelegationResourceScope, raw_path: str, cwd: Path) -> str | None:
    path = _canonical(raw_path, cwd)
    if path in _ALWAYS_ALLOWED_PATHS:
        return None
    if any(_is_within(path, root) for root in scope.allowed_roots):
        return None
    return f"path is outside delegated allowed roots: {path}"


def _terminal_block(
    scope: DelegationResourceScope, arguments: Mapping[str, Any], cwd: Path
) -> str | None:
    workdir = arguments.get("workdir")
    effective_cwd = _canonical(str(workdir), cwd) if workdir else cwd
    block = _path_block(scope, str(effective_cwd), cwd)
    if block:
        return f"terminal workdir {block}"
    command = arguments.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    if _ACCOUNT_WIDE_GH_RE.search(command):
        return "account-wide repository discovery is outside delegated forge scope"
    for match in _GH_REPOSITORY_RE.finditer(command):
        repository = match.group("repo").removesuffix(".git")
        if repository not in scope.allowed_repositories:
            return f"forge repository is outside delegated allowed repositories: {repository}"
    first_token = None
    try:
        tokens = shlex.split(command, posix=True)
        first_token = tokens[0] if tokens else None
    except ValueError:
        tokens = []
    for index, token in enumerate(tokens):
        candidate_token = None
        if token in {"cd", "pushd"} and index + 1 < len(tokens):
            candidate_token = tokens[index + 1]
        elif token == "-C" and index > 0 and tokens[index - 1] == "git" and index + 1 < len(tokens):
            candidate_token = tokens[index + 1]
        if candidate_token:
            if candidate_token.startswith(("~", "$HOME", "${HOME}")):
                return "terminal shell path outside delegated allowed roots: home expansion"
            block = _path_block(scope, candidate_token, effective_cwd)
            if block:
                return f"terminal shell path outside delegated allowed roots: {candidate_token}"
    for match in _PARENT_PATH_RE.finditer(command):
        candidate_token = match.group(0)
        block = _path_block(scope, candidate_token, effective_cwd)
        if block:
            return f"terminal shell path outside delegated allowed roots: {candidate_token}"
    for match in _ABSOLUTE_PATH_RE.finditer(command):
        raw = match.group(0).rstrip(",:")
        candidate = _canonical(raw, effective_cwd)
        if (
            first_token == raw
            and any(_is_within(candidate, prefix) for prefix in _SYSTEM_EXECUTABLE_PREFIXES)
        ):
            continue
        block = _path_block(scope, raw, effective_cwd)
        if block:
            return f"terminal command contains absolute path outside delegated allowed roots: {candidate}"
    return None


def evaluate_tool_call(
    scope: DelegationResourceScope,
    tool_name: str,
    arguments: Mapping[str, Any] | None,
    *,
    cwd: Path,
) -> str | None:
    """Return a block reason, or ``None`` when a child tool call is in scope."""

    args = arguments if isinstance(arguments, Mapping) else {}
    current = Path(cwd).expanduser().resolve(strict=False)
    if tool_name == "terminal":
        return _terminal_block(scope, args, current)
    for key, value in args.items():
        if str(key).lower() not in _DIRECT_PATH_KEYS:
            continue
        values = value if isinstance(value, list) else [value]
        for raw in values:
            if not isinstance(raw, str) or not raw:
                continue
            block = _path_block(scope, raw, current)
            if block:
                return block
    return None
