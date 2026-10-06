"""Correlate observed Copilot native subagent events with compound activity.

This parser uses subagent.started.agentId and tool.execution_* correlation fields
observed in the live local probe. It does not infer execution from narrative text.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from model_shell_guard import reject_model_shell_launch


def _data(event: dict) -> dict:
    value = event.get("data")
    return value if isinstance(value, dict) else {}


def _same_path(value: object, expected: Path) -> bool:
    return (
        isinstance(value, str)
        and Path(value).is_absolute()
        and Path(value).resolve() == expected.resolve()
    )


def _exact_prefix(text: str, prefix: list[str]) -> bool:
    normalized = " ".join(text.split())
    expected = " ".join(shlex.join(prefix).split())
    return re.search(r"(?<!\S)" + re.escape(expected) + r"(?=$|[\s.,;])", normalized) is not None


def _json_objects(text: str) -> list[dict]:
    decoder = json.JSONDecoder()
    found = []
    position = 0
    while (position := text.find("{", position)) >= 0:
        try:
            value, consumed = decoder.raw_decode(text[position:])
        except ValueError:
            position += 1
            continue
        if isinstance(value, dict):
            found.append(value)
        position += consumed
    return found


def _worker_prompt_evidence(events: list[dict], *, worker_id: str, handed: str) -> tuple[dict, str]:
    """Verify the real child hook kept reflection without injecting delegation."""
    messages = [
        event
        for event in events
        if event.get("type") == "user.message"
        and event.get("agentId") == worker_id
        and _data(event).get("content") == handed
    ]
    if len(messages) != 1:
        raise ValueError("Copilot matching child lacks its exact native prompt event.")
    transformed = _data(messages[0]).get("transformedContent")
    if not isinstance(transformed, str) or transformed.count(handed) != 1:
        raise ValueError("Copilot child transformed prompt does not preserve its native handoff.")
    before, _, after = transformed.partition(handed)
    additions = before + after
    if any(
        marker in additions
        for marker in (
            "Local knowledge compounding is due.",
            "Main agent: delegate",
            "Delegated compound worker:",
            "Compounding due-check unavailable",
            "Compounding due-check skipped",
        )
    ):
        raise ValueError("Copilot child hook injected another due/delegation reminder.")
    if (
        "Reflect and record useful observations" not in additions
        or (
            "Provider harness (copy exactly into origin.harness "
            "for a harness-origin signal): copilot"
        )
        not in additions
        or "Provider session ID (copy exactly into origin.session_id for a harness-origin signal): "
        + worker_id
        not in additions
    ):
        raise ValueError("Copilot child hook did not preserve reflection with its own session.")
    return {
        "native_child_prompt_event_id": messages[0].get("id"),
        "worker_marker_verified": True,
        "child_reflection_preserved": True,
        "child_compounding_reminder_suppressed": True,
    }, additions


def _parent_route_conflicts(handed: str, *, skill: Path, prefix: list[str]) -> bool:
    """Missing parent routes can use binding; explicit conflicting routes cannot."""
    # Prompts are prose, not shell programs: apostrophes in "parent's" must not
    # make route extraction fail. Only quoted/unquoted route tokens matter here.
    words = []
    for token in re.findall(r"\"(?:\\.|[^\"\\])*\"|'[^']*'|`[^`]*`|[^\s]+", handed):
        if token.startswith('"') and token.endswith('"'):
            token = json.loads(token)
        elif token.startswith(("'", "`")) and token[-1:] == token[:1]:
            token = token[1:-1]
        words.append(token.strip("`.,;()"))
    expected = {
        "--settings": prefix[prefix.index("--settings") + 1],
        "--profile": prefix[prefix.index("--profile") + 1],
    }
    for index, word in enumerate(words):
        if word.endswith("SKILL.md") and word != str(skill):
            return True
        if Path(word).name == "agent-knowledge" and word != prefix[0]:
            return True
        flag, equals, value = word.partition("=")
        if flag == "--config":
            return True
        if flag in expected:
            supplied = value if equals else words[index + 1] if index + 1 < len(words) else None
            if supplied != expected[flag]:
                return True
    return False


def _bound_route_evidence(
    additions: str, *, handed: str, worker_id: str, skill: Path, prefix: list[str]
) -> dict:
    heading = "Bound compounding worker context (Copilot):"
    if heading not in additions:
        if str(skill) not in handed or not _exact_prefix(handed, prefix):
            raise ValueError(
                "Copilot worker lacks exact skill/selector in parent or child binding."
            )
        return {
            "skill_selector_transport": "native-parent-handoff",
            "bound_worker_id_verified": False,
        }
    if additions.count(heading) != 1:
        raise ValueError("Copilot child has ambiguous setup-bound worker context.")
    bound = additions.split(heading, 1)[1]
    if (
        "Load " + json.dumps(str(skill)) not in bound
        or "Your native worker_id is " + json.dumps(worker_id) + "," not in bound
        or not _exact_prefix(bound, prefix)
        or _parent_route_conflicts(bound, skill=skill, prefix=prefix)
    ):
        raise ValueError(
            "Copilot child bound context has a conflicting worker ID or skill/selector."
        )
    return {
        "skill_selector_transport": "native-parent-handoff-and-child-binding"
        if str(skill) in handed and _exact_prefix(handed, prefix)
        else "native-child-binding",
        "bound_worker_id_verified": True,
    }


def copilot_worker_evidence(
    events: list[dict],
    identity: dict,
    *,
    skill: Path,
    prefix: list[str],
    session_id: str,
) -> dict:
    """Return correlated proof or raise ValueError for an actual evidence gap."""
    for event in events:
        data = event.get("data", {})
        command = (
            data.get("arguments", {}).get("command")
            if isinstance(data.get("arguments"), dict)
            else None
        )
        if (
            event.get("type") == "tool.execution_start"
            and str(data.get("toolName", "")).lower() == "bash"
            and isinstance(command, str)
        ):
            reject_model_shell_launch(command)

    worker_id = identity.get("worker_id")
    if (
        not isinstance(worker_id, str)
        or not worker_id
        or identity.get("parent_session_id") != session_id
        or identity.get("harness") != "copilot"
    ):
        raise ValueError("Copilot activity lacks the exact worker and original parent identity.")
    starts = [
        event
        for event in events
        if event.get("type") == "subagent.started" and event.get("agentId") == worker_id
    ]
    if len(starts) != 1 or _data(starts[0]).get("parentId") is not None:
        raise ValueError(
            "Copilot recorded worker is not a unique direct child of the main session."
        )
    native = starts[0]
    tool_call_id = _data(native).get("toolCallId")
    dispatched = [
        event
        for event in events
        if event.get("type") == "tool.execution_start"
        and _data(event).get("toolName") == "task"
        and _data(event).get("toolCallId") == tool_call_id
        and event.get("agentId") is None
        and _data(event).get("parentToolCallId") is None
        and event.get("id") == native.get("parentId")
    ]
    if len(dispatched) != 1:
        raise ValueError("Copilot native worker has no matching main-session task dispatch.")
    arguments = _data(dispatched[0]).get("arguments", {})
    handed = arguments.get("prompt") if isinstance(arguments, dict) else None
    if (
        not isinstance(handed, str)
        or session_id not in handed
        or _parent_route_conflicts(handed, skill=skill, prefix=prefix)
    ):
        raise ValueError(
            "Copilot worker did not receive the exact skill, selector and parent handoff."
        )
    if "[agent-knowledge-compound-worker]" not in handed:
        raise ValueError("Copilot worker handoff omitted the exact worker marker.")
    children = [
        event
        for event in events
        if event.get("agentId") == worker_id
        and _data(event).get("parentToolCallId") == tool_call_id
    ]
    calls = [event for event in children if event.get("type") == "tool.execution_start"]
    completions = {
        _data(event).get("toolCallId"): event
        for event in children
        if event.get("type") == "tool.execution_complete"
    }
    for call in calls:
        data = _data(call)
        nested = data.get("arguments", {})
        prompt = nested.get("prompt", "") if isinstance(nested, dict) else ""
        if data.get("toolName") == "task" and (
            str(skill) in prompt or "knowledge-compound" in prompt
        ):
            raise ValueError("Copilot compound worker recursively delegated another compound task.")
    skill_reads = []
    lifecycle = {}
    expected_settings = Path(prefix[prefix.index("--settings") + 1])
    expected_profile = prefix[prefix.index("--profile") + 1]
    for call in calls:
        data = _data(call)
        call_id = data.get("toolCallId")
        result_event = completions.get(call_id)
        result = _data(result_event) if isinstance(result_event, dict) else {}
        if result.get("success") is not True:
            continue
        output = result.get("result", {})
        content = output.get("content", "") if isinstance(output, dict) else ""
        if not isinstance(content, str) or not content:
            continue
        args = data.get("arguments", {})
        if not isinstance(args, dict):
            continue
        telemetry = result.get("toolTelemetry", {})
        properties = telemetry.get("properties", {}) if isinstance(telemetry, dict) else {}
        if (
            data.get("toolName") == "view"
            and _same_path(args.get("path"), skill)
            and properties.get("largeOutputAvoided") != "true"
            and not content.startswith("File too large to read")
        ):
            skill_reads.append(call_id)
        command = args.get("command")
        shell = result.get("shellExecution", {})
        if (
            data.get("toolName") != "bash"
            or not isinstance(command, str)
            or not _exact_prefix(command, [*prefix, "compound"])
            or not isinstance(shell, dict)
            or shell.get("exitCode") != 0
        ):
            continue
        for value in _json_objects(content):
            action = value.get("action")
            selected = value.get("selection", {})
            if (
                action not in {"start", "finish"}
                or value.get("status") != "ok"
                or value.get("run_id") != identity["run_id"]
                or not isinstance(selected, dict)
                or selected.get("mode") != "profile"
                or selected.get("profile") != expected_profile
                or not _same_path(selected.get("settings_path"), expected_settings)
            ):
                continue
            if action == "start" and value.get("started") is not True:
                continue
            if action == "finish" and value.get("completion") != "completed":
                continue
            lifecycle[action] = call_id
    if not skill_reads:
        raise ValueError("Copilot matching child has no successful installed-skill body read.")
    if set(lifecycle) != {"start", "finish"}:
        raise ValueError("Copilot matching child did not execute selected successful start/finish.")
    order = {_data(call)["toolCallId"]: index for index, call in enumerate(calls)}
    if (
        not min(order[read] for read in skill_reads)
        < order[lifecycle["start"]]
        < order[lifecycle["finish"]]
    ):
        raise ValueError("Copilot child lifecycle did not follow skill read, start, then finish.")
    prompt_evidence, additions = _worker_prompt_evidence(events, worker_id=worker_id, handed=handed)
    route_evidence = _bound_route_evidence(
        additions, handed=handed, worker_id=worker_id, skill=skill, prefix=prefix
    )
    return {
        "status": "passed",
        "provider": "copilot",
        "run_id": identity["run_id"],
        "worker_id": worker_id,
        "spawn_tool_call_id": tool_call_id,
        "native_subagent_event_id": native.get("id"),
        "skill_read_tool_call_ids": skill_reads,
        "lifecycle_tool_call_ids": lifecycle,
        "child_event_count": len(children),
        **prompt_evidence,
        **route_evidence,
    }
