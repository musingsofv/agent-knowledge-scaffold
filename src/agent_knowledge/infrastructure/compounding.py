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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from agent_knowledge.domain.compounding import (
    PublicationEvidence,
    SignalDisposition,
    SignalSnapshot,
    drainable_snapshots,
    parse_compound_request,
)
from agent_knowledge.domain.schema import parse_signal
from agent_knowledge.domain.signals import validate_signal_origin
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
from .usage import append_event, write_artifact

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


@dataclass(frozen=True, slots=True)
class ActivityState:
    """Expose parsed events and runs whose start has no matching end."""

    events: tuple[ActivityEvent, ...]
    active_runs: tuple[ActivityEvent, ...]


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
    ended: set[str] = set()
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
        events.append(event)
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
            if event.run_id in ended:
                raise ValidationError(
                    "invalid-activity-log",
                    f"{path}:{number}.run_id",
                    "A run may have only one end event.",
                )
            ended.add(event.run_id)
    active = tuple(event for run_id, event in starts.items() if run_id not in ended)
    return ActivityState(tuple(events), active)


def start_run(
    workspace: Workspace,
    *,
    selected: tuple[SignalSnapshot, ...],
    harness: str | None,
    session_id: str | None,
    automation_id: str | None,
    workspace_id: str,
) -> ActivityEvent:
    """Validate and archive exact selected inputs before recording an active run."""
    began = monotonic()
    path = activity_path(workspace)
    with lifecycle_lock(path):
        _rollover_activity(workspace, path)
        state = read_activity_log(path)
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
    return event


def finish_run(
    workspace: Workspace,
    *,
    run_id: str,
    outcome: str,
    dispositions: tuple[SignalDisposition, ...],
) -> ActivityEvent:
    """Record agent-reported outcome while deriving actual drainage from tool evidence."""
    began = monotonic()
    path = activity_path(workspace)
    with lifecycle_lock(path):
        active = _active_run(workspace, run_id)
        records = evidence_records(workspace, run_id)
        drained = _recorded_drained(records)
        retained = sorted({snapshot.id for snapshot in active.selected} - set(drained))
        event = ActivityEvent(
            event="end",
            run_id=run_id,
            workspace_id=active.workspace_id,
            active=False,
            ended_at=_now(),
            harness=active.harness,
            session_id=active.session_id,
            automation_id=active.automation_id,
            outcome=outcome,
            dispositions=dispositions,
            drained=drained,
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
    if event not in {"start", "end"}:
        raise ValidationError("invalid-activity-log", f"{path}.event", "Expected start or end.")
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
    ):
        if item is not None:
            value[key] = item
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


def _append(path: Path, value: Mapping[str, object]) -> None:
    """Serialize the small coordination append separately from analytics evidence."""
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
    # Copy all history first; retaining unmatched starts in the live log is enough
    # for coordination. Completed but unresolved evidence remains in its run archive.
    archive = (
        workspace.receipts.directory / "coordination" / (hashlib.sha256(raw).hexdigest() + ".jsonl")
    )
    write_artifact(archive, raw)
    retained = b"".join(
        (json.dumps(_event_mapping(event), sort_keys=True, separators=(",", ":")) + "\n").encode()
        for event in state.events
        if event.run_id in unresolved
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
    "DrainReport",
    "activity_path",
    "drain_signals",
    "event_view",
    "finish_run",
    "read_activity_log",
    "resolve_run",
    "start_run",
]
