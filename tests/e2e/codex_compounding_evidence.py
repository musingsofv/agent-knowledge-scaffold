"""Correlate native Codex rollouts; CLI JSONL alone omits child execution."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from harness_agent_smoke import HarnessSmokeFailure
from model_shell_guard import reject_model_shell_launch


def _objects(text: str) -> list[dict]:
    result = []
    decoder = json.JSONDecoder()
    position = 0
    while (position := text.find("{", position)) >= 0:
        try:
            value, consumed = decoder.raw_decode(text[position:])
        except ValueError:
            position += 1
            continue
        if isinstance(value, dict):
            result.append(value)
        position += consumed
    return result


def _metadata(records: list[dict]) -> dict:
    # Forked rollouts include inherited parent session_meta after their own header.
    # Only the first native header identifies this transcript.
    if (
        not records
        or records[0].get("type") != "session_meta"
        or not isinstance(records[0].get("payload"), dict)
    ):
        raise HarnessSmokeFailure("Native Codex session metadata header is unavailable.")
    return records[0]["payload"]


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def capture_codex_rollouts(
    codex_home: Path, logs: Path, *, session_id: str, worker_id: str | None, label: str
) -> tuple[list[dict], list[dict] | None, dict]:
    """Read only the exact parent and its metadata-linked child; retain local evidence."""
    parent_paths = list((codex_home / "sessions").rglob(f"*-{session_id}.jsonl"))
    if len(parent_paths) != 1:
        raise HarnessSmokeFailure("Exact native Codex parent rollout is unavailable or ambiguous.")
    parent_path = parent_paths[0]
    parent = _read(parent_path)
    parent_meta = _metadata(parent)
    if parent_meta.get("id") != session_id:
        raise HarnessSmokeFailure("Native parent session ID differs from the CLI result.")
    snapshots = {"parent_source": str(parent_path)}
    target = logs / f"codex-native-parent-{label}.jsonl"
    target.write_text(parent_path.read_text())
    snapshots["parent_snapshot"] = str(target)
    if worker_id is None:
        return parent, None, snapshots
    children = []
    # Child creation uses the same dated native session directory in the observed
    # format. Missing/moved/new formats fail closed rather than reading other bodies.
    for candidate in parent_path.parent.glob("*.jsonl"):
        with candidate.open() as stream:
            first = json.loads(stream.readline())
        meta = first.get("payload", {}) if first.get("type") == "session_meta" else {}
        if meta.get("parent_thread_id") == session_id and meta.get("agent_path") == worker_id:
            children.append(candidate)
    if len(children) != 1:
        raise HarnessSmokeFailure("Exact native Codex child rollout is unavailable or ambiguous.")
    child_path = children[0]
    target = logs / f"codex-native-child-{label}.jsonl"
    target.write_text(child_path.read_text())
    snapshots.update(child_source=str(child_path), child_snapshot=str(target))
    return parent, _read(child_path), snapshots


def codex_spawn_calls(records: list[dict], *, after_ordinal: int = -1) -> list[dict]:
    return [
        event
        for event in records
        if event.get("type") == "response_item"
        and isinstance(event.get("ordinal"), int)
        and event["ordinal"] > after_ordinal
        and event.get("payload", {}).get("type") == "function_call"
        and event["payload"].get("namespace") == "collaboration"
        and event["payload"].get("name") == "spawn_agent"
    ]


def _wrappers(payload: dict) -> list[dict]:
    raw = payload.get("output")
    texts = (
        [raw]
        if isinstance(raw, str)
        else [
            part["text"]
            for part in raw
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        ]
        if isinstance(raw, list)
        else []
    )
    return [
        value
        for text in texts
        for value in _objects(text)
        if value.get("exit_code") == 0 and isinstance(value.get("output"), str)
    ]


def _read_command(code: str, skill: Path, cwd: Path) -> bool:
    for literal in re.findall(r'cmd\s*:\s*("(?:\\.|[^"\\])*")', code):
        try:
            command = json.loads(literal)
            for line in command.splitlines():
                tokens = shlex.split(line)
                if tokens and tokens[0] == "cat":
                    for token in tokens[1:]:
                        path = Path(token)
                        if (
                            path if path.is_absolute() else cwd / path
                        ).resolve() == skill.resolve():
                            return True
        except (ValueError, TypeError):
            continue
    return False


def _command_strings(code: str, stored: dict[str, str]) -> list[str]:
    """Recognize observed literal/persisted-prefix commands without evaluating JS."""
    result = []
    quoted = r'"(?:\\.|[^"\\])*"'
    for match in re.finditer(
        r"cmd\s*:\s*(?:load\(\s*(" + quoted + r")\s*\)|(" + quoted + r"))", code
    ):
        value = (
            stored.get(json.loads(match.group(1)), "")
            if match.group(1)
            else json.loads(match.group(2))
        )
        suffix = re.match(r"\s*\+\s*(" + quoted + r")", code[match.end() :])
        if suffix:
            value += json.loads(suffix.group(1))
        result.append(value)
    return result


def _command_prefix_matches(
    code: str, prefix: list[str], stored: dict[str, str], cwd: Path
) -> bool:
    # Native exec defaults to the child's metadata cwd. Do not infer a cwd from
    # shell text or accept an unobserved/different tool workdir.
    if "workdir" in code:
        workdirs = re.findall(r'workdir\s*:\s*("(?:\\.|[^"\\])*")', code)
        if not workdirs or any(Path(json.loads(value)).resolve() != cwd for value in workdirs):
            return False

    def resolved(value: str) -> Path | None:
        if value.startswith("${PWD}/"):
            value = str(cwd) + value[len("${PWD}") :]
        elif value.startswith("$PWD/"):
            value = str(cwd) + value[len("$PWD") :]
        if "$" in value or "`" in value:
            return None
        path = Path(value)
        return (path if path.is_absolute() else cwd / path).resolve()

    settings_position = prefix.index("--settings") + 1
    for value in _command_strings(code, stored):
        try:
            tokens = shlex.split(value.splitlines()[0])
        except (ValueError, IndexError):
            continue
        if len(tokens) < len(prefix) or "/" not in tokens[0]:
            continue
        selected = tokens[: len(prefix)]
        if (
            resolved(selected[0]) != Path(prefix[0]).resolve()
            or resolved(selected[settings_position]) != Path(prefix[settings_position]).resolve()
        ):
            continue
        selected[0], selected[settings_position] = prefix[0], prefix[settings_position]
        if (
            selected == prefix
            and "compound" in tokens[len(prefix) :]
            and "--request-file" in tokens
        ):
            return True
    return False


def _guard_native_commands(records: list[dict]) -> None:
    stored: dict[str, str] = {}
    for event in records:
        payload = event.get("payload", {})
        if event.get("type") != "response_item":
            continue
        if payload.get("type") == "function_call" and payload.get("name") == "exec_command":
            arguments = json.loads(payload.get("arguments", "{}"))
            if isinstance(arguments.get("cmd"), str):
                reject_model_shell_launch(arguments["cmd"])
        if payload.get("type") != "custom_tool_call" or payload.get("name") != "exec":
            continue
        code = payload.get("input", "")
        for match in re.finditer(
            r'store\(\s*("(?:\\.|[^"\\])*")\s*,\s*("(?:\\.|[^"\\])*")\s*\)', code
        ):
            stored[json.loads(match.group(1))] = json.loads(match.group(2))
        for command in _command_strings(code, stored):
            reject_model_shell_launch(command)


def codex_worker_evidence(
    parent: list[dict],
    child: list[dict],
    identity: dict,
    *,
    skill: Path,
    prefix: list[str],
    session_id: str,
) -> dict:
    """Prove native spawn identity and actual post-fork skill/CLI execution."""
    parent_meta, child_meta = _metadata(parent), _metadata(child)
    if parent_meta.get("id") != session_id:
        raise HarnessSmokeFailure("Codex parent metadata does not match the actual session.")
    spawned = child_meta.get("source", {}).get("subagent", {}).get("thread_spawn", {})
    worker = identity["worker_id"]
    if (
        child_meta.get("parent_thread_id") != session_id
        or child_meta.get("forked_from_id") != session_id
        or child_meta.get("agent_path") != worker
        or spawned.get("parent_thread_id") != session_id
        or spawned.get("agent_path") != worker
        or child_meta.get("id") == session_id
        or child_meta.get("cwd") != parent_meta.get("cwd")
    ):
        raise HarnessSmokeFailure(
            "Codex child metadata is not linked to the recorded parent/worker."
        )
    calls = {event["payload"]["call_id"]: event["payload"] for event in codex_spawn_calls(parent)}
    matching = []
    for event in parent:
        payload = event.get("payload", {})
        if (
            event.get("type") == "response_item"
            and payload.get("type") == "function_call_output"
            and payload.get("call_id") in calls
        ):
            returned = _objects(payload.get("output", ""))
            if any(value.get("task_name") == worker for value in returned):
                matching.append(payload["call_id"])
    if len(matching) != 1:
        raise HarnessSmokeFailure(
            "No unique native Codex spawn result matches the recorded worker."
        )
    boundary = child_meta.get("subagent_history_start_ordinal")
    if not isinstance(boundary, int):
        raise HarnessSmokeFailure("Native Codex child history boundary is unavailable.")
    own = [
        event
        for event in child
        if isinstance(event.get("ordinal"), int)
        and event["ordinal"] >= boundary
        and event.get("timestamp", "") >= child_meta.get("timestamp", "")
    ]
    _guard_native_commands(parent)
    _guard_native_commands(own)
    own_calls = {
        event["payload"]["call_id"]: event
        for event in own
        if event.get("type") == "response_item"
        and event.get("payload", {}).get("type") == "custom_tool_call"
        and event["payload"].get("name") == "exec"
    }
    outputs = {
        event["payload"]["call_id"]: event["payload"]
        for event in own
        if event.get("type") == "response_item"
        and event.get("payload", {}).get("type") == "custom_tool_call_output"
    }
    read_ids, lifecycle = [], {}
    expected_skill = skill.read_text().strip()
    cwd = Path(child_meta["cwd"])
    stored: dict[str, str] = {}
    for identifier, event in own_calls.items():
        code = event["payload"].get("input", "")
        wrappers = _wrappers(outputs.get(identifier, {}))
        if not isinstance(code, str) or "tools.exec_command" not in code:
            continue
        for match in re.finditer(
            r'store\(\s*("(?:\\.|[^"\\])*")\s*,\s*("(?:\\.|[^"\\])*")\s*\)', code
        ):
            stored[json.loads(match.group(1))] = json.loads(match.group(2))
        if _read_command(code, skill, cwd) and any(
            expected_skill in value["output"] for value in wrappers
        ):
            read_ids.append(identifier)
        if not _command_prefix_matches(code, prefix, stored, cwd):
            continue
        for wrapper in wrappers:
            for returned in _objects(wrapper["output"]):
                action, selection = returned.get("action"), returned.get("selection", {})
                if (
                    action not in {"start", "finish"}
                    or returned.get("status") != "ok"
                    or returned.get("run_id") != identity["run_id"]
                    or selection.get("mode") != "profile"
                    or selection.get("profile") != prefix[prefix.index("--profile") + 1]
                    or not isinstance(selection.get("settings_path"), str)
                    or Path(selection["settings_path"]).resolve()
                    != Path(prefix[prefix.index("--settings") + 1]).resolve()
                ):
                    continue
                if action == "start" and returned.get("started") is not True:
                    continue
                if action == "finish" and returned.get("completion") != "completed":
                    continue
                lifecycle[action] = identifier
    if not read_ids or set(lifecycle) != {"start", "finish"}:
        raise HarnessSmokeFailure(
            "Matching Codex child lacks its own successful skill read and selected start/finish."
        )
    ordinal = {identifier: event["ordinal"] for identifier, event in own_calls.items()}
    if (
        not min(ordinal[item] for item in read_ids)
        < ordinal[lifecycle["start"]]
        < ordinal[lifecycle["finish"]]
    ):
        raise HarnessSmokeFailure("Codex child lifecycle did not follow skill read, start, finish.")
    return {
        "status": "passed",
        "provider": "codex",
        "run_id": identity["run_id"],
        "worker_id": worker,
        "child_thread_id": child_meta["id"],
        "spawn_call_id": matching[0],
        "skill_read_call_ids": read_ids,
        "lifecycle_call_ids": lifecycle,
        "child_history_start_ordinal": boundary,
        "child_native_spawn_count": len(codex_spawn_calls(own)),
        "worker_marker_verified": None,
        "parent_last_ordinal": max(event.get("ordinal", -1) for event in parent),
        "handoff_text": (
            "Provider-stored encrypted; worker marker not directly observable; "
            "effective skill/selector handoff verified "
            "through child execution."
        ),
    }
