#!/usr/bin/env python3
"""Opt-in acceptance through real harness launchers in a disposable Linux container.

The image is a test fixture, not a deployment product. No user home or knowledge
checkout is mounted. Authentication is passed only by explicit provider-specific
environment names; values never appear in argv, build contexts or saved reports.
Without --live-agent the report distinguishes installed/container evidence from
unperformed native harness proof. No native scheduler or publication is invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from claude_hook_acceptance import _hook_contexts, _json_lines
from container_launch_fixture import (
    CONSUMER,
    PROFILE,
    REFLECTION,
    REGISTRY,
    RUNTIME,
    SOURCE_VARIABLE,
    STATE,
    TARGET_VARIABLE,
    write_json,
)
from fresh_consumer_smoke import _write_consumer_files
from harness_agent_smoke import _redact
from profile_acceptance import _provider_evidence

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = ("codex", "claude", "copilot")
VERSIONS = {"codex": "0.160.1", "claude": "2.1.236", "copilot": "1.0.86"}
AUTH_VARIABLES = {
    "codex": {"OPENAI_API_KEY", "CODEX_API_KEY"},
    "claude": {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"},
    "copilot": {"COPILOT_GITHUB_TOKEN"},
}
SETUP = Path("/opt/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts")
TOOL_PROBE = "/opt/proof/container_launch_fixture.py"


def clean_parent_environment(environment: dict[str, str]) -> dict[str, str]:
    """Do not let a prior profile or the fixture's own target fake activation."""
    result = dict(environment)
    for name in tuple(result):
        if name.startswith(("KNOWLEDGE_", "AGENT_KNOWLEDGE_")) or name in {
            SOURCE_VARIABLE,
            TARGET_VARIABLE,
            "PYTHONPATH",
            "GH_TOKEN",
            "GITHUB_TOKEN",
        }:
            result.pop(name, None)
    return result


def auth_routes(values: list[str], environment: dict[str, str]) -> dict[str, str]:
    result = {}
    for raw in values:
        provider, separator, name = raw.partition(":")
        if not separator or name not in AUTH_VARIABLES.get(provider, set()) or provider in result:
            raise ValueError("Use one declared PROVIDER:AUTH_VARIABLE route per provider.")
        if not environment.get(name):
            raise ValueError(f"Declared {provider} authentication variable is absent or blank.")
        result[provider] = name
    return result


def native_environment(provider: str, source: str, environment: dict[str, str]) -> dict[str, str]:
    """Activate only the explicit test-auth route in the individual native child.

    Codex exec consumes CODEX_API_KEY, not an unconfigured OPENAI_API_KEY.
    https://learn.chatgpt.com/docs/non-interactive-mode#use-api-key-auth
    """
    if source not in AUTH_VARIABLES.get(provider, set()) or not environment.get(source):
        raise ValueError("Selected native authentication route is unavailable.")
    result = clean_parent_environment(environment)
    for name in set().union(*AUTH_VARIABLES.values()):
        result.pop(name, None)
    result["CODEX_API_KEY" if provider == "codex" else source] = environment[source]
    return result


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 900,
    cwd: Path | None = None,
    require_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, env=env, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode and require_success:
        raise RuntimeError(
            f"{Path(command[0]).name} failed ({result.returncode}): "
            + _redact(result.stderr[-1800:])
        )
    return result


def command_json(command: list[str], *, allow_failure: bool = False, **kwargs) -> dict:
    result = run(command, require_success=not allow_failure, **kwargs)
    report = json.loads(result.stdout)
    if result.returncode and report.get("status") != "failed":
        report.update(status="failed", reason="Child exited unsuccessfully.")
    return report


def export_evidence(container: str, output: Path) -> list[dict]:
    """Always attempt export before cleanup, including failed native runs."""
    outcomes = []
    for source, destination in (("evidence/.", output), ("setup.json", output / "setup.json")):
        try:
            result = run(
                ["docker", "cp", f"{container}:/state/{source}", str(destination)],
                timeout=30,
                require_success=False,
            )
            outcomes.append(
                {"source": source, "status": "saved" if not result.returncode else "unavailable"}
            )
        except (OSError, subprocess.TimeoutExpired):
            outcomes.append({"source": source, "status": "unavailable"})
    return outcomes


