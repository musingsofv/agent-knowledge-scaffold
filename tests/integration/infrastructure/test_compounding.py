"""Exercise advisory activity records and guarded signal drainage."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from agent_knowledge.domain.compounding import (
    CompoundDecision,
    OwnerReference,
    PublicationEvidence,
    SignalDisposition,
    SignalSnapshot,
)
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import compounding
from agent_knowledge.infrastructure.compounding import (
    activity_path,
    drain_signals,
    finish_run,
    read_activity_log,
    start_run,
)
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from agent_knowledge.infrastructure.errors import AdapterError
from tests.factories import catalog_data, signal_data


def workspace(tmp_path: Path) -> Workspace:
    source = tmp_path / "knowledge"
    source.mkdir()
    (source / "guidance").mkdir()
    (source / "guidance/example.md").write_text("Owned guidance.\n")
    scaffold = tmp_path / "scaffold"
    (scaffold / "ai" / "signals").mkdir(parents=True)
    (tmp_path / "catalog.yaml").write_text(yaml.safe_dump(catalog_data()))
    config = tmp_path / "workspace.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
                "signal_storage": {"scaffold_root": "scaffold", "code_root": "."},
            }
        )
    )
    return load_workspace(config)


def project_workspace(tmp_path: Path) -> Workspace:
    """Create a configured workspace with a durable project bucket."""
    code_root = tmp_path / "code"
    project = code_root / "products/orders"
    project.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(project)],
        check=True,
        capture_output=True,
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
    )
    source = tmp_path / "knowledge"
    source.mkdir()
    (source / "guidance").mkdir()
    (source / "guidance/example.md").write_text("Owned guidance.\n")
    scaffold = tmp_path / "scaffold"
    (scaffold / "ai" / "signals").mkdir(parents=True)
    (tmp_path / "catalog.yaml").write_text(yaml.safe_dump(catalog_data()))
    config = project / "workspace.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [
                    {
                        "id": "knowledge",
                        "root": str(source),
                        "catalog": str(tmp_path / "catalog.yaml"),
                    }
                ],
                "signal_storage": {"scaffold_root": str(scaffold), "code_root": str(code_root)},
            }
        )
    )
    return load_workspace(config)


def stored_signal(
    path: Path,
    identifier: str,
    *,
    workspace_id: str = "repo:orders",
    project_path: str | None = None,
    body: str = "# Observation\n\nPreserve this exact claim.\n",
) -> Path:
    """Write one schema-valid signal with explicit origin context."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        dump_document(
            signal_data(
                id=identifier,
                origin={
                    "workspace_id": workspace_id,
                    "project_path": project_path,
                    "applicable_scopes": ["org:example", "repo:orders"],
                    "source_ids": ["knowledge"],
                },
            ),
            body,
        )
    )
    return path


def snapshot(path: Path, identifier: str = "one") -> SignalSnapshot:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return SignalSnapshot(identifier, str(path), f"sha256:{digest}")


def disposition(identifier: str, decision: CompoundDecision) -> SignalDisposition:
    return SignalDisposition(
        identifier,
        decision,
        "The selected evidence was reviewed.",
        (OwnerReference("guidance/example.md", source="knowledge"),),
    )


def begin(loaded: Workspace, selected: tuple[SignalSnapshot, ...]) -> str:
    return start_run(
        loaded,
        selected=selected,
        harness="claude",
        session_id="session-1",
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
    ).run_id


