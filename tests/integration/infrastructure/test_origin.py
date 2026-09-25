"""Verify durable signal origins using isolated real Git checkouts."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.origin import check_durable_scaffold, resolve_project
from tests.factories import catalog_data
from tests.unit.domain.test_configuration import workspace_data

GIT = shutil.which("git")


def git(path: Path, *arguments: str) -> str:
    assert GIT is not None, "Origin integration tests require Git."
    result = subprocess.run(
        [GIT, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *arguments],
        cwd=path,
        env={"PATH": os.defpath, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def checkout(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "--initial-branch=main")
    git(path, "commit", "--allow-empty", "-m", "Fixture")
    return path


def configured(
    tmp_path: Path,
    directory: Path,
    *,
    code_root: Path | None = None,
    scaffold_root: Path | None = None,
) -> Workspace:
    directory.mkdir(parents=True, exist_ok=True)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(json.dumps(catalog_data()))
    path = directory / "knowledge-workspace.yaml"
    path.write_text(
        json.dumps(
            workspace_data(
                sources=[
                    {
                        "id": "knowledge",
                        "root": str(tmp_path / "knowledge"),
                        "catalog": str(catalog),
                    }
                ],
                signal_storage={
                    "scaffold_root": str(scaffold_root or tmp_path / "scaffold"),
                    "code_root": str(code_root or tmp_path / "code"),
                },
            )
        )
    )
    return load_workspace(path)


def test_preserves_nested_project_path_and_ignores_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = checkout(tmp_path / "code/products/orders-api")
    workspace = configured(tmp_path, project / "tooling")
    other = checkout(tmp_path / "unrelated")
    monkeypatch.chdir(other)
    assert resolve_project(workspace) == "products/orders-api"


def test_equal_project_basenames_remain_distinct(tmp_path: Path) -> None:
    first = checkout(tmp_path / "code/products/api")
    second = checkout(tmp_path / "code/platform/api")
    assert resolve_project(configured(tmp_path, first)) == "products/api"
    assert resolve_project(configured(tmp_path, second)) == "platform/api"


def test_linked_worktree_outside_code_root_uses_durable_primary(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/products/orders-api")
    worktree = tmp_path / "temporary/worktree"
    git(primary, "worktree", "add", "--detach", str(worktree))
    assert resolve_project(configured(tmp_path, worktree / "nested")) == "products/orders-api"


def test_two_linked_worktrees_share_only_their_durable_project_identity(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/products/orders-api")
    identities = []
    for name in ("one", "two"):
        worktree = tmp_path / "temporary" / name
        git(primary, "worktree", "add", "--detach", str(worktree))
        identities.append(resolve_project(configured(tmp_path, worktree)))
    assert identities == ["products/orders-api", "products/orders-api"]


def test_relative_linked_worktree_metadata_preserves_primary_identity(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/orders-api")
    worktree = tmp_path / "temporary/worktree"
    git(primary, "worktree", "add", "--detach", str(worktree))
    git_dir = Path(git(worktree, "rev-parse", "--absolute-git-dir"))
    (worktree / ".git").write_text(f"gitdir: {os.path.relpath(git_dir, worktree)}\n")
    (git_dir / "gitdir").write_text(f"{os.path.relpath(worktree / '.git', git_dir)}\n")
    assert resolve_project(configured(tmp_path, worktree)) == "orders-api"


def test_git_environment_and_global_config_cannot_replace_explicit_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = checkout(tmp_path / "code/orders-api")
    other = checkout(tmp_path / "other")
    workspace = configured(tmp_path, primary)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".gitconfig").write_text(f"[core]\nworktree = {other}\n")
    for key, value in {
        "HOME": str(fake_home),
        "GIT_DIR": str(other / ".git"),
        "GIT_WORK_TREE": str(other),
        "GIT_COMMON_DIR": str(other / ".git"),
        "GIT_CONFIG_PARAMETERS": "'core.bare=true'",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.bare",
        "GIT_CONFIG_VALUE_0": "true",
        "GIT_CEILING_DIRECTORIES": str(primary),
    }.items():
        monkeypatch.setenv(key, value)
    assert resolve_project(workspace) == "orders-api"


def test_runs_without_caller_environment_or_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = checkout(tmp_path / "code/orders-api")
    workspace = configured(tmp_path, project)
    monkeypatch.setattr(os, "environ", {})
    assert resolve_project(workspace) == "orders-api"


def test_non_git_workspace_returns_no_project_even_with_git_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = checkout(tmp_path / "code/elsewhere")
    workspace = configured(tmp_path, tmp_path / "non-project")
    monkeypatch.chdir(elsewhere)
    assert resolve_project(workspace) is None


@pytest.mark.parametrize("broken_metadata", [False, True])
def test_mount_boundary_absence_is_distinct_from_broken_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken_metadata: bool
) -> None:
    workspace = configured(tmp_path, tmp_path / "non-project")
    if broken_metadata:
        (workspace.path.parent / ".git").mkdir()

    def mount_boundary(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            "git",
            128,
            stdout=b"",
            stderr=(
                b"fatal: not a git repository (or any parent up to mount point /Volumes)\n"
                b"Stopping at filesystem boundary (GIT_DISCOVERY_ACROSS_FILESYSTEM not set).\n"
            ),
        )

    monkeypatch.setattr(subprocess, "run", mount_boundary)
    if broken_metadata:
        with pytest.raises(AdapterError) as error:
            resolve_project(workspace)
        assert error.value.code == "origin-unverifiable"
    else:
        assert resolve_project(workspace) is None


def test_bare_repository_is_not_a_project(tmp_path: Path) -> None:
    bare = tmp_path / "code/bare"
    bare.mkdir(parents=True)
    git(bare, "init", "--bare")
    with pytest.raises(AdapterError) as error:
        resolve_project(configured(tmp_path, bare))
    assert error.value.code == "origin-bare"
    assert error.value.exit_code == 2


@pytest.mark.parametrize("linked", [False, True])
def test_primary_outside_code_root_is_rejected(tmp_path: Path, linked: bool) -> None:
    primary = checkout(tmp_path / "outside/orders-api")
    location = primary
    if linked:
        location = tmp_path / "code/temporary"
        git(primary, "worktree", "add", "--detach", str(location))
    with pytest.raises(AdapterError) as error:
        resolve_project(configured(tmp_path, location))
    assert error.value.code == "origin-outside-code-root"
    assert error.value.exit_code == 2


def test_code_root_itself_cannot_be_a_relative_project_bucket(tmp_path: Path) -> None:
    project = checkout(tmp_path / "code")
    with pytest.raises(AdapterError) as error:
        resolve_project(configured(tmp_path, project))
    assert error.value.code == "origin-outside-code-root"
    assert error.value.exit_code == 2


@pytest.mark.parametrize("metadata_name", ["metadata", ".git"])
def test_separate_git_directory_is_explicitly_unsupported(
    tmp_path: Path, metadata_name: str
) -> None:
    project = tmp_path / "code/orders-api"
    project.mkdir(parents=True)
    git(project, "init", "--separate-git-dir", str(tmp_path / metadata_name))
    with pytest.raises(AdapterError) as error:
        resolve_project(configured(tmp_path, project))
    assert error.value.code == "origin-unsupported"
    assert error.value.exit_code == 2


def test_unregistered_copy_of_linked_worktree_pointer_is_unverifiable(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/orders-api")
    linked = tmp_path / "linked"
    git(primary, "worktree", "add", "--detach", str(linked))
    copied = tmp_path / "copied"
    copied.mkdir()
    (copied / ".git").write_bytes((linked / ".git").read_bytes())
    with pytest.raises(AdapterError) as error:
        resolve_project(configured(tmp_path, copied))
    assert error.value.code == "origin-unverifiable"


def test_submodule_is_explicitly_unsupported(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/primary")
    module = checkout(tmp_path / "module-source")
    git(primary, "-c", "protocol.file.allow=always", "submodule", "add", str(module), "child")
    with pytest.raises(AdapterError) as error:
        resolve_project(configured(tmp_path, primary / "child"))
    assert error.value.code == "origin-unsupported"
    assert error.value.exit_code == 2


def test_dangling_linked_worktree_cannot_become_non_project(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/orders-api")
    worktree = tmp_path / "temporary"
    git(primary, "worktree", "add", "--detach", str(worktree))
    workspace = configured(tmp_path, worktree)
    shutil.rmtree(primary)
    with pytest.raises(AdapterError) as error:
        resolve_project(workspace)
    assert error.value.code == "origin-unverifiable"


@pytest.mark.parametrize("marker", ["directory", "file"])
def test_broken_git_metadata_is_an_error_not_no_project(tmp_path: Path, marker: str) -> None:
    project = tmp_path / "code/orders-api"
    workspace = configured(tmp_path, project)
    if marker == "directory":
        (project / ".git").mkdir()
    else:
        (project / ".git").write_text("gitdir: /not-present/origin-metadata\n")
    with pytest.raises(AdapterError) as error:
        resolve_project(workspace)
    assert error.value.code == "origin-unverifiable"


def test_core_worktree_redirect_does_not_guess_primary(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/orders-api")
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    workspace = configured(tmp_path, primary)
    git(primary, "config", "core.worktree", str(redirected))
    with pytest.raises(AdapterError) as error:
        resolve_project(workspace)
    assert error.value.code == "origin-unverifiable"


def test_git_directory_symlink_does_not_establish_a_project(tmp_path: Path) -> None:
    primary = checkout(tmp_path / "code/orders-api")
    metadata = tmp_path / "metadata"
    (primary / ".git").rename(metadata)
    (primary / ".git").symlink_to(metadata, target_is_directory=True)
    with pytest.raises(AdapterError):
        resolve_project(configured(tmp_path, primary))


def test_missing_git_executable_is_explicit_setup_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = configured(tmp_path, tmp_path / "non-project")
    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: None)
    with pytest.raises(AdapterError) as error:
        resolve_project(workspace)
    assert error.value.code == "git-unavailable"


def test_git_timeout_is_explicit_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = checkout(tmp_path / "code/orders-api")
    workspace = configured(tmp_path, project)

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("git", 10)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(AdapterError) as error:
        resolve_project(workspace)
    assert error.value.code == "origin-unverifiable"


def test_directory_only_scaffold_is_valid_without_project_git_context(tmp_path: Path) -> None:
    scaffold = tmp_path / "scaffold"
    scaffold.mkdir()
    workspace = configured(tmp_path, tmp_path / "non-project")
    assert check_durable_scaffold(workspace) is None
    assert list(scaffold.iterdir()) == []


@pytest.mark.parametrize("nested", [False, True])
def test_primary_scaffold_or_subdirectory_can_be_outside_code_root(
    tmp_path: Path, nested: bool
) -> None:
    primary = checkout(tmp_path / "separate/scaffold")
    scaffold = primary / "data" if nested else primary
    scaffold.mkdir(exist_ok=True)
    workspace = configured(tmp_path, tmp_path / "non-project", scaffold_root=scaffold)
    assert check_durable_scaffold(workspace) is None
    assert not (scaffold / "ai").exists()


@pytest.mark.parametrize("inside_primary", [False, True])
def test_linked_scaffold_destination_is_rejected_without_creating_or_remapping(
    tmp_path: Path, inside_primary: bool
) -> None:
    primary = checkout(tmp_path / "durable/scaffold")
    linked = primary / "temporary" if inside_primary else tmp_path / "temporary"
    git(primary, "worktree", "add", "--detach", str(linked))
    scaffold = linked / "data"
    scaffold.mkdir()
    marker = scaffold / "existing.md"
    marker.write_text("Keep this existing input.\n")
    workspace = configured(tmp_path, tmp_path / "non-project", scaffold_root=scaffold)
    before = sorted(str(path) for path in tmp_path.rglob("*"))
    with pytest.raises(AdapterError) as error:
        check_durable_scaffold(workspace)
    assert error.value.code == "temporary-signal-scaffold"
    assert error.value.exit_code == 2
    assert sorted(str(path) for path in tmp_path.rglob("*")) == before
    assert marker.read_text() == "Keep this existing input.\n"
    assert workspace.signal_storage is not None
    assert workspace.signal_storage.scaffold_root == scaffold


def test_malformed_scaffold_git_metadata_does_not_become_directory_only(tmp_path: Path) -> None:
    scaffold = tmp_path / "scaffold"
    scaffold.mkdir()
    (scaffold / ".git").write_text("gitdir: /missing/scaffold-metadata\n")
    workspace = configured(tmp_path, tmp_path / "non-project")
    with pytest.raises(AdapterError) as error:
        check_durable_scaffold(workspace)
    assert error.value.code == "origin-unverifiable"


def test_bare_scaffold_has_no_durable_checkout(tmp_path: Path) -> None:
    scaffold = tmp_path / "scaffold"
    scaffold.mkdir()
    git(scaffold, "init", "--bare")
    workspace = configured(tmp_path, tmp_path / "non-project")
    with pytest.raises(AdapterError) as error:
        check_durable_scaffold(workspace)
    assert error.value.code == "origin-bare"
    assert error.value.exit_code == 2


def test_separate_scaffold_git_directory_remains_explicitly_unsupported(tmp_path: Path) -> None:
    scaffold = tmp_path / "scaffold"
    scaffold.mkdir()
    git(scaffold, "init", "--separate-git-dir", str(tmp_path / "metadata"))
    workspace = configured(tmp_path, tmp_path / "non-project")
    with pytest.raises(AdapterError) as error:
        check_durable_scaffold(workspace)
    assert error.value.code == "origin-unsupported"
    assert error.value.exit_code == 2


def test_missing_scaffold_is_not_created_by_durability_check(tmp_path: Path) -> None:
    workspace = configured(tmp_path, tmp_path / "non-project")
    with pytest.raises(AdapterError) as error:
        check_durable_scaffold(workspace)
    assert error.value.code == "directory-missing"
    assert not (tmp_path / "scaffold").exists()
