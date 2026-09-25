#!/usr/bin/env python3
"""Run the disposable authenticated Claude Code discovery-hook acceptance."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class ClaudeAcceptanceFailure(RuntimeError):
    """Describe a failed Claude provider contract assertion."""

    def __init__(self, message: str, *, report: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.report = report


_EXPECTED_MODEL = "claude-opus-5"
_MODEL_RECORD_MARKER = "MODEL_RECORD_OK"
_MODEL_DEDUP_MARKER = "MODEL_DEDUP_OK"
_MODEL_SIGNAL_ID = "model-hook-origin"
_MODEL_SIGNAL_FILE = "model-hook-origin.md"
_REFLECTION_MARKER = 'At a natural stopping point, follow "Reflect and record useful observations"'
_SESSION_ID_MARKER = (
    "Provider session ID (copy exactly into origin.session_id for a harness-origin signal): "
)
_PROVIDER_MARKER = (
    "Provider harness (copy exactly into origin.harness for a harness-origin signal): claude"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the disposable Claude Code Opus 5 hook acceptance."
    )
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument(
        "--hook-launcher",
        type=Path,
        required=True,
        help="Absolute consumer-local agent-knowledge-hook path returned by setup.",
    )
    parser.add_argument("--output", type=Path, help="Write the JSON evidence report to this path.")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        default=1.0,
        help="Maximum USD per bounded Claude turn (default: 1.0).",
    )
    parser.add_argument(
        "--require-passed",
        action="store_true",
        help="Return failure when Claude is unavailable or the acceptance does not pass.",
    )
    parser.add_argument(
        "--use-global-auth",
        action="store_true",
        help=(
            "Use the logged-in default Claude account for live proof; project/local "
            "consumer settings are still the only settings loaded."
        ),
    )
    return parser


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ClaudeAcceptanceFailure(message)


def _json_lines(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _hook_response_output(event: dict[str, Any]) -> dict[str, Any] | None:
    value = event.get("output")
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _hook_context_channels(value: dict[str, Any]) -> list[tuple[str, str]]:
    channels: list[tuple[str, str]] = []
    for field in ("additionalContext", "systemMessage"):
        content = value.get(field)
        if isinstance(content, str):
            channels.append((field, content))
    nested = value.get("hookSpecificOutput")
    if isinstance(nested, dict):
        content = nested.get("additionalContext")
        if isinstance(content, str):
            channels.append(("hookSpecificOutput.additionalContext", content))
        content = nested.get("systemMessage")
        if isinstance(content, str):
            channels.append(("hookSpecificOutput.systemMessage", content))
    return channels


def _hook_events(
    events: list[dict[str, Any]], hook_name: str, subtype: str
) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("subtype") == subtype and event.get("hook_name") == hook_name
    ]


def _hook_contexts(events: list[dict[str, Any]], hook_name: str) -> list[tuple[str, str]]:
    contexts: list[tuple[str, str]] = []
    for event in _hook_events(events, hook_name, "hook_response"):
        output = _hook_response_output(event)
        if output is not None:
            contexts.extend(_hook_context_channels(output))
    return contexts


def _event_summary(
    events: list[dict[str, Any]], expected_marker: str, lifecycle_source: str
) -> dict[str, Any]:
    init = next((event for event in events if event.get("subtype") == "init"), {})
    lifecycle_name = f"SessionStart:{lifecycle_source}"
    lifecycle_started = _hook_events(events, lifecycle_name, "hook_started")
    lifecycle_responses = _hook_events(events, lifecycle_name, "hook_response")
    lifecycle_contexts = _hook_contexts(events, lifecycle_name)
    prompt_started = _hook_events(events, "UserPromptSubmit", "hook_started")
    prompt_responses = _hook_events(events, "UserPromptSubmit", "hook_response")
    prompt_contexts = _hook_contexts(events, "UserPromptSubmit")
    assistant_markers = [
        content.get("text")
        for event in events
        if event.get("type") == "assistant" and isinstance(event.get("message"), dict)
        for content in event["message"].get("content", [])
        if isinstance(content, dict) and content.get("type") == "text"
    ]
    result_events = [event for event in events if event.get("type") == "result"]
    return {
        "session_id": init.get("session_id"),
        "model": init.get("model"),
        "claude_code_version": init.get("claude_code_version"),
        "lifecycle_hook": lifecycle_name,
        "hook_started": len(lifecycle_started),
        "hook_responses": len(lifecycle_responses),
        "context_channels": [name for name, _ in lifecycle_contexts],
        "context_markers": [
            "start_discovery"
            if lifecycle_source == "startup" and "agent-knowledge describe" in content
            else "resume_discovery"
            if lifecycle_source == "resume" and "rediscover" in content
            else "unknown"
            for _, content in lifecycle_contexts
        ],
        "prompt_hook_started": len(prompt_started),
        "prompt_hook_responses": len(prompt_responses),
        "prompt_context_channels": [name for name, _ in prompt_contexts],
        "prompt_context_markers": [
            "reflection" if _REFLECTION_MARKER in content else "unknown"
            for _, content in prompt_contexts
        ],
        "lifecycle_contexts": [content for _, content in lifecycle_contexts],
        "prompt_contexts": [content for _, content in prompt_contexts],
        "assistant_marker": expected_marker if expected_marker in assistant_markers else None,
        "result": expected_marker
        if any(event.get("result") == expected_marker for event in result_events)
        else None,
        "exit_outcomes": [event.get("stop_reason") for event in result_events],
    }


def _run_claude(
    command: list[str], *, consumer: Path, env: dict[str, str], timeout: float
) -> tuple[int, list[dict[str, Any]]]:
    try:
        result = subprocess.run(
            command,
            cwd=consumer,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ClaudeAcceptanceFailure("Claude Code acceptance timed out.") from error
    return result.returncode, _json_lines(result.stdout)


def _minimal_path(*, claude: Path, hook_launcher: Path) -> str:
    """Retain only the consumer runtime, provider executable, and system tools."""
    entries = [hook_launcher.parent, claude.parent]
    for name in ("node", "git"):
        found = shutil.which(name)
        if found is not None:
            entries.append(Path(found).resolve().parent)
    entries.extend(Path(path) for path in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    unique: list[str] = []
    for entry in entries:
        value = str(entry)
        if value not in unique:
            unique.append(value)
    return os.pathsep.join(unique)


def _isolated_environment(
    *, use_global_auth: bool, claude: Path, hook_launcher: Path
) -> tuple[Path | None, dict[str, str]]:
    """Keep provider authentication while excluding ambient knowledge launchers."""
    environment = dict(os.environ)
    environment["PATH"] = _minimal_path(claude=claude, hook_launcher=hook_launcher)
    if use_global_auth:
        environment.pop("CLAUDE_CONFIG_DIR", None)
        return None, environment
    config = Path(tempfile.mkdtemp(prefix="agent-knowledge-claude-config."))
    environment["CLAUDE_CONFIG_DIR"] = str(config)
    return config, environment


def _validate_hook_launcher(consumer: Path, hook_launcher: Path) -> Path:
    """Require setup's executable, consumer-local hook path rather than a marker."""
    _assert(hook_launcher.is_absolute(), "--hook-launcher must be an absolute path.")
    resolved = hook_launcher.resolve()
    venv = (consumer / ".agent-knowledge-venv").resolve()
    try:
        resolved.relative_to(venv)
    except ValueError as error:
        raise ClaudeAcceptanceFailure(
            "--hook-launcher must be inside the consumer's managed virtual environment."
        ) from error
    _assert(
        resolved.name in {"agent-knowledge-hook", "agent-knowledge-hook.exe"},
        "--hook-launcher must name the installed agent-knowledge-hook executable.",
    )
    _assert(
        resolved.is_file() and bool(resolved.stat().st_mode & 0o111),
        "--hook-launcher is missing or is not executable.",
    )
    return resolved


