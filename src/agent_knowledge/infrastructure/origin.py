"""Resolve explicit workspace Git context to a verified durable checkout identity."""

import os
import shutil
import subprocess
from pathlib import Path

from agent_knowledge.domain.validation import ValidationError, read_relative_path

from .configuration import Workspace
from .errors import AdapterError
from .filesystem import check_directory, read_bytes


def resolve_project(workspace: Workspace) -> str | None:
    """Return the main checkout's code-root-relative path, or no Git association.

    Config location determines Git context. Linked worktrees use the verified
    main checkout behind Git's common directory, so temporary checkout names do
    not become inbox identities. Bare, relocated-metadata and submodule layouts
    are rejected rather than inferring an unverified durable location.
    """
    storage = workspace.signal_storage
    if storage is None:
        raise ValidationError(
            "signal-storage-missing", "workspace.signal_storage", "Configure signal storage first."
        )
    checkout = _resolve_checkout(workspace.path.parent)
    if checkout is None:
        return None
    _, primary = checkout
    if not primary.is_relative_to(storage.code_root) or primary == storage.code_root:
        raise AdapterError(
            "origin-outside-code-root",
            str(primary),
            "The durable checkout must be below the configured code_root.",
            exit_code=2,
        )
    return read_relative_path(
        primary.relative_to(storage.code_root).as_posix(), "origin.project_path"
    )


def check_durable_scaffold(workspace: Workspace) -> None:
    """Reject capture destinations inside linked worktrees without remapping them.

    Existing non-Git directories and primary checkout subdirectories are valid.
    This check does not create directories and does not restrict the destination
    to code_root, which belongs only to the originating project identity.
    """
    storage = workspace.signal_storage
    if storage is None:
        raise ValidationError(
            "signal-storage-missing", "workspace.signal_storage", "Configure signal storage first."
        )
    checkout = _resolve_checkout(storage.scaffold_root)
    if checkout is not None and checkout[0] != checkout[1]:
        raise AdapterError(
            "temporary-signal-scaffold",
            str(storage.scaffold_root),
            "Signal storage is inside a linked worktree. Configure a primary checkout "
            "or a durable non-Git directory as scaffold_root.",
            exit_code=2,
        )


def _resolve_checkout(context: Path) -> tuple[Path, Path] | None:
    """Verify the current checkout top-level and its durable primary checkout."""
    check_directory(context)
    executable = _git_executable()
    bare = _query(executable, context, "--is-bare-repository", allow_absent=True)
    if bare is None:
        return None
    if bare == "true":
        raise AdapterError(
            "origin-bare", str(context), "A bare repository has no project checkout.", exit_code=2
        )
    if bare != "false" or _query(executable, context, "--is-inside-work-tree") != "true":
        raise _unverifiable(context)

    top = _git_path(executable, context, "--show-toplevel")
    git_dir = _git_path(executable, context, "--absolute-git-dir")
    common = _git_path(executable, context, "--git-common-dir")
    if not context.is_relative_to(top):
        raise _unverifiable(context)
    if common.name != ".git":
        raise _unsupported(context)
    primary = common.parent
    if git_dir == common:
        if top != primary:
            raise _unsupported(context)
    else:
        if git_dir.parent != common / "worktrees":
            raise _unsupported(context)
        _verify_backlink(top, git_dir)

    # A conventional-looking path is only a candidate until Git verifies all
    # three identities from the candidate itself. core.worktree redirects and
    # missing/moved primary checkouts must not silently change the project.
    if (
        _query(executable, primary, "--is-bare-repository") != "false"
        or _git_path(executable, primary, "--show-toplevel") != primary
        or _git_path(executable, primary, "--absolute-git-dir") != common
        or _git_path(executable, primary, "--git-common-dir") != common
    ):
        raise _unverifiable(context)
    return top, primary


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        executable = shutil.which("git", path=f"{os.defpath}:/opt/homebrew/bin:/usr/local/bin")
    if executable is None:
        raise AdapterError(
            "git-unavailable", "git", "Install Git to resolve the originating project checkout."
        )
    return executable


def _query(executable: str, context: Path, flag: str, *, allow_absent: bool = False) -> str | None:
    try:
        result = subprocess.run(
            [executable, "-c", "core.fsmonitor=false", "-C", str(context), "rev-parse", flag],
            env={
                "PATH": os.defpath,
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_TERMINAL_PROMPT": "0",
            },
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise _unverifiable(context) from error
    if result.returncode:
        if (
            allow_absent
            and result.returncode == 128
            and _reports_no_repository(result.stderr)
            and not _has_git_marker(context)
        ):
            return None
        raise _unverifiable(context)
    try:
        value = result.stdout.decode("utf-8").removesuffix("\n")
    except UnicodeDecodeError as error:
        raise _unverifiable(context) from error
    if not value or any(character in value for character in ("\n", "\r", "\x00")):
        raise _unverifiable(context)
    return value


def _git_path(executable: str, context: Path, flag: str) -> Path:
    value = _query(executable, context, flag)
    if value is None:
        raise _unverifiable(context)
    path = Path(value)
    if not path.is_absolute():
        path = context / path
    check_directory(path)
    return path.resolve()


def _verify_backlink(top: Path, git_dir: Path) -> None:
    try:
        backlink = read_bytes(git_dir / "gitdir", max_bytes=65536).decode("utf-8")
    except UnicodeDecodeError as error:
        raise _unverifiable(top) from error
    path = Path(backlink.removesuffix("\n"))
    if not path.is_absolute():
        path = git_dir / path
    if Path(os.path.normpath(path)) != top / ".git":
        raise _unverifiable(top)
    # Git must be discovering an actual registered pointer file, not an alias
    # copied from another worktree or introduced through a symlink.
    read_bytes(path, max_bytes=65536)


def _reports_no_repository(message: bytes) -> bool:
    return message == b"fatal: not a git repository (or any of the parent directories): .git\n" or (
        message.startswith(b"fatal: not a git repository (or any parent up to mount point ")
        and message.endswith(
            b")\nStopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).\n"
        )
    )


def _has_git_marker(context: Path) -> bool:
    for parent in (context, *context.parents):
        try:
            (parent / ".git").lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise _unverifiable(context) from error
        return True
    return False


def _unverifiable(context: Path) -> AdapterError:
    return AdapterError(
        "origin-unverifiable",
        str(context),
        "Cannot verify the originating Git checkout and its durable primary checkout.",
    )


def _unsupported(context: Path) -> AdapterError:
    return AdapterError(
        "origin-unsupported",
        str(context),
        "Origin requires a standard checkout or linked worktree; separate Git directories "
        "and submodules are not supported.",
        exit_code=2,
    )
