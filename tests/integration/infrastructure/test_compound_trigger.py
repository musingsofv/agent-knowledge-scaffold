"""Verify store-scoped due decisions and atomic automatic workers."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic

import pytest
import yaml

from agent_knowledge.application.compounding import compound_result
from agent_knowledge.domain.compounding import CompoundDecision, SignalDisposition
from agent_knowledge.domain.configuration import CompoundTrigger
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import compounding
from agent_knowledge.infrastructure.compound_evidence import lifecycle_lock
from agent_knowledge.infrastructure.compounding import (
    ActivityEvent,
    CompoundDue,
    activity_path,
    compound_due,
    configure_trigger,
    finish_run,
    read_activity_log,
    start_run,
)
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.errors import AdapterError
from tests.integration.infrastructure.test_compounding import snapshot, stored_signal, workspace


def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "prompt") -> Workspace:
    """Create a fictional store with a fixed clock and a registered trigger."""
    monkeypatch.setattr(compounding, "_now", lambda: "2026-10-06T10:00:00Z")
    loaded = workspace(tmp_path)
    value = yaml.safe_load(loaded.path.read_text())
    value["setup"] = {"compounding": {"mode": mode, "owner": "shared-store"}}
    loaded.path.write_text(yaml.safe_dump(value))
    loaded = load_workspace(loaded.path)
    configure_trigger(loaded)
    return loaded


def pending(loaded: Workspace) -> Path:
    assert loaded.signal_storage is not None
    return stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")


def automatic(loaded: Workspace, path: Path | None = None) -> ActivityEvent | CompoundDue:
    return start_run(
        loaded,
        selected=(snapshot(path),) if path else (),
        harness="codex",
        session_id="worker-session",
        parent_session_id="parent-session",
        worker_id="worker-exact",
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
        automatic=True,
    )


@pytest.mark.parametrize("mode", ["disabled", "manual", "local-schedule"])
def test_non_prompt_modes_are_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    loaded = configured(tmp_path, monkeypatch, mode)
    pending(loaded)
    assert compound_due(loaded).reason == mode
    assert not compound_due(loaded).due


def test_unconfigured_store_does_not_register_itself(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    assert compound_due(loaded).reason == "unconfigured"
    assert not activity_path(loaded).exists()


def test_empty_then_new_signal_is_immediately_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    assert compound_due(loaded).reason == "empty"
    path = pending(loaded)
    assert compound_due(loaded).due
    run = automatic(loaded)
    assert isinstance(run, ActivityEvent)
    path.unlink()  # Simulate a separate completed owner action, not runtime drain.
    finish_run(
        loaded,
        run_id=run.run_id,
        outcome="No eligible inputs.",
        dispositions=(),
        completion="empty",
    )
    assert compound_due(loaded).reason == "empty"
    pending(loaded)
    assert compound_due(loaded).due


@pytest.mark.parametrize(
    ("completion", "before", "due_time"),
    [
        ("completed", "2026-10-07T09:59:59Z", "2026-10-07T10:00:00Z"),
        ("deferred", "2026-10-07T09:59:59Z", "2026-10-07T10:00:00Z"),
        ("failed", "2026-10-06T10:59:59Z", "2026-10-06T11:00:00Z"),
    ],
)
def test_terminal_classification_controls_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completion: str,
    before: str,
    due_time: str,
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    path = pending(loaded)
    run = automatic(loaded, path)
    assert isinstance(run, ActivityEvent)
    assert run.worker_id == "worker-exact" and run.parent_session_id == "parent-session"
    assert compound_due(loaded).reason == "active"
    finish_run(
        loaded,
        run_id=run.run_id,
        outcome="Recorded outcome.",
        dispositions=(
            SignalDisposition("one", CompoundDecision.DEFER, "Required access unavailable."),
        ),
        completion=completion,
    )
    monkeypatch.setattr(compounding, "_now", lambda: before)
    assert not compound_due(loaded).due
    assert compound_due(loaded).next_due_at == due_time
    monkeypatch.setattr(compounding, "_now", lambda: due_time)
    assert compound_due(loaded).due


def test_concurrent_automatic_workers_and_stale_reminder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    path = pending(loaded)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: automatic(loaded, path), range(2)))
    winners = [item for item in results if isinstance(item, ActivityEvent)]
    assert len(winners) == 1
    loser = next(item for item in results if isinstance(item, CompoundDue))
    assert loser.reason == "active"
    run = winners[0]
    finish_run(
        loaded,
        run_id=run.run_id,
        outcome="Handled.",
        dispositions=(SignalDisposition("one", CompoundDecision.KEEP, "Already covered."),),
        completion="completed",
    )
    before = activity_path(loaded).read_bytes()
    stale = automatic(loaded, path)
    assert isinstance(stale, CompoundDue) and stale.reason == "recent"
    assert activity_path(loaded).read_bytes() == before


def test_due_never_waits_for_lifecycle_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    with lifecycle_lock(activity_path(loaded)):
        began = monotonic()
        assert compound_due(loaded).reason == "busy"
        assert monotonic() - began < 0.5


def test_large_metadata_probe_is_inconclusive_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    assert loaded.signal_storage is not None
    bucket = loaded.signal_storage.signal_root / "shared"
    bucket.mkdir()
    for index in range(150):
        (bucket / f"{index}.txt").touch()
    result = compound_due(loaded)
    assert result.due and result.inbox_probe == "inconclusive"


def test_probe_does_not_read_signal_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = configured(tmp_path, monkeypatch)
    path = pending(loaded)
    path.write_text("malformed signal")
    original = compounding.read_bytes

    def reject_signal(path: Path, **kwargs: object) -> bytes:
        assert path.suffix != ".md"
        return original(path, **kwargs)

    monkeypatch.setattr(compounding, "read_bytes", reject_signal)
    assert compound_due(loaded).due


def test_corrupt_or_future_state_never_authorizes_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    monkeypatch.setattr(compounding, "_now", lambda: "2026-10-06T09:59:59Z")
    assert compound_due(loaded).reason == "clock-regressed"
    path = activity_path(loaded)
    path.write_bytes(path.read_bytes() + b'{"event":')
    assert compound_due(loaded).reason == "invalid-activity-log"
    with pytest.raises(ValidationError, match="incomplete final record"):
        automatic(loaded)


def test_shared_alias_conflict_requires_explicit_compare_and_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    initial = loaded.definition.setup.compounding
    assert initial is not None
    value = yaml.safe_load(loaded.path.read_text())
    value["setup"]["compounding"]["mode"] = "manual"
    other_path = loaded.path.with_name("alias.yaml")
    other_path.write_text(yaml.safe_dump(value))
    alias = load_workspace(other_path)
    assert compound_due(alias).reason == "trigger-conflict"
    with pytest.raises(ValidationError, match="Shared-store trigger differs"):
        configure_trigger(alias)
    configure_trigger(alias, expected=initial)
    assert compound_due(loaded).reason == "trigger-conflict"
    assert compound_due(alias).reason == "manual"
    prior = activity_path(alias).read_bytes()
    configure_trigger(alias)
    assert activity_path(alias).read_bytes() == prior


def test_active_run_never_expires_or_allows_mode_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    run = automatic(loaded, pending(loaded))
    assert isinstance(run, ActivityEvent)
    monkeypatch.setattr(compounding, "_now", lambda: "2027-10-06T10:00:00Z")
    result = compound_due(loaded)
    assert not result.due and result.active_runs[0].worker_id == "worker-exact"
    value = yaml.safe_load(loaded.path.read_text())
    value["setup"]["compounding"]["mode"] = "disabled"
    loaded.path.write_text(yaml.safe_dump(value))
    with pytest.raises(AdapterError, match="unfinished"):
        configure_trigger(
            load_workspace(loaded.path), expected=CompoundTrigger("prompt", "shared-store")
        )


def test_automatic_finish_requires_structured_complete_dispositions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    run = automatic(loaded, pending(loaded))
    assert isinstance(run, ActivityEvent)
    for completion in (None, "completed", "deferred", "empty"):
        with pytest.raises(ValidationError):
            finish_run(
                loaded,
                run_id=run.run_id,
                outcome="Not sufficient.",
                dispositions=(),
                completion=completion,
            )
    assert len(read_activity_log(activity_path(loaded)).active_runs) == 1


def test_cli_shape_exposes_due_and_losing_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    assert compound_result(loaded, {"action": "due"})["reason"] == "empty"
    result = compound_result(
        loaded, {"action": "start", "workspace_id": "repo:orders", "automatic": True}
    )
    assert result["started"] is False
    assert "run_id" not in result
    assert compound_result(loaded, {"action": "status"})["trigger"]["mode"] == "prompt"


def test_rollover_retains_trigger_terminal_pair_and_archive_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    previous = []
    for _ in range(3):
        event = start_run(
            loaded,
            selected=(),
            harness="claude",
            session_id=None,
            automation_id=None,
            workspace_id=loaded.definition.workspace_id,
        )
        assert isinstance(event, ActivityEvent)
        previous.append(event.run_id)
        finish_run(
            loaded,
            run_id=event.run_id,
            outcome="Verified. " * 2000,
            dispositions=(),
            completion="completed",
        )
    log = activity_path(loaded)
    monkeypatch.setattr(compounding, "ACTIVITY_MAX_BYTES", log.stat().st_size * 2)
    recovered = start_run(
        loaded,
        selected=(),
        harness="copilot",
        session_id=None,
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
        recovery_of=previous[0],
        worker_id="replacement-worker",
    )
    assert isinstance(recovered, ActivityEvent)
    state = read_activity_log(log)
    assert state.trigger == CompoundTrigger("prompt", "shared-store")
    assert [item.run_id for item in state.events if item.event != "trigger"] == [
        previous[-1],
        previous[-1],
        recovered.run_id,
    ]
    assert recovered.recovery_of == previous[0]
    assert list((loaded.receipts.directory / "coordination").glob("*.jsonl"))
    finish_run(loaded, run_id=recovered.run_id, outcome="Reconciled.", dispositions=())
    assert compound_due(loaded).reason == "recent"


def test_worker_identity_changes_in_log_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    run = automatic(loaded)
    assert isinstance(run, ActivityEvent)
    finish_run(
        loaded, run_id=run.run_id, outcome="None eligible.", dispositions=(), completion="empty"
    )
    log = activity_path(loaded)
    import json

    records = [json.loads(line) for line in log.read_text().splitlines()]
    records[-1]["worker_id"] = "different-worker"
    log.write_text("".join(json.dumps(record) + "\n" for record in records))
    assert compound_due(loaded).reason == "invalid-activity-log"


def test_stale_config_cannot_overwrite_shared_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    value = yaml.safe_load(loaded.path.read_text())
    value["setup"]["compounding"]["mode"] = "disabled"
    loaded.path.write_text(yaml.safe_dump(value))
    with pytest.raises(AdapterError, match="Configuration changed"):
        configure_trigger(loaded)
    result = automatic(loaded)
    assert isinstance(result, CompoundDue) and result.reason == "workspace-changed"


def test_clock_regression_cannot_be_persisted_as_new_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    value = yaml.safe_load(loaded.path.read_text())
    value["setup"]["compounding"]["mode"] = "disabled"
    loaded.path.write_text(yaml.safe_dump(value))
    monkeypatch.setattr(compounding, "_now", lambda: "2026-10-06T09:00:00Z")
    before = activity_path(loaded).read_bytes()
    with pytest.raises(AdapterError, match="Clock precedes recorded activity"):
        configure_trigger(
            load_workspace(loaded.path), expected=CompoundTrigger("prompt", "shared-store")
        )
    assert activity_path(loaded).read_bytes() == before


def test_backward_record_sequence_is_ambiguous_even_after_clock_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    log = activity_path(loaded)
    original = json.loads(log.read_text())
    original["configured_at"] = "2026-10-06T09:00:00Z"
    with log.open("a") as stream:
        stream.write(json.dumps(original) + "\n")
    monkeypatch.setattr(compounding, "_now", lambda: "2026-10-06T11:00:00Z")
    assert compound_due(loaded).reason == "invalid-activity-log"


def test_missing_receipts_are_quiet_without_a_write_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    loaded.receipts.directory.rmdir()
    assert compound_due(loaded).reason == "receipts-unavailable"
    assert not loaded.receipts.directory.exists()


def test_failed_attempt_cannot_shorten_completed_check_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    pending(loaded)
    first = automatic(loaded)
    assert isinstance(first, ActivityEvent)
    finish_run(
        loaded, run_id=first.run_id, outcome="Checked.", dispositions=(), completion="completed"
    )
    later = start_run(
        loaded,
        selected=(),
        harness="claude",
        session_id=None,
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
    )
    assert isinstance(later, ActivityEvent)
    finish_run(
        loaded,
        run_id=later.run_id,
        outcome="Explicit attempt failed.",
        dispositions=(),
        completion="failed",
    )
    monkeypatch.setattr(compounding, "_now", lambda: "2026-10-06T11:00:00Z")
    assert compound_due(loaded).reason == "recent"


def test_stale_loser_does_not_roll_over_winners_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loaded = configured(tmp_path, monkeypatch)
    path = pending(loaded)
    run = automatic(loaded, path)
    assert isinstance(run, ActivityEvent)
    finish_run(
        loaded,
        run_id=run.run_id,
        outcome="Checked. " * 2000,
        dispositions=(SignalDisposition("one", CompoundDecision.KEEP, "Already covered."),),
        completion="completed",
    )
    log = activity_path(loaded)
    before = log.read_bytes()
    monkeypatch.setattr(compounding, "ACTIVITY_MAX_BYTES", len(before) * 2)
    result = automatic(loaded, path)
    assert isinstance(result, CompoundDue) and result.reason == "recent"
    assert log.read_bytes() == before
    assert not (loaded.receipts.directory / "coordination").exists()
