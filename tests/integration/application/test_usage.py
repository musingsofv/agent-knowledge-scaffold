"""Portable usage exports retain evidence boundaries and respect workspace isolation."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from agent_knowledge.application.usage import export_usage, maintain_usage, retain_usage
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.usage import (
    append_event,
    canonical_json,
    read_events,
    write_artifact,
)
from tests.factories import catalog_data


def _workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "catalog.yaml").write_text(yaml.safe_dump(catalog_data()))
    config = tmp_path / "workspace.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
                "signal_storage": {"scaffold_root": "scaffold", "code_root": "code"},
                "receipts": {"enabled": True, "directory": "usage", "retention_days": 30},
            }
        )
    )
    return load_workspace(config)


def _event(
    event_id: str,
    timestamp: str,
    *,
    run_id: str | None = None,
    operation: str = "search",
    workspace_id: str = "repo:orders",
) -> dict[str, object]:
    return {
        "schema_version": "knowledge-compound-receipt.v1"
        if operation.startswith("compound.")
        else "knowledge-retrieval-receipt.v1",
        "event_id": event_id,
        "recorded_at": timestamp,
        "operation": operation,
        "context": {
            "workspace_id": workspace_id,
            "harness": "claude",
            "session_id": "opaque-session",
            "compound_run_id": run_id,
        },
        "workspace_fingerprint": "sha256:" + "a" * 64,
        "descriptor": "descriptors/" + hashlib.sha256(_descriptor_bytes()).hexdigest() + ".json",
        "measurements": {"elapsed_ms": 7, "response_bytes": 19},
        "response": {"status": "ok", "truncated": False},
    }


def _request(tmp_path: Path, destination: str = "review") -> dict[str, str]:
    return {
        "since": "2026-09-08T00:00:00Z",
        "until": "2026-09-14T00:00:00Z",
        "destination": str(tmp_path / destination),
    }


def _descriptor_bytes() -> bytes:
    return canonical_json(
        {"workspace_id": "repo:orders", "sources": [{"source_version": "unavailable"}]}
    )


def _descriptor(workspace: Workspace) -> None:
    data = _descriptor_bytes()
    write_artifact(
        workspace.receipts.directory / "descriptors" / (hashlib.sha256(data).hexdigest() + ".json"),
        data,
    )


def test_export_trace_includes_prior_start_exact_input_patch_and_checksums(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    root = workspace.receipts.directory
    run = root / "compound" / "run-1"
    original = b"---\norigin:\n  session_id: opaque-session\n---\nOriginal observation.\n"
    write_artifact(run / "inputs" / "hash.md", original)
    write_artifact(run / "start.json", b'{"run_id":"run-1"}')
    write_artifact(run / "changes.patch", b"diff --git a/guidance.md b/guidance.md\n")
    start = _event("start", "2026-09-07T23:00:00Z", run_id="run-1", operation="compound.start")
    drain = _event("drain", "2026-09-12T00:00:00Z", run_id="run-1", operation="compound.drain")
    drain.update(
        artifacts={"changes": "changes.patch", "signal_snapshots": [{"path": "inputs/hash.md"}]},
        agent_report={"dispositions": [{"decision": "update", "signal_id": "x"}]},
        tool_result={"drained": ["x"], "retained": []},
    )
    append_event(run / "events.jsonl", start)
    append_event(run / "events.jsonl", drain)
    log = root / "retrieval" / "2026-09-08.jsonl"
    append_event(log, _event("included", "2026-09-08T00:00:00Z", run_id="run-1"))
    append_event(log, _event("before", "2026-09-07T23:59:59Z"))
    append_event(log, _event("exclusive", "2026-09-14T00:00:00Z"))
    append_event(log, _event("foreign", "2026-09-09T00:00:00Z", workspace_id="other-workspace"))
    _descriptor(workspace)
    before = log.read_bytes()
    result = export_usage(load_workspace(workspace.path), _request(tmp_path))
    destination = tmp_path / "review"
    exported = [
        json.loads(line) for line in (destination / "events.jsonl").read_text().splitlines()
    ]
    assert {event["event_id"] for event in exported} == {"start", "drain", "included"}
    assert (
        next(event for event in exported if event["event_id"] == "start")[
            "export_supporting_context"
        ]
        is True
    )
    assert (destination / "compound/run-1/inputs/hash.md").read_bytes() == original
    assert (destination / "compound/run-1/changes.patch").read_bytes() == (
        run / "changes.patch"
    ).read_bytes()
    assert log.read_bytes() == before
    manifest = json.loads((destination / "manifest.json").read_text())
    for item in manifest["files"]:
        data = (destination / item["path"]).read_bytes()
        assert item["checksum"] == "sha256:" + hashlib.sha256(data).hexdigest()
        assert item["bytes"] == len(data)
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["selected_events"] == 2
    assert summary["supporting_events"] == 1
    assert summary["dispositions"] == {"update": 1}
    assert "foreign" not in (destination / "events.jsonl").read_text()
    assert "usage-source-version-unavailable" in str(result["diagnostics"])


def test_export_reports_partial_unknown_missing_session_and_unavailable_artifacts(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    root = workspace.receipts.directory
    run = root / "compound" / "run-1"
    event = _event("future", "2026-09-09T00:00:00Z", run_id="run-1", operation="compound.start")
    event.update(
        schema_version="future.v2",
        context={"workspace_id": "repo:orders", "compound_run_id": "run-1", "session_id": None},
        artifacts={"changes": "missing.patch"},
    )
    append_event(run / "events.jsonl", event)
    with (run / "events.jsonl").open("ab") as stream:
        stream.write(b'{"torn":')
    result = export_usage(load_workspace(workspace.path), _request(tmp_path))
    diagnostics = str(result["diagnostics"])
    for code in (
        "usage-torn-record",
        "usage-unknown-version",
        "usage-session-unavailable",
        "usage-artifact-unavailable",
        "usage-descriptor-unavailable",
    ):
        assert code in diagnostics
    assert (run / "events.jsonl").read_bytes().endswith(b'{"torn":')


def test_export_never_copies_mixed_workspace_run_or_symlink_artifacts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    root = workspace.receipts.directory
    run = root / "compound" / "mixed"
    append_event(
        run / "events.jsonl",
        _event("ours", "2026-09-09T00:00:00Z", run_id="mixed", operation="compound.start"),
    )
    append_event(
        run / "events.jsonl",
        _event(
            "foreign",
            "2026-09-09T00:00:00Z",
            run_id="mixed",
            operation="compound.start",
            workspace_id="foreign",
        ),
    )
    write_artifact(run / "inputs" / "foreign.md", b"private foreign observation")
    result = export_usage(load_workspace(workspace.path), _request(tmp_path))
    assert not (tmp_path / "review/compound/mixed").exists()
    assert "usage-run-context-unavailable" in str(result["diagnostics"])
    assert "private foreign observation" not in "".join(
        path.read_text() for path in (tmp_path / "review").rglob("*") if path.is_file()
    )


@pytest.mark.parametrize(
    "destination", ["usage/review", "knowledge/review", "scaffold/ai/signals/review", "."]
)
def test_export_rejects_overlaps_with_managed_evidence(tmp_path: Path, destination: str) -> None:
    workspace = _workspace(tmp_path)
    with pytest.raises(ValidationError, match="overlaps"):
        export_usage(load_workspace(workspace.path), _request(tmp_path, destination))


def test_export_rejects_existing_destination_and_symlink_components(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (tmp_path / "review").mkdir()
    (tmp_path / "review/user.txt").write_text("preserve")
    with pytest.raises(AdapterError, match="new directory"):
        export_usage(load_workspace(workspace.path), _request(tmp_path))
    (tmp_path / "alias").symlink_to(tmp_path / "review", target_is_directory=True)
    with pytest.raises(AdapterError):
        export_usage(load_workspace(workspace.path), _request(tmp_path, "alias/new"))
    assert (tmp_path / "review/user.txt").read_text() == "preserve"


@pytest.mark.parametrize(
    "state", ["active", "unresolved", "resolved", "foreign", "unknown", "newly-completed"]
)
def test_retention_only_expires_old_fully_resolved_runs(tmp_path: Path, state: str) -> None:
    workspace = _workspace(tmp_path)
    root = workspace.receipts.directory
    run = root / "compound" / "run-1"
    write_artifact(run / "inputs/hash.md", b"original")
    write_artifact(run / "start.json", b"{}")
    write_artifact(run / "changes/attempt.patch", b"scoped patch")
    start = _event("start", "2026-07-01T00:00:00Z", run_id="run-1", operation="compound.start")
    if state == "foreign":
        start["context"] = {"workspace_id": "foreign", "compound_run_id": "run-1"}
    append_event(run / "events.jsonl", start)
    if state != "active":
        finish = _event(
            "finish",
            "2026-09-13T00:00:00Z" if state == "newly-completed" else "2026-08-01T00:00:00Z",
            run_id="run-1",
            operation="compound.finish",
        )
        finish["tool_result"] = {"unresolved": state == "unresolved"}
        if state == "unknown":
            finish["schema_version"] = "future.v2"
        append_event(run / "events.jsonl", finish)
    result = retain_usage(workspace, now=datetime(2026, 9, 14, tzinfo=UTC))
    assert result["completed_runs_expired"] == (["run-1"] if state == "resolved" else [])
    assert (run / "inputs/hash.md").exists() is (state != "resolved")
    if state == "resolved":
        assert (run / "expired.json").exists()
        assert not (run / "changes/attempt.patch").exists()
        result = export_usage(load_workspace(workspace.path), _request(tmp_path))
        assert "usage-evidence-expired" in str(result["diagnostics"])


def test_retention_handles_arbitrarily_large_valid_days(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    workspace = replace(workspace, receipts=replace(workspace.receipts, retention_days=10**30))
    path = workspace.receipts.directory / "retrieval/2026-08-01.jsonl"
    append_event(path, _event("old", "2026-08-01T00:00:00Z"))
    assert (
        retain_usage(workspace, now=datetime(2026, 9, 14, tzinfo=UTC))["retrieval_records_removed"]
        == 0
    )
    assert read_events(path).records[0]["event_id"] == "old"


def test_normal_use_retention_runs_once_per_workspace_day(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    assert maintain_usage(workspace)["status"] == "completed"
    assert maintain_usage(workspace)["status"] == "already-applied"
    assert len(list((workspace.receipts.directory / "maintenance").glob("*.json"))) == 1


def test_export_preserves_corrupted_snapshot_but_labels_fingerprint_mismatch(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    run = workspace.receipts.directory / "compound/run-1"
    write_artifact(run / "inputs/hash.md", b"changed bytes")
    write_artifact(run / "start.json", b"{}")
    event = _event("start", "2026-09-09T00:00:00Z", run_id="run-1", operation="compound.start")
    event["artifacts"] = {
        "signal_snapshots": [
            {
                "path": "inputs/hash.md",
                "fingerprint": "sha256:" + hashlib.sha256(b"original bytes").hexdigest(),
            }
        ]
    }
    append_event(run / "events.jsonl", event)
    result = export_usage(load_workspace(workspace.path), _request(tmp_path))
    assert "usage-artifact-fingerprint-mismatch" in str(result["diagnostics"])
    assert (tmp_path / "review/compound/run-1/inputs/hash.md").read_bytes() == b"changed bytes"


def test_export_does_not_read_symlink_snapshot_or_unrelated_run_file(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    run = workspace.receipts.directory / "compound/run-1"
    write_artifact(run / "start.json", b"{}")
    write_artifact(run / "unrelated.json", b'{"private":"not requested"}')
    (run / "inputs").mkdir()
    secret = tmp_path / "outside.md"
    secret.write_text("outside observation")
    (run / "inputs/hash.md").symlink_to(secret)
    append_event(
        run / "events.jsonl",
        _event("start", "2026-09-09T00:00:00Z", run_id="run-1", operation="compound.start"),
    )
    result = export_usage(load_workspace(workspace.path), _request(tmp_path))
    assert "usage-artifact-unavailable" in str(result["diagnostics"])
    assert not (tmp_path / "review/compound/run-1/inputs/hash.md").exists()
    assert not (tmp_path / "review/compound/run-1/unrelated.json").exists()


def test_retrieval_only_interval_reports_unavailable_referenced_run_start(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    append_event(
        workspace.receipts.directory / "retrieval/2026-09-09.jsonl",
        _event("search", "2026-09-09T00:00:00Z", run_id="run-1"),
    )
    result = export_usage(load_workspace(workspace.path), _request(tmp_path))
    assert "usage-run-context-unavailable" in str(result["diagnostics"])