def provider_arguments(provider: str, prompt: str) -> list[str]:
    """Narrow fictional-fixture permissions; never inherit broad bypass flags."""
    match provider:
        case "codex":
            return [
                "-c",
                "features.hooks=true",
                "-c",
                'approval_policy="never"',
                "-c",
                "allow_login_shell=false",
                "-c",
                # Codex ignores dotted quoted-path overrides; use its TOML map.
                "projects={" + json.dumps(str(CONSUMER)) + '={trust_level="trusted"}}',
                "exec",
                "--json",
                "--sandbox",
                "workspace-write",
                "--cd",
                str(CONSUMER),
                "--add-dir",
                str(STATE / "knowledge"),
                "--add-dir",
                str(STATE / "evidence"),
                prompt,
            ]
        case "claude":
            return [
                "--setting-sources",
                "project,local",
                "--include-hook-events",
                "--verbose",
                "--output-format",
                "stream-json",
                "--max-budget-usd",
                "3",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--tools",
                "Read,Bash",
                "--allowedTools",
                f"Bash({RUNTIME}/bin/python {TOOL_PROBE} *)",
                "Read",
                "-p",
                prompt,
            ]
        case "copilot":
            return [
                "-p",
                prompt,
                "--model",
                "auto",
                "--auto-tier",
                "efficiency",
                "--max-ai-credits",
                "10",
                "--no-ask-user",
                "--no-auto-update",
                "--no-remote",
                "--no-remote-export",
                "--disable-builtin-mcps",
                "--available-tools",
                "bash",
                "view",
                "--allow-tool",
                f"shell({RUNTIME}/bin/python:*)",
                "--allow-tool",
                "read",
                "--deny-url=*",
                "--disallow-temp-dir",
                "--add-dir",
                str(STATE),
                "--output-format",
                "json",
                "--log-level",
                "none",
                "-C",
                str(CONSUMER),
            ]
        case _:
            raise ValueError("Unsupported provider")


def native_hooks(provider: str, events: list[dict]) -> dict:
    """Only observed provider event channels prove firing, never assistant prose."""
    lifecycle, prompt = [], []
    if provider == "claude":
        lifecycle = [content for _, content in _hook_contexts(events, "SessionStart:startup")]
        prompt = [content for _, content in _hook_contexts(events, "UserPromptSubmit")]
    elif provider == "copilot":
        for event in events:
            data = event.get("data", {})
            if not isinstance(data, dict):
                continue
            if event.get("type") == "user.message" and isinstance(
                data.get("transformedContent"), str
            ):
                prompt.append(data["transformedContent"])
            if event.get("type") == "hook.end" and data.get("hookType") == "sessionStart":
                output = data.get("output")
                if isinstance(output, str):
                    lifecycle.append(output)
    # Codex's CLI JSONL does not consistently expose hook events. Do not promote
    # instruction text found in a rollout to a successful native hook firing.
    return {
        "lifecycle": "passed"
        if any("agent-knowledge describe" in s for s in lifecycle)
        else "pending",
        "prompt": "passed" if any(REFLECTION in s for s in prompt) else "pending",
        "reason": "native response/transformed-prompt evidence required; registration is separate",
    }


def _probe_command(command: str, provider: str, phase: str, session: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) >= 3 and Path(tokens[0]).name in {"bash", "sh", "zsh"}:
        return tokens[1] in {"-c", "-lc"} and _probe_command(tokens[2], provider, phase, session)
    if tokens[:2] != [str(RUNTIME / "bin/python"), TOOL_PROBE]:
        return False
    expected = {"--provider": provider, "--phase": phase, "--session-id": session}
    if len(tokens) != 8:
        return False
    return dict(zip(tokens[2::2], tokens[3::2], strict=True)) == expected


