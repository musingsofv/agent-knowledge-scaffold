#!/usr/bin/env python3
"""Exercise installed discovery hooks with provider-native lifecycle fixtures."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


class HookSmokeFailure(RuntimeError):
    """Describe one installed-hook assertion or subprocess failure."""


_PROVIDERS = ("codex", "claude", "copilot")
_START_MESSAGE_MARKER = "agent-knowledge describe"
_RESUME_MESSAGE_MARKER = "Context may have been compacted"
_REFLECTION_MESSAGE_MARKER = (
    'At a natural stopping point, follow "Reflect and record useful observations"'
)
_SESSION_ID_MARKER = (
    "Provider session ID (copy exactly into origin.session_id for a harness-origin signal): "
)
_PROVIDER_MARKER = (
    "Provider harness (copy exactly into origin.harness for a harness-origin signal): "
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exercise installed provider discovery hooks with native fixtures."
    )
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument(
        "--launcher",
        type=Path,
        required=True,
        help="Absolute path to the installed agent-knowledge-hook launcher.",
    )
    parser.add_argument("--output", type=Path, help="Write the JSON evidence report to this path.")
    return parser


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise HookSmokeFailure(message)


def _invoke(
    launcher: Path,
    payload: object,
    *,
    provider: str,
    cwd: Path,
    env: dict[str, str],
    logs: Path,
    label: str,
) -> dict[str, Any]:
    result = subprocess.run(
        [str(launcher), "--provider", provider],
        cwd=cwd,
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    log = logs / f"{label}.log"
    log.write_text(
        "COMMAND: "
        + str(launcher)
        + "\nEXIT: "
        + str(result.returncode)
        + "\n\nSTDOUT:\n"
        + result.stdout
        + "\nSTDERR:\n"
        + result.stderr,
        encoding="utf-8",
    )
    _assert(result.returncode == 0, f"Hook command failed for {label}; see {log}")
    if not result.stdout.strip():
        return {}
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HookSmokeFailure(f"Hook returned invalid JSON for {label}; see {log}") from error
    _assert(isinstance(value, dict), f"Hook returned a non-object response for {label}.")
    return value


def _context_channels(value: dict[str, Any]) -> list[str]:
    channels: list[str] = []
    if isinstance(value.get("additionalContext"), str):
        channels.append("additionalContext")
    hook_output = value.get("hookSpecificOutput")
    if isinstance(hook_output, dict) and isinstance(hook_output.get("additionalContext"), str):
        channels.append("hookSpecificOutput.additionalContext")
    if isinstance(value.get("systemMessage"), str):
        channels.append("systemMessage")
    if isinstance(value.get("modifiedTransformedPrompt"), str):
        channels.append("modifiedTransformedPrompt")
    return channels


def _fixtures(
    provider: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    if provider == "copilot":
        session_id = "copilot-hook-smoke-session"
        return (
            {"sessionId": session_id, "source": "startup"},
            {"sessionId": session_id, "source": "resume"},
            {
                "sessionId": session_id,
                "prompt": "Copilot prompt fixture",
                "transformedPrompt": "Opaque Copilot model-facing fixture",
            },
            {"sessionId": "hook-smoke-other", "hookEventName": "agentStop"},
        )
    if provider in {"codex", "claude"}:
        session_id = f"{provider}-hook-smoke-session"
        return (
            {
                "hook_event_name": "SessionStart",
                "source": "startup",
                "session_id": session_id,
            },
            {
                "hook_event_name": "SessionStart",
                "source": "resume",
                "session_id": session_id,
            },
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": session_id,
            },
            {
                "hook_event_name": "PostToolUse",
                "source": "startup",
                "session_id": f"{provider}-hook-smoke-other",
            },
        )
    raise HookSmokeFailure(f"Unsupported provider: {provider}")


def run_provider_hook_smoke(
    consumer: Path,
    launcher: Path,
    *,
    logs: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run lifecycle and prompt fixtures for each installed provider."""
    consumer = consumer.resolve()
    _assert(consumer.is_dir(), f"Consumer directory is missing: {consumer}")
    launcher = launcher.resolve()
    _assert(
        launcher.is_file() and launcher.stat().st_mode & 0o111,
        f"Installed agent-knowledge-hook launcher is missing or not executable: {launcher}",
    )
    log_root = logs or Path(tempfile.mkdtemp(prefix="agent-knowledge-hook-smoke."))
    log_root.mkdir(parents=True, exist_ok=True)
    cwd = consumer / ".hook-smoke" / "deep" / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)
    command_env = dict(env or os.environ)
    report: dict[str, Any] = {"status": "passed", "providers": {}}
    for provider in _PROVIDERS:
        start, resume, prompt, unrelated = _fixtures(provider)
        start_result = _invoke(
            launcher,
            start,
            provider=provider,
            cwd=cwd,
            env=command_env,
            logs=log_root,
            label=f"{provider}-startup",
        )
        resume_result = _invoke(
            launcher,
            resume,
            provider=provider,
            cwd=cwd,
            env=command_env,
            logs=log_root,
            label=f"{provider}-resume",
        )
        prompt_result = _invoke(
            launcher,
            prompt,
            provider=provider,
            cwd=cwd,
            env=command_env,
            logs=log_root,
            label=f"{provider}-prompt",
        )
        unrelated_result = _invoke(
            launcher,
            unrelated,
            provider=provider,
            cwd=cwd,
            env=command_env,
            logs=log_root,
            label=f"{provider}-unrelated",
        )
        start_channels = _context_channels(start_result)
        resume_channels = _context_channels(resume_result)
        prompt_channels = _context_channels(prompt_result)
        _assert(
            len(start_channels) == 1,
            f"{provider} startup emitted {len(start_channels)} context channels.",
        )
        _assert(
            len(resume_channels) == 1,
            f"{provider} resume emitted {len(resume_channels)} context channels.",
        )
        _assert(
            _START_MESSAGE_MARKER in json.dumps(start_result),
            f"{provider} startup omitted the discovery reminder.",
        )
        _assert(
            _RESUME_MESSAGE_MARKER in json.dumps(resume_result),
            f"{provider} resume omitted the rediscovery reminder.",
        )
        startup_session = str(start.get("session_id", start.get("sessionId", "")))
        _assert(startup_session, f"{provider} fixture has no session ID.")
        _assert(
            _SESSION_ID_MARKER + startup_session in json.dumps(start_result),
            f"{provider} startup omitted the exact session ID.",
        )
        _assert(
            _PROVIDER_MARKER + provider in json.dumps(start_result),
            f"{provider} startup omitted the normalized provider.",
        )
        _assert(
            _SESSION_ID_MARKER + startup_session in json.dumps(resume_result),
            f"{provider} resume omitted the exact session ID.",
        )
        _assert(
            _PROVIDER_MARKER + provider in json.dumps(resume_result),
            f"{provider} resume omitted the normalized provider.",
        )
        _assert(
            len(prompt_channels) == 1,
            f"{provider} prompt emitted {len(prompt_channels)} context channels.",
        )
        _assert(
            json.dumps(_REFLECTION_MESSAGE_MARKER)[1:-1] in json.dumps(prompt_result),
            f"{provider} prompt omitted the reflection reminder.",
        )
        _assert(
            _SESSION_ID_MARKER + startup_session in json.dumps(prompt_result),
            f"{provider} prompt omitted the exact startup session ID.",
        )
        _assert(
            _PROVIDER_MARKER + provider in json.dumps(prompt_result),
            f"{provider} prompt omitted the normalized provider.",
        )
        if provider == "copilot":
            _assert(
                str(prompt["transformedPrompt"])
                in str(prompt_result.get("modifiedTransformedPrompt", "")),
                "Copilot prompt hook did not preserve the opaque transformed prompt.",
            )
        _assert(not unrelated_result, f"{provider} unrelated event was not a no-op.")
        report["providers"][provider] = {
            "launcher": str(launcher),
            "startup_channels": start_channels,
            "resume_channels": resume_channels,
            "prompt_channels": prompt_channels,
            "session_id": startup_session,
            "unrelated": "empty",
        }
    return report


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_provider_hook_smoke(args.consumer, args.launcher)
    except HookSmokeFailure as error:
        rendered = json.dumps({"status": "error", "diagnostic": str(error)}, indent=2) + "\n"
        print(rendered, end="", file=sys.stderr)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        return 1
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
