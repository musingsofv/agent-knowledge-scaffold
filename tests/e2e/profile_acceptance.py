#!/usr/bin/env python3
"""Verify named profiles through one installed provider; live model use is opt-in."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from claude_hook_acceptance import (
    _hook_contexts,
    _isolated_environment,
    _json_lines,
    _tool_commands,
)
from harness_agent_smoke import (
    HarnessSmokeFailure,
    _isolated_copilot_environment,
    _redact,
    _run,
    _run_json,
)

_PROVIDERS = ("codex", "claude", "copilot")
_RETRIEVAL_OPERATIONS = frozenset({"catalog", "search", "inspect"})
_BODY_READERS = frozenset({"awk", "cat", "head", "perl", "python", "python3", "sed", "tail"})
_REMOTE_COMMAND = (
    "curl",
    "wget",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "gh",
)
_REFLECTION_MARKER = 'At a natural stopping point, follow "Reflect and record useful observations"'
_COPILOT_PROVIDER_MARKER = (
    "Provider harness (copy exactly into origin.harness for a harness-origin signal): copilot"
)


def _assert(value: object, message: str) -> None:
    if not value:
        raise HarnessSmokeFailure(message)


def _last(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    return next((event for event in reversed(events) if event.get("type") == event_type), {})


def _codex_commands(events: list[dict[str, Any]]) -> list[str]:
    return [
        command
        for event in events
        if event.get("type") == "item.completed"
        for item in [event.get("item")]
        if isinstance(item, dict) and item.get("type") == "command_execution"
        for command in [item.get("command")]
        if isinstance(command, str)
    ]


def _copilot_commands(events: list[dict[str, Any]]) -> list[str]:
    return [
        command
        for event in events
        if event.get("type") == "tool.execution_start"
        for data in [event.get("data")]
        if isinstance(data, dict) and str(data.get("toolName", "")).casefold() == "bash"
        for arguments in [data.get("arguments")]
        if isinstance(arguments, dict)
        for command in [arguments.get("command")]
        if isinstance(command, str)
    ]


def _copilot_transformed_prompts(events: list[dict[str, Any]]) -> list[str]:
    return [
        content
        for event in events
        if event.get("type") == "user.message"
        for data in [event.get("data")]
        if isinstance(data, dict)
        for content in [data.get("transformedContent")]
        if isinstance(content, str)
    ]


def _provider_evidence(provider: str, events: list[dict[str, Any]], log: Path) -> dict[str, Any]:
    """Normalize the provider's native JSONL without retaining tool output."""
    match provider:
        case "claude":
            init = next((event for event in events if event.get("subtype") == "init"), {})
            final = _last(events, "result")
            return {
                "status": "failed" if not final or final.get("is_error") else "passed",
                "session_id": init.get("session_id"),
                "model": init.get("model"),
                "response": _redact(str(final.get("result", ""))),
                "commands": [_redact(command) for command in _tool_commands(events)],
                "log": str(log),
            }
        case "codex":
            started = _last(events, "thread.started")
            completed = _last(events, "turn.completed")
            failed = _last(events, "turn.failed")
            messages = [
                item.get("text")
                for event in events
                if event.get("type") == "item.completed"
                for item in [event.get("item")]
                if isinstance(item, dict) and item.get("type") == "agent_message"
                if isinstance(item.get("text"), str)
            ]
            return {
                "status": "failed" if not completed or failed else "passed",
                "session_id": started.get("thread_id"),
                "model": None,
                "response": _redact(str(messages[-1] if messages else "")),
                "commands": [_redact(command) for command in _codex_commands(events)],
                "log": str(log),
            }
        case "copilot":
            final = _last(events, "result")
            routed = _last(events, "session.auto_mode_resolved")
            routed_data = routed.get("data") if isinstance(routed.get("data"), dict) else {}
            messages = [
                data
                for event in events
                if event.get("type") == "assistant.message"
                for data in [event.get("data")]
                if isinstance(data, dict)
                and isinstance(data.get("content"), str)
                and (data.get("phase") in {"final_answer", None})
            ]
            message = messages[-1] if messages else {}
            return {
                "status": "failed" if not final or final.get("exitCode") != 0 else "passed",
                "session_id": final.get("sessionId"),
                "model": routed_data.get("chosenModel") or message.get("model"),
                "response": _redact(str(message.get("content", ""))),
                "commands": [_redact(command) for command in _copilot_commands(events)],
                "log": str(log),
            }
        case _:
            raise ValueError(f"Unsupported provider: {provider}")


