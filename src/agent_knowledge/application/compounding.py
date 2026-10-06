"""Coordinate the explicit activity/drain helper used by knowledge-compound."""

from pathlib import Path
from typing import TypedDict

from agent_knowledge.domain.compounding import parse_compound_request
from agent_knowledge.domain.configuration import compound_trigger_view
from agent_knowledge.infrastructure.compounding import (
    ActivityState,
    CompoundDue,
    activity_path,
    compound_due,
    configure_trigger,
    drain_signals,
    event_view,
    finish_run,
    read_activity_log,
    record_worker,
    start_run,
)
from agent_knowledge.infrastructure.configuration import Workspace


class CompoundResult(TypedDict, total=False):
    """Machine-readable result for coordination-only compound actions."""

    updated: bool
    harness: str | None
    worker_id: str | None
    parent_session_id: str | None
    due: bool
    reason: str
    next_due_at: str | None
    inbox_probe: str
    started: bool
    trigger: dict[str, object] | None
    completion: str | None
    action: str
    activity_path: str
    run_id: str
    active: bool
    started_at: str | None
    ended_at: str | None
    drained: list[str]
    events: list[dict[str, object]]
    active_runs: list[dict[str, object]]
    retained: list[str]
    diagnostics: list[dict[str, str]]


def compound_result(workspace: Workspace, value: object) -> CompoundResult:
    """Run one explicit coordination action; publication remains agent-owned."""
    request = parse_compound_request(value)
    activity = activity_path(workspace)
    if request.action == "due":
        return _due_result(compound_due(workspace), activity, "due")
    if request.action == "configure-trigger":
        trigger = configure_trigger(workspace, expected=request.expected_trigger)
        return {
            "action": "configure-trigger",
            "activity_path": str(activity),
            "trigger": compound_trigger_view(trigger),
        }
    if request.action == "record-worker":
        assert request.run_id is not None and request.worker_id is not None
        worker_event, updated = record_worker(
            workspace,
            run_id=request.run_id,
            worker_id=request.worker_id,
            parent_session_id=request.parent_session_id,
            harness=request.harness,
        )
        return {
            "action": "record-worker",
            "run_id": worker_event.run_id,
            "updated": updated,
            "harness": worker_event.harness,
            "worker_id": worker_event.worker_id,
            "parent_session_id": worker_event.parent_session_id,
            "activity_path": str(activity),
        }
    if request.action == "status":
        state = read_activity_log(activity)
        return _status(state, activity)
    if request.action == "start":
        assert request.workspace_id is not None
        event = start_run(
            workspace,
            selected=request.selected,
            harness=request.harness,
            session_id=request.session_id,
            automation_id=request.automation_id,
            workspace_id=request.workspace_id,
            automatic=request.automatic,
            worker_id=request.worker_id,
            parent_session_id=request.parent_session_id,
            recovery_of=request.recovery_of,
        )
        if isinstance(event, CompoundDue):
            return {**_due_result(event, activity, "start"), "started": False}
        return {
            "started": True,
            "action": "start",
            "activity_path": str(activity),
            "run_id": event.run_id,
            "active": event.active,
            "started_at": event.started_at,
        }
    if request.action == "finish":
        assert request.run_id is not None and request.outcome is not None
        event = finish_run(
            workspace,
            run_id=request.run_id,
            outcome=request.outcome,
            dispositions=request.dispositions,
            completion=request.completion,
        )
        return {
            "action": "finish",
            "completion": event.completion,
            "activity_path": str(activity),
            "run_id": event.run_id,
            "active": event.active,
            "ended_at": event.ended_at,
            "drained": list(event.drained),
        }
    report = drain_signals(
        workspace,
        request.selected,
        request.dispositions,
        run_id=request.run_id or "",
        publication_verified=request.publication_verified,
        publication=request.publication,
    )
    return {
        "action": "drain",
        "activity_path": str(activity),
        "drained": list(report.drained),
        "retained": list(report.retained),
        "diagnostics": list(report.diagnostics),
    }


def _status(state: ActivityState, activity: Path) -> CompoundResult:
    return {
        "trigger": compound_trigger_view(state.trigger) if state.trigger else None,
        "action": "status",
        "activity_path": str(activity),
        "active": bool(state.active_runs),
        "events": [event_view(event) for event in state.events],
        "active_runs": [event_view(event) for event in state.active_runs],
    }


__all__ = ["CompoundResult", "compound_result"]


def _due_result(result: CompoundDue, activity: Path, action: str) -> CompoundResult:
    return {
        "action": action,
        "activity_path": str(activity),
        "due": result.due,
        "reason": result.reason,
        "next_due_at": result.next_due_at,
        "inbox_probe": result.inbox_probe,
        "active_runs": [event_view(event) for event in result.active_runs],
    }
