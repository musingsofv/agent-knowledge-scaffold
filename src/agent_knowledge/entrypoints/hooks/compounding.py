"""Bound the optional prompt-time check independently of discovery/reflection.

The child only resolves explicit configuration, checks coordination metadata and
stats the installed skill. It never invokes a model, reads signal bodies or
activates credentials. A slow mount cannot suppress the parent hook's reminder.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import cast

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.errors import AdapterError

CHECK_TIMEOUT_SECONDS = 1.0
WORKER_MARKER = "[agent-knowledge-compound-worker]"
_MAX_REQUEST_BYTES = 16_384
_MAX_ANCESTORS = 32


def is_worker_prompt(payload: object) -> bool:
    """Suppress inherited delegation without inferring roles or granting ownership.

    Providers can invoke prompt hooks for native child tasks without exposing a
    child-role field. The parent copies this explicit marker in the handoff.
    It is only a quiet-path hint; automatic start still owns eligibility.
    """
    return isinstance(payload, dict) and any(
        isinstance(payload.get(field), str) and WORKER_MARKER in payload[field]
        for field in ("prompt", "transformedPrompt")
    )


def bounded_compound_context(
    *,
    config: Path | None,
    settings: Path | None,
    profile: str | None,
    skill: Path,
    provider: str,
    session_id: str | None,
    cwd: object,
    worker: bool = False,
) -> str | None:
    """Return concise context, or a quiet no-op with value-free stderr diagnostics."""
    request = {
        "config": str(config) if config is not None else None,
        "settings": str(settings) if settings is not None else None,
        "profile": profile,
        "skill": str(skill),
        "provider": provider,
        "session_id": session_id,
        "cwd": cwd if isinstance(cwd, str) else None,
        "worker": worker,
    }
    encoded = json.dumps(request)
    if len(encoded.encode()) > _MAX_REQUEST_BYTES:
        return None
    try:
        child = subprocess.run(
            [sys.executable, "-I", "-m", "agent_knowledge.entrypoints.hooks.compounding"],
            input=encoded,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        if child.returncode != 0:
            print(
                "Compounding due-check unavailable; inspect compound due with the bound selector.",
                file=sys.stderr,
            )
            return None
        value = json.loads(child.stdout)
        return value if isinstance(value, str) else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        print(
            "Compounding due-check skipped; check runtime, storage and compound due diagnostics.",
            file=sys.stderr,
        )
        return None


def _installed_skill(raw: str, cwd: str | None) -> Path:
    path = Path(raw)
    if path.is_absolute():
        if path.is_file():
            return path
        raise ValueError("Installed skill unavailable.")
    if ".." in path.parts or cwd is None or not Path(cwd).is_absolute():
        raise ValueError("Portable skill needs the provider's absolute working directory.")
    parent = Path(cwd)
    for _ in range(_MAX_ANCESTORS):
        candidate = parent / path
        if candidate.is_file():
            return candidate
        if parent == parent.parent:
            break
        parent = parent.parent
    raise ValueError("Installed skill unavailable within bounded consumer ancestry.")


def compound_context(request: dict[str, object]) -> str | None:
    """Return due delegation or restore the marked Copilot worker's bound context."""
    from agent_knowledge.infrastructure.compounding import compound_due
    from agent_knowledge.infrastructure.configuration import resolve_workspace

    config, settings, profile = (request.get(key) for key in ("config", "settings", "profile"))
    if config is None and profile is None:
        raise ValueError("Conditional compounding requires an explicit selection.")
    if any(
        value is not None and not isinstance(value, str) for value in (config, settings, profile)
    ):
        raise ValueError("Invalid selection.")
    workspace = resolve_workspace(
        config=Path(config) if isinstance(config, str) else None,
        settings=Path(settings) if isinstance(settings, str) else None,
        profile=cast(str | None, profile),
    )
    worker = request.get("worker", False)
    if not isinstance(worker, bool):
        raise ValueError("Invalid worker role.")
    if worker and request.get("provider") != "copilot":
        raise ValueError("Unsupported provider worker identity.")
    if not worker:
        eligibility = compound_due(workspace)
        if not eligibility.due:
            return None
    raw_skill, cwd = request.get("skill"), request.get("cwd")
    if not isinstance(raw_skill, str) or (cwd is not None and not isinstance(cwd, str)):
        raise ValueError("Invalid skill binding.")
    skill = _installed_skill(raw_skill, cwd)
    launcher = Path(sys.executable).parent / "agent-knowledge"
    if not launcher.is_file():
        raise ValueError("Installed knowledge launcher unavailable.")
    selection = workspace.selection
    arguments = [str(launcher)]
    if selection.mode == "config":
        arguments.extend(["--config", str(selection.config)])
    else:
        arguments.extend(
            ["--settings", str(selection.settings), "--profile", str(selection.profile)]
        )
    provider, session = request.get("provider"), request.get("session_id")
    if provider not in {"codex", "claude", "copilot"} or not isinstance(session, str):
        raise ValueError("Provider/session identity unavailable.")
    if worker:
        return (
            "Bound compounding worker context (Copilot):\n"
            "You are already the native compounding worker. Load "
            + json.dumps(str(skill))
            + ". Your native worker_id is "
            + json.dumps(session)
            + ", exposed by this child prompt hook. Include this worker_id and "
            "session_id on automatic compound start: "
            + json.dumps(
                {
                    "automatic": True,
                    "harness": provider,
                    "worker_id": session,
                    "session_id": session,
                }
            )
            + ". Keep parent_session_id from the "
            "original parent assignment; never replace it with your own ID. "
            "Use this exact prefix for every configured call: "
            + shlex.join(arguments)
            + ". For describe only, use "
            + shlex.quote(str(launcher))
            + " describe without selectors. This setup-bound route must agree with any "
            "route supplied by the parent. Missing parent identity or conflicting routes "
            "require clarification from that parent before compounding; never discover or "
            "substitute a default or unrelated profile. Do not spawn another compound worker. "
            "Preserve the parent's consumer instructions and publication limits. This role "
            "context grants no authorization or run ownership: follow the installed skill "
            "and atomically start with automatic:true; exit without edits on started:false. "
            "Report the returned run_id and your worker_id to the parent."
        )
    handoff = json.dumps(
        {
            "worker_marker": WORKER_MARKER,
            "harness": provider,
            "parent_session_id": session,
            "workspace_id": workspace.definition.workspace_id,
            "consumer_cwd": cwd,
        },
        ensure_ascii=True,
    )
    return (
        "Local knowledge compounding is due.\n"
        + (
            "Copilot main agent: invoke the native task tool for this due run before your "
            "final response. Pass the worker assignment below to a general-purpose native "
            "subagent. Loading the knowledge-compound skill in the main agent does not "
            "replace this delegation; the worker loads that skill. The marked child hook "
            "supplies its bound CLI route and exact worker_id. Still pass the original "
            "parent_session_id and consumer/publication instructions. Retain the returned "
            "agent_id and worker run_id; use compound action:record-worker if the worker "
            "could not persist its identity.\n"
            if provider == "copilot"
            else ""
        )
        + "First identify your assignment: if a parent already assigned you to compound "
        "knowledge, you are the delegated worker. Skip the main-agent paragraph below. "
        "An inherited hook is not a new assignment: keep the original parent's handoff "
        "and parent_session_id; this hook's session is your own, not a replacement parent.\n"
        "Main agent: use your harness's native subagent tool to delegate one worker now, "
        "and continue the "
        "user's task alongside it. Reuse an available compound worker when supported. "
        "Never launch a worker through shell/terminal model CLI processes such as codex exec, "
        "claude -p or copilot -p. Begin the native worker's task with the exact marker "
        + WORKER_MARKER
        + " so inherited prompt hooks suppress further delegation. "
        "Pass consumer instructions and verified publication routes. Relay the returned "
        "worker handle when exposed without delaying the worker indefinitely. The worker must load "
        + json.dumps(str(skill))
        + ". Use this exact prefix for configured calls: "
        + shlex.join(arguments)
        + ". Main-agent handoff for a newly delegated worker only: "
        + handoff
        + ". If delegation is unavailable, report that prerequisite; do not silently ignore "
        "this due work or substitute a parent-run compound. When the worker reports its run_id, "
        "associate your exact native worker handle using compound action:record-worker with "
        "run_id, worker_id, harness and parent_session_id from this handoff, even if the run "
        "has finished. This records identity only; do not start another run.\n"
        "Delegated compound worker: do not delegate another compound worker or act on this "
        "reminder recursively. Follow the installed skill. At start include automatic:true, "
        "harness and parent_session_id from the original parent handoff, and worker_id if "
        "the native handle is known. Exit without edits when started:false. "
        "Preserve exact available worker/session IDs "
        "without inventing handles. Prompt fallback has no automation_id; omit it. "
        "Preserve ownership, review, publication and guarded-drain "
        "requirements, and record the structured terminal result. Report meaningful results "
        "or required action and the exact run_id to the parent."
    )


def main() -> int:
    """Private installed child boundary; no exception details or values on output."""
    try:
        raw = sys.stdin.buffer.read(_MAX_REQUEST_BYTES + 1)
        if len(raw) > _MAX_REQUEST_BYTES:
            return 2
        request = json.loads(raw)
        if not isinstance(request, dict):
            return 2
        print(json.dumps(compound_context(request)))
        return 0
    except (AdapterError, OSError, ValidationError, ValueError, TypeError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