def _provider_command(
    provider: str,
    executable: str,
    *,
    consumer: Path,
    session: str | None,
    prompt: str,
    first: bool,
    budget: float,
    copilot_credits: int,
    log_dir: Path,
) -> list[str]:
    """Build a persisted, resumable, non-interactive provider command."""
    match provider:
        case "claude":
            common = [
                executable,
                "--model",
                "opus",
                "--setting-sources",
                "project,local",
                "--include-hook-events",
                "--output-format",
                "stream-json",
                "--verbose",
                "--max-budget-usd",
                str(budget),
                "--permission-mode",
                "bypassPermissions",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--tools",
                "Read,Write,Edit,Bash,Grep,Glob,Skill",
            ]
            if first:
                return [*common, "-p", prompt]
            _assert(session, "Claude resume requires its emitted session ID.")
            return [*common, "--resume", str(session), "-p", prompt]
        case "codex":
            if first:
                return [
                    executable,
                    "exec",
                    "--json",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--dangerously-bypass-hook-trust",
                    "--ignore-user-config",
                    "--cd",
                    str(consumer),
                    prompt,
                ]
            _assert(session, "Codex resume requires its emitted thread ID.")
            return [
                executable,
                "exec",
                "resume",
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                "--dangerously-bypass-hook-trust",
                "--ignore-user-config",
                str(session),
                prompt,
            ]
        case "copilot":
            _assert(session, "Copilot requires a chosen session ID.")
            return [
                executable,
                "-p",
                prompt,
                "--model",
                "auto",
                "--auto-tier",
                "efficiency",
                "--max-ai-credits",
                str(copilot_credits),
                "--allow-all-tools",
                "--disallow-temp-dir",
                "--deny-url=*",
                "--no-ask-user",
                "--no-auto-update",
                "--no-remote",
                "--no-remote-export",
                "--disable-builtin-mcps",
                "--add-dir",
                ".",
                "--output-format",
                "json",
                "--log-level",
                "none",
                "--log-dir",
                str(log_dir),
                f"--session-id={session}" if first else f"--resume={session}",
                "-C",
                str(consumer),
            ]
        case _:
            raise ValueError(f"Unsupported provider: {provider}")