def native_probe_executed(provider: str, events: list[dict], phase: str, session: str) -> bool:
    """Correlate a successful actual shell call, never a narrative command mention."""
    expected_path = str(STATE / "evidence" / provider / f"{phase}-tool.json")

    def output_passed(output: object) -> bool:
        if not isinstance(output, str):
            return False
        return any(
            value.get("status") == "passed"
            and value.get("tool_proof") == expected_path
            and value.get("session_id") == session
            for value in _json_lines(output)
        )

    if provider == "codex":
        return any(
            event.get("type") == "item.completed"
            and isinstance(item := event.get("item"), dict)
            and item.get("type") == "command_execution"
            and item.get("exit_code") == 0
            and _probe_command(str(item.get("command", "")), provider, phase, session)
            and output_passed(item.get("aggregated_output"))
            for event in events
        )
    if provider == "copilot":
        calls = {
            data.get("toolCallId")
            for event in events
            if event.get("type") == "tool.execution_start"
            and isinstance(data := event.get("data"), dict)
            and data.get("toolName") == "bash"
            and isinstance(data.get("arguments"), dict)
            and _probe_command(str(data["arguments"].get("command", "")), provider, phase, session)
        }
        return any(
            event.get("type") == "tool.execution_complete"
            and isinstance(data := event.get("data"), dict)
            and data.get("toolCallId") in calls
            and data.get("success") is True
            and data.get("shellExecution", {}).get("exitCode") == 0
            and output_passed(data.get("result", {}).get("content"))
            for event in events
        )
    calls = set()
    results = []
    for event in events:
        message = event.get("message", {})
        parts = message.get("content", []) if isinstance(message, dict) else []
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            if (
                part.get("type") == "tool_use"
                and part.get("name") == "Bash"
                and _probe_command(
                    str(part.get("input", {}).get("command", "")), provider, phase, session
                )
            ):
                calls.add(part.get("id"))
            if part.get("type") == "tool_result":
                results.append(part)
    return any(
        part.get("tool_use_id") in calls
        and not part.get("is_error")
        and output_passed(part.get("content"))
        for part in results
    )


def verify_tool_proof(proof: dict, evidence: dict, *, provider: str, phase: str) -> None:
    if evidence.get("status") != "passed" or proof.get("session_id") != evidence.get("session_id"):
        raise ValueError("Actual native session and successful tool proof do not correlate.")
    if proof.get("provider") != provider or proof.get("phase") != phase:
        raise ValueError("Tool proof belongs to a different provider or launch.")
    if not proof.get("container_marker") or proof.get("uid") != 1000:
        raise ValueError("Harness tool did not establish the intended nonroot container context.")
    if proof.get("registry") != str(REGISTRY) or proof.get("profile") != PROFILE:
        raise ValueError("Harness tool used another profile or registry.")
    if evidence.get("probe_execution") is not True:
        raise ValueError("No successful native shell call executed the controlled tool probe.")
    operations = set(proof.get("retrieval", {}).get("receipt_operations", []))
    if not {"catalog", "search", "inspect"} <= operations:
        raise ValueError("Selected native-session retrieval receipts are incomplete.")
    if not all(
        proof.get("credentials", {}).get(key) is True
        for key in ("target_matches_fixture", "source_not_exposed")
    ):
        raise ValueError("Clean-parent mapped credential activation was not proven.")
    if proof.get("scope", {}).get("canonical_fixture_write_denied") is not True:
        raise ValueError("Canonical fixture was unexpectedly writable.")
    if proof.get("doctor", {}).get("status") != "ok":
        raise ValueError("Write-mode doctor did not pass inside the native harness tool.")
    if proof.get("doctor", {}).get("workspace_id") != "workspace:container-fixture":
        raise ValueError("Native doctor resolved the wrong workspace.")
    if proof.get("signal", {}).get("finish") != "ok":
        raise ValueError("Supported fixture signal cleanup did not finish.")
    signal = proof.get("signal", {})
    if (
        signal.get("id") != f"container-{provider}-{phase}"
        or signal.get("cleanup", {}).get("drained") != [signal.get("id")]
        or signal.get("cleanup", {}).get("retained")
        or signal.get("absent_after") is not True
    ):
        raise ValueError("The exact fixture signal was not drained and confirmed absent.")


def persistent_snapshot(root: Path) -> dict:
    """Only fixture signals/usage, never private credentials or native auth/session files."""
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            result[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "inode": path.stat().st_ino,
            }
    return result


def checkpoint_state() -> dict:
    snapshot = persistent_snapshot(STATE / "knowledge/ai")
    write_json(STATE / "evidence/state-checkpoint.json", snapshot)
    return {"files": len(snapshot), "status": "recorded" if snapshot else "empty"}


