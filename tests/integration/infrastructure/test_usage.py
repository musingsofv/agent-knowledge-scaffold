"""Concurrent receipt persistence and archive safety across actual filesystem boundaries."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.usage import (
    append_event,
    prune_retrieval,
    read_events,
    write_artifact,
)


def test_concurrent_appends_preserve_every_complete_record(tmp_path: Path) -> None:
    path = tmp_path / "usage" / "retrieval" / "2026-09-14.jsonl"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(
            pool.map(
                lambda index: append_event(path, {"id": index, "description": "x" * 5000}),
                range(80),
            )
        )
    result = read_events(path)
    assert result.diagnostics == ()
    assert {event["id"] for event in result.records} == set(range(80))
    assert len(path.read_bytes().splitlines()) == 80


@pytest.mark.parametrize("tail", [b'{"id": 2}', b'{"id":', b'{"id": }\n', b'{"id": 1,"id":2}\n'])
def test_torn_or_malformed_tail_is_not_extended_or_counted(tmp_path: Path, tail: bytes) -> None:
    path = tmp_path / "events.jsonl"
    original = b'{"id":1}\n' + tail
    path.write_bytes(original)
    loaded = read_events(path)
    assert loaded.records == ({"id": 1},)
    assert len(loaded.diagnostics) == 1
    with pytest.raises(AdapterError, match="final usage record"):
        append_event(path, {"id": 3})
    assert path.read_bytes() == original


def test_invalid_middle_record_is_reported_without_losing_later_complete_evidence(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"id":1}\nnot json\n{"id":3}\n')
    loaded = read_events(path)
    assert loaded.records == ({"id": 1}, {"id": 3})
    assert loaded.diagnostics[0].code == "usage-invalid-record"


def test_snapshots_are_immutable_and_exact_retries_are_safe(tmp_path: Path) -> None:
    path = tmp_path / "compound" / "run" / "inputs" / "hash.md"
    data = b"---\nkind: concept\n---\nExact signal bytes.\n"
    write_artifact(path, data)
    write_artifact(path, data)
    with pytest.raises(AdapterError):
        write_artifact(path, b"different")
    assert path.read_bytes() == data
    assert path.stat().st_nlink == 1


def test_writes_reject_symlink_ancestors_and_files_and_hardlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    for action in (
        lambda: append_event(linked / "events.jsonl", {"id": 1}),
        lambda: write_artifact(linked / "input.md", b"x"),
    ):
        with pytest.raises(AdapterError):
            action()
    existing = outside / "evidence"
    existing.write_text("untouched")
    target = tmp_path / "events.jsonl"
    target.symlink_to(existing)
    with pytest.raises(AdapterError):
        append_event(target, {"id": 1})
    target.unlink()
    os.link(existing, target)
    with pytest.raises(AdapterError):
        append_event(target, {"id": 1})
    assert existing.read_text() == "untouched"


def test_retention_preserves_foreign_correlated_unknown_and_partial_records(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    base: dict[str, object] = {
        "schema_version": "knowledge-retrieval-receipt.v1",
        "recorded_at": "2026-08-01T00:00:00Z",
        "context": {"workspace_id": "ours", "compound_run_id": None},
    }
    events = [
        dict(base, event_id="old"),
        dict(base, event_id="foreign", context={"workspace_id": "other"}),
        dict(base, event_id="active", context={"workspace_id": "ours", "compound_run_id": "run-1"}),
        dict(base, event_id="unknown", schema_version="future.v2"),
        dict(base, event_id="new", recorded_at="2026-09-14T00:00:00Z"),
    ]
    for event in events:
        append_event(path, event)
    cutoff = datetime(2026, 9, 1, tzinfo=UTC)
    assert prune_retrieval(path, workspace_id="ours", cutoff=cutoff) == 1
    assert [item["event_id"] for item in read_events(path).records] == [
        "foreign",
        "active",
        "unknown",
        "new",
    ]
    with path.open("ab") as stream:
        stream.write(b"{")
    before = path.read_bytes()
    assert prune_retrieval(path, workspace_id="ours", cutoff=cutoff) == 0
    assert path.read_bytes() == before


def test_concurrent_retention_and_appends_share_a_persistent_lock(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    base: dict[str, object] = {
        "schema_version": "knowledge-retrieval-receipt.v1",
        "context": {"workspace_id": "ours", "compound_run_id": None},
    }
    append_event(path, dict(base, event_id="old", recorded_at="2026-08-01T00:00:00Z"))

    def write(index: int) -> None:
        append_event(path, dict(base, event_id=index, recorded_at="2026-09-14T00:00:00Z"))

    with ThreadPoolExecutor(max_workers=5) as pool:
        operations = [pool.submit(write, index) for index in range(40)]
        maintenance = pool.submit(
            prune_retrieval, path, workspace_id="ours", cutoff=datetime(2026, 9, 1, tzinfo=UTC)
        )
        for future in operations:
            future.result()
        assert maintenance.result() == 1
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert {event["event_id"] for event in events} == set(range(40))