def _runtime_launcher(hook_launcher: Path) -> Path:
    """Find the paired installed CLI without searching the ambient PATH."""
    name = "agent-knowledge.exe" if hook_launcher.suffix == ".exe" else "agent-knowledge"
    launcher = hook_launcher.with_name(name)
    _assert(
        launcher.is_file() and bool(launcher.stat().st_mode & 0o111),
        "The consumer's installed agent-knowledge launcher is missing or is not executable.",
    )
    return launcher


def _is_expected_hook_command(command: str, hook_launcher: Path, event_name: str) -> bool:
    try:
        arguments = shlex.split(command)
    except ValueError:
        return False
    expected = [str(hook_launcher.resolve()), "--provider", "claude"]
    if event_name == "UserPromptSubmit":
        return arguments == expected
    if arguments == expected:
        return True
    if (
        len(arguments) < 9
        or arguments[:3] != expected
        or arguments[3] != "--environment-file"
        or arguments[5] != "--environment-state-directory"
        or len(arguments[7:]) % 2
    ):
        return False
    environment_file = Path(arguments[4])
    state_directory = Path(arguments[6])
    mappings = arguments[7:]
    return (
        environment_file.is_absolute()
        and environment_file.is_file()
        and state_directory.is_absolute()
        and state_directory.is_dir()
        and all(
            flag == "--environment-map"
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=[A-Za-z_][A-Za-z0-9_]*", mapping) is not None
            for flag, mapping in zip(mappings[::2], mappings[1::2], strict=True)
        )
    )