def verify_bound_audit(report: dict) -> dict:
    """APM replays markers; the fixture additionally owns verified hook binding."""
    expected = {
        ".claude/apm-hooks.json",
        ".claude/settings.json",
        ".codex/apm-hooks.json",
        ".codex/hooks.json",
        ".github/hooks/knowledge-agent-pack-knowledge-discovery.json",
    }
    checks = report.get("checks", [])
    required = {
        "lockfile-exists",
        "ref-consistency",
        "deployment-ledger-owners",
        "deployed-files-present",
        "no-orphaned-packages",
        "skill-subset-consistency",
        "config-consistency",
        "content-integrity",
        "includes-consent",
        "drift",
    }
    if {row.get("name") for row in checks} != required or len(checks) != len(required):
        raise ValueError("APM audit omitted an expected fixture check.")
    if any(row.get("passed") is not True for row in checks if row["name"] != "drift"):
        raise ValueError("A non-drift APM check failed after binding.")
    changes = report.get("drift", {}).get("drift", [])
    if (
        len(changes) != len(expected)
        or {row.get("path") for row in changes} != expected
        or any(row.get("kind") != "modified" for row in changes)
    ):
        raise ValueError("APM replay differs outside the exact setup-owned hook bindings.")
    return {
        "apm_replay_passed": report.get("passed"),
        "expected_bound_hook_differences": sorted(expected),
        "other_audit_checks": "passed",
    }


