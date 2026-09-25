#!/usr/bin/env python3
"""Exercise business onboarding through an installed skill in disposable provider turns.

Native scheduling is deliberately excluded. The scripted user confirms meaning;
the model must discover the skill, produce configuration and preserve it on repeat.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from claude_hook_acceptance import _json_lines, _tool_commands
from harness_agent_smoke import (
    HarnessSmokeFailure,
    _clean_runtime_env,
    _isolated_copilot_environment,
    _redact,
    _run,
    _run_json,
)
from provider_hook_smoke import run_provider_hook_smoke

_PROVIDERS = ("codex", "claude", "copilot")
_REMOTE_COMMANDS = ("curl", "wget", "ssh", "scp", "sftp", "rsync", "gh")
_REFLECTION_MARKER = 'At a natural stopping point, follow "Reflect and record useful observations"'
_COPILOT_PROVIDER_MARKER = (
    "Provider harness (copy exactly into origin.harness for a harness-origin signal): copilot"
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert(value: object, message: str) -> None:
    if not value:
        raise HarnessSmokeFailure(message)


def _assert_fresh_signal_storage(config: Path, consumer: Path) -> None:
    """Require the documented fresh-workspace signal origin layout."""
    document = yaml.safe_load(config.read_text(encoding="utf-8"))
    _assert(isinstance(document, dict), "Workspace configuration is not a mapping.")
    storage = document.get("signal_storage") if isinstance(document, dict) else None
    _assert(isinstance(storage, dict), "Workspace omitted signal_storage.")

    def resolved(field: str) -> Path:
        value = storage.get(field) if isinstance(storage, dict) else None
        _assert(isinstance(value, str) and value, f"signal_storage.{field} is missing.")
        path = Path(value)
        return (path if path.is_absolute() else config.parent / path).resolve()

    scaffold_root = resolved("scaffold_root")
    code_root = resolved("code_root")
    checkout = consumer.resolve()
    _assert(scaffold_root == checkout, "Fresh setup did not use the checkout as scaffold_root.")
    _assert(
        checkout != code_root and checkout.is_relative_to(code_root),
        "Fresh setup must place the checkout strictly below signal_storage.code_root.",
    )


def _last(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    """Return the last event with the requested type, or an empty mapping."""
    return next(
        (event for event in reversed(events) if event.get("type") == event_type),
        {},
    )


def _codex_commands(events: list[dict[str, Any]]) -> list[str]:
    """Return commands from Codex command-execution completion events."""
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
    """Return Bash commands from Copilot tool-execution start events."""
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
    """Return model-facing Copilot prompts emitted in the native JSONL stream."""
    return [
        content
        for event in events
        if event.get("type") == "user.message"
        for data in [event.get("data")]
        if isinstance(data, dict)
        for content in [data.get("transformedContent")]
        if isinstance(content, str)
    ]


def _assert_no_remote_activity(events: list[dict[str, Any]], commands: list[str]) -> None:
    """Reject remote shell commands and provider tools in the disposable proof."""
    for command in commands:
        lowered = command.casefold()
        if any(
            re.search(rf"(?:^|[;&|\s]){re.escape(name)}(?:$|\s)", lowered)
            for name in _REMOTE_COMMANDS
        ) or re.search(r"(?:^|[;&|\s])git\s+(?:clone|fetch|pull|push)(?:$|\s)", lowered):
            raise HarnessSmokeFailure("Onboarding invoked a remote-capable shell command.")
    remote_tools: list[str] = []
    for event in events:
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
    _assert(
        not remote_tools, "Onboarding invoked a remote provider tool: " + ", ".join(remote_tools)
    )


def _hook_commands(value: object) -> list[str]:
    """Collect command fields from a provider hook document."""
    if isinstance(value, dict):
        return [
            *([value["command"]] if isinstance(value.get("command"), str) else []),
            *(command for child in value.values() for command in _hook_commands(child)),
        ]
    if isinstance(value, list):
        return [command for child in value for command in _hook_commands(child)]
    return []


def _assert_hook_registration(consumer: Path, launcher: Path) -> dict[str, object]:
    """Require setup to bind every package hook to the installed launcher."""
    registrations = {
        "codex": consumer / ".codex/apm-hooks.json",
        "claude": consumer / ".claude/apm-hooks.json",
        "copilot": consumer / ".github/hooks/knowledge-agent-pack-knowledge-discovery.json",
    }
    report: dict[str, object] = {}
    for provider, path in registrations.items():
        _assert(path.is_file(), f"Configured setup omitted the {provider} hook registration.")
        document = json.loads(path.read_text(encoding="utf-8"))
        commands = _hook_commands(document)
        _assert(commands, f"Configured {provider} hook registration has no command.")
        _assert(
            all(str(launcher.resolve()) in command for command in commands),
            f"Configured {provider} hook is not bound to the installed launcher.",
        )
        _assert(
            all(command != "agent-knowledge-hook" for command in commands),
            f"Configured {provider} hook retained the portable marker.",
        )
        if provider == "copilot":
            hooks = document.get("hooks") if isinstance(document, dict) else None
            _assert(
                isinstance(hooks, dict) and set(hooks) == {"sessionStart", "userPromptTransformed"},
                "Configured Copilot hooks omit the native prompt transformation event.",
            )
        report[provider] = {"path": str(path), "commands": len(commands)}
    return report


def _provider_evidence(
    provider: str, label: str, events: list[dict[str, Any]], log: Path
) -> dict[str, Any]:
    """Normalize one provider's JSONL events into reviewable turn evidence."""
    match provider:
        case "claude":
            init = next((event for event in events if event.get("subtype") == "init"), {})
            final = _last(events, "result")
            failed = not final or bool(final.get("is_error"))
            return {
                "phase": label,
                "session_id": init.get("session_id"),
                "model": init.get("model"),
                "status": "failed" if failed else "passed",
                "provider_terminal_reason": final.get("terminal_reason") or final.get("subtype"),
                "provider_errors": [_redact(str(item)) for item in final.get("errors", [])],
                "cost_usd": final.get("total_cost_usd"),
                "response": _redact(str(final.get("result", ""))),
                "commands": [_redact(value) for value in _tool_commands(events)],
                "log": str(log),
            }
        case "codex":
            started = _last(events, "thread.started")
            completed = _last(events, "turn.completed")
            failed_event = _last(events, "turn.failed")
            messages = [
                item.get("text")
                for event in events
                if event.get("type") == "item.completed"
                for item in [event.get("item")]
                if isinstance(item, dict) and item.get("type") == "agent_message"
                if isinstance(item.get("text"), str)
            ]
            failed = not completed or bool(failed_event)
            return {
                "phase": label,
                "session_id": started.get("thread_id"),
                "model": None,
                "status": "failed" if failed else "passed",
                "provider_terminal_reason": "turn.failed" if failed_event else None,
                "provider_errors": (
                    [_redact(json.dumps(failed_event, sort_keys=True))] if failed_event else []
                ),
                "cost_usd": None,
                "response": _redact(str(messages[-1] if messages else "")),
                "commands": [_redact(value) for value in _codex_commands(events)],
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
                if isinstance(data, dict) and data.get("phase") == "final_answer"
            ]
            message = messages[-1] if messages else {}
            usage = final.get("usage") if isinstance(final.get("usage"), dict) else {}
            failed = not final or final.get("exitCode") != 0
            return {
                "phase": label,
                "session_id": final.get("sessionId"),
                "model": routed_data.get("chosenModel") or message.get("model"),
                "status": "failed" if failed else "passed",
                "provider_terminal_reason": (
                    f"exit-{final.get('exitCode')}" if final and failed else None
                ),
                "provider_errors": [],
                "cost_usd": None,
                "credits_used": usage.get("premiumRequests"),
                "response": _redact(str(message.get("content", ""))),
                "commands": [_redact(value) for value in _copilot_commands(events)],
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
) -> list[str]:
    """Build one provider-native non-interactive onboarding command."""
    match provider:
        case "claude":
            _assert(session is not None, "Claude onboarding requires a chosen session ID.")
            return [
                executable,
                "--model",
                "opus",
                "--setting-sources",
                "project,local",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--tools",
                "Read,Write,Edit,Bash,Grep,Glob,Skill",
                "--output-format",
                "stream-json",
                "--verbose",
                "--permission-mode",
                "bypassPermissions",
                "--max-budget-usd",
                str(budget),
                "--session-id" if first else "--resume",
                session,
                "-p",
                prompt,
            ]
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
            _assert(session is not None, "Codex resume requires its emitted thread ID.")
            return [
                executable,
                "exec",
                "resume",
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                "--dangerously-bypass-hook-trust",
                "--ignore-user-config",
                session,
                prompt,
            ]
        case "copilot":
            _assert(session is not None, "Copilot onboarding requires a chosen session ID.")
            _assert(copilot_credits >= 30, "Copilot requires at least 30 session credits.")
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
                f"--session-id={session}" if first else f"--resume={session}",
                "-C",
                str(consumer),
            ]
        case _:
            raise ValueError(f"Unsupported provider: {provider}")