def _event_commands(document: object, event_name: str) -> list[str]:
    """Read direct command entries for an event in a merged Claude settings file."""
    if not isinstance(document, dict):
        return []
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        return []
    groups = hooks.get(event_name)
    if not isinstance(groups, list):
        return []
    return [
        command
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("hooks"), list)
        for entry in group["hooks"]
        if isinstance(entry, dict)
        for command in [entry.get("command")]
        if isinstance(command, str)
    ]


def _assert_package_registration(consumer: Path, hook_launcher: Path) -> None:
    """Ensure the sidecar and active Claude settings use the managed launcher."""
    path = consumer / ".claude" / "apm-hooks.json"
    _assert(path.is_file(), f"Package-owned Claude hook registration is missing: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ClaudeAcceptanceFailure(
            "Package-owned Claude hook registration is invalid JSON."
        ) from error
    _assert(
        isinstance(document, dict),
        "Package-owned Claude hook registration is not an object.",
    )
    expected_events = {"SessionStart", "UserPromptSubmit"}
    _assert(
        set(document) == expected_events,
        "Package-owned Claude registration must contain only SessionStart and UserPromptSubmit.",
    )
    for event_name in expected_events:
        groups = document.get(event_name)
        _assert(
            isinstance(groups, list) and len(groups) == 1,
            f"Claude package {event_name} registration is ambiguous.",
        )
        group = groups[0]
        _assert(isinstance(group, dict), f"Claude package {event_name} group is invalid.")
        _assert(
            group.get("_apm_source") == "_local/knowledge-agent-pack",
            f"Claude {event_name} hook ownership marker is missing.",
        )
        hooks = group.get("hooks")
        _assert(
            isinstance(hooks, list) and len(hooks) == 1,
            f"Claude package {event_name} must contain one hook command.",
        )
        entry = hooks[0]
        _assert(isinstance(entry, dict), f"Claude package {event_name} hook entry is invalid.")
        _assert(
            entry.get("command") != "agent-knowledge-hook",
            f"Claude package {event_name} retained the bare hook launcher marker.",
        )
        command = entry.get("command")
        _assert(
            isinstance(command, str)
            and _is_expected_hook_command(command, hook_launcher, event_name),
            f"Claude package {event_name} does not use the verified absolute hook launcher.",
        )

    settings_path = consumer / ".claude" / "settings.json"
    _assert(settings_path.is_file(), f"Consumer Claude settings are missing: {settings_path}")
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ClaudeAcceptanceFailure("Consumer Claude settings are invalid JSON.") from error
    _assert(isinstance(settings, dict), "Consumer Claude settings are not an object.")
    _assert(
        isinstance(settings.get("hooks"), dict),
        "Consumer Claude settings have no hooks object.",
    )
    for event_name in expected_events:
        commands = _event_commands(settings, event_name)
        _assert(
            "agent-knowledge-hook" not in commands,
            f"Claude active {event_name} retained the bare hook launcher marker.",
        )
        _assert(
            sum(
                _is_expected_hook_command(command, hook_launcher, event_name)
                for command in commands
            )
            == 1,
            f"Claude active {event_name} does not use exactly one verified absolute hook launcher.",
        )


def _failing_hook_settings(settings: bytes) -> bytes:
    try:
        document = json.loads(settings)
    except json.JSONDecodeError as error:
        raise ClaudeAcceptanceFailure("Consumer Claude settings are invalid JSON.") from error
    if not isinstance(document, dict):
        raise ClaudeAcceptanceFailure("Consumer Claude settings are not an object.")
    document["hooks"] = {
        "SessionStart": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": "/bin/false", "timeout": 1}],
            }
        ]
    }
    return (json.dumps(document, indent=2) + "\n").encode("utf-8")


