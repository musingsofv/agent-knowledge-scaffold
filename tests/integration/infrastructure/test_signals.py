"""Prove durable signal capture and exact-bucket discovery without destructive repair."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import signals
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.signals import capture_signal, inventory_signals
from tests.factories import catalog_data
from tests.unit.domain.test_configuration import workspace_data


def make_workspace(tmp_path: Path, *, canonical: str = "knowledge") -> Workspace:
    """Configure an isolated destination independently of its absent inbox."""
    (tmp_path / "catalog.yaml").write_text(json.dumps(catalog_data()))
    (tmp_path / "scaffold").mkdir()
    path = tmp_path / "workspace.yaml"
    path.write_text(
        json.dumps(
            workspace_data(
                sources=[{"id": "knowledge", "root": canonical, "catalog": "catalog.yaml"}],
                signal_storage={"scaffold_root": "scaffold", "code_root": "."},
            )
        )
    )
    return load_workspace(path)


def test_capture_preserves_exact_bytes_and_mirrors_nested_project(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    data = b"---\r\nid: original\r\n---\r\nExact claim.\r\n"
    path = capture_signal(workspace, "products/orders", data)
    assert path.parent == tmp_path / "scaffold/ai/signals/projects/products/orders"
    assert path.suffix == ".md"
    assert path.read_bytes() == data
    assert list(path.parent.iterdir()) == [path]
    assert path.stat().st_mode & 0o777 == 0o600


def test_parallel_captures_are_unique_and_never_replace_another_signal(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    with ThreadPoolExecutor(max_workers=5) as pool:
        paths = list(
            pool.map(lambda i: capture_signal(workspace, "orders", str(i).encode()), range(12))
        )
    assert len(set(paths)) == 12
    assert {path.read_bytes() for path in paths} == {str(i).encode() for i in range(12)}


def test_basename_collisions_and_shared_origin_use_distinct_buckets(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    first = capture_signal(workspace, "a/orders", b"first")
    second = capture_signal(workspace, "b/orders", b"second")
    shared = capture_signal(workspace, None, b"shared")
    assert inventory_signals(workspace, "a/orders").files == (first,)
    assert inventory_signals(workspace, "b/orders").files == (second,)
    assert inventory_signals(workspace, "a/orders", include_shared=True).files == tuple(
        sorted((first, shared))
    )
    assert inventory_signals(workspace, None, include_shared=True).files == (shared,)


def test_inventory_does_not_recurse_into_nested_project_buckets(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    parent = capture_signal(workspace, "products", b"parent")
    nested = capture_signal(workspace, "products/orders", b"nested")
    assert inventory_signals(workspace, "products").files == (parent,)
    assert inventory_signals(workspace, "products/orders").files == (nested,)


def test_missing_inbox_and_bucket_are_stable_empty_read_only_results(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    before = set(tmp_path.rglob("*"))
    initial = inventory_signals(workspace, "absent/orders")
    assert initial.files == ()
    assert initial == inventory_signals(workspace, "absent/orders")
    assert set(tmp_path.rglob("*")) == before
    capture_signal(workspace, "other", b"other")
    assert inventory_signals(workspace, "absent/orders").files == ()
    assert initial.fingerprint != inventory_signals(workspace, "absent/orders").fingerprint


@pytest.mark.parametrize("operation", ["capture", "inventory"])
def test_scaffold_root_must_already_exist(tmp_path: Path, operation: str) -> None:
    workspace = make_workspace(tmp_path)
    (tmp_path / "scaffold").rmdir()
    with pytest.raises(AdapterError) as error:
        if operation == "capture":
            capture_signal(workspace, None, b"claim")
        else:
            inventory_signals(workspace, None)
    assert error.value.code == "directory-missing"
    assert not (tmp_path / "scaffold").exists()


@pytest.mark.parametrize("canonical", ["scaffold", "scaffold/ai/signals/future", "scaffold/ai"])
def test_absent_canonical_roots_are_protected_before_creating_inbox(
    tmp_path: Path, canonical: str
) -> None:
    workspace = make_workspace(tmp_path, canonical=canonical)
    with pytest.raises(ValidationError) as error:
        capture_signal(workspace, "orders", b"claim")
    assert error.value.code == "signal-root-overlap"
    assert not (tmp_path / "scaffold/ai").exists()


@pytest.mark.parametrize("relative", ["../outside", "/outside", "a/../b", "a//b"])
def test_adapter_defensively_rejects_escaping_project_path(tmp_path: Path, relative: str) -> None:
    workspace = make_workspace(tmp_path)
    with pytest.raises(ValidationError):
        capture_signal(workspace, relative, b"claim")
    assert not (tmp_path / "scaffold/ai").exists()


@pytest.mark.parametrize("part", ["ai", "ai/signals", "ai/signals/projects/orders"])
def test_capture_and_inventory_refuse_internal_symlink_traversal(tmp_path: Path, part: str) -> None:
    workspace = make_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "scaffold" / part
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)
    for operation in (
        lambda: capture_signal(workspace, "orders", b"claim"),
        lambda: inventory_signals(workspace, "orders"),
    ):
        with pytest.raises((AdapterError, ValidationError)):
            operation()
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("suffix", ["yaml", "yml"])
def test_legacy_signal_inside_selected_bucket_is_visible_error(tmp_path: Path, suffix: str) -> None:
    workspace = make_workspace(tmp_path)
    path = capture_signal(workspace, "orders", b"claim")
    legacy = path.parent / f"legacy.{suffix}"
    legacy.write_text("old signal")
    with pytest.raises(ValidationError) as error:
        inventory_signals(workspace, "orders")
    assert error.value.code == "unsupported-signal-format"
    assert legacy.read_text() == "old signal"


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_nonregular_selected_entries_are_diagnosed_without_opening(
    tmp_path: Path, kind: str
) -> None:
    workspace = make_workspace(tmp_path)
    path = capture_signal(workspace, "orders", b"claim")
    foreign = path.parent / "foreign.md"
    if kind == "symlink":
        foreign.symlink_to(tmp_path / "missing")
    else:
        os.mkfifo(foreign)
    with pytest.raises(AdapterError) as error:
        inventory_signals(workspace, "orders")
    assert error.value.code == ("unsafe-path" if kind == "symlink" else "not-regular-file")


@pytest.mark.parametrize("change", ["edit", "replace", "add", "delete"])
def test_inventory_snapshot_changes_when_selected_inputs_change(
    tmp_path: Path, change: str
) -> None:
    workspace = make_workspace(tmp_path)
    path = capture_signal(workspace, "orders", b"claim")
    before = inventory_signals(workspace, "orders")
    if change == "edit":
        path.write_bytes(b"other")
    elif change == "replace":
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"claim")
        replacement.replace(path)
    elif change == "add":
        capture_signal(workspace, "orders", b"new")
    else:
        path.unlink()
    assert before.fingerprint != inventory_signals(workspace, "orders").fingerprint


def test_activity_log_and_unselected_legacy_bucket_are_not_signal_inputs(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    path = capture_signal(workspace, "orders", b"claim")
    (tmp_path / "scaffold/ai/signals/compound-activity.jsonl").write_text("invalid log")
    other = tmp_path / "scaffold/ai/signals/shared"
    other.mkdir()
    (other / "legacy.yaml").write_text("old signal")
    assert inventory_signals(workspace, "orders").files == (path,)


def test_output_collision_preserves_existing_file_and_cleans_only_owned_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    monkeypatch.setattr(signals, "_new_name", lambda: "fixed.md")
    path = capture_signal(workspace, "orders", b"first")
    with pytest.raises(AdapterError) as error:
        capture_signal(workspace, "orders", b"second")
    assert error.value.code == "signal-collision"
    assert path.read_bytes() == b"first"
    assert list(path.parent.iterdir()) == [path]


def test_write_failure_never_publishes_partial_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)

    def fail(descriptor: int, data: bytes) -> int:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(signals.os, "write", fail)
    with pytest.raises(AdapterError):
        capture_signal(workspace, "orders", b"claim")
    assert list((tmp_path / "scaffold/ai/signals/projects/orders").iterdir()) == []


def test_post_publication_sync_failure_preserves_completed_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    capture_signal(workspace, "orders", b"existing")
    original = os.fsync

    def fail_directory(descriptor: int) -> None:
        if os.fstat(descriptor).st_mode & 0o170000 == 0o040000:
            raise OSError("simulated directory sync failure")
        original(descriptor)

    monkeypatch.setattr(signals.os, "fsync", fail_directory)
    with pytest.raises(AdapterError) as error:
        capture_signal(workspace, "orders", b"new claim")
    assert error.value.code == "signal-publication-uncertain"
    assert {
        p.read_bytes() for p in (tmp_path / "scaffold/ai/signals/projects/orders").glob("*.md")
    } == {b"existing", b"new claim"}


def test_replaced_temporary_file_is_preserved_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.fsync
    replacement: list[Path] = []

    def replace_after_sync(descriptor: int) -> None:
        original(descriptor)
        if os.fstat(descriptor).st_mode & 0o170000 == 0o100000:
            temporary = next((tmp_path / "scaffold/ai/signals/projects/orders").glob("*.tmp"))
            temporary.unlink()
            temporary.write_bytes(b"foreign replacement")
            replacement.append(temporary)

    monkeypatch.setattr(signals.os, "fsync", replace_after_sync)
    with pytest.raises(AdapterError) as error:
        capture_signal(workspace, "orders", b"claim")
    assert error.value.code == "signals-changed"
    assert replacement[0].read_bytes() == b"foreign replacement"
    assert list(replacement[0].parent.glob("*.md")) == []


def test_replaced_scaffold_during_write_is_detected_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.write

    def replace(descriptor: int, data: bytes) -> int:
        result = original(descriptor, data)
        (tmp_path / "scaffold").rename(tmp_path / "moved-scaffold")
        (tmp_path / "scaffold").mkdir()
        return result

    monkeypatch.setattr(signals.os, "write", replace)
    with pytest.raises(AdapterError):
        capture_signal(workspace, "orders", b"claim")
    assert list((tmp_path / "scaffold").rglob("*.md")) == []
    assert list((tmp_path / "moved-scaffold").rglob("*.md")) == []
    assert list((tmp_path / "moved-scaffold").rglob("*.tmp")) == []


def test_canonical_alias_added_during_write_blocks_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.write

    def add_alias(descriptor: int, data: bytes) -> int:
        result = original(descriptor, data)
        (tmp_path / "knowledge").symlink_to(tmp_path / "scaffold/ai/signals")
        return result

    monkeypatch.setattr(signals.os, "write", add_alias)
    with pytest.raises(ValidationError) as error:
        capture_signal(workspace, "orders", b"claim")
    assert error.value.code == "signal-root-overlap"
    assert list((tmp_path / "scaffold").rglob("*.md")) == []


def test_completed_output_replacement_is_retained_and_reported_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.link

    def replace(src: str, dst: str, **kwargs: object) -> None:
        original(src, dst, **kwargs)
        output = tmp_path / "scaffold/ai/signals/projects/orders" / dst
        output.unlink()
        output.write_bytes(b"foreign output")

    monkeypatch.setattr(signals.os, "link", replace)
    with pytest.raises(AdapterError) as error:
        capture_signal(workspace, "orders", b"claim")
    assert error.value.code == "signal-publication-uncertain"
    outputs = list((tmp_path / "scaffold/ai/signals/projects/orders").iterdir())
    assert len(outputs) == 1
    assert outputs[0].read_bytes() == b"foreign output"


def test_capture_and_inventory_require_explicit_signal_storage(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    config = json.loads(workspace.path.read_text())
    del config["signal_storage"]
    workspace.path.write_text(json.dumps(config))
    workspace = load_workspace(workspace.path)
    with pytest.raises(ValidationError, match="Configure durable signal storage"):
        capture_signal(workspace, "orders", b"claim")
    with pytest.raises(ValidationError, match="Configure durable signal storage"):
        inventory_signals(workspace, "orders")


def test_addition_during_inventory_never_reports_complete_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    signal = capture_signal(workspace, "orders", b"claim")
    original = os.listdir

    def changing(descriptor: int) -> list[str]:
        names = original(descriptor)
        (signal.parent / "late.md").write_bytes(b"new")
        return names

    monkeypatch.setattr(signals.os, "listdir", changing)
    with pytest.raises(AdapterError) as error:
        inventory_signals(workspace, "orders")
    assert error.value.code == "signals-changed"


def test_inventory_reports_unreadable_bucket_without_empty_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    capture_signal(workspace, "orders", b"claim")

    def denied(descriptor: int) -> list[str]:
        raise PermissionError(13, "simulated denial")

    monkeypatch.setattr(signals.os, "listdir", denied)
    with pytest.raises(AdapterError) as error:
        inventory_signals(workspace, "orders")
    assert error.value.code == "directory-unreadable"


def test_inventory_reports_unreadable_signal_without_skipping_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    capture_signal(workspace, "orders", b"claim")
    original = os.access

    def denied(path: str, mode: int, **kwargs: object) -> bool:
        return False if path.endswith(".md") else original(path, mode, **kwargs)

    monkeypatch.setattr(signals.os, "access", denied)
    with pytest.raises(AdapterError) as error:
        inventory_signals(workspace, "orders")
    assert error.value.code == "file-unreadable"


def test_inventory_returns_malformed_markdown_for_callers_schema_validation(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    path = capture_signal(workspace, "orders", b"malformed on purpose")
    assert inventory_signals(workspace, "orders").files == (path,)
    assert path.read_bytes() == b"malformed on purpose"


@pytest.mark.parametrize("moment", ["before-link", "after-link"])
def test_same_inode_mutation_around_publication_is_retained_as_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, moment: str
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.link

    def mutate(src: str, dst: str, **kwargs: object) -> None:
        bucket = tmp_path / "scaffold/ai/signals/projects/orders"
        if moment == "before-link":
            (bucket / src).write_bytes(b"concurrent edit")
        original(src, dst, **kwargs)
        if moment == "after-link":
            (bucket / dst).write_bytes(b"concurrent edit")

    monkeypatch.setattr(signals.os, "link", mutate)
    with pytest.raises(AdapterError) as error:
        capture_signal(workspace, "orders", b"claim")
    assert error.value.code == "signal-publication-uncertain"
    outputs = list((tmp_path / "scaffold/ai/signals/projects/orders").iterdir())
    assert len(outputs) == 1
    assert outputs[0].read_bytes() == b"concurrent edit"


def test_temporary_cleanup_failure_preserves_publication_uncertain_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)

    def denied(path: str, **kwargs: object) -> None:
        raise PermissionError(13, "simulated cleanup denial")

    monkeypatch.setattr(signals.os, "unlink", denied)
    with pytest.raises(AdapterError) as error:
        capture_signal(workspace, "orders", b"claim")
    assert error.value.code == "signal-publication-uncertain"
    outputs = list((tmp_path / "scaffold/ai/signals/projects/orders").iterdir())
    assert len(outputs) == 2
    assert {output.suffix for output in outputs} == {".tmp", ".md"}
    assert all(output.read_bytes() == b"claim" for output in outputs)