def _provider_turn(
    provider: str,
    executable: str,
    *,
    consumer: Path,
    env: dict[str, str],
    log: Path,
    session: str | None,
    prompt: str,
    first: bool,
    timeout: float,
    budget: float,
    copilot_credits: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    command = _provider_command(
        provider,
        executable,
        consumer=consumer,
        session=session,
        prompt=prompt,
        first=first,
        budget=budget,
        copilot_credits=copilot_credits,
        log_dir=log.parent / f"{provider}-internal",
    )
    result = _run(command, cwd=consumer, env=env, timeout=timeout, log=log)
    events = _json_lines(result.stdout)
    evidence = _provider_evidence(provider, events, log)
    _assert(evidence["status"] == "passed", f"{provider.title()} turn failed; inspect {log}.")
    actual = evidence.get("session_id")
    _assert(isinstance(actual, str) and actual, f"{provider.title()} omitted its session ID.")
    if session is not None:
        _assert(actual == session, f"{provider.title()} changed the provider session ID.")
    if provider == "claude":
        _assert(evidence["model"] == "claude-opus-5", "Claude did not use Opus 5.")
    return events, evidence


def _tokenizations(command: str) -> list[list[str]]:
    """Tokenize a command and any nested shell script arguments once."""
    pending = [command]
    seen: set[str] = set()
    tokenizations: list[list[str]] = []
    while pending:
        value = pending.pop()
        if value in seen:
            continue
        seen.add(value)
        try:
            tokens = shlex.split(value)
        except ValueError:
            continue
        tokenizations.append(tokens)
        pending.extend(
            token
            for token in tokens
            if token not in seen
            and any(marker in token for marker in ("agent-knowledge", "release.md"))
        )
    return tokenizations


def _resolved_shell_argument(value: str, tokens: list[str]) -> str:
    match = re.fullmatch(r"\$([A-Za-z_][A-Za-z0-9_]*)|\$\{([A-Za-z_][A-Za-z0-9_]*)\}", value)
    if match is None:
        return value
    name = next(group for group in match.groups() if group is not None)
    prefix = name + "="
    for token in tokens:
        candidate = token.rstrip(";")
        if candidate.startswith(prefix):
            return candidate[len(prefix) :].strip("\"'")
    return value


def _path_argument_matches(
    value: str, expected: Path, *, cwd: Path, tokens: list[str] | None = None
) -> bool:
    resolved = _resolved_shell_argument(value, tokens or [])
    if resolved == expected.name:
        return True
    candidate = Path(resolved).expanduser()
    if not candidate.is_absolute():
        candidate = cwd / candidate
    return candidate.resolve() == expected.resolve()


def _session_argument_matches(
    value: str, *, provider: str, session: str, tokens: list[str]
) -> bool:
    resolved = _resolved_shell_argument(value, tokens)
    if resolved == session:
        return True
    return provider == "copilot" and resolved in {
        "$COPILOT_AGENT_SESSION_ID",
        "${COPILOT_AGENT_SESSION_ID}",
    }


def _invokes_cli(
    command: str,
    *,
    launcher: Path,
    settings: Path,
    cwd: Path,
    profile: str,
    provider: str,
    session: str,
    operation: tuple[str, ...],
) -> bool:
    for tokens in _tokenizations(command):
        start = next(
            (
                index
                for index, token in enumerate(tokens)
                if _path_argument_matches(token, launcher, cwd=cwd, tokens=tokens)
            ),
            None,
        )
        if start is None:
            continue
        arguments = tokens[start + 1 :]
        flags = ("--settings", "--profile", "--harness", "--session-id")
        if any(flag not in arguments for flag in flags):
            continue
        values = {
            flag: arguments[arguments.index(flag) + 1]
            for flag in flags
            if arguments.index(flag) + 1 < len(arguments)
        }
        if len(values) != len(flags):
            continue
        if not _path_argument_matches(values["--settings"], settings, cwd=cwd, tokens=tokens):
            continue
        if values["--profile"] != profile or values["--harness"] != provider:
            continue
        if not _session_argument_matches(
            values["--session-id"], provider=provider, session=session, tokens=tokens
        ):
            continue
        if any(
            arguments[index : index + len(operation)] == list(operation)
            for index in range(len(arguments))
        ):
            return True
    return False


def _assert_model_activity(
    commands: list[str],
    *,
    launcher: Path,
    settings: Path,
    profile: str,
    provider: str,
    session: str,
    body: Path,
) -> None:
    _assert(
        any(
            _invokes_cli(
                command,
                launcher=launcher,
                settings=settings,
                cwd=launcher.parent.parent.parent,
                profile=profile,
                provider=provider,
                session=session,
                operation=("context",),
            )
            for command in commands
        ),
        "Model did not invoke installed context with the exact profile and session.",
    )
    body_value = str(body.resolve())
    read = False
    for command in commands:
        if body_value not in command:
            continue
        for tokens in _tokenizations(command):
            if any(Path(token).name in _BODY_READERS for token in tokens):
                read = True
                break
    _assert(read, "Model did not perform an ordinary file read of the selected body.")


def _assert_signal_list_activity(
    commands: list[str],
    *,
    launcher: Path,
    settings: Path,
    profile: str,
    provider: str,
    session: str,
) -> None:
    values = [re.escape(session)]
    if provider == "copilot":
        values.extend(
            [
                r"\$COPILOT_AGENT_SESSION_ID",
                r"\$\{COPILOT_AGENT_SESSION_ID\}",
            ]
        )
        for tokens in _tokenizations("\n".join(commands)):
            for token in tokens:
                assignment = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.+?);?", token)
                if assignment is None:
                    continue
                if assignment.group(2).strip("\"'") in {
                    "$COPILOT_AGENT_SESSION_ID",
                    "${COPILOT_AGENT_SESSION_ID}",
                }:
                    values.extend(
                        [
                            re.escape("$" + assignment.group(1)),
                            re.escape("${" + assignment.group(1) + "}"),
                        ]
                    )
    session_pattern = re.compile(
        r"(?:\"session_id\"|'session_id'|\bsession_id\b)\s*:\s*(?:\"|')?(?:"
        + "|".join(values)
        + r")(?:\"|')?(?=\s*(?:[,}\n|]|$))"
    )
    _assert(
        any(
            _invokes_cli(
                command,
                launcher=launcher,
                settings=settings,
                cwd=launcher.parent.parent.parent,
                profile=profile,
                provider=provider,
                session=session,
                operation=("signal", "list"),
            )
            and any(
                session_pattern.search(value) is not None
                for value in [command, *(" ".join(tokens) for tokens in _tokenizations(command))]
            )
            for command in commands
        ),
        "Resumed model did not list exact-session signals with an inline session filter.",
    )


