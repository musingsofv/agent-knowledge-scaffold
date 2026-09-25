"""Coordinate the explicit activity/drain helper used by knowledge-compound."""

from pathlib import Path
from typing import TypedDict

from agent_knowledge.domain.compounding import parse_compound_request
from agent_knowledge.infrastructure.compounding import (
    ActivityState,
    activity_path,
    drain_signals,
    event_view,
    finish_run,
    read_activity_log,
    start_run,
)
from agent_knowledge.infrastructure.configuration import Workspace


class CompoundResult(TypedDict, total=False):
    """Machine-readable result for coordination-only compound actions."""

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
        )
        return {
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
        )
        return {
            "action": "finish",
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
        "action": "status",
        "activity_path": str(activity),
        "active": bool(state.active_runs),
        "events": [event_view(event) for event in state.events],
        "active_runs": [event_view(event) for event in state.active_runs],
    }


__all__ = ["CompoundResult", "compound_result"]
