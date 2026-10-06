"""Durable coordination and guarded signal drainage for compounding runs.

The native harness starts the skill; this adapter records what that run did and
performs the final, explicit removal check.  It never decides whether a claim
belongs in canonical knowledge and never contacts GitHub.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic

from agent_knowledge.domain.compounding import (
    PublicationEvidence,
    SignalDisposition,
    SignalSnapshot,
    drainable_snapshots,
    parse_compound_request,
)
from agent_knowledge.domain.configuration import (
    CompoundTrigger,
    compound_trigger_view,
    parse_compound_trigger,
)
from agent_knowledge.domain.schema import parse_signal
from agent_knowledge.domain.signals import validate_signal_origin
from agent_knowledge.domain.usage import read_utc_timestamp
from agent_knowledge.domain.validation import ValidationError

from .compound_evidence import (
    append_compound_event,
    archive_path,
    capture_changes,
    disposition_view,
    evidence_records,
    lifecycle_lock,
    publication_view,
    resolved_owners,
    run_root,
)
from .configuration import (
    SignalStorage,
    Workspace,
    validate_signal_storage,
    workspace_is_current,
    workspace_route,
)
from .documents import load_mapping, parse_document
from .errors import AdapterError
from .filesystem import _identity, open_directory, read_bytes
from .origin import resolve_project
from .signals import signal_bucket
from .usage import append_event, ensure_directory, write_artifact

ACTIVITY_SCHEMA = "compound-activity.v1"
ACTIVITY_MAX_BYTES = 1_048_576
_FINGERPRINT_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    """A validated append-only activity record."""

    event: str
    run_id: str
    workspace_id: str
    active: bool
    started_at: str | None = None
    ended_at: str | None = None
    harness: str | None = None
    session_id: str | None = None
    automation_id: str | None = None
    selected: tuple[SignalSnapshot, ...] = ()
    outcome: str | None = None
    dispositions: tuple[SignalDisposition, ...] = ()
    drained: tuple[str, ...] = ()
    automatic: bool = False
    worker_id: str | None = None
    parent_session_id: str | None = None
    recovery_of: str | None = None
    completion: str | None = None
    trigger: CompoundTrigger | None = None
    configured_at: str | None = None
    recorded_at: str | None = None


@dataclass(frozen=True, slots=True)
class ActivityState:
    """Expose parsed events and runs whose start has no matching end."""

    events: tuple[ActivityEvent, ...]
    active_runs: tuple[ActivityEvent, ...]
    trigger: CompoundTrigger | None = None


@dataclass(frozen=True, slots=True)
class CompoundDue:
    """A bounded advisory result, never a reservation or permission to mutate."""

    due: bool
    reason: str
    next_due_at: str | None = None
    active_runs: tuple[ActivityEvent, ...] = ()
    inbox_probe: str = "not-checked"


@dataclass(frozen=True, slots=True)
class DrainReport:
    """Report partial cleanup without hiding retained signals or errors."""

    drained: tuple[str, ...]
    retained: tuple[str, ...]
    diagnostics: tuple[dict[str, str], ...]


def activity_path(workspace: Workspace) -> Path:
    """Return the log path after validating signal/canonical containment."""
    storage = validate_signal_storage(workspace)
    if storage is None:
        raise ValidationError(
            "signal-storage-required", "signal_storage", "Configure durable signal storage."
        )
    return storage.signal_root / "compound-activity.jsonl"


def read_activity_log(path: Path) -> ActivityState:
    """Read a JSONL log and derive active runs from unmatched events."""
    try:
        raw = read_bytes(path, max_bytes=ACTIVITY_MAX_BYTES)
    except AdapterError as error:
        if error.code == "file-missing":
            return ActivityState((), ())
        raise
    if raw and not raw.endswith(b"\n"):
        raise ValidationError(
            "invalid-activity-log", str(path), "Activity log has an incomplete final record."
        )
    events: list[ActivityEvent] = []
    starts: dict[str, ActivityEvent] = {}
    workers: dict[str, ActivityEvent] = {}
    ended: set[str] = set()
    trigger = None
    last_timestamp: datetime | None = None
    for number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise ValidationError(
                "invalid-activity-log", f"{path}:{number}", "Activity log lines cannot be blank."
            )
        try:
            value = load_mapping(line, path=f"{path}:{number}")
            event = _event_from_mapping(value, f"{path}:{number}")
        except ValidationError as error:
            raise ValidationError(
                error.code, f"{path}:{number}:{error.path}", error.message
            ) from error
        timestamp = _event_timestamp(event)
        if last_timestamp is not None and timestamp < last_timestamp:
            raise ValidationError(
                "invalid-activity-log",
                str(path),
                "Activity timestamps move backwards; inspect clock history.",
            )
        last_timestamp = timestamp
        events.append(event)
        if event.event == "trigger":
            trigger = event.trigger
            continue
        if event.event == "worker":
            prior = starts.get(event.run_id) or workers.get(event.run_id)
            if prior is not None:
                effective = _merge_worker(prior, event)
                if event.run_id in starts:
                    starts[event.run_id] = effective
            workers[event.run_id] = event
            continue
        if event.event == "start":
            if event.run_id in starts:
                raise ValidationError(
                    "invalid-activity-log",
                    f"{path}:{number}.run_id",
                    "A run may have only one start event.",
                )
            starts[event.run_id] = event
        else:
            started = starts.get(event.run_id)
            if started is None:
                raise ValidationError(
                    "invalid-activity-log",
                    f"{path}:{number}.run_id",
                    "An end event must follow its start event.",
                )
            if started.workspace_id != event.workspace_id:
                raise ValidationError(
                    "invalid-activity-log",
                    f"{path}:{number}.workspace_id",
                    "Start and end workspace IDs must match.",
                )
            if (
                started.automatic,
                started.worker_id,
                started.parent_session_id,
                started.recovery_of,
                started.harness,
                started.session_id,
                started.automation_id,
            ) != (
                event.automatic,
                event.worker_id,
                event.parent_session_id,
                event.recovery_of,
                event.harness,
                event.session_id,
                event.automation_id,
            ):
                raise ValidationError(
                    "invalid-activity-log",
                    f"{path}:{number}",
                    "Run identity must match across the terminal pair.",
                )
            assert started.started_at is not None and event.ended_at is not None
            if read_utc_timestamp(event.ended_at, "ended_at") < read_utc_timestamp(
                started.started_at, "started_at"
            ):
                raise ValidationError(
                    "invalid-activity-log", str(path), "End cannot precede start."
                )
            if event.completion in {"completed", "deferred"} and {
                item.id for item in started.selected
            } != {item.signal_id for item in event.dispositions}:
                raise ValidationError(
                    "invalid-activity-log", str(path), "Terminal dispositions are incomplete."
                )
            if event.completion == "empty" and (started.selected or event.dispositions):
                raise ValidationError(
                    "invalid-activity-log", str(path), "Empty completion contains inputs."
                )
            if event.run_id in ended:
                raise ValidationError(
                    "invalid-activity-log",
                    f"{path}:{number}.run_id",
                    "A run may have only one end event.",
                )
            ended.add(event.run_id)
    active = tuple(event for run_id, event in starts.items() if run_id not in ended)
    return ActivityState(tuple(events), active, trigger)


def configure_trigger(
    workspace: Workspace, *, expected: CompoundTrigger | None = None
) -> CompoundTrigger:
    """Register one shared-store agreement; compare-and-swap explicit replacements."""
    configured = workspace.definition.setup.compounding if workspace.definition.setup else None
    if configured is None:
        raise ValidationError(
            "trigger-unconfigured",
            "setup.compounding",
            "Configure the local trigger before registration.",
        )
    path = activity_path(workspace)
    with lifecycle_lock(path):
        _rollover_activity(workspace, path)
        state = read_activity_log(path)
        if not workspace_is_current(workspace):
            raise AdapterError(
                "workspace-changed",
                str(workspace.path),
                "Configuration changed before trigger registration.",
            )
        ensure_directory(workspace.receipts.directory)
        if state.trigger == configured:
            return configured
        if state.active_runs:
            raise AdapterError(
                "compound-active", str(path), "Inspect unfinished work before changing its trigger."
            )
        if state.trigger != expected:
            raise ValidationError(
                "trigger-conflict",
                "expected_trigger",
                "Shared-store trigger differs; inspect and explicitly reconcile the "
                "recorded agreement.",
            )
        _append(
            path,
            _event_mapping(
                ActivityEvent(
                    event="trigger",
                    run_id="",
                    workspace_id=workspace.definition.workspace_id,
                    active=False,
                    trigger=configured,
                    configured_at=_now(),
                )
            ),
        )
        return configured


def compound_due(workspace: Workspace) -> CompoundDue:
    """Perform a bounded nonblocking advisory check without claim-body reads."""
    try:
        path = activity_path(workspace)
        with lifecycle_lock(path, blocking=False):
            return _due_locked(workspace, read_activity_log(path))
    except (AdapterError, ValidationError, OSError) as error:
        code = error.code if isinstance(error, AdapterError | ValidationError) else "io-unavailable"
        return CompoundDue(False, "busy" if code == "usage-lock-busy" else code)


def _due_locked(workspace: Workspace, state: ActivityState) -> CompoundDue:
    configured = workspace.definition.setup.compounding if workspace.definition.setup else None
    if configured is None or state.trigger is None:
        return CompoundDue(False, "unconfigured")
    if configured != state.trigger:
        return CompoundDue(False, "trigger-conflict")
    if configured.mode != "prompt":
        return CompoundDue(False, configured.mode)
    if state.active_runs:
        return CompoundDue(False, "active", active_runs=state.active_runs)
    now = read_utc_timestamp(_now(), "clock")
    timestamps = [
        read_utc_timestamp(timestamp, "activity.timestamp")
        for event in state.events
        for timestamp in (event.started_at, event.ended_at, event.configured_at, event.recorded_at)
        if timestamp is not None
    ]
    if any(timestamp > now for timestamp in timestamps):
        return CompoundDue(False, "clock-regressed")
    # Retain the completed-check interval even when a later explicit failed
    # attempt adds a retry bound. A subsequent completion supersedes failures.
    relevant = [
        event
        for event in state.events
        if event.event == "end" and event.completion in {"completed", "deferred", "failed"}
    ]
    completed = next(
        (event for event in reversed(relevant) if event.completion in {"completed", "deferred"}),
        None,
    )
    deadlines: list[tuple[datetime, str]] = []
    if completed is not None:
        deadlines.append(
            (
                read_utc_timestamp(completed.ended_at, "ended_at")
                + timedelta(seconds=configured.interval_seconds),
                "recent",
            )
        )
    if relevant and relevant[-1].completion == "failed":
        deadlines.append(
            (
                read_utc_timestamp(relevant[-1].ended_at, "ended_at")
                + timedelta(seconds=configured.retry_seconds),
                "retry-wait",
            )
        )
    if deadlines:
        next_due, reason = max(deadlines)
        if now < next_due:
            return CompoundDue(
                False,
                reason,
                next_due_at=next_due.isoformat(timespec="seconds").replace("+00:00", "Z"),
            )
    try:
        with open_directory(workspace.receipts.directory) as descriptor:
            if not os.access(".", os.W_OK | os.X_OK, dir_fd=descriptor):
                return CompoundDue(False, "receipts-unavailable")
    except (AdapterError, OSError):
        return CompoundDue(False, "receipts-unavailable")
    probe = _probe_inbox(workspace)
    return CompoundDue(probe != "empty", "empty" if probe == "empty" else "due", inbox_probe=probe)


def _probe_inbox(workspace: Workspace, *, budget: int = 128) -> str:
    """Bound metadata examination; unknown candidates belong to the worker."""
    storage = validate_signal_storage(workspace)
    assert storage is not None
    project = resolve_project(workspace)
    buckets = [signal_bucket(storage, None)]
    if project is not None:
        buckets.append(signal_bucket(storage, project))
    seen = 0
    for bucket in buckets:
        try:
            with open_directory(bucket) as descriptor, os.scandir(descriptor) as entries:
                for entry in entries:
                    seen += 1
                    if seen > budget:
                        return "inconclusive"
                    if entry.name.endswith((".md", ".yaml", ".yml")):
                        return "potential"
        except AdapterError as error:
            if error.code not in {"file-missing", "directory-missing"}:
                raise
        except FileNotFoundError:
            continue
    return "empty"


def start_run(
    workspace: Workspace,
    *,
    selected: tuple[SignalSnapshot, ...],
    harness: str | None,
    session_id: str | None,
    automation_id: str | None,
    workspace_id: str,
    automatic: bool = False,
    worker_id: str | None = None,
    parent_session_id: str | None = None,
    recovery_of: str | None = None,
) -> ActivityEvent | CompoundDue:
    """Validate and archive exact selected inputs before recording an active run."""
    began = monotonic()
    path = activity_path(workspace)
    with lifecycle_lock(path):
        state = read_activity_log(path)
        if automatic:
            if not workspace_is_current(workspace):
                return CompoundDue(False, "workspace-changed")
            eligibility = _due_locked(workspace, state)
            if not eligibility.due:
                return eligibility
        if recovery_of is not None:
            prior = resolve_run(workspace, recovery_of)
            if any(event.run_id == prior.run_id for event in state.active_runs) or not any(
                record.get("operation") == "compound.finish"
                for record in evidence_records(workspace, prior.run_id)
            ):
                raise ValidationError(
                    "recovery-unresolved",
                    "recovery_of",
                    "Reconcile and finish the prior run before recovery.",
                )
        if state.active_runs:
            active_ids = ", ".join(event.run_id for event in state.active_runs)
            raise AdapterError(
                "compound-active",
                str(path),
                f"An unfinished run is recorded ({active_ids}); inspect before retrying.",
                exit_code=2,
            )
        if workspace_id != workspace.definition.workspace_id:
            raise ValidationError(
                "workspace-mismatch",
                "workspace_id",
                "The run workspace ID must equal the selected configuration.",
            )
        _rollover_activity(workspace, path)
        storage = validate_signal_storage(workspace)
        assert storage is not None
        project = resolve_project(workspace)
        if len({item.id for item in selected}) != len(selected) or len(
            {item.path for item in selected}
        ) != len(selected):
            raise ValidationError(
                "duplicate-value", "selected", "Selected IDs and paths must be unique."
            )
        inputs: list[tuple[SignalSnapshot, bytes]] = []
        for snapshot in selected:
            target = _target(storage.signal_root, snapshot.path)
            data = _read_target(target)
            _validate_drain_target(workspace, storage, project, target, snapshot, data)
            if _fingerprint(data) != snapshot.fingerprint:
                raise AdapterError(
                    "signal-changed",
                    str(target),
                    "Selected bytes changed before archival; refresh selection.",
                )
            inputs.append((snapshot, data))
        event = ActivityEvent(
            event="start",
            run_id="compound-" + secrets.token_hex(16),
            workspace_id=workspace_id,
            active=True,
            started_at=_now(),
            harness=harness,
            session_id=session_id,
            automation_id=automation_id,
            selected=selected,
            automatic=automatic,
            worker_id=worker_id,
            parent_session_id=parent_session_id,
            recovery_of=recovery_of,
        )
        artifacts: list[dict[str, object]] = []
        for snapshot, data in inputs:
            target = archive_path(workspace, event.run_id, snapshot)
            write_artifact(target, data)
            artifacts.append(
                {
                    "signal_id": snapshot.id,
                    "path": str(target.relative_to(run_root(workspace, event.run_id))),
                    "fingerprint": snapshot.fingerprint,
                }
            )
        write_artifact(
            run_root(workspace, event.run_id) / "start.json",
            json.dumps(
                {**_event_mapping(event), "configuration_route": workspace_route(workspace)},
                sort_keys=True,
            ).encode(),
        )
        append_compound_event(
            workspace,
            event.run_id,
            "compound.start",
            context=_context(event),
            payload={
                "selected": [_snapshot_view(item) for item in selected],
                "started_at": event.started_at,
                "artifacts": {"signal_snapshots": artifacts},
            },
            began=began,
        )
        _append(path, _event_mapping(event))
        return event


def resolve_run(workspace: Workspace, run_id: str) -> ActivityEvent:
    """Resolve recorded context from mandatory archive, independent of log rollover."""
    path = run_root(workspace, run_id) / "start.json"
    raw = read_bytes(path, max_bytes=ACTIVITY_MAX_BYTES)
    value = load_mapping(raw, path=str(path))
    event = _event_from_mapping(value, str(path))
    if (
        event.event != "start"
        or event.run_id != run_id
        or event.workspace_id != workspace.definition.workspace_id
    ):
        raise ValidationError(
            "workspace-mismatch",
            "run_id",
            "Recorded run does not belong to the selected workspace.",
        )
    if value.get("configuration_route") != workspace_route(workspace):
        raise ValidationError(
            "configuration-route-mismatch",
            "run_id",
            (
                "The run configuration route changed; retain inputs and restore the "
                "original selection."
            ),
        )
    if not workspace_is_current(workspace):
        raise AdapterError(
            "workspace-changed", str(workspace.path), "Configuration changed during run resolution."
        )
    records = evidence_records(workspace, run_id)
    if not any(record.get("operation") == "compound.start" for record in records):
        raise AdapterError(
            "compound-start-incomplete", str(path), "Run start evidence is incomplete."
        )
    for record in records:
        if record.get("operation") == "compound.worker":
            attachment = record.get("worker")
            if not isinstance(attachment, Mapping):
                raise ValidationError(
                    "invalid-worker-record", str(path), "Worker evidence is malformed."
                )
            worker = _event_from_mapping(attachment, str(path))
            if worker.event != "worker":
                raise ValidationError(
                    "invalid-worker-record", str(path), "Expected worker metadata."
                )
            event = _merge_worker(event, worker)
    return event


def record_worker(
    workspace: Workspace,
    *,
    run_id: str,
    worker_id: str,
    parent_session_id: str | None = None,
    harness: str | None = None,
) -> tuple[ActivityEvent, bool]:
    """Attach a late native worker handle without changing lifecycle or outcomes."""
    began = monotonic()
    path = activity_path(workspace)
    with lifecycle_lock(path):
        state = read_activity_log(path)
        original = resolve_run(workspace, run_id)
        active = next((event for event in state.active_runs if event.run_id == run_id), None)
        records = evidence_records(workspace, run_id)
        if active is None and not any(
            record.get("operation") == "compound.finish" for record in records
        ):
            raise AdapterError(
                "compound-run-missing",
                str(path),
                "Run coordination is incomplete; inspect before attaching a worker.",
            )
        worker = ActivityEvent(
            event="worker",
            run_id=run_id,
            workspace_id=original.workspace_id,
            active=False,
            recorded_at=_now(),
            worker_id=worker_id,
            parent_session_id=parent_session_id
            if parent_session_id is not None
            else original.parent_session_id,
            harness=harness if harness is not None else original.harness,
        )
        # Reuse the public strict identity codec before persisting caller metadata.
        worker = _event_from_mapping(_event_mapping(worker), str(path))
        effective = _merge_worker(original, worker)
        if effective == original and (active is None or active == effective):
            return effective, False
        if state.events and _event_timestamp(worker) < _event_timestamp(state.events[-1]):
            raise AdapterError(
                "clock-regressed",
                str(path),
                "Clock precedes recorded activity; inspect before writing.",
            )
        _rollover_activity(workspace, path)
        if effective != original:
            append_compound_event(
                workspace,
                run_id,
                "compound.worker",
                context=_context(original),
                payload={"worker": _event_mapping(worker)},
                began=began,
            )
        # If an earlier attachment archived successfully but its activity append
        # was interrupted, the identical retry repairs only that metadata append.
        _append(path, _event_mapping(worker))
        return effective, True


def _merge_worker(original: ActivityEvent, worker: ActivityEvent) -> ActivityEvent:
    if original.run_id != worker.run_id or original.workspace_id != worker.workspace_id:
        raise ValidationError(
            "worker-context-mismatch", "run_id", "Worker metadata belongs to another run."
        )
    for field in ("harness", "worker_id", "parent_session_id"):
        prior = getattr(original, field)
        supplied = getattr(worker, field)
        if prior is not None and supplied != prior:
            raise ValidationError(
                "worker-context-mismatch",
                field,
                "Worker metadata conflicts with the recorded identity.",
            )
    return replace(
        original,
        harness=worker.harness,
        worker_id=worker.worker_id,
        parent_session_id=worker.parent_session_id,
    )


def finish_run(
    workspace: Workspace,
    *,
    run_id: str,
    outcome: str,
    dispositions: tuple[SignalDisposition, ...],
    completion: str | None = None,
) -> ActivityEvent:
    """Record agent-reported outcome while deriving actual drainage from tool evidence."""
    began = monotonic()
    path = activity_path(workspace)
    with lifecycle_lock(path):
        active = _active_run(workspace, run_id)
        if active.automatic and completion is None:
            raise ValidationError(
                "missing-field", "completion", "Automatic runs require a terminal classification."
            )
        if completion is not None and completion not in {
            "completed",
            "deferred",
            "failed",
            "empty",
        }:
            raise ValidationError("invalid-value", "completion", "Unknown terminal classification.")
        selected_ids = {item.id for item in active.selected}
        disposition_ids = {item.signal_id for item in dispositions}
        if completion in {"completed", "deferred"} and selected_ids != disposition_ids:
            raise ValidationError(
                "incomplete-dispositions",
                "dispositions",
                "Classified completion requires exactly one disposition per selected input.",
            )
        if completion == "empty" and (active.selected or dispositions):
            raise ValidationError(
                "invalid-completion",
                "completion",
                "Empty completion requires no selected inputs or dispositions.",
            )
        ended_at = _now()
        assert active.started_at is not None
        if read_utc_timestamp(ended_at, "ended_at") < read_utc_timestamp(
            active.started_at, "started_at"
        ):
            raise AdapterError(
                "clock-regressed",
                str(path),
                "Clock precedes the active run; inspect before finishing.",
            )
        records = evidence_records(workspace, run_id)
        drained = _recorded_drained(records)
        retained = sorted({snapshot.id for snapshot in active.selected} - set(drained))
        event = ActivityEvent(
            event="end",
            run_id=run_id,
            workspace_id=active.workspace_id,
            active=False,
            ended_at=ended_at,
            harness=active.harness,
            session_id=active.session_id,
            automation_id=active.automation_id,
            outcome=outcome,
            dispositions=dispositions,
            drained=drained,
            automatic=active.automatic,
            worker_id=active.worker_id,
            parent_session_id=active.parent_session_id,
            recovery_of=active.recovery_of,
            completion=completion,
        )
        existing_finish = next(
            (record for record in records if record.get("operation") == "compound.finish"), None
        )
        if existing_finish is not None:
            raise AdapterError(
                "compound-finish-incomplete",
                str(path),
                "Finish evidence exists but coordination is unfinished; inspect recovery.",
            )
        append_compound_event(
            workspace,
            run_id,
            "compound.finish",
            context=_context(active),
            began=began,
            payload={
                "agent_report": {
                    "outcome": outcome,
                    "completion": completion,
                    "verification": "agent-reported",
                    "dispositions": [disposition_view(item) for item in dispositions],
                },
                "tool_result": {
                    "drained": list(drained),
                    "retained": retained,
                    "unresolved": bool(retained),
                },
                "ended_at": event.ended_at,
                "evidence_event_ids": [record.get("event_id") for record in records],
            },
        )
        _append(path, _event_mapping(event))
        return event


def _active_run(workspace: Workspace, run_id: str) -> ActivityEvent:
    recorded = resolve_run(workspace, run_id)
    state = read_activity_log(activity_path(workspace))
    active = next((event for event in state.active_runs if event.run_id == run_id), None)
    if active is None:
        raise AdapterError(
            "compound-run-missing",
            str(activity_path(workspace)),
            "No unfinished run with that ID is recorded; inspect the activity log.",
            exit_code=2,
        )
    if active != recorded:
        raise AdapterError(
            "compound-run-mismatch",
            str(activity_path(workspace)),
            "Run archive and activity context differ.",
        )
    return active


def _context(event: ActivityEvent) -> dict[str, object]:
    return {
        "workspace_id": event.workspace_id,
        "harness": event.harness,
        "session_id": event.session_id,
        "compound_run_id": event.run_id,
    }


def _snapshot_view(snapshot: SignalSnapshot) -> dict[str, object]:
    return {"id": snapshot.id, "path": snapshot.path, "fingerprint": snapshot.fingerprint}


def _recorded_drained(records: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    drained: set[str] = set()
    for record in records:
        if record.get("operation") == "compound.drain.removed":
            signal_id = record.get("signal_id")
            if isinstance(signal_id, str):
                drained.add(signal_id)
        if record.get("operation") == "compound.drain":
            result = record.get("tool_result")
            if isinstance(result, dict) and isinstance(result.get("drained"), list):
                drained.update(item for item in result["drained"] if isinstance(item, str))
    return tuple(sorted(drained))


def event_view(event: ActivityEvent) -> dict[str, object]:
    """Render an activity event without exposing signal claim bodies."""
    return _event_mapping(event)


def drain_signals(
    workspace: Workspace,
    snapshots: tuple[SignalSnapshot, ...],
    dispositions: tuple[SignalDisposition, ...],
    *,
    run_id: str,
    publication_verified: bool,
    publication: PublicationEvidence | None = None,
) -> DrainReport:
    """Persist intent, verify immutable archives, and remove only eligible unchanged inputs."""
    began = monotonic()
    path = activity_path(workspace)
    with lifecycle_lock(path):
        active = _active_run(workspace, run_id)
        if set(snapshots) != set(active.selected) or len(snapshots) != len(active.selected):
            raise ValidationError(
                "selection-mismatch",
                "selected",
                "Drain snapshots must equal the recorded run selection.",
            )
        if any(
            item.signal_id not in {snapshot.id for snapshot in snapshots} for item in dispositions
        ):
            raise ValidationError(
                "foreign-disposition",
                "dispositions",
                "Disposition does not belong to the run selection.",
            )
        records = evidence_records(workspace, run_id)
        if any(record.get("operation") == "compound.finish" for record in records):
            raise AdapterError(
                "compound-finished",
                str(path),
                "The run has already finished; no further drainage is allowed.",
            )
        already_drained = set(_recorded_drained(records))
        storage = validate_signal_storage(workspace)
        assert storage is not None
        project = resolve_project(workspace)
        attempt_id = secrets.token_hex(16)
        context = _context(active)
        owner_results = resolved_owners(workspace, dispositions)
        changes = capture_changes(workspace, run_id, attempt_id, publication)
        report_payload: dict[str, object] = {
            "attempt_id": attempt_id,
            "agent_report": {
                "dispositions": [disposition_view(item) for item in dispositions],
                "publication": publication_view(publication, verified=publication_verified),
            },
            "owner_resolution": owner_results,
            "artifacts": {"changes": changes},
        }
        # A failure here must precede every unlink. Mandatory even with receipts disabled.
        append_compound_event(
            workspace,
            run_id,
            "compound.drain.intent",
            context=context,
            payload={**report_payload, "selected": [_snapshot_view(item) for item in snapshots]},
            began=began,
        )
        unresolved_owners = {
            str(item["signal_id"])
            for item in owner_results
            if item["status"] == "unresolved"
            and any(
                d.signal_id == item["signal_id"]
                and d.decision.value in {"create", "update", "delete-retire"}
                for d in dispositions
            )
        }
        for disposition in dispositions:
            for owner in disposition.owners:
                source = next((item for item in workspace.sources if item.id == owner.source), None)
                if (
                    source is not None
                    and source.publication is not None
                    and (
                        publication is None
                        or publication.repository != source.publication.repository
                    )
                ):
                    unresolved_owners.add(disposition.signal_id)
        current: dict[str, str] = {}
        errors: list[dict[str, str]] = [
            {
                "signal_id": identifier,
                "code": "owner-unavailable",
                "message": "Owner source or its configured publication route is unresolved.",
            }
            for identifier in sorted(unresolved_owners)
        ]
        for snapshot in snapshots:
            if snapshot.id in already_drained:
                errors.append(
                    {
                        "signal_id": snapshot.id,
                        "code": "signal-already-drained",
                        "message": "Earlier tool evidence records removal; no repeat removal.",
                    }
                )
                continue
            try:
                archived = read_bytes(
                    archive_path(workspace, run_id, snapshot), max_bytes=8_388_608
                )
                if _fingerprint(archived) != snapshot.fingerprint:
                    raise AdapterError(
                        "signal-archive-corrupt",
                        snapshot.path,
                        "Archived bytes do not match selection; input retained.",
                    )
                target = _target(storage.signal_root, snapshot.path)
                data = _read_target(target)
                _validate_drain_target(workspace, storage, project, target, snapshot, data)
                current[snapshot.id] = _fingerprint(data)
            except (AdapterError, ValidationError) as error:
                if error.code == "file-missing" and any(
                    record.get("operation") == "compound.drain.intent" for record in records
                ):
                    errors.append(
                        {
                            "signal_id": snapshot.id,
                            "code": "drain-result-unknown",
                            "message": "Missing input after intent; removal is unconfirmed.",
                        }
                    )
                else:
                    errors.append(_diagnostic(snapshot.id, error))
        try:
            candidates = drainable_snapshots(
                snapshots,
                dispositions,
                current_fingerprints={
                    key: value for key, value in current.items() if key not in unresolved_owners
                },
                publication_verified=publication_verified,
                publication=publication,
            )
        except ValueError as error:
            raise ValidationError("invalid-drain-request", "signals", str(error)) from error
        drained: list[str] = []
        retained = {snapshot.id for snapshot in snapshots} - already_drained
        for snapshot in candidates:
            try:
                if (
                    _fingerprint(
                        read_bytes(archive_path(workspace, run_id, snapshot), max_bytes=8_388_608)
                    )
                    != snapshot.fingerprint
                ):
                    raise AdapterError(
                        "signal-archive-corrupt",
                        snapshot.path,
                        "Archived bytes changed before removal; input retained.",
                    )
                target = _target(storage.signal_root, snapshot.path)
                _unlink_verified_file(target, expected=snapshot.fingerprint)
                drained.append(snapshot.id)
                retained.discard(snapshot.id)
                append_compound_event(
                    workspace,
                    run_id,
                    "compound.drain.removed",
                    context=context,
                    payload={
                        "attempt_id": attempt_id,
                        "signal_id": snapshot.id,
                        "fingerprint": snapshot.fingerprint,
                    },
                    began=began,
                )
            except (AdapterError, ValidationError) as error:
                errors.append(_diagnostic(snapshot.id, error))
                # If removal succeeded but acknowledgement failed, stop rather than lose
                # evidence for more inputs. The durable intent exposes crash ambiguity.
                if snapshot.id in drained:
                    break
            except KeyboardInterrupt:
                errors.append(
                    {
                        "signal_id": snapshot.id,
                        "code": "drain-interrupted",
                        "message": "Drain interrupted; inspect intent and results before retry.",
                    }
                )
                break
        report = DrainReport(tuple(drained), tuple(sorted(retained)), tuple(errors))
        append_compound_event(
            workspace,
            run_id,
            "compound.drain",
            context=context,
            began=began,
            payload={
                **report_payload,
                "tool_result": {
                    "drained": list(report.drained),
                    "already_drained": sorted(already_drained),
                    "retained": list(report.retained),
                    "diagnostics": list(report.diagnostics),
                },
            },
        )
        return report


def _event_from_mapping(value: Mapping[str, object], path: str) -> ActivityEvent:
    """Decode the small runtime record without accepting arbitrary payloads."""
    schema = value.get("schema")
    event = value.get("event")
    if schema != ACTIVITY_SCHEMA:
        raise ValidationError(
            "unsupported-schema", f"{path}.schema", f"Expected {ACTIVITY_SCHEMA}."
        )
    if event == "trigger":
        if set(value) != {"schema", "event", "workspace_id", "trigger", "configured_at"}:
            raise ValidationError("invalid-activity-log", path, "Invalid trigger record fields.")
        configured_at = _text(value.get("configured_at"), f"{path}.configured_at")
        read_utc_timestamp(configured_at, f"{path}.configured_at")
        return ActivityEvent(
            event="trigger",
            run_id="",
            workspace_id=_text(value.get("workspace_id"), f"{path}.workspace_id"),
            active=False,
            trigger=parse_compound_trigger(value.get("trigger")),
            configured_at=configured_at,
        )
    if event == "worker":
        required = {
            "schema",
            "event",
            "run_id",
            "workspace_id",
            "recorded_at",
            "worker_id",
            "harness",
        }
        if not required <= set(value) or set(value) - required - {"parent_session_id"}:
            raise ValidationError("invalid-activity-log", path, "Invalid worker record fields.")
        recorded_at = _text(value.get("recorded_at"), f"{path}.recorded_at")
        read_utc_timestamp(recorded_at, f"{path}.recorded_at")
        identity = parse_compound_request(
            {
                "action": "record-worker",
                "run_id": value["run_id"],
                "worker_id": value["worker_id"],
                "parent_session_id": value.get("parent_session_id"),
            }
        )
        harness = _text(value.get("harness"), f"{path}.harness")
        if harness not in {"codex", "claude", "copilot"}:
            raise ValidationError(
                "invalid-activity-log",
                path,
                "Worker attachment requires the exact supported provider.",
            )
        return ActivityEvent(
            event="worker",
            run_id=_text(value["run_id"], f"{path}.run_id"),
            workspace_id=_text(value["workspace_id"], f"{path}.workspace_id"),
            active=False,
            recorded_at=recorded_at,
            harness=harness,
            worker_id=identity.worker_id,
            parent_session_id=identity.parent_session_id,
        )
    if event not in {"start", "end"}:
        raise ValidationError(
            "invalid-activity-log", f"{path}.event", "Expected start, end, trigger or worker."
        )
    allowed = {
        "schema",
        "configuration_route",
        "event",
        "run_id",
        "workspace_id",
        "active",
        "started_at",
        "ended_at",
        "harness",
        "session_id",
        "automation_id",
        "selected",
        "outcome",
        "dispositions",
        "drained",
        "automatic",
        "worker_id",
        "parent_session_id",
        "recovery_of",
        "completion",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValidationError(
            "unknown-field", f"{path}.{sorted(unknown)[0]}", "Field is not supported."
        )
    run_id = _text(value.get("run_id"), f"{path}.run_id")
    workspace_id = _text(value.get("workspace_id"), f"{path}.workspace_id")
    active = value.get("active")
    if not isinstance(active, bool) or active != (event == "start"):
        raise ValidationError(
            "invalid-activity-log", f"{path}.active", "active must match the event type."
        )
    started_at = _optional_text(value.get("started_at"), f"{path}.started_at")
    ended_at = _optional_text(value.get("ended_at"), f"{path}.ended_at")
    if event == "start" and not started_at:
        raise ValidationError(
            "invalid-activity-log", f"{path}.started_at", "Start requires started_at."
        )
    if event == "end" and not ended_at:
        raise ValidationError("invalid-activity-log", f"{path}.ended_at", "End requires ended_at.")
    for timestamp in (started_at, ended_at):
        if timestamp is not None:
            read_utc_timestamp(timestamp, path)
    automatic = value.get("automatic", False)
    if not isinstance(automatic, bool):
        raise ValidationError("invalid-activity-log", path, "automatic must be boolean.")
    completion = _optional_text(value.get("completion"), f"{path}.completion")
    if completion is not None and completion not in {"completed", "deferred", "failed", "empty"}:
        raise ValidationError("invalid-activity-log", path, "Unknown terminal classification.")
    if event == "start" and completion is not None:
        raise ValidationError("invalid-activity-log", path, "Start cannot have a completion.")
    if event == "end" and automatic and completion is None:
        raise ValidationError("invalid-activity-log", path, "Automatic end requires completion.")
    selected = _snapshots(value.get("selected", []), f"{path}.selected")
    dispositions = _dispositions(value.get("dispositions", []), f"{path}.dispositions")
    drained = _strings(value.get("drained", []), f"{path}.drained")
    outcome = _optional_text(value.get("outcome"), f"{path}.outcome")
    if event == "end" and outcome is None:
        raise ValidationError("invalid-activity-log", f"{path}.outcome", "End requires outcome.")
    if event == "start" and (ended_at is not None or outcome is not None):
        raise ValidationError(
            "invalid-activity-log", path, "Start events cannot contain end fields."
        )
    if event == "start" and dispositions:
        raise ValidationError(
            "invalid-activity-log",
            f"{path}.dispositions",
            "Start events cannot contain dispositions.",
        )
    if event == "start" and drained:
        raise ValidationError(
            "invalid-activity-log", f"{path}.drained", "Start events cannot contain drained IDs."
        )
    return ActivityEvent(
        automatic=automatic,
        completion=completion,
        worker_id=_optional_text(value.get("worker_id"), f"{path}.worker_id"),
        parent_session_id=_optional_text(
            value.get("parent_session_id"), f"{path}.parent_session_id"
        ),
        recovery_of=_optional_text(value.get("recovery_of"), f"{path}.recovery_of"),
        event=str(event),
        run_id=run_id,
        workspace_id=workspace_id,
        active=active,
        started_at=started_at,
        ended_at=ended_at,
        harness=_optional_text(value.get("harness"), f"{path}.harness"),
        session_id=_optional_text(value.get("session_id"), f"{path}.session_id"),
        automation_id=_optional_text(value.get("automation_id"), f"{path}.automation_id"),
        selected=selected,
        outcome=outcome,
        dispositions=dispositions,
        drained=drained,
    )


def _event_mapping(event: ActivityEvent) -> dict[str, object]:
    if event.event == "trigger":
        assert event.trigger is not None
        return {
            "schema": ACTIVITY_SCHEMA,
            "event": "trigger",
            "workspace_id": event.workspace_id,
            "trigger": compound_trigger_view(event.trigger),
            "configured_at": event.configured_at,
        }
    if event.event == "worker":
        result: dict[str, object] = {
            "schema": ACTIVITY_SCHEMA,
            "event": "worker",
            "run_id": event.run_id,
            "workspace_id": event.workspace_id,
            "recorded_at": event.recorded_at,
            "harness": event.harness,
            "worker_id": event.worker_id,
        }
        if event.parent_session_id is not None:
            result["parent_session_id"] = event.parent_session_id
        return result
    value: dict[str, object] = {
        "schema": ACTIVITY_SCHEMA,
        "event": event.event,
        "run_id": event.run_id,
        "workspace_id": event.workspace_id,
        "active": event.active,
    }
    for key, item in (
        ("started_at", event.started_at),
        ("ended_at", event.ended_at),
        ("harness", event.harness),
        ("session_id", event.session_id),
        ("automation_id", event.automation_id),
        ("outcome", event.outcome),
        ("completion", event.completion),
        ("worker_id", event.worker_id),
        ("parent_session_id", event.parent_session_id),
        ("recovery_of", event.recovery_of),
    ):
        if item is not None:
            value[key] = item
    if event.automatic:
        value["automatic"] = True
    if event.selected:
        value["selected"] = [
            {"id": item.id, "path": item.path, "fingerprint": item.fingerprint}
            for item in event.selected
        ]
    if event.dispositions:
        value["dispositions"] = [disposition_view(item) for item in event.dispositions]
    if event.drained:
        value["drained"] = list(event.drained)
    return value


def _event_timestamp(event: ActivityEvent) -> datetime:
    timestamp = (
        event.configured_at
        if event.event == "trigger"
        else (event.started_at if event.event == "start" else event.ended_at)
    )
    if event.event == "worker":
        timestamp = event.recorded_at
    return read_utc_timestamp(timestamp, "activity.timestamp")


def _append(path: Path, value: Mapping[str, object]) -> None:
    """Serialize the small coordination append separately from analytics evidence."""
    event = _event_from_mapping(value, str(path))
    state = read_activity_log(path)
    if state.events and _event_timestamp(event) < _event_timestamp(state.events[-1]):
        raise AdapterError(
            "clock-regressed",
            str(path),
            "Clock precedes recorded activity; inspect before writing.",
        )
    payload_size = len(json.dumps(value).encode())
    if payload_size > ACTIVITY_MAX_BYTES // 4:
        raise AdapterError(
            "activity-event-too-large",
            str(path),
            "Coordination event exceeds its bounded size; use a smaller batch.",
        )
    append_event(path, dict(value))


def _rollover_activity(workspace: Workspace, path: Path) -> None:
    """Archive completed coordination history before the bounded reader can fill."""
    try:
        raw = read_bytes(path, max_bytes=ACTIVITY_MAX_BYTES)
    except AdapterError as error:
        if error.code == "file-missing":
            return
        raise
    if len(raw) < ACTIVITY_MAX_BYTES // 4:
        return
    state = read_activity_log(path)
    unresolved = {event.run_id for event in state.active_runs}
    # Retain terminal pairs needed for cadence/retry and the most recent empty/manual
    # check for clock safety, plus the latest shared-store trigger agreement.
    latest_end = next((event for event in reversed(state.events) if event.event == "end"), None)
    latest_relevant = next(
        (
            event
            for event in reversed(state.events)
            if event.event == "end" and event.completion in {"completed", "deferred", "failed"}
        ),
        None,
    )
    latest_completed = next(
        (
            event
            for event in reversed(state.events)
            if event.event == "end" and event.completion in {"completed", "deferred"}
        ),
        None,
    )
    retained_ids = unresolved | {
        event.run_id for event in (latest_end, latest_relevant, latest_completed) if event
    }
    latest_trigger = next(
        (event for event in reversed(state.events) if event.event == "trigger"), None
    )
    latest_worker = next(
        (event for event in reversed(state.events) if event.event == "worker"), None
    )
    archive = (
        workspace.receipts.directory / "coordination" / (hashlib.sha256(raw).hexdigest() + ".jsonl")
    )
    write_artifact(archive, raw)
    retained = b"".join(
        (json.dumps(_event_mapping(event), sort_keys=True, separators=(",", ":")) + "\n").encode()
        for event in state.events
        if (event.event != "trigger" and event.run_id in retained_ids)
        or event is latest_trigger
        or event is latest_worker
    )
    if len(retained) >= ACTIVITY_MAX_BYTES // 2:
        raise AdapterError(
            "activity-unresolved-limit",
            str(path),
            "Unresolved coordination history requires inspection.",
        )
    # Same-directory atomic replacement preserves an intact archive if interrupted.
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    write_artifact(temporary, retained)
    with open_directory(path.parent) as directory:
        os.replace(temporary.name, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)


def _target(root: Path, raw_path: str) -> Path:
    target = Path(raw_path)
    if not target.is_absolute():
        raise ValidationError(
            "invalid-path", "signals.path", "Signal paths must be absolute previews."
        )
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise ValidationError(
            "signal-outside-storage", "signals.path", "Signal path is outside configured storage."
        ) from error
    if not relative.parts or relative.name in {"", ".", ".."}:
        raise ValidationError("invalid-path", "signals.path", "Signal path must name a file.")
    return target


def _read_target(path: Path) -> bytes:
    return read_bytes(path, max_bytes=8_388_608)


def _validate_drain_target(
    workspace: Workspace,
    storage: SignalStorage,
    project: str | None,
    path: Path,
    snapshot: SignalSnapshot,
    data: bytes,
) -> None:
    """Require one current-workspace signal before considering its removal."""
    expected_project = _bucket_project(storage, project, path)
    if path.suffix != ".md":
        raise ValidationError(
            "invalid-signal-extension", "signals.path", "Signals must use a Markdown .md file."
        )
    parsed = parse_document(data, path=str(path))
    signal = parse_signal(parsed.metadata, parsed.body, workspace.catalog)
    if signal.id != snapshot.id:
        raise ValidationError(
            "signal-id-mismatch", "signals.id", "Snapshot ID must equal the stored signal ID."
        )
    validate_signal_origin(
        signal.origin,
        workspace_id=workspace.definition.workspace_id,
        applicable_scopes=workspace.definition.applicable_scopes,
        source_ids=tuple(source.id for source in workspace.sources),
        project_path=expected_project,
    )


def _bucket_project(storage: SignalStorage, project: str | None, path: Path) -> str | None:
    """Map an exact eligible signal bucket to its expected origin project."""
    if path.parent == signal_bucket(storage, None):
        return None
    if project is not None and path.parent == signal_bucket(storage, project):
        return project
    raise ValidationError(
        "signal-outside-workspace",
        "signals.path",
        "Signal path is outside the selected workspace's eligible signal buckets.",
    )


def _unlink_verified_file(path: Path, *, expected: str) -> None:
    """Remove an unchanged regular file after a final identity check.

    The descriptor pins the bytes being verified and the directory descriptor
    prevents path traversal. A no-follow stat immediately before unlink avoids
    removing a replacement that appeared during verification.
    """
    with open_directory(path.parent) as directory:
        descriptor = os.open(
            path.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=directory,
        )
        try:
            before = os.fstat(descriptor)
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if (
                not stat.S_ISREG(before.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or not _same_identity(before, current)
            ):
                raise AdapterError(
                    "signal-changed", str(path), "Signal identity changed before drain."
                )
            chunks: list[bytes] = []
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(descriptor)
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            data = b"".join(chunks)
            if (
                not stat.S_ISREG(current.st_mode)
                or not _same_identity(before, after)
                or not _same_identity(after, current)
            ):
                raise AdapterError(
                    "signal-changed", str(path), "Signal changed while preparing drain."
                )
            if _fingerprint(data) != expected:
                raise AdapterError(
                    "signal-changed",
                    str(path),
                    "Signal bytes differ from the selected snapshot; input retained.",
                )
            final = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(final.st_mode) or not _same_identity(after, final):
                raise AdapterError(
                    "signal-changed", str(path), "Signal changed before removal; input retained."
                )
            os.unlink(path.name, dir_fd=directory)
            os.fsync(directory)
        except OSError as error:
            raise AdapterError(
                "signal-drain-failed", str(path), "Could not inspect signal for drain."
            ) from error
        finally:
            os.close(descriptor)


def _same_identity(first: os.stat_result, second: os.stat_result) -> bool:
    return _identity(first) == _identity(second)


def _fingerprint(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("invalid-activity-log", path, "Expected nonblank text.")
    return value


def _optional_text(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _text(value, path)


def _strings(value: object, path: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValidationError("invalid-activity-log", path, "Expected a list of nonblank strings.")
    return tuple(value)


def _snapshots(value: object, path: str) -> tuple[SignalSnapshot, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValidationError("invalid-activity-log", path, "Expected a list of snapshots.")
    result: list[SignalSnapshot] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValidationError("invalid-activity-log", f"{path}[{index}]", "Expected an object.")
        allowed = {"id", "path", "fingerprint"}
        unknown = set(item) - allowed
        if unknown:
            raise ValidationError(
                "unknown-field", f"{path}[{index}].{sorted(unknown)[0]}", "Field is not supported."
            )
        result.append(
            SignalSnapshot(
                _text(item.get("id"), f"{path}[{index}].id"),
                _text(item.get("path"), f"{path}[{index}].path"),
                _text(item.get("fingerprint"), f"{path}[{index}].fingerprint"),
            )
        )
        if not _FINGERPRINT_PATTERN.fullmatch(result[-1].fingerprint):
            raise ValidationError(
                "invalid-activity-log",
                f"{path}[{index}].fingerprint",
                "Expected sha256:<64 lowercase hex digits>.",
            )
        if not Path(result[-1].path).is_absolute():
            raise ValidationError(
                "invalid-activity-log",
                f"{path}[{index}].path",
                "Signal paths must be absolute previews.",
            )
    if len({item.id for item in result}) != len(result):
        raise ValidationError("duplicate-value", path, "Snapshot IDs must be unique.")
    return tuple(result)


def _dispositions(value: object, path: str) -> tuple[SignalDisposition, ...]:
    if value is None:
        return ()
    return parse_compound_request({"action": "status", "dispositions": value}).dispositions


def _diagnostic(signal_id: str, error: AdapterError | ValidationError) -> dict[str, str]:
    return {"signal_id": signal_id, "code": error.code, "message": error.message}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = [
    "ACTIVITY_SCHEMA",
    "ActivityEvent",
    "ActivityState",
    "CompoundDue",
    "compound_due",
    "configure_trigger",
    "DrainReport",
    "activity_path",
    "drain_signals",
    "event_view",
    "finish_run",
    "read_activity_log",
    "resolve_run",
    "record_worker",
    "start_run",
]
