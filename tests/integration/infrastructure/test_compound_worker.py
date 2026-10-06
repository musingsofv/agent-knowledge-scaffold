"""Attach exact late provider worker identities without rerunning work."""

from pathlib import Path

import pytest

from agent_knowledge.application.compounding import compound_result
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import compounding
from agent_knowledge.infrastructure.compound_evidence import evidence_records
from agent_knowledge.infrastructure.compounding import (
    ActivityEvent,
    activity_path,
    finish_run,
    read_activity_log,
    record_worker,
    resolve_run,
    start_run,
)
from agent_knowledge.infrastructure.configuration import Workspace
from tests.integration.infrastructure.test_compounding import workspace


def begin(loaded: Workspace, *, parent: str | None = None) -> ActivityEvent:
    event = start_run(
        loaded,
        selected=(),
        harness="claude",
        session_id="exact-session",
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
        parent_session_id=parent,
    )
    assert isinstance(event, ActivityEvent)
    return event


@pytest.mark.parametrize("finished", [False, True])
def test_late_worker_preserves_active_or_finished_lifecycle(tmp_path: Path, finished: bool) -> None:
    loaded = workspace(tmp_path)
    run = begin(loaded)
    if finished:
        finish_run(
            loaded, run_id=run.run_id, outcome="Completed.", dispositions=(), completion="completed"
        )
    initial = read_activity_log(activity_path(loaded))
    result = compound_result(
        loaded,
        {
            "action": "record-worker",
            "run_id": run.run_id,
            "worker_id": "native-agent-12",
            "parent_session_id": "exact-parent",
            "harness": "claude",
        },
    )
    assert result["updated"] is True
    state = read_activity_log(activity_path(loaded))
    assert len(state.events) == len(initial.events) + 1
    assert state.events[-1].event == "worker"
    assert len(state.active_runs) == (0 if finished else 1)
    effective = resolve_run(loaded, run.run_id)
    assert effective.worker_id == "native-agent-12"
    assert effective.parent_session_id == "exact-parent"
    assert effective.session_id == run.session_id
    assert evidence_records(loaded, run.run_id)[-1]["operation"] == "compound.worker"
    if not finished:
        finish_run(
            loaded, run_id=run.run_id, outcome="Completed.", dispositions=(), completion="completed"
        )
        assert not read_activity_log(activity_path(loaded)).active_runs


def test_same_attachment_is_noop_and_parent_can_be_filled_once(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    run = begin(loaded)
    record_worker(loaded, run_id=run.run_id, worker_id="native-agent-12")
    before = activity_path(loaded).read_bytes()
    receipts = evidence_records(loaded, run.run_id)
    _, changed = record_worker(loaded, run_id=run.run_id, worker_id="native-agent-12")
    assert not changed
    assert activity_path(loaded).read_bytes() == before
    assert evidence_records(loaded, run.run_id) == receipts
    record_worker(
        loaded, run_id=run.run_id, worker_id="native-agent-12", parent_session_id="native-parent"
    )
    assert resolve_run(loaded, run.run_id).parent_session_id == "native-parent"


@pytest.mark.parametrize(
    "changes",
    [
        {"worker_id": "another-worker"},
        {"harness": "codex"},
        {"parent_session_id": "another-parent"},
    ],
)
def test_conflicts_preserve_all_evidence(tmp_path: Path, changes: dict[str, str]) -> None:
    loaded = workspace(tmp_path)
    run = begin(loaded, parent="native-parent")
    record_worker(loaded, run_id=run.run_id, worker_id="native-agent-12")
    before = activity_path(loaded).read_bytes()
    receipts = evidence_records(loaded, run.run_id)
    with pytest.raises(ValidationError, match="conflicts"):
        record_worker(loaded, run_id=run.run_id, **{"worker_id": "native-agent-12", **changes})
    assert activity_path(loaded).read_bytes() == before
    assert evidence_records(loaded, run.run_id) == receipts


def test_archived_finished_run_can_receive_late_identity_and_resolve_after_rollover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = workspace(tmp_path)
    first = begin(loaded)
    finish_run(loaded, run_id=first.run_id, outcome="Completed. " * 2000, dispositions=())
    second = begin(loaded)
    finish_run(loaded, run_id=second.run_id, outcome="Completed. " * 2000, dispositions=())
    log = activity_path(loaded)
    monkeypatch.setattr(compounding, "ACTIVITY_MAX_BYTES", log.stat().st_size * 2)
    record_worker(loaded, run_id=first.run_id, worker_id="late-agent")
    assert not any(
        event.event == "start" and event.run_id == first.run_id
        for event in read_activity_log(log).events
    )
    third = begin(loaded)
    finish_run(loaded, run_id=third.run_id, outcome="Completed. " * 2000, dispositions=())
    fourth = begin(loaded)
    assert resolve_run(loaded, first.run_id).worker_id == "late-agent"
    assert read_activity_log(log).active_runs[0].run_id == fourth.run_id
    _, changed = record_worker(loaded, run_id=first.run_id, worker_id="late-agent")
    assert not changed


def test_interrupted_activity_append_can_retry_metadata_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = workspace(tmp_path)
    run = begin(loaded)
    original = compounding._append

    def fail_append(*args: object, **kwargs: object) -> None:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(compounding, "_append", fail_append)
    with pytest.raises(RuntimeError, match="interrupted"):
        record_worker(loaded, run_id=run.run_id, worker_id="late-agent")
    monkeypatch.setattr(compounding, "_append", original)
    _, changed = record_worker(loaded, run_id=run.run_id, worker_id="late-agent")
    assert changed
    assert read_activity_log(activity_path(loaded)).active_runs[0].worker_id == "late-agent"
    assert (
        sum(
            record["operation"] == "compound.worker"
            for record in evidence_records(loaded, run.run_id)
        )
        == 1
    )
    finish_run(loaded, run_id=run.run_id, outcome="Completed.", dispositions=())