def _copilot_tool_arguments(events: list[dict[str, Any]]) -> list[str]:
    """Return serialized native tool arguments without retaining tool output."""
    return [
        json.dumps(arguments, sort_keys=True)
        for event in events
        if event.get("type") == "tool.execution_start"
        for data in [event.get("data")]
        if isinstance(data, dict)
        for arguments in [data.get("arguments")]
        if isinstance(arguments, dict)
    ]


def _references_profile_root(value: str, *, other_root: Path, consumer: Path) -> bool:
    """Match the alternate root or its descendants with path boundaries."""
    absolute = other_root.resolve()
    aliases = [str(absolute)]
    try:
        relative = absolute.relative_to(consumer.resolve()).as_posix()
    except ValueError:
        relative = None
    if relative is not None:
        aliases.append(relative)
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_-]){re.escape(alias)}(?=$|[\\/\s\"'`,;:}}\])])",
            value,
        )
        is not None
        for alias in aliases
    )


def _assert_profile_isolation(
    commands: list[str],
    *,
    other_profile: str,
    other_root: Path,
    consumer: Path,
    events: list[dict[str, Any]] | None = None,
) -> None:
    observed = [*commands, *_copilot_tool_arguments(events or [])]
    for command in observed:
        _assert(
            not _references_profile_root(
                command,
                other_root=other_root,
                consumer=consumer,
            ),
            "Model directly read from the alternate profile.",
        )
        for tokens in _tokenizations(command):
            if "--profile" not in tokens:
                continue
            index = tokens.index("--profile")
            _assert(
                index + 1 >= len(tokens) or tokens[index + 1] != other_profile,
                "Model invoked the alternate profile.",
            )


def _usage_events(directory: Path) -> list[dict[str, Any]]:
    return [
        event
        for path in sorted(directory.rglob("*.jsonl"))
        for event in _json_lines(path.read_text(encoding="utf-8"))
    ]


def _retrieval_proof(
    events: list[dict[str, Any]],
    *,
    profile: str,
    provider: str,
    session: str,
    body: Path,
) -> dict[str, Any]:
    correlated = [
        event
        for event in events
        if event.get("schema_version") == "knowledge-retrieval-receipt.v1"
        and isinstance(event.get("context"), dict)
        and event["context"].get("harness") == provider
        and event["context"].get("session_id") == session
    ]
    _assert(correlated, "No retrieval receipts use the exact provider session provenance.")
    _assert(
        all(
            isinstance(event.get("selection"), dict)
            and event["selection"].get("profile") == profile
            for event in correlated
        ),
        "A correlated retrieval receipt used a different selected profile.",
    )
    operations = {str(event.get("operation")) for event in correlated}
    missing = sorted(_RETRIEVAL_OPERATIONS - operations)
    _assert(not missing, "Missing retrieval receipts: " + ", ".join(missing))
    terminal = {
        operation: next(
            event for event in reversed(correlated) if event.get("operation") == operation
        )
        for operation in _RETRIEVAL_OPERATIONS
    }
    _assert(
        all(
            isinstance(event.get("response"), dict) and event["response"].get("status") == "ok"
            for event in terminal.values()
        ),
        "A required retrieval operation did not recover to a successful terminal receipt.",
    )
    selected_path = str(body.resolve())
    search_paths = [
        str(result.get("local_path"))
        for event in correlated
        if event.get("operation") == "search" and isinstance(event.get("response"), dict)
        for results in [event["response"].get("results")]
        if isinstance(results, list)
        for result in results
        if isinstance(result, dict)
    ]
    inspect_paths = [
        str(preview.get("local_path"))
        for event in correlated
        if event.get("operation") == "inspect" and isinstance(event.get("response"), dict)
        for preview in [event["response"].get("preview")]
        if isinstance(preview, dict)
    ]
    _assert(selected_path in search_paths, "Search receipts did not select the expected body.")
    _assert(selected_path in inspect_paths, "Inspect receipts did not preview the expected body.")
    return {
        "receipt_count": len(correlated),
        "operations": sorted(operations),
        "recovered_attempts": sum(
            1
            for event in correlated
            if event.get("operation") in _RETRIEVAL_OPERATIONS
            and isinstance(event.get("response"), dict)
            and event["response"].get("status") != "ok"
        ),
        "session_id": session,
        "profile": profile,
    }


