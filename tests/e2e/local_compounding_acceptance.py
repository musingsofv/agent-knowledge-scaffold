#!/usr/bin/env python3
"""Prove prompt-triggered delegation in isolated installed consumers.

Real provider calls are opt-in. Each consumer retains its transcripts and activity
evidence; no real inbox, native scheduler or remote publication is involved.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import yaml
from claude_hook_acceptance import _json_lines
from codex_compounding_evidence import (
    capture_codex_rollouts,
    codex_spawn_calls,
    codex_worker_evidence,
)
from copilot_compounding_evidence import copilot_worker_evidence
from harness_agent_smoke import (
    HarnessSmokeFailure,
    _clean_runtime_env,
    _fresh_consumer,
    _isolated_copilot_environment,
    _prepare_signal,
    _run,
    _run_json,
)
from model_shell_guard import reject_model_shell_launch
from profile_acceptance import _provider_command, _provider_evidence

ROOT = Path(__file__).resolve().parents[2]


def _spawn_evidence(events: list[dict]) -> list[dict]:
    """Retain native delegation events, never infer spawning from prose."""
    found = []
    for event in events:
        item = event.get("item", {})
        data = event.get("data", {})
        if isinstance(item, dict) and (
            item.get("tool") == "spawn_agent" or item.get("tool_name") == "spawn_agent"
        ):
            found.append(event)
        if (
            event.get("type") == "tool.execution_start"
            and isinstance(data, dict)
            and str(data.get("toolName", "")).lower() in {"task", "agent"}
        ):
            found.append(event)
        message = event.get("message", {})
        if (
            isinstance(message, dict)
            and isinstance(message.get("content"), list)
            and any(
                isinstance(part, dict)
                and part.get("type") == "tool_use"
                and part.get("name") in {"Agent", "Task"}
                for part in message["content"]
            )
        ):
            found.append(event)
    return found


def _tool_parts(event: dict, kind: str) -> list[dict]:
    message = event.get("message")
    parts = message.get("content") if isinstance(message, dict) else None
    return (
        [part for part in parts if isinstance(part, dict) and part.get("type") == kind]
        if isinstance(parts, list)
        else []
    )


def _result_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(
            str(part["text"])
            for part in value
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def _json_objects(text: str) -> list[dict]:
    """Read actual tool-result JSON amid optional shell headings/trailing output."""
    decoder = json.JSONDecoder()
    result = []
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


def _run_identity(activity: dict, session_id: str, provider: str) -> dict:
    records = activity.get("events", [])
    starts = [e for e in records if e.get("event") == "start" and e.get("automatic")]
    ends = [e for e in records if e.get("event") == "end" and e.get("automatic")]
    if len(starts) != 1 or len(ends) != 1 or activity.get("active"):
        raise HarnessSmokeFailure("Expected exactly one finished automatic run.")
    start, end = starts[0], ends[0]
    if start.get("run_id") != end.get("run_id") or end.get("completion") != "completed":
        raise HarnessSmokeFailure("Automatic lifecycle is incomplete or belongs to different runs.")
    identity = dict(start)
    for event in records:
        if event.get("event") != "worker" or event.get("run_id") != start.get("run_id"):
            continue
        for field in ("worker_id", "parent_session_id", "harness"):
            value = event.get(field)
            if value is not None:
                if identity.get(field) not in (None, value):
                    raise HarnessSmokeFailure(
                        "Late worker evidence conflicts with recorded identity."
                    )
                identity[field] = value
    if identity.get("parent_session_id") != session_id or identity.get("harness") != provider:
        raise HarnessSmokeFailure("Compound identity does not match the actual parent/provider.")
    if not isinstance(identity.get("worker_id"), str) or not identity["worker_id"]:
        raise HarnessSmokeFailure("Exact native worker handle is absent from compound activity.")
    if start.get("automation_id") is not None or end.get("automation_id") is not None:
        raise HarnessSmokeFailure("Prompt fallback fabricated a scheduler automation handle.")
    return identity


def _claude_worker_evidence(
    events: list[dict], identity: dict, *, skill: Path, prefix: list[str], session_id: str
) -> dict:
    """Correlate observed Claude Agent/Task, agentId and parent_tool_use_id fields."""
    for event in events:
        for call in _tool_parts(event, "tool_use"):
            command = call.get("input", {}).get("command")
            if call.get("name") == "Bash" and isinstance(command, str):
                reject_model_shell_launch(command)
    candidates = []
    for event in events:
        if event.get("parent_tool_use_id") is not None:
            continue
        for call in _tool_parts(event, "tool_use"):
            if call.get("name") not in {"Agent", "Task"}:
                continue
            handles = set()
            for result_event in events:
                if result_event.get("parent_tool_use_id") is not None:
                    continue
                results = _tool_parts(result_event, "tool_result")
                if not any(result.get("tool_use_id") == call.get("id") for result in results):
                    continue
                native = result_event.get("tool_use_result")
                if isinstance(native, dict) and isinstance(native.get("agentId"), str):
                    handles.add(native["agentId"])
            if handles == {identity["worker_id"]}:
                candidates.append(call)
    if len(candidates) != 1:
        raise HarnessSmokeFailure(
            "No unique native delegation result matches the recorded worker ID."
        )
    spawn = candidates[0]
    handed = spawn.get("input", {}).get("prompt", "")
    if not isinstance(handed, str) or str(skill) not in handed or not _exact_prefix(handed, prefix):
        raise HarnessSmokeFailure(
            "The matching worker did not receive the exact skill/selector handoff."
        )
    if session_id not in handed:
        raise HarnessSmokeFailure("The matching worker handoff omitted the exact parent handle.")
    if "[agent-knowledge-compound-worker]" not in handed:
        raise HarnessSmokeFailure("The matching worker handoff omitted the exact worker marker.")
    children = [event for event in events if event.get("parent_tool_use_id") == spawn["id"]]
    calls = [part for event in children for part in _tool_parts(event, "tool_use")]
    results = {
        part["tool_use_id"]: part
        for event in children
        for part in _tool_parts(event, "tool_result")
        if isinstance(part.get("tool_use_id"), str)
    }
    skill_reads = [
        call["id"]
        for call in calls
        if call.get("name") == "Read"
        and _same_path(call.get("input", {}).get("file_path"), skill)
        and call.get("id") in results
        and not results[call["id"]].get("is_error")
        and _result_text(results[call["id"]].get("content"))
    ]
    if not skill_reads:
        raise HarnessSmokeFailure(
            "The matching child has no successful read of the installed skill."
        )
    lifecycle = {}
    expected_settings = Path(prefix[prefix.index("--settings") + 1])
    expected_profile = prefix[prefix.index("--profile") + 1]
    for call in calls:
        command = call.get("input", {}).get("command", "")
        result = results.get(call.get("id"), {})
        if (
            call.get("name") != "Bash"
            or not isinstance(command, str)
            or "agent-knowledge" not in command
            or re.search(r"(?:^|\s)compound(?:\s|$)", command) is None
            or result.get("is_error")
        ):
            continue
        for value in _json_objects(_result_text(result.get("content"))):
            action = value.get("action")
            if action not in {"start", "finish"} or value.get("status") != "ok":
                continue
            selected = value.get("selection", {})
            if (
                value.get("run_id") != identity["run_id"]
                or selected.get("mode") != "profile"
                or selected.get("profile") != expected_profile
                or not _same_path(selected.get("settings_path"), expected_settings)
            ):
                continue
            if action == "start" and value.get("started") is not True:
                continue
            if action == "finish" and value.get("completion") != "completed":
                continue
            lifecycle[action] = call["id"]
    if set(lifecycle) != {"start", "finish"}:
        raise HarnessSmokeFailure(
            "The matching child did not execute successful selected start/finish."
        )
    order = {call["id"]: index for index, call in enumerate(calls)}
    if (
        not min(order[read] for read in skill_reads)
        < order[lifecycle["start"]]
        < order[lifecycle["finish"]]
    ):
        raise HarnessSmokeFailure("Child lifecycle did not follow skill read, start, then finish.")
    return {
        "status": "passed",
        "provider": "claude",
        "run_id": identity["run_id"],
        "worker_id": identity["worker_id"],
        "spawn_tool_use_id": spawn["id"],
        "worker_marker_verified": True,
        "skill_read_tool_use_ids": skill_reads,
        "lifecycle_tool_use_ids": lifecycle,
        "child_event_count": len(children),
    }


def _delegation_evidence(
    provider: str,
    events: list[dict],
    activity: dict,
    *,
    skill: Path,
    prefix: list[str],
    session_id: str,
    native_logs: Path | None = None,
    codex_home: Path | None = None,
) -> dict:
    """Fail closed until native identity and actual child execution are correlated."""
    try:
        identity = _run_identity(activity, session_id, provider)
        if provider == "codex":
            if native_logs is None or codex_home is None:
                raise HarnessSmokeFailure(
                    "Native Codex rollout locations are required for child correlation."
                )
            parent, child, snapshots = capture_codex_rollouts(
                codex_home,
                native_logs,
                session_id=session_id,
                worker_id=identity["worker_id"],
                label="turn-1",
            )
            assert child is not None
            return {
                **codex_worker_evidence(
                    parent, child, identity, skill=skill, prefix=prefix, session_id=session_id
                ),
                **snapshots,
            }
        if provider == "copilot":
            return copilot_worker_evidence(
                events, identity, skill=skill, prefix=prefix, session_id=session_id
            )
        if provider != "claude":
            raise HarnessSmokeFailure("Unsupported native child correlation provider.")
        return _claude_worker_evidence(
            events, identity, skill=skill, prefix=prefix, session_id=session_id
        )
    except (HarnessSmokeFailure, KeyError, TypeError, ValueError, OSError) as error:
        return {"status": "failed", "provider": provider, "reason": str(error)}


def _fixture_prompt(*, first: bool) -> str:
    task = (
        "Read task.txt and report its word count."
        if first
        else "Read task.txt again and report its last word."
    )
    return (
        task + " Write only inside this disposable checkout. You may read installed resources "
        "and their verified owning sources identified by package metadata outside the checkout "
        "for owner discovery; do not write outside it. Do not publish, access network services "
        "or modify canonical knowledge. Finish any hook-delegated local work before your "
        "final response."
    )


def _write_observation_evidence(consumer: Path, provider: str) -> Path:
    path = consumer / "docs" / f"r8-{provider}-observation.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        "# Disposable hook observation evidence\n\n"
        "This fixture seeds an observation for local prompt-hook acceptance. The installed "
        "compound skill owns worker handoff, provenance and guarded disposition. The input "
        "does not establish a new domain claim or require canonical edits/publication.\n"
    )
    return path


def _codex_hook_overrides(consumer: Path) -> list[str]:
    """Use a top-level TOML map; dotted quoted-path overrides are ignored by Codex."""
    return [
        "-c",
        "projects={" + json.dumps(str(consumer)) + '={trust_level="trusted"}}',
        "-c",
        "features.hooks=true",
    ]


def _fixture_environment(launcher: Path, registry: Path) -> dict[str, str]:
    """Keep omitted-selector discovery in the disposable registry, not user profiles."""
    environment = _clean_runtime_env()
    environment.pop("PYTHONPATH", None)
    environment["PATH"] = str(launcher.parent) + os.pathsep + environment.get("PATH", "")
    environment["AGENT_KNOWLEDGE_SETTINGS"] = str(registry.resolve())
    return environment


def run(provider: str, *, live: bool, timeout: int) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f"agent-knowledge-local-{provider}."))
    logs = work / "logs"
    logs.mkdir()
    report: dict = {"provider": provider, "work_root": str(work), "turns": []}
    try:
        consumer, launcher, config, fresh = _fresh_consumer(ROOT, work, timeout)
        report["consumer"] = str(consumer)
        report["fresh_consumer"] = fresh["status"]
        registry = consumer / "local-profiles.yaml"
        environment = _fixture_environment(launcher, registry)
        report["probe_registry_isolation"] = {
            "mechanism": "AGENT_KNOWLEDGE_SETTINGS",
            "settings_path": str(registry.resolve()),
            "default_profile": None,
        }
        registry.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "knowledge-profiles.v1",
                    "profiles": {"example": {"config": str(config)}},
                }
            )
        )
        document = yaml.safe_load(config.read_text())
        document.setdefault("setup", {})["compounding"] = {
            "mode": "prompt",
            "owner": "agent-knowledge-compound:workspace:fresh-consumer",
        }
        config.write_text(yaml.safe_dump(document, sort_keys=False))
        setup = (
            ROOT
            / "packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py"
        )
        report["binding"] = _run_json(
            [
                str(launcher.parent / "python"),
                str(setup),
                "--workspace",
                str(config),
                "--consumer",
                str(consumer),
                "--package",
                str(next((consumer.parent / "dist").glob("*.whl"))),
                "--venv",
                str(launcher.parent.parent),
                "--profile",
                "example",
                "--settings",
                str(registry),
                "--apm-mode",
                "bind",
                "--runtime-mode",
                "existing",
            ],
            cwd=consumer,
            env=environment,
            log=logs / "bind.log",
            timeout=timeout,
        )
        prefix = [str(launcher), "--settings", str(registry), "--profile", "example"]

        def compound(action: str, label: str) -> dict:
            return _run_json(
                [*prefix, "compound", "--request-file", "-"],
                cwd=consumer,
                env=environment,
                log=logs / f"{label}.log",
                timeout=30,
                input_text=json.dumps({"action": action}),
            )

        compound("configure-trigger", "trigger")
        signal = _prepare_signal(consumer, launcher, config, provider, environment, logs, timeout)
        report["observation_evidence"] = str(_write_observation_evidence(consumer, provider))
        # A fixture-only no-write observation exercises ordinary guarded disposition.
        body = Path(signal["path"])
        body.write_text(
            body.read_text() + "\nThis disposable observation is only a hook test; "
            "it states no reusable claim and should receive no_update after review.\n"
        )
        (consumer / "task.txt").write_text("alpha beta gamma\n")
        report["due_before"] = compound("due", "due-before")
        if not report["due_before"]["due"]:
            raise HarnessSmokeFailure("Fresh pending input was not due.")
        executable = shutil.which(provider)
        if not executable:
            report.update(status="unavailable", reason="Provider CLI is unavailable.")
            return report
        report["version"] = subprocess.check_output([executable, "--version"], text=True).strip()
        if not live:
            report["status"] = "ready"
            return report
        if provider == "copilot":
            environment = _isolated_copilot_environment(
                consumer, base_env=environment, state_directory=logs / "copilot-home"
            )
        session = str(uuid4()) if provider == "copilot" else None
        for index in range(2):
            prompt = _fixture_prompt(first=index == 0)
            command = _provider_command(
                provider,
                executable,
                consumer=consumer,
                session=session,
                prompt=prompt,
                first=index == 0,
                budget=4,
                copilot_credits=30,
                log_dir=logs,
            )
            if provider == "codex":
                command[1:1] = _codex_hook_overrides(consumer)
            if provider == "claude":
                # Enable native delegation, absent from the older retrieval-only proof.
                tools_index = command.index("--tools") + 1
                command[tools_index] += ",Agent,SendMessage"
            log = logs / f"turn-{index + 1}.log"
            began = time.monotonic()
            result = _run(command, cwd=consumer, env=environment, log=log, timeout=timeout)
            events = _json_lines(result.stdout)
            evidence = _provider_evidence(provider, events, log)
            evidence["elapsed_seconds"] = round(time.monotonic() - began, 3)
            evidence["delegation_events"] = _spawn_evidence(events)
            report["turns"].append(evidence)
            if evidence["status"] != "passed":
                raise HarnessSmokeFailure("Provider turn did not complete successfully.", log=log)
            actual = evidence["session_id"]
            if not actual or (session and session != actual):
                raise HarnessSmokeFailure(
                    "Provider did not retain its exact session handle.", log=log
                )
            session = actual
            status = compound("status", f"status-{index + 1}")
            report["activity"] = status
            automatic = [
                event
                for event in status["events"]
                if event["event"] == "start" and event.get("automatic")
            ]
            finished = [
                event
                for event in status["events"]
                if event["event"] == "end" and event.get("automatic")
            ]
            if len(automatic) != 1 or len(finished) != 1 or status["active"]:
                raise HarnessSmokeFailure("Expected exactly one finished automatic run.", log=log)
            _run_identity(status, session, provider)
            if index == 0:
                skill = Path(report["binding"]["compounding"]["skill"])
                if not skill.is_absolute():
                    skill = consumer / skill
                evidence["delegation_verification"] = _delegation_evidence(
                    provider,
                    events,
                    status,
                    skill=skill,
                    prefix=prefix,
                    session_id=session,
                    native_logs=logs,
                    codex_home=Path(environment.get("CODEX_HOME", str(Path.home() / ".codex"))),
                )
                if evidence["delegation_verification"]["status"] != "passed":
                    raise HarnessSmokeFailure(
                        evidence["delegation_verification"]["reason"], log=log
                    )
            if index == 1 and provider == "codex":
                parent, _, snapshots = capture_codex_rollouts(
                    Path(environment.get("CODEX_HOME", str(Path.home() / ".codex"))),
                    logs,
                    session_id=session,
                    worker_id=None,
                    label="turn-2",
                )
                prior_ordinal = report["turns"][0]["delegation_verification"]["parent_last_ordinal"]
                new_spawns = codex_spawn_calls(parent, after_ordinal=prior_ordinal)
                evidence["native_repeat_verification"] = {
                    "new_spawn_count": len(new_spawns),
                    **snapshots,
                }
                if new_spawns:
                    raise HarnessSmokeFailure(
                        "Repeat prompt delegated another native Codex worker.", log=log
                    )
            if index == 1 and evidence["delegation_events"]:
                raise HarnessSmokeFailure("Repeat prompt delegated another worker.", log=log)
        report["due_after"] = compound("due", "due-after")
        if report["due_after"]["due"] or Path(signal["path"]).exists():
            raise HarnessSmokeFailure("Repeat eligibility or guarded drain was not satisfied.")
        report["status"] = "passed"
    except (HarnessSmokeFailure, OSError, ValueError, subprocess.SubprocessError) as error:
        report.update(status="failed", reason=str(error))
        if isinstance(error, HarnessSmokeFailure) and error.log:
            report["failure_log"] = str(error.log)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("codex", "claude", "copilot"), required=True)
    parser.add_argument("--live-agent", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.provider, live=args.live_agent, timeout=args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"status": report["status"], "report": str(args.output), "reason": report.get("reason")}
        )
    )
    return 0 if report["status"] in {"ready", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