def _skill_path(consumer: Path, provider: str) -> Path:
    """Return the provider's installed knowledge-setup skill path."""
    match provider:
        case "claude":
            path = consumer / ".claude/skills/knowledge-setup/SKILL.md"
        case "codex" | "copilot":
            path = consumer / ".agents/skills/knowledge-setup/SKILL.md"
        case _:
            raise ValueError(f"Unsupported provider: {provider}")
    _assert(path.is_file(), f"APM did not install the setup skill for {provider}.")
    return path


def _provider_turn(
    provider: str,
    executable: str,
    *,
    consumer: Path,
    env: dict[str, str],
    log: Path,
    session: str | None,
    label: str,
    prompt: str,
    timeout: int,
    budget: float,
    copilot_credits: int,
    report: dict[str, Any],
    first: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    """Run one provider turn and return its events with the exact session ID."""
    print(f"{provider.title()} onboarding: {label}", file=sys.stderr, flush=True)
    args = _provider_command(
        provider,
        executable,
        consumer=consumer,
        session=session,
        prompt=prompt,
        first=first,
        budget=budget,
        copilot_credits=copilot_credits,
    )
    failure = None
    try:
        result = _run(args, cwd=consumer, env=env, log=log, timeout=timeout)
        events = _json_lines(result.stdout)
    except HarnessSmokeFailure as error:
        failure = error
        cause = error.__cause__
        if isinstance(cause, subprocess.TimeoutExpired):
            partial = cause.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode("utf-8", errors="replace")
            with log.open("a") as output:
                output.write("\nPARTIAL_STDOUT:\n" + _redact(partial))
        events = _json_lines(log.read_text()) if log.is_file() else []
    evidence = _provider_evidence(provider, label, events, log)
    if provider == "copilot" and evidence.get("session_id") is None:
        evidence["session_id"] = session
    if failure is not None:
        evidence["status"] = "failed"
        if isinstance(failure.__cause__, subprocess.TimeoutExpired):
            evidence["provider_terminal_reason"] = "timeout"
    report["turns"].append(evidence)
    if evidence["status"] != "passed":
        reason = evidence["provider_terminal_reason"] or "provider-error"
        raise HarnessSmokeFailure(
            f"{provider.title()} {label} ended with {reason}; inspect {log}.", log=log
        )
    actual_session = evidence.get("session_id")
    _assert(
        isinstance(actual_session, str) and actual_session, f"{provider} omitted its session ID."
    )
    if session is not None:
        _assert(
            actual_session == session,
            f"{provider.title()} did not preserve the provider session ID.",
        )
    if provider == "claude":
        _assert(
            evidence["model"] == "claude-opus-5",
            "Claude did not use the expected Opus 5 model.",
        )
    if provider == "copilot":
        _assert(
            isinstance(evidence.get("model"), str) and evidence["model"],
            "Copilot did not report the model selected by automatic routing.",
        )
    _assert_no_remote_activity(events, [str(value) for value in evidence["commands"]])
    return events, actual_session


def run(
    wheel: Path,
    *,
    live: bool,
    keep: bool,
    timeout: int,
    budget: float,
    provider: str = "claude",
    copilot_credits: int = 30,
) -> dict[str, Any]:
    """Prepare and optionally run the complete onboarding scenario."""
    root = Path(__file__).resolve().parents[2]
    package = root / "packages/knowledge-agent-pack"
    work = Path(tempfile.mkdtemp(prefix="knowledge-onboarding.")).resolve()
    consumer = work / "studio"
    consumer.mkdir()
    logs = work / "logs"
    logs.mkdir()
    env = _clean_runtime_env()
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    env.pop("CLAUDE_CONFIG_DIR", None)  # Explicit --live-agent uses existing provider auth.
    env["PATH"] = os.pathsep.join(
        part
        for part in env.get("PATH", os.defpath).split(os.pathsep)
        if not Path(part).resolve().is_relative_to(root)
    )
    report: dict[str, Any] = {
        "schema": "setup-onboarding-acceptance.v1",
        "status": "prepared",
        "consumer": str(consumer),
        "scheduling": "not-tested; paused by user",
        "provider": provider,
        "global_auth_used": live,
        "semantic_quality": "requires review of proposal and authored content",
        "turns": [],
    }
    completed = False
    try:

        def command(args: list[str], label: str, *, cwd: Path = consumer) -> None:
            _run(args, cwd=cwd, env=env, log=logs / f"{label}.log", timeout=timeout)

        command(["git", "init", "-q", "--initial-branch=main"], "git-init")
        (consumer / "apm.yml").write_text(
            "name: onboarding-consumer\nversion: 0.0.1\n"
            "description: Fictional business onboarding acceptance.\n"
            "dependencies:\n  apm:\n    - " + json.dumps(str(package)) + "\n"
        )
        command(
            [
                "apm",
                "install",
                "--refresh",
                "--no-policy",
                "--target",
                "codex,claude,copilot",
            ],
            "apm-install",
        )
        command(
            ["apm", "compile", "--target", "codex,claude,copilot", "--force-instructions"],
            "apm-compile",
        )
        # A standalone installed launcher supplies schemas before workspace configuration.
        bootstrap = work / "bootstrap"
        command(["uv", "venv", "--python", "3.11", str(bootstrap)], "bootstrap-venv")
        command(
            ["uv", "pip", "install", "--python", str(bootstrap / "bin/python"), str(wheel)],
            "bootstrap-install",
        )
        env["PATH"] = str(bootstrap / "bin") + os.pathsep + env["PATH"]
        config = consumer / "knowledge-workspace.yaml"
        catalog = consumer / "catalog.yaml"
        brief = consumer / "business.md"
        brief.write_text(
            "# Studio business brief\n\n"
            "Studio is a solo business building a client-intake product for small agencies. "
            "Agents should help with software testing and lead generation. Knowledge is "
            "shared across this one business; there are no departments or separate squads. "
            "A technology stack and deployment environments have not been chosen.\n\n"
            "Our lead-qualification workflow: the founder checks an agency's intake needs "
            "against our product before outreach, records evidence and unresolved questions, "
            "and excludes an agency when its needs are outside our product's scope.\n"
        )
        sentinel = consumer / "user-owned.txt"
        sentinel.write_text("This file belongs to the consumer and must remain unchanged.\n")
        sentinel_hash = _digest(sentinel)
        runtime_wheel = consumer / ".acceptance" / wheel.name
        runtime_wheel.parent.mkdir()
        shutil.copy2(wheel, runtime_wheel)
        skill = _skill_path(consumer, provider)
        installed_reference = skill.parent / "references/business-onboarding.md"
        _assert(
            installed_reference.read_bytes()
            == (
                package / ".apm/skills/knowledge-setup/references/business-onboarding.md"
            ).read_bytes(),
            "Installed onboarding reference differs from source.",
        )
        if not live:
            report["next"] = (
                f"Rerun with --provider {provider} --live-agent to use the authenticated "
                f"{provider} account."
            )
            completed = True
            return report

        provider_executable = shutil.which(provider)
        _assert(provider_executable, f"{provider.title()} CLI is unavailable.")
        session = None if provider == "codex" else str(uuid4())

        def commit_copilot_state(label: str) -> None:
            if provider != "copilot":
                return
            for key, value in (
                ("user.email", "acceptance@example.invalid"),
                ("user.name", "Agent Knowledge Acceptance"),
            ):
                command(["git", "config", key, value], f"copilot-git-{key.replace('.', '-')}")
            command(["git", "add", "."], f"copilot-git-add-{label}")
            command(
                [
                    "git",
                    "commit",
                    "--allow-empty",
                    "--no-verify",
                    "-m",
                    f"Prepare Copilot onboarding {label}",
                ],
                f"copilot-git-commit-{label}",
            )

        commit_copilot_state("initial")
        if provider == "copilot":
            env = _isolated_copilot_environment(
                consumer,
                base_env=env,
                state_directory=work / "copilot-home",
            )
        boundary = (
            f"This is a disposable acceptance workspace at {consumer}. All writes must stay "
            f"inside it. Use the installed knowledge-setup skill at {skill}. "
            f"The runtime wheel is {runtime_wheel}. Read package resources as needed. "
            "Native automation testing is paused: do not create, update or trigger any "
            "scheduled task, daemon or background job. Report that part as paused. This "
            "does not pause APM compilation or hook binding: setup must retain the default "
            "codex,claude,copilot targets and must not pass an empty --targets value. "
            "Publication is disabled; no GitHub or remote Git operations. "
            "Do not edit global configuration or shell startup files. "
        )

        def turn(label: str, prompt: str, *, first: bool = False) -> list[dict[str, Any]]:
            nonlocal session
            events, session = _provider_turn(
                provider,
                str(provider_executable),
                consumer=consumer,
                env=env,
                log=logs / f"{label}.log",
                session=session,
                label=label,
                prompt=boundary + prompt,
                timeout=timeout,
                budget=budget,
                copilot_credits=copilot_credits,
                report=report,
                first=first,
            )
            _assert(
                _digest(sentinel) == sentinel_hash, "Onboarding changed an unrelated user file."
            )
            return events

        turn(
            "proposal",
            f"Set up knowledge for this business using business.md. Use {config} "
            "as the config location. First inspect context and propose the meaningful choices "
            "for my confirmation. Stop before configuration/catalog writes.",
            first=True,
        )
        _assert(
            not config.exists() and not catalog.exists(),
            "Setup wrote configuration before confirmation.",
        )
        turn(
            "configure",
            "I confirm the proposed business scope and initial vocabulary. "
            "Create the configuration and catalog, using sensible routine defaults. "
            "Run the installed runtime/setup helper and its checks. Leave canonical knowledge "
            "empty for now and finish with the readiness report; scheduling remains paused.",
        )
        _assert(
            config.is_file() and catalog.is_file(),
            "Confirmed setup did not create the paired files.",
        )
        _assert_fresh_signal_storage(config, consumer)
        commit_copilot_state("configured")
        launcher = consumer / ".agent-knowledge-venv/bin/agent-knowledge"
        _assert(launcher.is_file(), "Setup did not create its consumer-local runtime.")
        hook_launcher = launcher.with_name("agent-knowledge-hook")
        registrations = _assert_hook_registration(consumer, hook_launcher)
        hook_smoke = run_provider_hook_smoke(
            consumer,
            hook_launcher,
            logs=logs / "provider-hook-smoke",
            env=env,
        )

        def cli(operation: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
            return _run_json(
                [str(launcher), "--config", str(config), *operation.split(), "--request-file", "-"],
                cwd=consumer,
                env=env,
                log=logs / (operation.replace(" ", "-") + ".log"),
                timeout=timeout,
                input_text=json.dumps(request or {}),
            )

        context = cli("context")
        _assert(
            len(context["applicable_scopes"]) == 1 and len(context["sources"]) == 1,
            "Solo onboarding invented scope or source layers.",
        )
        _assert(context["sources"][0]["publication"] is None, "Setup enabled publication.")
        source_id = context["sources"][0]["id"]
        _assert(
            cli("validate", {"sources": [source_id]})["checked"] == 0,
            "Setup fabricated canonical knowledge.",
        )
        _assert(cli("doctor")["readiness"]["read"] == "ready", "Configured doctor is not ready.")
        # Preserve an unrelated registered concept as well as user comments on repeat.
        existing_catalog = yaml.safe_load(catalog.read_text())
        existing_catalog["topics"]["audit-history"] = {
            "label": "Audit history",
            "description": "Existing user vocabulary unrelated to this onboarding task.",
        }
        catalog.write_text(
            yaml.safe_dump(existing_catalog, sort_keys=False)
            + "\n# User-owned catalog note; preserve on repeat.\n"
        )
        before = {str(path): _digest(path) for path in (config, catalog)}
        repeat_events = turn(
            "repeat",
            "Run setup again with the same confirmed business meaning and paths. "
            "No business choices changed; preserve my configuration and catalog. Verify readiness.",
        )
        if provider == "copilot":
            transformed = _copilot_transformed_prompts(repeat_events)
            _assert(
                any(
                    _REFLECTION_MARKER in value
                    and _COPILOT_PROVIDER_MARKER in value
                    and str(session) in value
                    for value in transformed
                ),
                "Configured Copilot prompt hook omitted provider/session provenance.",
            )
        _assert(
            all(_digest(Path(path)) == digest for path, digest in before.items()),
            "Repeat setup rewrote existing configuration or catalog.",
        )

        prior_signal_ids = {
            row["id"] for row in cli("signal list", {"include_shared": True})["results"]
        }
        report["marketing_checkpoint"] = {
            "prior_signal_ids": sorted(prior_signal_ids),
            "session_id": session,
            "repeat_preservation_proved": True,
        }
        turn(
            "marketing",
            "Capture one signal describing the durable lead-qualification "
            "workflow in business.md, using this session's exact provider ID. Then use the "
            "installed knowledge-compound skill to prepare its canonical workflow with supported "
            "scope/topics and evidence. Validate and discover it with the CLI. Close the compound "
            "activity as prepared but unpublished; retain the signal because "
            "publication is disabled.",
        )
        validated = cli("validate", {"sources": [source_id]})
        _assert(
            validated["valid"] and validated["checked"] >= 1,
            "Authored business knowledge did not validate.",
        )
        results = cli("search", {"kind": ["workflow"]})
        _assert(results["returned"] >= 1, "The marketing workflow is not discoverable.")
        signals = cli("signal list", {"include_shared": True, "session_id": session})
        captured = [row for row in signals["results"] if row["id"] not in prior_signal_ids]
        _assert(
            len(captured) == 1,
            "Expected the new workflow signal retained from this provider session.",
        )
        _assert(
            captured[0]["origin"]["harness"] == provider,
            f"Signal lacks {provider} provenance.",
        )
        activity = cli("compound", {"action": "status"})
        _assert(
            activity["events"] and not activity["active"], "Compounding activity was not closed."
        )

        before = {str(path): _digest(path) for path in (config, catalog)}
        (consumer / "conflicting-note.md").write_text(
            "# Undated draft\n\nStudio knowledge is shared across every contractor's other "
            "businesses. Treat all those companies as one shared knowledge scope.\n"
        )
        turn(
            "conflict",
            "Revisit onboarding using business.md and conflicting-note.md. "
            "Work out whether the configured sharing boundary needs to change.",
        )
        _assert(
            all(_digest(Path(path)) == digest for path, digest in before.items()),
            "Setup silently changed scope based on conflicting business evidence.",
        )
        report.update(
            status="passed",
            provider_session_id=session,
            context=context,
            validation=validated,
            workflow_paths=[row["path"] for row in results["results"]],
            retained_signal=captured[0],
            activity=activity,
            hook_registration=registrations,
            hook_smoke=hook_smoke,
            checks=[
                "confirmation before writes",
                "one solo scope/source",
                "empty initial knowledge",
                "installed runtime readiness",
                "installed hook registration and provider fixtures",
                "repeat preserves configuration",
                "marketing workflow retrieval",
                "session-bound signal and closed compounding",
                "conflicting context leaves scope unchanged",
            ],
        )
        completed = True
        return report
    except (HarnessSmokeFailure, OSError, KeyError, ValueError) as error:
        report.update(status="failed", diagnostic=_redact(str(error)))
        return report
    finally:
        if not keep and completed:
            shutil.rmtree(work)
        elif not completed:
            print(f"Retained failed acceptance workspace: {work}", file=sys.stderr)


def resume(
    source_report: Path,
    wheel: Path,
    *,
    live: bool,
    timeout: int,
    budget: float,
    provider: str = "claude",
    copilot_credits: int = 30,
) -> dict[str, Any]:
    """Continue a retained marketing failure without replaying approved setup phases."""
    previous_bytes = source_report.read_bytes()
    report = json.loads(previous_bytes)
    _assert(report.get("schema") == "setup-onboarding-acceptance.v1", "Unsupported resume report.")
    _assert(report.get("status") == "failed", "Resume requires a failed acceptance report.")
    recorded_provider = str(report.get("provider", "claude"))
    _assert(
        recorded_provider == provider,
        f"Resume provider {provider} does not match retained provider {recorded_provider}.",
    )
    report["provider"] = provider
    previous_turns = report.get("turns", [])
    _assert(
        all(
            any(
                turn.get("phase") == phase and turn.get("status", "passed") == "passed"
                for turn in previous_turns
            )
            for phase in ("proposal", "configure", "repeat")
        ),
        "Resume supports marketing failures after completed proposal/configure/repeat only.",
    )
    sessions = {turn.get("session_id") for turn in previous_turns}
    _assert(len(sessions) == 1 and None not in sessions, "Prior turns lack one exact session ID.")
    session = str(next(iter(sessions)))
    consumer = Path(report["consumer"]).resolve(strict=True)
    work = consumer.parent
    logs = work / "logs" / ("resume-" + uuid4().hex[:12])
    logs.mkdir()
    (logs / "previous-report.json").write_bytes(previous_bytes)
    previous_marketing = work / "logs/marketing.log"
    if previous_marketing.is_file() and not any(
        turn.get("phase") == "marketing" for turn in previous_turns
    ):
        report["turns"].append(
            _provider_evidence(
                provider,
                "marketing",
                _json_lines(previous_marketing.read_text()),
                previous_marketing,
            )
        )
    report.setdefault("resume_history", []).append(
        {
            "source_report": str(source_report),
            "source_sha256": hashlib.sha256(previous_bytes).hexdigest(),
            "preserved_report": str(logs / "previous-report.json"),
            "prior_diagnostic": report.pop("diagnostic", None),
            "session_id": session,
            "logs": str(logs),
        }
    )
    report["status"] = "prepared"
    report["continued_from_retained_state"] = True
    report["inherited_checks"] = [
        "confirmation before configuration writes",
        "one solo scope/source and empty initial knowledge",
        "repeat configuration/catalog byte preservation proved before failed marketing turn",
    ]
    if not live:
        report["next"] = (
            "Use --live-agent with --resume-report to continue the exact provider session."
        )
        return report
    root = Path(__file__).resolve().parents[2]
    env = _clean_runtime_env()
    for key in ("PYTHONPATH", "VIRTUAL_ENV", "CLAUDE_CONFIG_DIR"):
        env.pop(key, None)
    env["PATH"] = (
        str(work / "bootstrap/bin")
        + os.pathsep
        + os.pathsep.join(
            part
            for part in env.get("PATH", os.defpath).split(os.pathsep)
            if not Path(part).resolve().is_relative_to(root)
        )
    )
    if provider == "copilot":
        env = _isolated_copilot_environment(
            consumer,
            base_env=env,
            state_directory=work / "copilot-home",
        )
    config = consumer / "knowledge-workspace.yaml"
    catalog = consumer / "catalog.yaml"
    launcher = consumer / ".agent-knowledge-venv/bin/agent-knowledge"
    skill = _skill_path(consumer, provider)
    sentinel = consumer / "user-owned.txt"
    cli_count = 0

    def cli(operation: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        nonlocal cli_count
        cli_count += 1
        return _run_json(
            [str(launcher), "--config", str(config), *operation.split(), "--request-file", "-"],
            cwd=consumer,
            env=env,
            log=logs / f"{cli_count:02}-{operation.replace(' ', '-')}.log",
            timeout=timeout,
            input_text=json.dumps(request or {}),
        )

    def signals() -> list[dict[str, Any]]:
        result = cli("signal list", {"include_shared": True, "session_id": session, "limit": 100})
        _assert(not result["truncated"], "Resume signal inventory needs more than one page.")
        return result["results"]

    try:
        _assert(
            launcher.is_file() and skill.is_file(), "Retained installed runtime/skill is missing."
        )
        _assert(
            sentinel.read_text()
            == "This file belongs to the consumer and must remain unchanged.\n",
            "Retained user-owned sentinel differs from original acceptance input.",
        )
        sentinel_hash = _digest(sentinel)
        context = cli("context")
        _assert(
            len(context["applicable_scopes"]) == 1 and len(context["sources"]) == 1,
            "Retained solo scope/source shape changed.",
        )
        _assert(context["sources"][0]["publication"] is None, "Retained setup enabled publication.")
        source_id = context["sources"][0]["id"]
        pending = signals()
        original_inputs = {row["local_path"]: _digest(Path(row["local_path"])) for row in pending}
        workflows = [row for row in pending if row["kind_hint"] == "workflow"]
        _assert(
            len(workflows) <= 1, "Resume cannot identify one previously captured workflow signal."
        )
        original_workflow = workflows[0] if workflows else None
        checkpoint = report.get("marketing_checkpoint")
        prior_ids = (
            set(checkpoint["prior_signal_ids"])
            if checkpoint
            else {row["id"] for row in pending if row != original_workflow}
        )
        activity_before = cli("compound", {"action": "status"})
        original_runs = {event["run_id"] for event in activity_before["events"]}
        _assert(
            not original_runs or original_workflow is not None,
            "Existing compound run has no retained workflow signal to verify.",
        )
        if original_workflow:
            selected_ids = {
                item["id"]
                for event in activity_before["events"]
                for item in event.get("selected", [])
            }
            _assert(
                not original_runs or original_workflow["id"] in selected_ids,
                "Existing compound run is unrelated to the retained workflow signal.",
            )
        report["resume_checkpoint"] = {
            "pending_inputs": original_inputs,
            "workflow_signal_id": original_workflow["id"] if original_workflow else None,
            "activity_before": activity_before,
            "baseline_source": "original checkpoint" if checkpoint else "recovered retained state",
        }
        provider_executable = shutil.which(provider)
        _assert(provider_executable, f"{provider.title()} CLI is unavailable.")
        boundary = (
            f"Continue this disposable acceptance workspace at {consumer}; all writes must remain "
            f"inside it. Installed setup skill: {skill}; runtime wheel: "
            f"{consumer / '.acceptance' / wheel.name}. "
            "Native automation testing remains paused; no scheduled tasks, daemons or background "
            "jobs. Publication remains disabled: no GitHub/remote operations or global edits. "
        )
        _, continued_session = _provider_turn(
            provider,
            str(provider_executable),
            consumer=consumer,
            env=env,
            log=logs / "marketing-resume.log",
            session=session,
            label="marketing-resume",
            timeout=timeout,
            budget=budget,
            copilot_credits=copilot_credits,
            report=report,
            prompt=boundary
            + (
                "Continue the previous lead-qualification marketing task after its provider budget "
                "cap. First inspect the current compound activity and existing session-scoped "
                "signals. Preserve every pending signal's original bytes; do not record another "
                "copy of an observation already captured. If a run is active, finish that SAME "
                "run; if its run is already closed, verify the existing result without starting "
                "another run. Only if no run ever started may you start one for the existing "
                "workflow signal. The required result remains a validated, CLI-discoverable "
                "lead-qualification workflow from business.md, with supported scope/topics and "
                "evidence, and a closed prepared-but-unpublished compound run. Retain the workflow "
                "signal because publication is disabled. If the previous turn already completed "
                "these actions, use the installed CLI to confirm them and report what is on disk. "
                "Keep the response brief and distinguish the prior budget cap from actual results."
            ),
        )
        _assert(continued_session == session, "Continuation changed the provider session ID.")
        _assert(_digest(sentinel) == sentinel_hash, "Continuation changed the user-owned file.")
        _assert(
            all(
                Path(path).is_file() and _digest(Path(path)) == digest
                for path, digest in original_inputs.items()
            ),
            "Continuation changed a pending input.",
        )
        validated = cli("validate", {"sources": [source_id]})
        _assert(
            validated["valid"] and validated["checked"] >= 1, "Business knowledge did not validate."
        )
        results = cli("search", {"kind": ["workflow"]})
        _assert(results["returned"] >= 1, "Marketing workflow is not discoverable.")
        captured = [row for row in signals() if row["id"] not in prior_ids]
        _assert(
            len(captured) == 1 and captured[0]["kind_hint"] == "workflow",
            "Expected one retained workflow signal from the exact provider session.",
        )
        _assert(
            captured[0]["origin"]["harness"] == provider,
            f"Signal lacks {provider} provenance.",
        )
        activity = cli("compound", {"action": "status"})
        _assert(activity["events"] and not activity["active"], "Compound activity remains open.")
        _assert(
            not original_runs or {event["run_id"] for event in activity["events"]} == original_runs,
            "Continuation started a second compound run.",
        )
        # Establish this baseline after marketing, which may legitimately update the catalog.
        before_conflict = {str(path): _digest(path) for path in (config, catalog)}
        report["conflict_checkpoint"] = before_conflict
        (consumer / "conflicting-note.md").write_text(
            "# Undated draft\n\nStudio knowledge is shared across every contractor's other "
            "businesses. Treat all those companies as one shared knowledge scope.\n"
        )
        _, conflict_session = _provider_turn(
            provider,
            str(provider_executable),
            consumer=consumer,
            env=env,
            log=logs / "conflict.log",
            session=session,
            label="conflict",
            timeout=timeout,
            budget=budget,
            copilot_credits=copilot_credits,
            report=report,
            prompt=boundary + "Revisit onboarding using business.md and conflicting-note.md. "
            "Work out whether the configured sharing boundary needs to change.",
        )
        _assert(conflict_session == session, "Conflict turn changed the provider session ID.")
        _assert(
            all(_digest(Path(path)) == digest for path, digest in before_conflict.items()),
            "Setup silently changed scope based on conflicting evidence.",
        )
        _assert(
            _digest(sentinel) == sentinel_hash, "Conflict handling changed the user-owned file."
        )
        report.pop("next", None)
        report.update(
            status="passed",
            provider_session_id=session,
            context=context,
            validation=validated,
            workflow_paths=[row["path"] for row in results["results"]],
            retained_signal=captured[0],
            activity=activity,
            checks=[
                "retained pending input bytes preserved",
                "marketing workflow retrieval",
                "session-bound retained signal and closed original compound run",
                "conflicting context leaves scope/configuration unchanged",
            ],
        )
    except (HarnessSmokeFailure, OSError, KeyError, ValueError) as error:
        report.update(status="failed", diagnostic=_redact(str(error)))
    return report


def main() -> int:
    """Run the onboarding acceptance CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument(
        "--provider",
        choices=_PROVIDERS,
        default="claude",
        help="Authenticated CLI to exercise (default: claude).",
    )
    parser.add_argument(
        "--live-agent", action="store_true", help="Use the authenticated provider account."
    )
    parser.add_argument("--keep", action="store_true")
    parser.add_argument(
        "--resume-report",
        type=Path,
        help="Continue a retained failure after repeat setup; never rerun setup.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        default=4.0,
        help="Per Claude turn; ignored by Codex and Copilot.",
    )
    parser.add_argument(
        "--max-ai-credits",
        type=int,
        default=30,
        help="Copilot session credit cap (minimum/default: 30).",
    )
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error("--wheel must name a built wheel")
    if args.max_ai_credits < 30:
        parser.error("--max-ai-credits must be at least 30")
    try:
        if args.resume_report is not None:
            source_report = args.resume_report.resolve(strict=True)
            if args.output and args.output.exists():
                parser.error(
                    "--output must be a new file when resuming; preserve previous evidence"
                )
            report = resume(
                source_report,
                wheel,
                live=args.live_agent,
                timeout=args.timeout,
                budget=args.max_budget_usd,
                provider=args.provider,
                copilot_credits=args.max_ai_credits,
            )
        else:
            report = run(
                wheel,
                live=args.live_agent,
                keep=args.keep,
                timeout=args.timeout,
                budget=args.max_budget_usd,
                provider=args.provider,
                copilot_credits=args.max_ai_credits,
            )
    except (HarnessSmokeFailure, OSError, KeyError, ValueError) as error:
        report = {
            "schema": "setup-onboarding-acceptance.v1",
            "status": "failed",
            "diagnostic": _redact(str(error)),
        }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0 if report["status"] in {"passed", "prepared"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