def _assert_no_remote_effects(events: list[dict[str, Any]], commands: list[str]) -> None:
    for command in commands:
        lowered = command.casefold()
        if any(
            re.search(rf"(?:^|[;&|\s]){re.escape(name)}(?:$|\s)", lowered)
            for name in _REMOTE_COMMAND
        ) or re.search(r"(?:^|[;&|\s])git\s+(?:clone|fetch|pull|push)(?:$|\s)", lowered):
            raise HarnessSmokeFailure("Model invoked a remote-capable shell command.")
    remote_tools: list[str] = []
    for event in events:
        if event.get("type") == "assistant":
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, list):
                remote_tools.extend(
                    str(item.get("name"))
                    for item in content
                    if isinstance(item, dict)
                    and item.get("type") == "tool_use"
                    and str(item.get("name", "")).casefold()
                    in {"webfetch", "websearch", "web_fetch", "web_search"}
                )
        item = event.get("item")
        if isinstance(item, dict) and str(item.get("type", "")).casefold() in {
            "mcp_tool_call",
            "web_search",
        }:
            remote_tools.append(str(item.get("type")))
        data = event.get("data")
        if event.get("type") == "tool.execution_start" and isinstance(data, dict):
            name = str(data.get("toolName", "")).casefold()
            if name.startswith(("github", "web_", "http")) or "mcp" in name:
                remote_tools.append(name)
    _assert(not remote_tools, "Model invoked a remote provider tool: " + ", ".join(remote_tools))


