"""Exercise explicit workspace roots and bounded file access with temporary files."""

import json
import os
from pathlib import Path

import pytest

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import load_workspace, validate_signal_storage
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import (
    check_directory,
    open_directory,
    read_bytes,
    resolve_document_path,
    resolve_path,
)
from tests.factories import catalog_data
from tests.unit.domain.test_configuration import workspace_data


def write_workspace(tmp_path: Path, **overrides: object) -> Path:
    config_dir = tmp_path / "consumer"
    config_dir.mkdir(exist_ok=True)
    (tmp_path / "catalog.yaml").write_text(json.dumps(catalog_data()))
    path = config_dir / "workspace.yaml"
    path.write_text(json.dumps(workspace_data(**overrides)))
    return path


def test_loads_catalog_without_requiring_source_or_inbox_availability(tmp_path: Path) -> None:
    path = write_workspace(
        tmp_path, signal_storage={"scaffold_root": "../scaffold", "code_root": ".."}
    )
    workspace = load_workspace(path)
    assert workspace.path == path.resolve()
    assert workspace.sources[0].root == (tmp_path / "knowledge").resolve()
    assert not workspace.sources[0].root.exists()
    assert workspace.signal_storage.signal_root == (tmp_path / "scaffold/ai/signals").resolve()
    assert validate_signal_storage(workspace) == workspace.signal_storage
    assert workspace.catalog.source_ids == ("knowledge",)


def test_paths_resolve_against_config_directory_not_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_workspace(tmp_path)
    before = load_workspace(path)
    monkeypatch.chdir(tmp_path.parent)
    assert load_workspace(path) == before
    assert resolve_path("../knowledge", base=path.parent) == before.sources[0].root


def test_symlinked_explicit_config_uses_target_file_directory(tmp_path: Path) -> None:
    path = write_workspace(tmp_path)
    alias = tmp_path / "workspace-link.yaml"
    alias.symlink_to(path)
    assert load_workspace(alias) == load_workspace(path)


def test_combines_two_source_catalogs_and_coalesces_identical_ids(tmp_path: Path) -> None:
    path = write_workspace(
        tmp_path,
        sources=[
            {"id": "first", "root": "../first", "catalog": "../catalog.yaml"},
            {"id": "second", "root": "../second", "catalog": "../catalog-two.yaml"},
        ],
    )
    (tmp_path / "catalog-two.yaml").write_text(json.dumps(catalog_data()))
    workspace = load_workspace(path)
    assert workspace.catalog.source_ids == ("first", "second")
    assert all(record.source_ids == ("first", "second") for record in workspace.catalog.records)


def test_accepts_valid_empty_corpus_and_catalog(tmp_path: Path) -> None:
    path = write_workspace(tmp_path, applicable_scopes=[])
    data = {key: {} for key in catalog_data() if key != "schema_version"}
    data["schema_version"] = "knowledge-catalog.v1"
    (tmp_path / "catalog.yaml").write_text(json.dumps(data))
    (tmp_path / "knowledge").mkdir()
    workspace = load_workspace(path)
    assert workspace.catalog.records == ()
    check_directory(workspace.sources[0].root)


def test_unknown_configured_scope_fails_without_inferred_workspace_membership(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="Unknown scopes"):
        load_workspace(write_workspace(tmp_path, applicable_scopes=["repo:missing"]))


def test_missing_catalog_is_error_instead_of_empty_vocabulary(tmp_path: Path) -> None:
    path = write_workspace(tmp_path)
    (tmp_path / "catalog.yaml").unlink()
    with pytest.raises(AdapterError) as error:
        load_workspace(path)
    assert error.value.code == "file-missing"
    assert error.value.exit_code == 2


@pytest.mark.parametrize("second_root", ["../knowledge", "../knowledge/nested", ".."])
def test_source_overlap_is_rejected_even_when_paths_do_not_exist(
    tmp_path: Path, second_root: str
) -> None:
    path = write_workspace(
        tmp_path,
        sources=[
            {"id": "first", "root": "../knowledge", "catalog": "../catalog.yaml"},
            {"id": "second", "root": second_root, "catalog": "../catalog.yaml"},
        ],
    )
    with pytest.raises(ValidationError) as error:
        load_workspace(path)
    assert error.value.code == "source-root-overlap"


def test_source_alias_overlap_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "knowledge", target_is_directory=True)
    path = write_workspace(
        tmp_path,
        sources=[
            {"id": "first", "root": "../knowledge", "catalog": "../catalog.yaml"},
            {"id": "second", "root": "../alias", "catalog": "../catalog.yaml"},
        ],
    )
    with pytest.raises(ValidationError, match="overlap"):
        load_workspace(path)