def test_activity_lifecycle_preserves_provenance_and_drained_ids(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    signal = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")

    started = start_run(
        loaded,
        selected=(snapshot(signal),),
        harness="codex",
        session_id="session-1",
        automation_id="automation-1",
        workspace_id="repo:orders",
    )
    assert started.active is True
    with pytest.raises(AdapterError, match="unfinished"):
        start_run(
            loaded,
            selected=(),
            harness=None,
            session_id=None,
            automation_id=None,
            workspace_id="repo:orders",
        )

    drain_signals(
        loaded,
        (snapshot(signal),),
        (disposition("one", CompoundDecision.KEEP),),
        run_id=started.run_id,
        publication_verified=False,
    )
    ended = finish_run(
        loaded,
        run_id=started.run_id,
        outcome="published",
        dispositions=(disposition("one", CompoundDecision.UPDATE),),
    )
    state = read_activity_log(activity_path(loaded))
    assert state.active_runs == ()
    assert state.events[-1] == ended
    assert ended.active is False
    assert ended.drained == ("one",)
    assert ended.session_id == "session-1"


@pytest.mark.parametrize(
    "line",
    [
        {
            "schema": "compound-activity.v1",
            "event": "end",
            "run_id": "missing",
            "workspace_id": "repo:orders",
            "active": False,
            "ended_at": "2026-09-10T00:00:00Z",
            "outcome": "failed",
        },
        {
            "schema": "compound-activity.v1",
            "event": "start",
            "run_id": "one",
            "workspace_id": "repo:orders",
            "active": True,
            "started_at": "2026-09-10T00:00:00Z",
            "selected": [{"id": "one", "path": "/tmp/one.md", "fingerprint": "bad"}],
        },
        {
            "schema": "compound-activity.v1",
            "event": "start",
            "run_id": "one",
            "workspace_id": "repo:orders",
            "active": True,
            "started_at": "2026-09-10T00:00:00Z",
            "outcome": "unexpected",
        },
    ],
)
def test_malformed_activity_log_requires_inspection(
    tmp_path: Path, line: dict[str, object]
) -> None:
    loaded = workspace(tmp_path)
    activity_path(loaded).write_text(json.dumps(line) + "\n")

    with pytest.raises(ValidationError, match="activity"):
        read_activity_log(activity_path(loaded))


def test_start_rejects_snapshot_outside_signal_storage(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_bytes(b"outside")

    with pytest.raises(ValidationError, match="outside"):
        start_run(
            loaded,
            selected=(snapshot(outside),),
            harness=None,
            session_id=None,
            automation_id=None,
            workspace_id="repo:orders",
        )
    assert not activity_path(loaded).exists()


def test_drain_removes_only_handled_unchanged_files(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    root = loaded.signal_storage.signal_root
    one = stored_signal(root / "shared/one.md", "one")
    two = stored_signal(root / "shared/two.md", "two")
    changed = stored_signal(root / "shared/changed.md", "changed", body="# Before\n\nClaim.\n")
    selected = (snapshot(one), snapshot(two, "two"), snapshot(changed, "changed"))
    run_id = begin(loaded, selected)
    stored_signal(changed, "changed", body="# After\n\nChanged claim.\n")

    report = drain_signals(
        loaded,
        selected,
        (
            disposition("one", CompoundDecision.UPDATE),
            disposition("two", CompoundDecision.KEEP),
            disposition("changed", CompoundDecision.UPDATE),
        ),
        run_id=run_id,
        publication_verified=True,
        publication=PublicationEvidence(
            "published", repository="example/knowledge", commit="a" * 40
        ),
    )

    assert report.drained == ("one", "two")
    assert report.retained == ("changed",)
    assert one.exists() is False
    assert two.exists() is False
    assert changed.exists()
    assert report.diagnostics == ()


def test_drain_removes_current_project_signal(tmp_path: Path) -> None:
    loaded = project_workspace(tmp_path)
    root = loaded.signal_storage.signal_root
    local = stored_signal(
        root / "projects/products/orders/local.md", "local", project_path="products/orders"
    )

    selected = (snapshot(local, "local"),)
    run_id = begin(loaded, selected)
    report = drain_signals(
        loaded,
        selected,
        (disposition("local", CompoundDecision.KEEP),),
        run_id=run_id,
        publication_verified=False,
    )

    assert report.drained == ("local",)
    assert report.retained == ()
    assert local.exists() is False


@pytest.mark.parametrize("fault", ["id", "schema", "bucket", "missing", "symlink", "foreign"])
def test_start_rejects_invalid_or_unsafe_selection(tmp_path: Path, fault: str) -> None:
    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    match fault:
        case "id":
            selected = (snapshot(path, "wrong"),)
        case "schema":
            path.write_text("not a signal")
            selected = (snapshot(path),)
        case "bucket":
            path = stored_signal(loaded.signal_storage.signal_root / "loose.md", "one")
            selected = (snapshot(path),)
        case "missing":
            path.unlink()
        case "symlink":
            outside = tmp_path / "outside.md"
            outside.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(outside)
        case "foreign":
            stored_signal(path, "one", workspace_id="repo:other")
            selected = (snapshot(path),)
    with pytest.raises((AdapterError, ValidationError)):
        begin(loaded, selected)
    assert not activity_path(loaded).exists()


@pytest.mark.parametrize("fault", ["id", "schema", "foreign", "missing", "symlink"])
def test_drain_revalidates_signal_after_start(tmp_path: Path, fault: str) -> None:
    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    match fault:
        case "id":
            stored_signal(path, "changed-id")
        case "schema":
            path.write_text("not a signal")
        case "foreign":
            stored_signal(path, "one", workspace_id="repo:other")
        case "missing":
            path.unlink()
        case "symlink":
            outside = tmp_path / "outside.md"
            outside.write_bytes(path.read_bytes())
            path.unlink()
            path.symlink_to(outside)
    report = drain_signals(
        loaded,
        selected,
        (disposition("one", CompoundDecision.KEEP),),
        run_id=run_id,
        publication_verified=False,
    )
    assert report.drained == ()
    assert report.retained == ("one",)
    assert report.diagnostics


def test_partial_cleanup_reports_successes_and_retains_failed_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = workspace(tmp_path)
    root = loaded.signal_storage.signal_root
    one = stored_signal(root / "shared/one.md", "one")
    two = stored_signal(root / "shared/two.md", "two")
    real_unlink = os.unlink

    def fail_second(name: str, *, dir_fd: int | None = None) -> None:
        if name == "two.md":
            raise PermissionError("keep two")
        real_unlink(name, dir_fd=dir_fd)

    monkeypatch.setattr("agent_knowledge.infrastructure.compounding.os.unlink", fail_second)
    selected = (snapshot(one), snapshot(two, "two"))
    run_id = begin(loaded, selected)
    report = drain_signals(
        loaded,
        selected,
        tuple(disposition(item.id, CompoundDecision.KEEP) for item in selected),
        run_id=run_id,
        publication_verified=False,
    )

    assert report.drained == ("one",)
    assert report.retained == ("two",)
    assert two.exists()
    assert report.diagnostics[0]["signal_id"] == "two"


def test_final_identity_check_retains_file_replaced_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    real_stat = os.stat
    real_unlink = compounding._unlink_verified_file
    unlink_started = False
    replaced = False

    def replace_on_final_stat(name: object, *args: object, **kwargs: object):
        nonlocal replaced
        result = real_stat(name, *args, **kwargs)
        if (
            unlink_started
            and name == "one.md"
            and kwargs.get("dir_fd") is not None
            and not replaced
        ):
            replaced = True
            path.unlink()
            path.write_bytes(b"replacement")
            result = real_stat(name, *args, **kwargs)
        return result

    def replace_before_unlink(target: Path, *, expected: str) -> None:
        nonlocal unlink_started
        unlink_started = True
        real_unlink(target, expected=expected)

    monkeypatch.setattr(compounding, "_unlink_verified_file", replace_before_unlink)
    monkeypatch.setattr(compounding.os, "stat", replace_on_final_stat)
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    report = drain_signals(
        loaded,
        selected,
        (disposition("one", CompoundDecision.KEEP),),
        run_id=run_id,
        publication_verified=False,
    )

    assert report.drained == ()
    assert report.retained == ("one",)
    assert path.read_bytes() == b"replacement"


def test_start_archives_exact_bytes_and_provenance_with_disabled_diagnostics(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from agent_knowledge.infrastructure.compound_evidence import archive_path, evidence_records

    loaded = workspace(tmp_path)
    loaded = replace(loaded, receipts=replace(loaded.receipts, enabled=False))
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    original = path.read_bytes()
    run_id = begin(loaded, selected)
    archive = archive_path(loaded, run_id, selected[0])
    assert archive.read_bytes() == original
    assert archive.stem != selected[0].id
    record = evidence_records(loaded, run_id)[0]
    assert record["operation"] == "compound.start"
    assert record["context"]["session_id"] == "session-1"
    assert archive.is_relative_to(loaded.receipts.directory)
    assert not archive.is_relative_to(loaded.signal_storage.signal_root)


@pytest.mark.parametrize("fault", ["missing", "corrupt", "symlink"])
def test_bad_archive_retains_signal(tmp_path: Path, fault: str) -> None:
    from agent_knowledge.infrastructure.compound_evidence import archive_path

    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    archive = archive_path(loaded, run_id, selected[0])
    archive.unlink()
    match fault:
        case "corrupt":
            archive.write_bytes(b"corrupt")
        case "symlink":
            archive.symlink_to(path)
    result = drain_signals(
        loaded,
        selected,
        (disposition("one", CompoundDecision.KEEP),),
        run_id=run_id,
        publication_verified=False,
    )
    assert result.drained == ()
    assert result.retained == ("one",)
    assert result.diagnostics
    assert path.exists()


def test_failed_durable_intent_leaves_all_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    real_append = compounding.append_compound_event

    def fail_intent(*args, **kwargs):
        if args[2] == "compound.drain.intent":
            raise AdapterError("test-write-failed", "events", "Cannot persist intent.")
        return real_append(*args, **kwargs)

    monkeypatch.setattr(compounding, "append_compound_event", fail_intent)
    with pytest.raises(AdapterError, match="intent"):
        drain_signals(
            loaded,
            selected,
            (disposition("one", CompoundDecision.KEEP),),
            run_id=run_id,
            publication_verified=False,
        )
    assert path.exists()


def test_repeated_drain_preserves_prior_success_and_archive(tmp_path: Path) -> None:
    from agent_knowledge.infrastructure.compound_evidence import archive_path, evidence_records

    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    decisions = (disposition("one", CompoundDecision.KEEP),)
    original = archive_path(loaded, run_id, selected[0]).read_bytes()
    first = drain_signals(loaded, selected, decisions, run_id=run_id, publication_verified=False)
    assert first.drained == ("one",)
    # A new input at the same path must not be removed by a retry of the old run.
    stored_signal(path, "one", body="# Newly observed\n\nAnother observation.\n")
    second = drain_signals(loaded, selected, decisions, run_id=run_id, publication_verified=False)
    assert second.drained == ()
    assert second.diagnostics[0]["code"] == "signal-already-drained"
    assert path.exists()
    assert archive_path(loaded, run_id, selected[0]).read_bytes() == original
    finished = finish_run(loaded, run_id=run_id, outcome="agent says done", dispositions=decisions)
    assert finished.drained == ("one",)
    assert (
        len(
            [
                item
                for item in evidence_records(loaded, run_id)
                if item["operation"] == "compound.drain"
            ]
        )
        == 2
    )


def test_lost_acknowledgement_is_not_fabricated_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.infrastructure.compound_evidence import evidence_records

    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    decisions = (disposition("one", CompoundDecision.KEEP),)
    real_append = compounding.append_compound_event

    def fail_after_intent(*args, **kwargs):
        if args[2] in {"compound.drain.removed", "compound.drain"}:
            raise AdapterError("test-write-failed", "events", "Cannot persist result.")
        return real_append(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(compounding, "append_compound_event", fail_after_intent)
        with pytest.raises(AdapterError, match="result"):
            drain_signals(loaded, selected, decisions, run_id=run_id, publication_verified=False)
    assert not path.exists()
    retried = drain_signals(loaded, selected, decisions, run_id=run_id, publication_verified=False)
    assert retried.drained == ()
    assert retried.retained == ("one",)
    assert retried.diagnostics[0]["code"] == "drain-result-unknown"
    finished = finish_run(loaded, run_id=run_id, outcome="published", dispositions=decisions)
    assert finished.drained == ()
    assert evidence_records(loaded, run_id)[-1]["tool_result"]["unresolved"] is True


def test_foreign_run_and_altered_selection_cannot_drain(tmp_path: Path) -> None:
    from dataclasses import replace

    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    decisions = (disposition("one", CompoundDecision.KEEP),)
    with pytest.raises(ValidationError, match="selection"):
        drain_signals(
            loaded,
            (replace(selected[0], fingerprint="sha256:" + "a" * 64),),
            decisions,
            run_id=run_id,
            publication_verified=False,
        )
    foreign = replace(loaded, definition=replace(loaded.definition, workspace_id="repo:other"))
    with pytest.raises(ValidationError, match="workspace"):
        drain_signals(foreign, selected, decisions, run_id=run_id, publication_verified=False)
    assert path.exists()


def test_torn_run_evidence_is_not_accepted(tmp_path: Path) -> None:
    from agent_knowledge.infrastructure.compound_evidence import run_root

    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    with (run_root(loaded, run_id) / "events.jsonl").open("ab") as output:
        output.write(b'{"operation":"compound.drain.removed"')
    with pytest.raises(AdapterError, match="evidence"):
        drain_signals(
            loaded,
            selected,
            (disposition("one", CompoundDecision.KEEP),),
            run_id=run_id,
            publication_verified=False,
        )
    assert path.exists()


def test_rollover_preserves_unresolved_run_evidence_and_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.infrastructure.compound_evidence import evidence_records

    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    first_id = begin(loaded, selected)
    finish_run(loaded, run_id=first_id, outcome="deferred", dispositions=())
    log_size = activity_path(loaded).stat().st_size
    monkeypatch.setattr(compounding, "ACTIVITY_MAX_BYTES", log_size * 3)
    second_id = begin(loaded, selected)
    assert second_id != first_id
    assert [item.run_id for item in read_activity_log(activity_path(loaded)).events] == [second_id]
    assert compounding.resolve_run(loaded, first_id).run_id == first_id
    assert evidence_records(loaded, first_id)[-1]["tool_result"]["unresolved"] is True
    assert list((loaded.receipts.directory / "coordination").glob("*.jsonl"))


def test_concurrent_start_serializes_entire_lifecycle(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    loaded = workspace(tmp_path)

    def attempt():
        try:
            return begin(loaded, ())
        except AdapterError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item.startswith("compound-") and item != "compound-active" for item in results) == 1
    assert any(item in {"compound-active", "usage-lock-failed"} for item in results)
    assert len(read_activity_log(activity_path(loaded)).active_runs) == 1


@pytest.mark.parametrize("decision", [CompoundDecision.UPDATE, CompoundDecision.DELETE_RETIRE])
def test_missing_owner_is_only_drainable_for_declared_deletion(
    tmp_path: Path, decision: CompoundDecision
) -> None:
    loaded = workspace(tmp_path)
    (loaded.sources[0].root / "guidance/example.md").unlink()
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    result = drain_signals(
        loaded,
        selected,
        (disposition("one", decision),),
        run_id=run_id,
        publication_verified=True,
        publication=PublicationEvidence(
            "published", repository="example/knowledge", commit="a" * 40
        ),
    )
    assert result.drained == (("one",) if decision == CompoundDecision.DELETE_RETIRE else ())
    assert path.exists() == (decision == CompoundDecision.UPDATE)


def test_foreign_configured_publication_retains_signal(tmp_path: Path) -> None:
    from dataclasses import replace

    from agent_knowledge.domain.configuration import Publication

    loaded = workspace(tmp_path)
    # Keep descriptor/config snapshot intact while substituting only the interpreted
    # source's publication route to exercise this explicit gate.
    source = replace(
        loaded.sources[0], publication=Publication("example/expected", "main", "knowledge/")
    )
    loaded = replace(loaded, sources=(source,))
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    run_id = begin(loaded, selected)
    report = drain_signals(
        loaded,
        selected,
        (disposition("one", CompoundDecision.UPDATE),),
        run_id=run_id,
        publication_verified=True,
        publication=PublicationEvidence("published", repository="example/foreign", commit="a" * 40),
    )
    assert report.drained == ()
    assert report.retained == ("one",)
    assert report.diagnostics[0]["code"] == "owner-unavailable"


def test_start_rejects_edited_preview_before_archival(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    path = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(path),)
    path.write_bytes(path.read_bytes() + b"\nChanged after selection.\n")
    with pytest.raises(AdapterError, match="changed"):
        begin(loaded, selected)
    assert not activity_path(loaded).exists()