def run(
    consumer: Path,
    *,
    live: bool,
    timeout: float,
    budget: float,
    provider: str = "claude",
    copilot_credits: int = 30,
) -> dict[str, Any]:
    consumer = consumer.resolve()
    launcher = consumer / ".agent-knowledge-venv/bin/agent-knowledge"
    python = launcher.parent / "python"
    hook = launcher.parent / "agent-knowledge-hook"
    logs = consumer / "profile-proof/logs"
    logs.mkdir(parents=True)
    settings = consumer / "profile-proof/config.yaml"
    candidate = settings.with_name("candidate.yaml")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PATH"] = str(launcher.parent) + os.pathsep + env.get("PATH", os.defpath)
    home = consumer / "profile-proof/home"
    home.mkdir()
    cli_env = {**env, "HOME": str(home)}
    report: dict[str, Any] = {
        "status": "running",
        "consumer": str(consumer),
        "settings": str(settings),
        "provider": provider,
        "native_scheduling": "not-run",
        "live": [],
        "deterministic": [],
    }
    sequence = 0

    def cli(name: str, command: str, request: object = None) -> dict[str, Any]:
        nonlocal sequence
        sequence += 1
        return _run_json(
            [
                str(launcher),
                "--settings",
                str(settings),
                "--profile",
                name,
                *command.split(),
                "--request-file",
                "-",
            ],
            cwd=consumer,
            env=cli_env,
            input_text=json.dumps(request or {}),
            timeout=timeout,
            log=logs / f"cli-{sequence}.log",
        )

    registry: dict[str, Any] = {
        "schema_version": "knowledge-profiles.v1",
        "default_profile": "work",
        "profiles": {},
    }
    for name, answer in (("personal", "blue-window-17"), ("work", "amber-window-29")):
        root = consumer / "profile-proof" / name
        knowledge = root / "knowledge"
        knowledge.mkdir(parents=True)
        (root / "ai/signals").mkdir(parents=True)
        (root / "ai/usage").mkdir(parents=True)
        (root / ".gitignore").write_text("ai/signals/\nai/usage/\n")
        catalog = {
            "schema_version": "knowledge-catalog.v1",
            "scopes": {"org:example": {"label": "Example"}},
            **{
                field: {}
                for field in [
                    "entities",
                    "topics",
                    "languages",
                    "technologies",
                    "technology_families",
                    "environments",
                ]
            },
        }
        catalog["topics"] = {"release-management": {"label": "Release management"}}
        (root / "catalog.yaml").write_text(yaml.safe_dump(catalog))
        metadata = {
            "schema_version": "knowledge.v1",
            "kind": "runbook",
            "title": "Release window",
            "description": "Find the approved release window for this workspace.",
            "scope": ["org:example"],
            "topics": ["release-management"],
        }
        (knowledge / "release.md").write_text(
            "---\n"
            + yaml.safe_dump(metadata)
            + "---\n\n# Release window\n\nThe approved window is "
            + answer
            + ".\n"
        )
        config = root / "workspace.yaml"
        config.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "knowledge-workspace.v1",
                    "workspace_id": "workspace:" + name,
                    "applicable_scopes": ["org:example"],
                    "sources": [
                        {"id": "local", "root": "./knowledge", "catalog": "./catalog.yaml"}
                    ],
                    "signal_storage": {"scaffold_root": ".", "code_root": str(consumer.parent)},
                    "setup": {"venv": str(launcher.parent.parent)},
                }
            )
        )
        registry["profiles"][name] = {
            "config": str(config),
            "overrides": {"receipts": {"retention_days": 60}},
        }
    candidate.write_text("# Preserve this registry comment.\n" + yaml.safe_dump(registry))
    setup_dir = consumer / ".claude/skills/knowledge-setup/scripts"
    register = [
        str(python),
        str(setup_dir / "register_profile.py"),
        "--settings",
        str(settings),
        "--candidate",
        str(candidate),
        "--expected-sha256",
        "missing",
    ]
    _run(register, cwd=consumer, env=cli_env, timeout=timeout, log=logs / "register.log")
    assert settings.read_bytes() == candidate.read_bytes()
    report["deterministic"].append("Installed registry helper preserves candidate bytes")
    for name in registry["profiles"]:
        assert cli(name, "context")["selection"]["profile"] == name
        assert cli(name, "doctor")["readiness"]["read"] == "ready"
        result = cli(name, "search", {"text": {"any": ["release window"]}})
        assert len(result["results"]) == 1
        assert name in Path(result["results"][0]["local_path"]).parts
        assert cli(name, "validate", {"sources": ["local"]})["valid"]
    report["deterministic"].append("Installed context/doctor/search/validate isolate both profiles")
    # The default path is explicitly confined to a disposable home.
    default = home / ".config/agent-knowledge/config.yaml"
    default.parent.mkdir(parents=True)
    default.write_text(settings.read_text())
    result = _run_json(
        [str(launcher), "context"],
        cwd=consumer,
        env=cli_env,
        timeout=timeout,
        log=logs / "default.log",
    )
    assert result["selection"]["profile"] == "work"
    report["deterministic"].append("Unqualified installed context reads temporary HOME default")
    if not live:
        report["status"] = "ready"
        return report
    executable = shutil.which(provider)
    if not executable:
        report.update(status="unavailable", reason=f"{provider.title()} CLI not installed")
        return report
    temporary = None
    if provider == "claude":
        temporary, provider_env = _isolated_environment(
            use_global_auth=True,
            claude=Path(executable),
            hook_launcher=hook,
        )
    else:
        provider_env = dict(os.environ)
        provider_env.pop("PYTHONPATH", None)
        provider_env["PATH"] = (
            str(launcher.parent) + os.pathsep + provider_env.get("PATH", os.defpath)
        )
    if provider == "copilot":
        provider_env = _isolated_copilot_environment(
            consumer,
            base_env=provider_env,
            state_directory=logs / "copilot-home",
        )
        for key, value in (
            ("user.email", "acceptance@example.invalid"),
            ("user.name", "Agent Knowledge Acceptance"),
        ):
            _run(
                ["git", "config", key, value],
                cwd=consumer,
                env=provider_env,
                timeout=timeout,
                log=logs / f"copilot-git-{key.replace('.', '-')}.log",
            )
        _run(
            ["git", "add", "."],
            cwd=consumer,
            env=provider_env,
            timeout=timeout,
            log=logs / "copilot-git-add.log",
        )
        _run(
            ["git", "commit", "--no-verify", "-m", "Prepare Copilot acceptance consumer"],
            cwd=consumer,
            env=provider_env,
            timeout=timeout,
            log=logs / "copilot-git-commit.log",
        )
        report["deterministic"].append(
            "Copilot repository hooks are committed before the live session"
        )
    # Authentication stays provider-owned. Knowledge selectors always name the disposable registry.
    try:
        # One live profile plus an alternate default proves selection and isolation
        # without spending a second pair of provider turns on the symmetric case.
        for name, answer in (("personal", "blue-window-17"),):
            body = consumer / "profile-proof" / name / "knowledge/release.md"
            other = "work" if name == "personal" else "personal"
            other_root = consumer / "profile-proof" / other
            boundary = (
                f"Work only in the disposable consumer {consumer}. Use knowledge profile {name} "
                f"from registry {settings} for this session, with installed CLI {launcher}. "
                "Read the installed guide returned by describe and follow its session workflow. "
                "Do not use --config or another profile. No scheduling, remote access, global "
                "configuration changes, or compounding. "
                f"On every selected knowledge call pass --settings {settings}, --profile {name}, "
                f"--harness {provider}, and the exact provider session ID supplied by hook "
                "context as --session-id. Put those global flags before the operation. "
            )
            prompt = boundary + (
                "What is this workspace's approved release window? First run context, then "
                "catalog, search, and inspect with the installed CLI. Use --request-file - for "
                "structured requests. After inspect, read the selected preview's exact local_path "
                "with ordinary POSIX cat or sed; the answer exists only in the body. "
                "Separately, I observed a durable gap: the release runbook omits where rollback "
                "evidence should be attached. Reflect and record this gap for follow-up using "
                "the installed signal template and configured CLI, checking this session's "
                "pending signals first. Do not change canonical knowledge. End with only the "
                "approved release-window value, with no label, punctuation, or explanation."
            )
            chosen_session = str(uuid4()) if provider == "copilot" else None
            events, first = _provider_turn(
                provider,
                executable,
                consumer=consumer,
                env=provider_env,
                session=chosen_session,
                prompt=prompt,
                first=True,
                timeout=timeout,
                budget=budget,
                copilot_credits=copilot_credits,
                log=logs / f"{name}-first.log",
            )
            session = str(first["session_id"])
            if provider == "copilot":
                transformed = _copilot_transformed_prompts(events)
                _assert(
                    any(
                        _REFLECTION_MARKER in value
                        and _COPILOT_PROVIDER_MARKER in value
                        and session in value
                        for value in transformed
                    ),
                    "Copilot prompt hook omitted provider/session provenance.",
                )
            commands = [str(command) for command in first["commands"]]
            entry: dict[str, Any] = {
                "profile": name,
                "session_id": session,
                "model": first.get("model"),
                "first_log": str(logs / f"{name}-first.log"),
                "status": "checking",
            }
            report["live"].append(entry)
            _assert(
                str(first["response"]).strip() == answer,
                f"{provider.title()} did not return the exact selected-profile answer.",
            )
            _assert_model_activity(
                commands,
                launcher=launcher,
                settings=settings,
                profile=name,
                provider=provider,
                session=session,
                body=body,
            )
            retrieval = _retrieval_proof(
                _usage_events(consumer / "profile-proof" / name / "ai/usage"),
                profile=name,
                provider=provider,
                session=session,
                body=body,
            )
            _assert_no_remote_effects(events, commands)
            _assert_profile_isolation(
                commands,
                other_profile=other,
                other_root=other_root,
                consumer=consumer,
                events=events,
            )
            if provider == "claude":
                contexts = _hook_contexts(events, "SessionStart:startup") + _hook_contexts(
                    events, "UserPromptSubmit"
                )
                _assert(
                    contexts and all(session in value for _, value in contexts),
                    "Exact Claude hook session context missing.",
                )
            recorded = cli(name, "signal list", {"session_id": session, "include_shared": True})
            _assert(recorded["total_matches"] == 1, "Expected one exact-session signal.")
            signal = recorded["results"][0]
            _assert(
                signal["origin"]["harness"] == provider
                and signal["origin"]["session_id"] == session
                and signal["origin"]["workspace_id"] == f"workspace:{name}",
                "Signal omitted exact provider, session, or profile provenance.",
            )
            _assert(
                cli(other, "signal list", {"session_id": session, "include_shared": True})[
                    "total_matches"
                ]
                == 0,
                "Signal crossed the selected profile boundary.",
            )
            foreign_receipts = [
                event
                for event in _usage_events(consumer / "profile-proof" / other / "ai/usage")
                if isinstance(event.get("context"), dict)
                and event["context"].get("session_id") == session
            ]
            _assert(
                not foreign_receipts,
                "Retrieval receipts crossed the selected profile boundary.",
            )
            # Change the default; the retained explicit selection must survive.
            registry["default_profile"] = other
            settings.write_text("# Preserve this registry comment.\n" + yaml.safe_dump(registry))
            resume_prompt = boundary + (
                "Continue this session's selected profile after the registry default changed. "
                "The rollback-evidence gap is the same observation as before. Use signal list "
                "with an inline JSON or YAML request containing this exact session_id on stdin "
                "and --request-file -. Inspect the existing note using its local path, and follow "
                "the installed duplicate guidance. Do not record an equivalent signal or change "
                "the registry. Respond with exactly NO_DUPLICATE."
            )
            resumed_events, resumed = _provider_turn(
                provider,
                executable,
                consumer=consumer,
                env=provider_env,
                session=session,
                prompt=resume_prompt,
                first=False,
                timeout=timeout,
                budget=budget,
                copilot_credits=copilot_credits,
                log=logs / f"{name}-resume.log",
            )
            resumed_commands = [str(command) for command in resumed["commands"]]
            _assert(
                str(resumed["response"]).strip() == "NO_DUPLICATE",
                f"{provider.title()} resume did not complete the duplicate check.",
            )
            if provider == "copilot":
                transformed = _copilot_transformed_prompts(resumed_events)
                _assert(
                    any(
                        _REFLECTION_MARKER in value
                        and _COPILOT_PROVIDER_MARKER in value
                        and session in value
                        for value in transformed
                    ),
                    "Copilot resume prompt omitted provider/session provenance.",
                )
            _assert_signal_list_activity(
                resumed_commands,
                launcher=launcher,
                settings=settings,
                profile=name,
                provider=provider,
                session=session,
            )
            _assert_no_remote_effects(resumed_events, resumed_commands)
            _assert_profile_isolation(
                resumed_commands,
                other_profile=other,
                other_root=other_root,
                consumer=consumer,
                events=resumed_events,
            )
            if provider == "claude":
                _assert(
                    _hook_contexts(resumed_events, "SessionStart:resume"),
                    "Claude resume hook context is missing.",
                )
            _assert(
                cli(name, "signal list", {"session_id": session, "include_shared": True})[
                    "total_matches"
                ]
                == 1,
                "Resume recorded a duplicate signal.",
            )
            _assert(
                settings.read_text().startswith("# Preserve this registry comment."),
                "Provider changed the profile registry.",
            )
            entry.update(
                status="passed",
                response=first["response"],
                commands=commands,
                retrieval=retrieval,
                resume_log=str(logs / f"{name}-resume.log"),
                resume_response=resumed["response"],
                resume_commands=resumed_commands,
            )
        report["status"] = "passed"
        return report
    finally:
        if temporary:
            shutil.rmtree(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument("--provider", choices=_PROVIDERS, default="claude")
    parser.add_argument("--live-agent", action="store_true")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--max-budget-usd", type=float, default=2)
    parser.add_argument("--max-ai-credits", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(
            args.consumer,
            live=args.live_agent,
            timeout=args.timeout,
            budget=args.max_budget_usd,
            provider=args.provider,
            copilot_credits=args.max_ai_credits,
        )
    except Exception as error:
        report = {
            "status": "failed",
            "reason": _redact(str(error)),
            "consumer": str(args.consumer),
            "provider": args.provider,
            "native_scheduling": "not-run",
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] in {"ready", "passed"} else 1


if __name__ == "__main__":
    sys.exit(main())