def _run_failing_hook_check(
    *,
    claude: str,
    consumer: Path,
    settings: Path,
    original_settings: bytes,
    environment: dict[str, str],
    timeout: float,
    max_budget_usd: float,
) -> dict[str, Any]:
    """Prove a failing advisory hook does not block a model turn."""
    settings.write_bytes(_failing_hook_settings(original_settings))
    try:
        code, events = _run_claude(
            [
                claude,
                "--model",
                "opus",
                "--setting-sources",
                "project,local",
                "--include-hook-events",
                "--output-format",
                "stream-json",
                "--verbose",
                "--permission-mode",
                "plan",
                "--max-budget-usd",
                str(max_budget_usd),
                "-p",
                "Respond with exactly FAIL_OPEN_OK.",
            ],
            consumer=consumer,
            env=environment,
            timeout=timeout,
        )
    finally:
        settings.write_bytes(original_settings)
    summary = _event_summary(events, "FAIL_OPEN_OK", "startup")
    _assert(code == 0, "Claude stopped when the advisory hook failed.")
    _assert(summary["model"] == _EXPECTED_MODEL, "Fail-open check did not use exact Opus 5.")
    _assert(summary["result"] == "FAIL_OPEN_OK", "Fail-open check did not complete the model turn.")
    failures = [
        event
        for event in events
        if event.get("subtype") == "hook_response"
        and event.get("hook_name") == "SessionStart:startup"
        and event.get("outcome") not in {"success", None}
    ]
    _assert(failures, "Fail-open check did not observe the failing hook response.")
    return {
        "status": "passed",
        "model": summary["model"],
        "result": summary["result"],
        "hook_outcome": failures[0].get("outcome"),
        "hook_exit_code": failures[0].get("exit_code"),
    }