def prepare() -> dict:
    """Create the fictional consumer once; repeat only owned binding/checks."""
    STATE.mkdir(exist_ok=True)
    (STATE / "home").mkdir(exist_ok=True)
    package = Path("/opt/knowledge-agent-pack")
    first = not CONSUMER.exists()
    checkpoint = STATE / "evidence/state-checkpoint.json"
    prior_state = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if prior_state is not None and prior_state != persistent_snapshot(STATE / "knowledge/ai"):
        raise ValueError("Persisted signal, receipt or lock identity changed across recreation.")
    if first:
        _write_consumer_files(Path("/opt/fixture"), CONSUMER, package)
        # The shared fixture contains deliberately unavailable hand-authored hook
        # commands. This fixture owns those inputs and uses an inert command.
        for relative in (
            ".codex/hooks.json",
            ".claude/settings.json",
            ".github/hooks/hand-authored.json",
        ):
            path = CONSUMER / relative
            text = path.read_text()
            for name in (
                "hand-authored-codex-stop",
                "hand-authored-codex",
                "hand-authored-claude-stop",
                "hand-authored-claude",
                "hand-authored-copilot",
            ):
                text = text.replace(name, "true")
            path.write_text(text)
        configuration = {
            "schema_version": "knowledge-workspace.v1",
            "workspace_id": "workspace:container-fixture",
            "applicable_scopes": ["org:example", "group:commerce", "repo:orders-api"],
            "sources": [
                {
                    "id": "fixture",
                    "root": "/opt/fixture/knowledge",
                    "catalog": "/opt/fixture/catalog.yaml",
                }
            ],
            "signal_storage": {"scaffold_root": "/state/knowledge", "code_root": "/state"},
            "receipts": {
                "enabled": True,
                "directory": "/state/knowledge/ai/usage",
                "retention_days": 30,
            },
            "setup": {
                "venv": str(RUNTIME),
                "compounding": {"mode": "manual", "owner": "container-fixture"},
            },
        }
        write_json(CONSUMER / "knowledge-workspace.yaml", configuration)
        for path in (
            STATE / "knowledge/ai/signals",
            STATE / "knowledge/ai/usage",
            STATE / "evidence",
        ):
            path.mkdir(parents=True, exist_ok=True)
        private = STATE / "private"
        private.mkdir(mode=0o700)
        environment_file = private / "fixture.env"
        environment_file.write_text(SOURCE_VARIABLE + "=fixture-" + uuid.uuid4().hex + "\n")
        environment_file.chmod(0o600)
        write_json(
            REGISTRY,
            {
                "schema_version": "knowledge-profiles.v1",
                "default_profile": "unused-default",
                "profiles": {
                    "unused-default": {"config": "/deliberately/unavailable/workspace.yaml"},
                    PROFILE: {
                        "config": str(CONSUMER / "knowledge-workspace.yaml"),
                        "environment": {
                            "file": str(environment_file),
                            "variables": {
                                "canary": {
                                    "from_env": SOURCE_VARIABLE,
                                    "expose_as": TARGET_VARIABLE,
                                    "description": "Synthetic isolated acceptance canary",
                                }
                            },
                        },
                    },
                },
            },
        )
        run(["git", "init", "--quiet"], cwd=CONSUMER)
        # Signal provenance belongs to the central fixture checkout, distinct
        # from the consumer. Doctor's filesystem probe does not establish Git.
        run(["git", "init", "--quiet"], cwd=STATE / "knowledge")
    arguments = [
        str(RUNTIME / "bin/python"),
        str(SETUP / "setup_runtime.py"),
        "--workspace",
        str(CONSUMER / "knowledge-workspace.yaml"),
        "--package",
        "/opt/reference.whl",
        "--venv",
        str(RUNTIME),
        "--runtime-mode",
        "existing",
        "--consumer",
        str(CONSUMER),
        "--settings",
        str(REGISTRY),
        "--profile",
        PROFILE,
        "--portable-hooks",
    ]
    if first:
        command_json([*arguments, "--apm-mode", "prepare"], cwd=CONSUMER)
        run(
            ["apm", "install", "--refresh", "--no-policy", "--target", "codex,claude,copilot"],
            cwd=CONSUMER,
        )
        run(
            ["apm", "compile", "--target", "codex,claude,copilot", "--force-instructions"],
            cwd=CONSUMER,
        )
        installed_audit = command_json(["apm", "audit", "--ci", "--format", "json"], cwd=CONSUMER)
        if installed_audit.get("passed") is not True:
            raise ValueError("Installed package failed APM audit before binding.")
        write_json(STATE / "evidence/apm-installed-audit.json", installed_audit)
        # A fixture-owned project source narrows this harness task; generated outputs stay owned.
        (CONSUMER / "TASK.txt").write_text(
            "Only run the designated acceptance probe; no publication or scheduler.\n"
        )

    def hook_snapshot() -> dict:
        return {
            p.relative_to(CONSUMER).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in (".codex", ".claude", ".github/hooks")
            for p in (CONSUMER / folder).rglob("*.json")
            if p.is_file()
        }

    before = hook_snapshot()
    report = command_json([*arguments, "--apm-mode", "bind"], cwd=CONSUMER)
    again = command_json([*arguments, "--apm-mode", "bind"], cwd=CONSUMER)
    if set(report["hooks"]["targets"]) != set(PROVIDERS):
        raise ValueError("Owned integration pruned an established APM target.")
    if again.get("apm_lock", {}).get("status") != "current":
        raise ValueError("Repeat bind did not preserve the deployed lock contract.")
    audit = run(["apm", "audit", "--ci", "--format", "json"], cwd=CONSUMER, require_success=False)
    raw_audit = json.loads(audit.stdout)
    write_json(STATE / "evidence/apm-bound-audit.json", raw_audit)
    bound_audit = verify_bound_audit(raw_audit)
    after = hook_snapshot()
    if not first and before != after:
        raise ValueError("Reuse binding changed already verified hook registrations.")
    write_json(STATE / "setup.json", report)
    startup = {}
    for provider in PROVIDERS:
        checked = run(
            [
                str(RUNTIME / "bin/python"),
                str(SETUP / "launch_container.py"),
                "--setup-report",
                str(STATE / "setup.json"),
                "--provider",
                provider,
                "--",
                "--version",
            ],
            env=clean_parent_environment(dict(os.environ)),
            cwd=CONSUMER,
        )
        startup[provider] = {
            "status": "passed",
            "version": checked.stdout.strip(),
            "proof": "real launcher and CLI startup; no native hooks/model call",
        }
    return {
        "status": "passed",
        "first": first,
        "targets": report["hooks"]["targets"],
        "setup_report": str(STATE / "setup.json"),
        "registry": str(REGISTRY),
        "profile": PROFILE,
        "runtime": report["runtime"],
        "rebind": "idempotent",
        "bound_audit": bound_audit,
        "launch": report.get("launch", {"status": "pending", "reason": "launcher recipe absent"}),
        "provider_versions": {p: run([p, "--version"]).stdout.strip() for p in PROVIDERS},
        "apm_version": run(["apm", "--version"]).stdout.strip(),
        "uid": os.getuid(),
        "container_hostname": os.uname().nodename,
        "launcher_startup": startup,
        "persistent_state": "passed" if prior_state else "not-yet-established",
        "persistent_files": len(prior_state or {}),
    }