@pytest.mark.parametrize(
    "root", ["../scaffold/ai/signals", "../scaffold/ai", "../scaffold/ai/signals/knowledge"]
)
def test_signal_overlap_is_reported_separately_from_readable_configuration(
    tmp_path: Path, root: str
) -> None:
    path = write_workspace(
        tmp_path,
        sources=[{"id": "knowledge", "root": root, "catalog": "../catalog.yaml"}],
        signal_storage={"scaffold_root": "../scaffold", "code_root": ".."},
    )
    workspace = load_workspace(path)
    assert workspace.catalog.records
    with pytest.raises(ValidationError) as error:
        validate_signal_storage(workspace)
    assert error.value.code == "signal-root-overlap"


def test_signal_symlink_into_canonical_root_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "scaffold/ai").mkdir(parents=True)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "scaffold/ai/signals").symlink_to(tmp_path / "knowledge", target_is_directory=True)
    path = write_workspace(
        tmp_path, signal_storage={"scaffold_root": "../scaffold", "code_root": ".."}
    )
    with pytest.raises(ValidationError, match="overlap"):
        validate_signal_storage(load_workspace(path))


def test_fingerprint_tracks_config_catalog_bytes_and_resolved_identity(tmp_path: Path) -> None:
    path = write_workspace(tmp_path)
    first = load_workspace(path).fingerprint
    with (tmp_path / "catalog.yaml").open("a") as output:
        output.write("\n")
    assert load_workspace(path).fingerprint != first
    second = load_workspace(path).fingerprint
    with path.open("a") as output:
        output.write("\n")
    assert load_workspace(path).fingerprint != second


def test_bounded_regular_file_reader_preserves_exact_bytes(tmp_path: Path) -> None:
    path = tmp_path / "file.md"
    path.write_bytes(b"a\r\nb\x00")
    assert read_bytes(path, max_bytes=5) == b"a\r\nb\x00"
    with pytest.raises(AdapterError) as error:
        read_bytes(path, max_bytes=4)
    assert error.value.code == "file-too-large"
    assert error.value.exit_code == 2


@pytest.mark.parametrize("kind", ["directory", "fifo", "symlink"])
def test_reader_rejects_non_regular_file_and_symlink_without_hanging(
    tmp_path: Path, kind: str
) -> None:
    path = tmp_path / "unsafe"
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        target = tmp_path / "target"
        target.write_text("hidden")
        path.symlink_to(target)
    with pytest.raises(AdapterError):
        read_bytes(path, max_bytes=100)


def test_reader_and_directory_guard_reject_internal_symlink_traversal(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "file").write_text("hidden")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(AdapterError):
        read_bytes(alias / "file", max_bytes=100)
    with pytest.raises(AdapterError):
        check_directory(alias)


def test_open_directory_pins_target_for_relative_operations(tmp_path: Path) -> None:
    with open_directory(tmp_path) as directory:
        fd = os.open("probe", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        os.close(fd)
        os.unlink("probe", dir_fd=directory)
    assert not (tmp_path / "probe").exists()


def test_document_resolution_rejects_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (root / "alias.md").symlink_to(outside)
    assert resolve_document_path(root, "runbooks/index.md") == root / "runbooks/index.md"
    for value in ["../outside.md", "/outside.md", "alias.md"]:
        with pytest.raises(ValidationError):
            resolve_document_path(root, value)


def test_signal_root_cannot_redirect_outside_scaffold_even_when_not_canonical(
    tmp_path: Path,
) -> None:
    (tmp_path / "scaffold/ai").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "scaffold/ai/signals").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    workspace = load_workspace(
        write_workspace(
            tmp_path, signal_storage={"scaffold_root": "../scaffold", "code_root": ".."}
        )
    )
    with pytest.raises(ValidationError) as error:
        validate_signal_storage(workspace)
    assert error.value.code == "unsafe-signal-path"


def test_file_replacement_during_read_is_diagnosed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"before")
    original_read = os.read
    changed = False

    def replace_during_read(descriptor: int, length: int) -> bytes:
        nonlocal changed
        if not changed:
            changed = True
            path.unlink()
            path.write_bytes(b"after!")
        return original_read(descriptor, length)

    monkeypatch.setattr(os, "read", replace_during_read)
    with pytest.raises(AdapterError) as error:
        read_bytes(path, max_bytes=20)
    assert error.value.code == "file-changed"


def test_file_growth_cannot_escape_byte_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"short")
    original_read = os.read
    changed = False

    def grow_during_read(descriptor: int, length: int) -> bytes:
        nonlocal changed
        if not changed:
            changed = True
            path.write_bytes(b"x" * 200)
        return original_read(descriptor, length)

    monkeypatch.setattr(os, "read", grow_during_read)
    with pytest.raises(AdapterError) as error:
        read_bytes(path, max_bytes=20)
    assert error.value.code == "file-too-large"