def _tool_uses(events: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Return model tool requests without retaining their output or transcript."""
    uses: list[tuple[str, dict[str, Any]]] = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            inputs = item.get("input")
            name = item.get("name")
            if isinstance(name, str) and isinstance(inputs, dict):
                uses.append((name, inputs))
    return uses


def _tool_commands(events: list[dict[str, Any]]) -> list[str]:
    """Return shell commands actually requested by the model."""
    return [
        command
        for name, inputs in _tool_uses(events)
        if name.casefold() == "bash"
        for command in [inputs.get("command")]
        if isinstance(command, str)
    ]


def _has_inline_session_filter(command: str, session_id: str) -> bool:
    """Check that an inline list request binds this exact hook session ID."""
    pattern = (
        r"(?:\"session_id\"|'session_id'|\bsession_id\b)\s*:\s*(?:\"|')?"
        + re.escape(session_id)
        + r"(?:\"|')?(?=\s*(?:[,}\n]|$))"
    )
    return re.search(pattern, command) is not None


def _invokes_installed_launcher(command: str, launcher: Path, cwd: Path) -> bool:
    """Accept absolute or consumer-relative execution of the same installed file."""
    for line in command.splitlines():
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|")
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            continue
        for index, token in enumerate(tokens):
            if index > 0 and tokens[index - 1] not in {"|", "||", ";", "&&"}:
                continue
            if "/" not in token:
                continue
            executable = Path(token)
            if not executable.is_absolute():
                executable = cwd / executable
            if executable.resolve() == launcher.resolve():
                return True
    return False


def _uses_explicit_config(command: str, config: Path) -> bool:
    """Resolve an explicitly supplied path; do not treat ambient configuration as proof."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    for index, token in enumerate(tokens[:-1]):
        if token != "--config":
            continue
        path = Path(tokens[index + 1])
        if not path.is_absolute():
            path = config.parent / path
        if path.resolve() == config.resolve():
            return True
    return False


def _assert_model_used_cli(
    events: list[dict[str, Any]],
    *,
    launcher: Path,
    config: Path,
    session_id: str,
    operations: tuple[str, ...],
) -> list[str]:
    """Require inline session-filtered calls to the installed explicit CLI."""
    commands = _tool_commands(events)
    for operation in operations:
        requires_session_filter = operation == "signal list"
        _assert(
            any(
                _invokes_installed_launcher(command, launcher, config.parent)
                and _uses_explicit_config(command, config)
                and operation in command
                and "--request-file -" in command
                and (not requires_session_filter or _has_inline_session_filter(command, session_id))
                for command in commands
            ),
            "Claude model flow did not run installed agent-knowledge "
            f"{operation} with the required inline request.",
        )
    return commands


def _shell_inspects_path(command: str, signal_path: Path) -> bool:
    """Recognize a body-reading shell invocation, excluding mere path mentions."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    readers = {
        "awk",
        "cat",
        "head",
        "less",
        "more",
        "perl",
        "python",
        "python3",
        "sed",
        "tail",
    }
    return str(signal_path) in tokens and any(Path(token).name in readers for token in tokens)


def _assert_model_inspected(events: list[dict[str, Any]], signal_path: Path) -> None:
    """Require an actual Read or body-reading shell call for the listed candidate."""
    resolved = signal_path.resolve()
    for name, inputs in _tool_uses(events):
        if name.casefold() == "read":
            location = inputs.get("file_path", inputs.get("path"))
            if isinstance(location, str) and Path(location).resolve() == resolved:
                return
    commands = _tool_commands(events)
    _assert(
        any(_shell_inspects_path(command, resolved) for command in commands),
        "Claude model flow did not inspect the listed same-session signal body.",
    )


def _run_agent_knowledge(
    launcher: Path,
    *,
    consumer: Path,
    config: Path,
    request: dict[str, object],
    timeout: float,
    environment: dict[str, str],
    command: tuple[str, ...],
) -> dict[str, Any]:
    """Use the installed consumer CLI to verify persisted model-side effects."""
    try:
        result = subprocess.run(
            [
                str(launcher),
                "--config",
                str(config),
                *command,
                "--request-file",
                "-",
            ],
            cwd=consumer,
            env=environment,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ClaudeAcceptanceFailure(
            "Installed agent-knowledge verification timed out."
        ) from error
    _assert(result.returncode == 0, "Installed agent-knowledge verification command failed.")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ClaudeAcceptanceFailure(
            "Installed agent-knowledge verification did not return JSON."
        ) from error
    _assert(
        isinstance(payload, dict) and payload.get("status") == "ok",
        "Installed agent-knowledge verification did not report success.",
    )
    return payload


def _session_signal(
    launcher: Path,
    *,
    consumer: Path,
    config: Path,
    session_id: str,
    timeout: float,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Verify one persisted, preview-only signal belongs to the hook session."""
    listing = _run_agent_knowledge(
        launcher,
        consumer=consumer,
        config=config,
        request={"session_id": session_id},
        timeout=timeout,
        environment=environment,
        command=("signal", "list"),
    )
    rows = listing.get("results")
    _assert(
        isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict),
        "Claude model flow did not leave exactly one same-session signal.",
    )
    signal = rows[0]
    origin = signal.get("origin")
    _assert(signal.get("id") == _MODEL_SIGNAL_ID, "Claude recorded the wrong signal ID.")
    _assert(isinstance(origin, dict), "Claude signal preview omitted origin provenance.")
    _assert(origin.get("harness") == "claude", "Claude signal origin omitted harness provenance.")
    _assert(
        origin.get("session_id") == session_id,
        "Claude signal origin did not preserve the exact hook session ID.",
    )
    location = signal.get("local_path")
    _assert(
        isinstance(location, str) and Path(location).is_file(),
        "Claude signal was not persisted.",
    )
    _assert(
        "model-flow observation" not in json.dumps(signal),
        "Claude signal listing exposed the model-authored claim body.",
    )
    return signal


def _record_prompt(*, launcher: Path, config: Path) -> str:
    """Ask the model to use only the ID delivered by its hook context."""
    return f"""You are in a disposable Claude acceptance consumer. The hook context contains the
only session ID you may use; do not invent, ask for, or receive a session ID in this prompt.

Use only the installed CLI at {launcher} with explicit config {config}. First list pending
signals for the current project with the exact session ID from the hook context. Put an inline
JSON or YAML request containing that `session_id` directly on stdin and invoke the list command
with `--request-file -`; do not use a temporary request file. Inspect any likely equivalent
candidates returned by that list. If no equivalent is present, author and record exactly one
concise signal at {_MODEL_SIGNAL_FILE}. Put the record request inline on stdin with
`--request-file -` too. It must be valid `knowledge-signal.v1` with id `{_MODEL_SIGNAL_ID}`,
created_at `2026-09-12T12:00:00Z`, kind_hint `limitation`, and:

origin:
  workspace_id: workspace:fresh-consumer
  project_path: consumer
  applicable_scopes: [org:example, group:commerce, repo:orders-api]
  source_ids: [example-knowledge]
  harness: claude
  session_id: the exact hook-provided value

Use one file evidence reference, `consumer/{_MODEL_SIGNAL_FILE}`, and a body that includes the
phrase "model-flow observation". Its only factual claim must be this fictional fixture gap:
"The fixture runbook omits the restriction that an index build must not run inside a transaction."
Do not add another factual claim. Do not edit canonical knowledge, use a global launcher, or touch
files outside this disposable consumer. After the signal is successfully recorded, respond with
exactly {_MODEL_RECORD_MARKER}."""