def native(provider: str, phase: str, timeout: int, auth_source: str) -> dict:
    parent = native_environment(provider, auth_source, dict(os.environ))
    parent.update(
        HOME="/state/home",
        CODEX_HOME="/state/home/.codex",
        COPILOT_HOME="/state/home/.copilot",
        AGENT_KNOWLEDGE_SETTINGS=str(REGISTRY),
    )
    directory = STATE / "evidence" / provider
    directory.mkdir(parents=True, exist_ok=True)
    # Exact fixture-owned project trust only; no user/global home is mounted.
    if provider == "copilot":
        write_json(
            Path(parent["COPILOT_HOME"]) / "settings.json",
            {
                "trustedFolders": [str(CONSUMER)],
                "autoUpdate": False,
                "disableAllHooks": False,
                "memory": False,
            },
        )
    prompt = (
        "Run one bounded container acceptance check. Obtain your exact native session handle "
        "from the installed hook/native context; never invent one. Use your shell tool to run "
        f"{RUNTIME}/bin/python {TOOL_PROBE} --provider {provider} --phase {phase} "
        "--session-id YOUR_EXACT_SESSION_HANDLE. This trusted fixture probe tests selected-profile "
        "retrieval, write doctor, synthetic credential presence and fixture signal cleanup. "
        "Do not change files or configuration yourself; do not read credentials or invoke models. "
        "Do not schedule, compound real inputs, publish, install tools or widen permissions. "
        "Report missing hooks/session/tool access as a prerequisite. Keep the result brief."
    )
    command = [
        str(RUNTIME / "bin/python"),
        str(SETUP / "launch_container.py"),
        "--setup-report",
        str(STATE / "setup.json"),
        "--provider",
        provider,
        "--",
        *provider_arguments(provider, prompt),
    ]
    result = subprocess.run(
        command,
        cwd=CONSUMER,
        env=parent,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    private_value = (STATE / "private/fixture.env").read_text().strip().partition("=")[2]
    secrets = [private_value, *(parent.get(name, "") for name in AUTH_VARIABLES[provider])]
    log_text = result.stdout + "\n" + result.stderr
    for secret in filter(None, secrets):
        log_text = log_text.replace(secret, "[redacted]")
    log = directory / f"{phase}-native.jsonl"
    log.write_text(_redact(log_text))
    events = _json_lines(result.stdout)
    evidence = _provider_evidence(provider, events, log)
    evidence["probe_execution"] = native_probe_executed(
        provider, events, phase, str(evidence.get("session_id", ""))
    )
    # Do not retain final prose, arbitrary tool arguments or credentials in the report.
    report = {
        "status": "pending",
        "provider": provider,
        "authentication_source": auth_source,
        "phase": phase,
        "native_exit": result.returncode,
        "session_id": evidence.get("session_id"),
        "log": str(log),
        "hooks": native_hooks(provider, events),
        "trust": "isolated fixture project only; actual firing reported independently",
        "launch_argv": command[: -len(provider_arguments(provider, prompt))],
        "parent_target_absent": TARGET_VARIABLE not in parent,
        "scheduling": "not-run",
        "real_compounding": "not-run",
        "publication": "not-run",
        "scope": {
            "canonical_write_denial": "unverified",
            "credential_write_denial": "unverified",
            "explicit_read_only_launch": "unverified",
        },
    }
    proof_path = directory / f"{phase}-tool.json"
    if not proof_path.is_file():
        report["reason"] = "Native harness did not produce tool proof; inspect native transcript."
        return report
    proof = json.loads(proof_path.read_text())
    try:
        verify_tool_proof(proof, evidence, provider=provider, phase=phase)
    except ValueError as error:
        report.update(status="failed", reason=str(error))
        return report
    report.update(
        status="passed",
        tool_proof=str(proof_path),
        retrieval="passed",
        credential_activation="passed",
        write_doctor="passed",
    )
    report["scope"]["canonical_write_denial"] = "passed"
    report.update(
        status="partial", reason="Credential-write and explicit read-only sandbox proof pending."
    )
    if "pending" in (report["hooks"]["lifecycle"], report["hooks"]["prompt"]):
        report.update(status="partial", reason="Native hook firing proof incomplete.")
    return report


def dockerfile() -> str:
    return r"""FROM node:24-trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv git curl ca-certificates libicu76 && rm -rf /var/lib/apt/lists/*
RUN arch=$(uname -m); case "$arch" in aarch64) arch=arm64;; x86_64) arch=x86_64;; \
    *) exit 1;; esac; url=https://github.com/microsoft/apm/releases/download/v0.29.0; \
    cd /tmp && curl -fsSLO $url/apm-linux-$arch.tar.gz && \
    curl -fsSLO $url/apm-linux-$arch.tar.gz.sha256 && \
    sha256sum -c apm-linux-$arch.tar.gz.sha256 && mkdir /opt/apm && \
    tar -xzf apm-linux-$arch.tar.gz -C /opt/apm --strip-components=1 && \
    ln -s /opt/apm/apm /usr/local/bin/apm && rm /tmp/apm-linux-*
RUN npm install --global @openai/codex@0.160.1 \
    @anthropic-ai/claude-code@2.1.236 @github/copilot@1.0.86
COPY dist/ /opt/wheels/
COPY reference.whl /opt/reference.whl
RUN python3 -m venv /opt/runtime && /opt/runtime/bin/pip install /opt/wheels/*.whl && \
    chmod -R a-w /opt/runtime
COPY knowledge-agent-pack/ /opt/knowledge-agent-pack/
COPY fixture/ /opt/fixture/
COPY proof/ /opt/proof/
ENV PATH=/opt/runtime/bin:/usr/local/bin:/usr/bin:/bin HOME=/state/home \
    PYTHONDONTWRITEBYTECODE=1 AGENT_KNOWLEDGE_SETTINGS=/state/profiles.yaml
USER 1000:1000
WORKDIR /state
"""


def host(args: argparse.Namespace) -> dict:
    if shutil.which("docker") is None or shutil.which("uv") is None:
        return {"status": "pending", "reason": "Docker and uv are explicit host prerequisites."}
    routes = auth_routes(args.auth_env, dict(os.environ))
    run(["docker", "info", "--format", "{{.OSType}}"])
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    security = ["--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    seccomp = None
    if args.docker_seccomp_profile is not None:
        # Explicit fixture-only Docker policy; never change daemon or harness policy.
        seccomp = args.docker_seccomp_profile.resolve(strict=True)
        security += ["--security-opt", f"seccomp={seccomp}"]
        shutil.copyfile(seccomp, output / "docker-seccomp.json")
    suffix = uuid.uuid4().hex[:12]
    image, volume = f"knowledge-launch-proof:{suffix}", f"knowledge-launch-proof-{suffix}"
    container = f"knowledge-launch-proof-{suffix}"
    report = {
        "status": "running",
        "scope": "disposable installed Linux consumer; no user data",
        "native_scheduling": "not-run",
        "host_windows_mount_proof": "not-run",
        "image": image,
        "volume": volume,
        "providers": {},
        "preparation": [],
        "docker_security": {
            "cap_drop": ["ALL"],
            "no_new_privileges": True,
            "seccomp": str(seccomp) if seccomp else "docker-default",
        },
    }
    with tempfile.TemporaryDirectory(prefix="knowledge-launch-build-") as temporary:
        context = Path(temporary)
        run(["uv", "build", "--wheel", "--out-dir", str(context / "dist"), str(ROOT)])
        wheel = next((context / "dist").glob("*.whl"))
        shutil.copy2(wheel, context / "reference.whl")
        shutil.copytree(
            ROOT / "packages/knowledge-agent-pack",
            context / "knowledge-agent-pack",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copytree(ROOT / "examples", context / "fixture/examples")
        shutil.copytree(ROOT / "examples/knowledge", context / "fixture/knowledge")
        shutil.copy2(ROOT / "examples/catalog.yaml", context / "fixture/catalog.yaml")
        (context / "proof").mkdir()
        for script in (
            "container_launch_acceptance.py",
            "container_launch_fixture.py",
            "fresh_consumer_smoke.py",
            "claude_hook_acceptance.py",
            "harness_agent_smoke.py",
            "profile_acceptance.py",
            "provider_hook_smoke.py",
        ):
            shutil.copy2(ROOT / "tests/e2e" / script, context / "proof" / script)
        (context / "Dockerfile").write_text(dockerfile())
        report["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        report["source_revision"] = run(["git", "rev-parse", "HEAD"], cwd=ROOT).stdout.strip()
        report["driver_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        try:
            build = run(["docker", "build", "--tag", image, str(context)], timeout=1800)
            (output / "build.log").write_text(_redact(build.stdout + build.stderr))
            report["image_id"] = run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image]
            ).stdout.strip()
            run(["docker", "volume", "create", volume])
            mount = ["--mount", f"type=volume,src={volume},dst=/state"]
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    "0:0",
                    *mount,
                    image,
                    "chown",
                    "1000:1000",
                    "/state",
                ]
            )
            for recreation in range(2):
                auth_flags = (
                    [part for name in routes.values() for part in ("--env", name)]
                    if args.live_agent
                    else []
                )
                run(
                    [
                        "docker",
                        "run",
                        "--detach",
                        "--name",
                        container,
                        *security,
                        *mount,
                        *auth_flags,
                        image,
                        "sleep",
                        "infinity",
                    ],
                    env=clean_parent_environment(dict(os.environ)),
                )
                try:
                    prepared = command_json(
                        [
                            "docker",
                            "exec",
                            container,
                            "/opt/runtime/bin/python",
                            "/opt/proof/container_launch_acceptance.py",
                            "--inside",
                            "prepare",
                        ]
                    )
                    report["preparation"].append(prepared)
                    phases = ("fresh", "reused") if recreation == 0 else ("recreated",)
                    for provider in args.providers.split(","):
                        bucket = report["providers"].setdefault(provider, {"native": []})
                        if not args.live_agent or provider not in routes:
                            bucket.update(
                                status="pending",
                                reason="Native mode not selected"
                                if not args.live_agent
                                else "Explicit supported provider authentication unavailable",
                            )
                            continue
                        for phase in phases:
                            result = command_json(
                                [
                                    "docker",
                                    "exec",
                                    container,
                                    "/opt/runtime/bin/python",
                                    "/opt/proof/container_launch_acceptance.py",
                                    "--inside",
                                    "native",
                                    "--provider",
                                    provider,
                                    "--phase",
                                    phase,
                                    "--timeout",
                                    str(args.timeout),
                                    "--auth-source",
                                    routes[provider],
                                ],
                                timeout=args.timeout + 60,
                                allow_failure=True,
                            )
                            bucket["native"].append(result)
                            bucket["status"] = (
                                "passed"
                                if all(r["status"] == "passed" for r in bucket["native"])
                                else "partial"
                            )
                    checkpoint_state_result = command_json(
                        [
                            "docker",
                            "exec",
                            container,
                            "/opt/runtime/bin/python",
                            "/opt/proof/container_launch_acceptance.py",
                            "--inside",
                            "checkpoint",
                        ]
                    )
                    report.setdefault("state_checkpoints", []).append(checkpoint_state_result)
                finally:
                    report.setdefault("evidence_exports", []).extend(
                        export_evidence(container, output)
                    )
                    subprocess.run(
                        ["docker", "rm", "--force", container], capture_output=True, check=False
                    )
            report["persistence"] = {
                "recreated_container": report["preparation"][0]["container_hostname"]
                != report["preparation"][1]["container_hostname"],
                "same_volume": True,
                "repeat_bind": "passed",
            }
            report["status"] = (
                "passed"
                if all(p.get("status") == "passed" for p in report["providers"].values())
                else "partial"
            )
        except Exception as error:
            report.update(status="failed", reason=_redact(str(error)))
        finally:
            if not args.keep:
                subprocess.run(["docker", "volume", "rm", volume], capture_output=True, check=False)
                subprocess.run(["docker", "image", "rm", image], capture_output=True, check=False)
            report["fixture_retained"] = args.keep
            write_json(output / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--providers", default=",".join(PROVIDERS))
    parser.add_argument("--live-agent", action="store_true")
    parser.add_argument("--auth-env", action="append", default=[], metavar="PROVIDER:VARIABLE")
    parser.add_argument(
        "--docker-seccomp-profile",
        type=Path,
        help="Explicit operator-approved syscall policy for this disposable fixture only.",
    )
    parser.add_argument(
        "--keep", action="store_true", help="Retain disposable image and volume for diagnosis."
    )
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--inside", choices=("prepare", "native", "checkpoint"), help=argparse.SUPPRESS
    )
    parser.add_argument("--provider", choices=PROVIDERS, help=argparse.SUPPRESS)
    parser.add_argument("--auth-source", help=argparse.SUPPRESS)
    parser.add_argument("--phase", choices=("fresh", "reused", "recreated"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside == "prepare":
        result = prepare()
    elif args.inside == "checkpoint":
        result = checkpoint_state()
    elif args.inside == "native":
        result = native(args.provider, args.phase, args.timeout, args.auth_source)
    else:
        if args.output is None or not set(args.providers.split(",")) <= set(PROVIDERS):
            parser.error("--output and supported --providers are required")
        result = host(args)
    print(json.dumps(result, sort_keys=True))
    return 1 if result.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