def test_permission_errors_remain_io_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno

    def denied(*args: object, **kwargs: object) -> int:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(AdapterError) as error:
        read_bytes(tmp_path / "file", max_bytes=20)
    assert error.value.exit_code == 3
    assert "unreadable" in error.value.code


def test_invalid_second_catalog_cannot_leave_a_partial_success(tmp_path: Path) -> None:
    path = write_workspace(
        tmp_path,
        sources=[
            {"id": "first", "root": "../first", "catalog": "../catalog.yaml"},
            {"id": "second", "root": "../second", "catalog": "../broken.yaml"},
        ],
    )
    (tmp_path / "broken.yaml").write_text("schema_version: knowledge-catalog.v1\nscopes: []\n")
    with pytest.raises(ValidationError):
        load_workspace(path)


def test_conflicting_source_definitions_are_configuration_errors(tmp_path: Path) -> None:
    path = write_workspace(
        tmp_path,
        sources=[
            {"id": "first", "root": "../first", "catalog": "../catalog.yaml"},
            {"id": "second", "root": "../second", "catalog": "../second.yaml"},
        ],
    )
    catalog = catalog_data()
    catalog["scopes"] = {"org:example": {"label": "A conflicting organization"}}
    (tmp_path / "second.yaml").write_text(json.dumps(catalog))
    with pytest.raises(ValidationError) as error:
        load_workspace(path)
    assert error.value.code == "catalog-conflict"


def test_platform_temp_alias_is_accepted_when_explicitly_resolved(tmp_path: Path) -> None:
    alias = tmp_path / "named-alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    path = alias / "data"
    (tmp_path / "data").write_bytes(b"named data")
    assert read_bytes(resolve_path(str(path), base=tmp_path), max_bytes=20) == b"named data"


def test_receipt_defaults_resolve_against_config_without_creating_storage(tmp_path: Path) -> None:
    path = write_workspace(tmp_path)
    workspace = load_workspace(path)
    assert workspace.receipts.enabled is True
    assert workspace.receipts.retention_days == 30
    assert workspace.receipts.directory == path.parent / "ai/usage"
    assert not workspace.receipts.directory.exists()


def test_explicit_durable_receipt_location_is_independent_of_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_workspace(
        tmp_path,
        receipts={"enabled": False, "directory": "../scaffold/ai/usage", "retention_days": 9},
    )
    workspace = load_workspace(path)
    monkeypatch.chdir(tmp_path.parent)
    assert load_workspace(path).receipts == workspace.receipts
    assert workspace.receipts.directory == tmp_path / "scaffold/ai/usage"
    assert workspace.receipts.enabled is False
    assert workspace.receipts.retention_days == 9


@pytest.mark.parametrize(
    "directory",
    [
        "../knowledge",
        "../knowledge/usage",
        "..",
        "../catalog.yaml",
        "../scaffold/ai/signals",
        "../scaffold/ai",
        "../scaffold/ai/signals/usage",
    ],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_usage_cannot_overlap_canonical_catalog_or_signal_paths(
    tmp_path: Path, directory: str, enabled: bool
) -> None:
    path = write_workspace(
        tmp_path,
        signal_storage={"scaffold_root": "../scaffold", "code_root": ".."},
        receipts={"enabled": enabled, "directory": directory},
    )
    with pytest.raises(ValidationError) as error:
        load_workspace(path)
    assert error.value.code == "receipt-root-overlap"


@pytest.mark.parametrize("directory", ["../alias", "../alias/nested", "../alias/../usage"])
def test_usage_path_cannot_follow_a_symlink_even_outside_knowledge(
    tmp_path: Path, directory: str
) -> None:
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    path = write_workspace(tmp_path, receipts={"directory": directory})
    with pytest.raises(ValidationError) as error:
        load_workspace(path)
    assert error.value.code == "unsafe-receipt-path"


def test_usage_policy_changes_invalidate_workspace_fingerprint(tmp_path: Path) -> None:
    path = write_workspace(tmp_path)
    initial = load_workspace(path)
    data = json.loads(path.read_text())
    data["receipts"] = {"retention_days": 2}
    path.write_text(json.dumps(data))
    assert load_workspace(path).fingerprint != initial.fingerprint


def test_usage_cannot_overlap_an_inbox_alias(tmp_path: Path) -> None:
    path = write_workspace(
        tmp_path,
        signal_storage={"scaffold_root": "../scaffold", "code_root": ".."},
    )
    usage = path.parent / "ai/usage"
    usage.mkdir(parents=True)
    inbox = tmp_path / "scaffold/ai/signals"
    inbox.parent.mkdir(parents=True)
    inbox.symlink_to(usage, target_is_directory=True)
    with pytest.raises(ValidationError) as error:
        load_workspace(path)
    assert error.value.code == "receipt-root-overlap"