def _dedup_prompt(*, launcher: Path, config: Path) -> str:
    """Ask for a second natural reflection decision without directing its outcome."""
    return f"""At this new reflection point, revisit the same model-flow observation from this
session: the fictional fixture gap is that the fixture runbook omits the restriction that an index
build must not run inside a transaction. Use only the installed CLI at {launcher} with explicit
config {config}, and use the exact session ID supplied by this turn's hook context. Put an inline
JSON or YAML list request containing that `session_id` directly on stdin and invoke the list
command with `--request-file -`; do not use a temporary request file. Follow the installed
reflection guidance: inspect each likely equivalent body using its returned local path, then
decide whether another signal is worth retaining. Do not edit canonical knowledge, use a global
launcher, or touch files outside this disposable consumer. When the reflection is complete,
respond with exactly {_MODEL_DEDUP_MARKER}."""


def _assert_transport(
    summary: dict[str, Any],
    *,
    code: int,
    lifecycle_source: str,
    session_id: str | None = None,
) -> str:
    """Assert one model-visible lifecycle and prompt context for a provider turn."""
    _assert(code == 0, f"Claude {lifecycle_source} exited with {code}.")
    _assert(summary["model"] == _EXPECTED_MODEL, "Claude did not run the exact Opus 5 model.")
    received = summary.get("session_id")
    _assert(isinstance(received, str) and received, "Claude did not return a session id.")
    if session_id is not None:
        _assert(received == session_id, "Claude resume changed the session id.")
    _assert(summary["hook_started"] >= 1, f"Claude {lifecycle_source} did not run SessionStart.")
    _assert(
        summary["hook_responses"] >= 1,
        f"Claude {lifecycle_source} did not return a SessionStart hook response.",
    )
    _assert(
        summary["context_channels"] == ["hookSpecificOutput.additionalContext"],
        f"Claude {lifecycle_source} did not use exactly one lifecycle context channel.",
    )
    expected_context = "start_discovery" if lifecycle_source == "startup" else "resume_discovery"
    _assert(
        summary["context_markers"] == [expected_context],
        f"Claude {lifecycle_source} lifecycle context omitted the discovery reminder.",
    )
    _assert(
        len(summary["lifecycle_contexts"]) == 1
        and _SESSION_ID_MARKER + received in summary["lifecycle_contexts"][0]
        and _PROVIDER_MARKER in summary["lifecycle_contexts"][0],
        f"Claude {lifecycle_source} lifecycle context omitted provider provenance.",
    )
    _assert(
        summary["prompt_hook_started"] == 1,
        f"Claude {lifecycle_source} did not run UserPromptSubmit once.",
    )
    _assert(
        summary["prompt_hook_responses"] == 1,
        f"Claude {lifecycle_source} did not return one UserPromptSubmit response.",
    )
    _assert(
        summary["prompt_context_channels"] == ["hookSpecificOutput.additionalContext"],
        f"Claude {lifecycle_source} prompt did not use exactly one hook context channel.",
    )
    _assert(
        summary["prompt_context_markers"] == ["reflection"],
        f"Claude {lifecycle_source} prompt omitted the reflection reminder.",
    )
    _assert(
        len(summary["prompt_contexts"]) == 1
        and _SESSION_ID_MARKER + received in summary["prompt_contexts"][0]
        and _PROVIDER_MARKER in summary["prompt_contexts"][0],
        f"Claude {lifecycle_source} prompt context omitted provider provenance.",
    )
    return received


def _failure_report(
    *,
    use_global_auth: bool,
    transport: dict[str, Any],
    model_flow: dict[str, Any],
    diagnostic: str,
) -> dict[str, Any]:
    """Keep completed transport evidence when a later model-flow assertion fails."""
    return {
        "status": "failed",
        "provider": "claude",
        "model_required": _EXPECTED_MODEL,
        "global_config_used": use_global_auth,
        "minimal_path": True,
        "transport": transport,
        "model_flow": model_flow,
        "diagnostic": diagnostic,
    }


def run_acceptance(
    *,
    consumer: Path,
    hook_launcher: Path,
    timeout: float,
    max_budget_usd: float,
    use_global_auth: bool = False,
) -> dict[str, Any]:
    """Prove transport and a bounded model record/list/decision workflow."""
    consumer = consumer.resolve()
    _assert(consumer.is_dir(), f"Consumer directory is missing: {consumer}")
    hook_launcher = _validate_hook_launcher(consumer, hook_launcher)
    launcher = _runtime_launcher(hook_launcher)
    workspace = consumer / "knowledge-workspace.yaml"
    _assert(workspace.is_file(), f"Consumer workspace config is missing: {workspace}")
    authored = consumer / _MODEL_SIGNAL_FILE
    _assert(
        not authored.exists(),
        f"Consumer already contains {authored.name}; use a fresh consumer.",
    )
    settings = consumer / ".claude" / "settings.json"
    _assert(settings.is_file(), f"Consumer Claude settings are missing: {settings}")
    settings_before = settings.read_bytes()
    _assert_package_registration(consumer, hook_launcher)
    claude_value = shutil.which("claude")
    if claude_value is None:
        return {
            "status": "unavailable",
            "reason": "claude CLI is not installed",
            "provider": "claude",
            "model_required": _EXPECTED_MODEL,
            "global_config_used": False,
            "transport": {"status": "not-run"},
            "model_flow": {"status": "not-run", "reason": "claude CLI is not installed"},
        }
    claude = Path(claude_value).resolve()

    temporary_config, environment = _isolated_environment(
        use_global_auth=use_global_auth,
        claude=claude,
        hook_launcher=hook_launcher,
    )
    try:
        common = [
            str(claude),
            "--model",
            "opus",
            "--setting-sources",
            "project,local",
            "--include-hook-events",
            "--output-format",
            "stream-json",
            "--verbose",
            "--max-budget-usd",
            str(max_budget_usd),
            "--permission-mode",
            "bypassPermissions",
        ]
        startup_code, startup_events = _run_claude(
            [*common, "-p", _record_prompt(launcher=launcher, config=workspace)],
            consumer=consumer,
            env=environment,
            timeout=timeout,
        )
        startup = _event_summary(startup_events, _MODEL_RECORD_MARKER, "startup")
        auth_error = any(
            event.get("error") == "authentication_failed"
            or "not logged in" in str(event.get("result", "")).casefold()
            for event in startup_events
        )
        if auth_error:
            return {
                "status": "auth-required",
                "provider": "claude",
                "model_required": _EXPECTED_MODEL,
                "global_config_used": use_global_auth,
                "transport": {"status": "auth-required", "startup_exit": startup_code},
                "model_flow": {"status": "not-run", "reason": "authentication required"},
            }
        transport: dict[str, Any] = {"status": "failed", "startup": startup}
        try:
            session_id = _assert_transport(startup, code=startup_code, lifecycle_source="startup")
        except ClaudeAcceptanceFailure as error:
            raise ClaudeAcceptanceFailure(
                str(error),
                report=_failure_report(
                    use_global_auth=use_global_auth,
                    transport=transport,
                    model_flow={"status": "not-run"},
                    diagnostic=str(error),
                ),
            ) from error

        transport["status"] = "passed"
        model_stage = "record"
        try:
            _assert(
                startup["assistant_marker"] == _MODEL_RECORD_MARKER
                and startup["result"] == _MODEL_RECORD_MARKER,
                "Claude did not confirm the model record step.",
            )
            _assert_model_used_cli(
                startup_events,
                launcher=launcher,
                config=workspace,
                session_id=session_id,
                operations=("signal list", "signal record"),
            )
            recorded = _session_signal(
                launcher,
                consumer=consumer,
                config=workspace,
                session_id=session_id,
                timeout=timeout,
                environment=environment,
            )
            location = recorded.get("local_path")
            _assert(isinstance(location, str), "Recorded model signal omitted its local path.")
            recorded_path = Path(location)
            try:
                recorded_bytes = recorded_path.read_bytes()
            except OSError as error:
                raise ClaudeAcceptanceFailure(
                    "Recorded model signal could not be snapshotted before resume."
                ) from error

            model_stage = "dedup"
            resume_code, resume_events = _run_claude(
                [
                    *common,
                    "--resume",
                    session_id,
                    "-p",
                    _dedup_prompt(launcher=launcher, config=workspace),
                ],
                consumer=consumer,
                env=environment,
                timeout=timeout,
            )
            resume = _event_summary(resume_events, _MODEL_DEDUP_MARKER, "resume")
            transport["resume"] = resume
            _assert(
                not _hook_events(resume_events, "SessionStart:startup", "hook_started"),
                "Claude resume was classified as startup.",
            )
            try:
                _assert_transport(
                    resume,
                    code=resume_code,
                    lifecycle_source="resume",
                    session_id=session_id,
                )
            except ClaudeAcceptanceFailure:
                transport["status"] = "failed"
                raise
            _assert(
                resume["assistant_marker"] == _MODEL_DEDUP_MARKER
                and resume["result"] == _MODEL_DEDUP_MARKER,
                "Claude did not confirm the independent duplicate decision step.",
            )
            _assert_model_used_cli(
                resume_events,
                launcher=launcher,
                config=workspace,
                session_id=session_id,
                operations=("signal list",),
            )
            _assert_model_inspected(resume_events, recorded_path)
            retained = _session_signal(
                launcher,
                consumer=consumer,
                config=workspace,
                session_id=session_id,
                timeout=timeout,
                environment=environment,
            )
            _assert(
                retained.get("local_path") == location,
                "Claude model flow recorded a duplicate instead of retaining the inspected signal.",
            )
            try:
                signal_unchanged = recorded_path.read_bytes() == recorded_bytes
            except OSError as error:
                raise ClaudeAcceptanceFailure(
                    "Recorded model signal could not be read after the duplicate decision."
                ) from error
            _assert(
                signal_unchanged,
                "Claude model flow modified the recorded signal after inspecting it.",
            )
        except ClaudeAcceptanceFailure as error:
            raise ClaudeAcceptanceFailure(
                str(error),
                report=_failure_report(
                    use_global_auth=use_global_auth,
                    transport=transport,
                    model_flow={"status": "failed", "stage": model_stage, "diagnostic": str(error)},
                    diagnostic=str(error),
                ),
            ) from error

        model_flow = {
            "status": "passed",
            "record": {
                "result": startup["result"],
                "signal_id": recorded["id"],
                "exact_hook_session_provenance": True,
            },
            "dedup": {
                "result": resume["result"],
                "inspected_listed_signal": True,
                "matching_signal_count": 1,
                "duplicate_recorded": False,
                "signal_unchanged": True,
            },
        }
        try:
            _assert(settings.read_bytes() == settings_before, "Claude modified consumer settings.")
            failing_hook = _run_failing_hook_check(
                claude=str(claude),
                consumer=consumer,
                settings=settings,
                original_settings=settings_before,
                environment=environment,
                timeout=timeout,
                max_budget_usd=max_budget_usd,
            )
            _assert(
                settings.read_bytes() == settings_before,
                "Fail-open check did not restore settings.",
            )
        except ClaudeAcceptanceFailure as error:
            raise ClaudeAcceptanceFailure(
                str(error),
                report=_failure_report(
                    use_global_auth=use_global_auth,
                    transport=transport,
                    model_flow=model_flow,
                    diagnostic=str(error),
                ),
            ) from error
        return {
            "status": "passed",
            "provider": "claude",
            "model": _EXPECTED_MODEL,
            "claude_code_version": startup["claude_code_version"],
            "global_config_used": use_global_auth,
            "minimal_path": True,
            "transport": transport,
            "model_flow": model_flow,
            "failing_hook": failing_hook,
            "consumer_settings_unchanged": True,
        }
    finally:
        if temporary_config is not None:
            shutil.rmtree(temporary_config, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_acceptance(
            consumer=args.consumer,
            hook_launcher=args.hook_launcher,
            timeout=args.timeout,
            max_budget_usd=args.max_budget_usd,
            use_global_auth=args.use_global_auth,
        )
    except ClaudeAcceptanceFailure as error:
        report = error.report or {
            "status": "failed",
            "provider": "claude",
            "model_required": _EXPECTED_MODEL,
            "global_config_used": args.use_global_auth,
            "diagnostic": str(error),
        }
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered, end="", file=sys.stderr if report["status"] == "failed" else sys.stdout)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["status"] == "passed" or not args.require_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
