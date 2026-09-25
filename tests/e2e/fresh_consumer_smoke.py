#!/usr/bin/env python3
"""Build and exercise a fresh APM consumer without ambient workspace state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from provider_hook_smoke import _context_channels, _fixtures, run_provider_hook_smoke

_PACKAGE_HOOK_SOURCE = "_local/knowledge-agent-pack"
_DESCRIPTOR_HOOK_COMMAND = "agent-knowledge-hook"


class SmokeFailure(RuntimeError):
    """Describe one failed consumer assertion or external command."""

    def __init__(self, message: str, *, log: Path | None = None) -> None:
        super().__init__(message)
        self.log = log


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and verify an isolated agent-knowledge APM consumer."
    )
    parser.add_argument("--output", type=Path, help="Write the JSON evidence report to this path.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary consumer and logs.")
    parser.add_argument(
        "--python",
        default="cpython>=3.11",
        help="Installed CPython request or path (default: any installed CPython 3.11+).",
    )
    parser.add_argument(
        "--live-cli",
        action="store_true",
        help="Run no-auth --version and --help checks for available harness CLIs.",
    )
    return parser


def _repo_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    if not (root / "pyproject.toml").is_file():
        raise SmokeFailure(f"Could not locate repository root from {__file__}.")
    return root


def _command(name: str) -> Path:
    resolved = shutil.which(name)
    if not resolved:
        raise SmokeFailure(f"Required command is unavailable: {name}")
    return Path(resolved).resolve()


def _git_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _yaml_string(value: str) -> str:
    """Quote a path for the small YAML files authored by this test."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _clean_environment(*, home: Path, xdg_config: Path, path_entries: list[Path]) -> dict[str, str]:
    unique: list[str] = []
    for entry in path_entries:
        text = str(entry)
        if text not in unique:
            unique.append(text)
    unique.extend(part for part in ("/usr/bin", "/bin", "/usr/sbin", "/sbin") if part not in unique)
    return {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(xdg_config),
        "PATH": os.pathsep.join(unique),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    logs: Path,
    label: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    log = logs / f"{label}.log"
    log.write_text(
        "COMMAND: "
        + " ".join(command)
        + "\nEXIT: "
        + str(result.returncode)
        + "\n\nSTDOUT:\n"
        + result.stdout
        + "\nSTDERR:\n"
        + result.stderr,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise SmokeFailure(f"Command failed ({result.returncode}): {' '.join(command)}", log=log)
    return result


def _run_json(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    logs: Path,
    label: str,
    expected_exit: int = 0,
) -> dict[str, Any]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    log = logs / f"{label}.log"
    log.write_text(
        "COMMAND: "
        + " ".join(command)
        + "\nEXIT: "
        + str(result.returncode)
        + "\n\nSTDOUT:\n"
        + result.stdout
        + "\nSTDERR:\n"
        + result.stderr,
        encoding="utf-8",
    )
    if result.returncode != expected_exit:
        raise SmokeFailure(
            f"Command failed ({result.returncode}, expected {expected_exit}): {' '.join(command)}",
            log=log,
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SmokeFailure(f"Command did not return JSON: {' '.join(command)}", log=log) from error
    if not isinstance(value, dict):
        raise SmokeFailure(
            f"Command returned a non-object JSON value: {' '.join(command)}", log=log
        )
    return value


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def _commands(value: object) -> list[str]:
    """Collect command strings from a provider hook document for ownership proof."""
    if isinstance(value, dict):
        commands: list[str] = []
        command = value.get("command")
        if isinstance(command, str):
            commands.append(command)
        for child in value.values():
            commands.extend(_commands(child))
        return commands
    if isinstance(value, list):
        commands = []
        for child in value:
            commands.extend(_commands(child))
        return commands
    return []


def _event_groups(document: object, event: str) -> object:
    """Read a provider event from either flat or nested hook JSON."""
    if not isinstance(document, dict):
        return None
    hooks = document.get("hooks")
    if isinstance(hooks, dict):
        return hooks.get(event)
    return document.get(event)


def _provider_hook_files(consumer: Path) -> dict[str, Path]:
    return {
        "codex": consumer / ".codex" / "hooks.json",
        "claude": consumer / ".claude" / "settings.json",
        "copilot": consumer / ".github" / "hooks" / "hand-authored.json",
    }


def _portable_binding_proof(
    *,
    consumer: Path,
    bind_args: list[str],
    clean_env: dict[str, str],
    profile_settings: Path,
    runtime: Path,
    logs: Path,
) -> dict[str, str]:
    """Execute identical installed hooks using two local homes, registries and runtimes."""
    snapshot: dict[Path, bytes] | None = None
    request = logs / "portable-doctor.json"
    request.write_text('{"mode":"write"}\n')
    for index in range(2):
        home = logs.parent / f"portable-home-{index}"
        settings = home / ".config/agent-knowledge/config.yaml"
        settings.parent.mkdir(parents=True)
        credential = settings.parent / "example.env"
        canary = f"portable-environment-{index}-canary"
        credential.write_text(f"PROFILE_PROOF_TOKEN={canary}\n")
        credential.chmod(0o600)
        registry = json.loads(profile_settings.read_text())
        registry["profiles"]["example"]["environment"]["file"] = str(credential)
        settings.write_text(json.dumps(registry))
        venv = runtime if index == 0 else home / "runtime"
        env = {
            **clean_env,
            "HOME": str(home),
            "PATH": str(venv / "bin") + os.pathsep + clean_env["PATH"],
        }
        # The second environment uses explicit registry indirection as a container would.
        if index == 1:
            env["AGENT_KNOWLEDGE_SETTINGS"] = str(settings)
        args = list(bind_args)
        args[args.index("--settings") + 1] = str(settings)
        setup = _run_json(
            [*args, "--venv", str(venv), "--portable-hooks"],
            cwd=consumer,
            env=env,
            logs=logs,
            label=f"portable-bind-{index}",
        )
        paths = [
            consumer / "apm.lock.yaml",
            consumer / ".codex/apm-hooks.json",
            consumer / ".claude/apm-hooks.json",
            consumer
            / "apm_modules/_local/knowledge-agent-pack/.apm/hooks/knowledge-discovery.json",
            consumer / ".github/hooks/knowledge-agent-pack-knowledge-discovery.json",
            *_provider_hook_files(consumer).values(),
        ]
        current = {path: path.read_bytes() for path in paths}
        if snapshot is not None:
            _assert(current == snapshot, "Rebinding in another environment changed shared hooks.")
        snapshot = current
        for provider, registration in setup["hooks"]["registrations"].items():
            event = "sessionStart" if provider == "copilot" else "SessionStart"
            command = registration["commands"][event]
            _assert(
                command == f"agent-knowledge-hook --provider {provider} --profile example",
                "Portable hook contains machine-specific arguments.",
            )
            start, _, _, _ = _fixtures(provider)
            destination = home / "claude-session.env"
            result = subprocess.run(
                shlex.split(command),
                cwd=consumer,
                env={**env, "CLAUDE_ENV_FILE": str(destination)},
                input=json.dumps(start),
                text=True,
                capture_output=True,
                timeout=10,
            )
            _assert(result.returncode == 0, f"Portable {provider} hook failed.")
            value = json.loads(result.stdout)
            _assert(len(_context_channels(value)) == 1, "Portable hook lost its context channel.")
            _assert(canary not in result.stdout + result.stderr, "Hook exposed a credential.")
            if provider == "claude":
                _assert(
                    destination.is_file() and canary in destination.read_text(),
                    "Claude did not activate the environment-local credential.",
                )
                destination.unlink()
        doctor = _run_json(
            ["agent-knowledge", "--profile", "example", "doctor", "--request-file", str(request)],
            cwd=consumer,
            env=env,
            logs=logs,
            label=f"portable-doctor-{index}",
        )
        _assert(
            all(
                doctor["readiness"][name] == "ready"
                for name in ("read", "write", "receipts", "environment")
            ),
            "Portable environment did not pass write-mode doctor.",
        )
    return {"status": "passed", "environments": "2", "shared_hook_bytes": "unchanged"}


def _package_hook_groups(document: object, event: str) -> list[dict[str, Any]]:
    """Select only this package's APM-owned groups for one provider event."""
    groups = _event_groups(document, event)
    if not isinstance(groups, list):
        return []
    return [
        group
        for group in groups
        if isinstance(group, dict) and group.get("_apm_source") == _PACKAGE_HOOK_SOURCE
    ]


def _expected_hook_command(
    hook_launcher: Path | None,
    provider: str,
    event_name: str,
    environment: dict[str, Any] | None,
) -> str:
    """Use the portable descriptor only before setup has installed a runtime."""
    if hook_launcher is None:
        return _DESCRIPTOR_HOOK_COMMAND
    arguments = [str(hook_launcher.resolve()), "--provider", provider]
    if (
        provider == "claude"
        and event_name == "SessionStart"
        and isinstance(environment, dict)
        and environment.get("status") == "ready"
    ):
        file_value = environment.get("environment_file")
        state_directory = environment.get("session_state_directory")
        variables = environment.get("variables")
        _assert(isinstance(file_value, str), "Environment report omitted its file.")
        _assert(
            isinstance(state_directory, str),
            "Environment report omitted its session state directory.",
        )
        _assert(isinstance(variables, list) and variables, "Environment report omitted mappings.")
        arguments.extend(
            (
                "--environment-file",
                file_value,
                "--environment-state-directory",
                state_directory,
            )
        )
        for variable in variables:
            _assert(isinstance(variable, dict), "Environment report contains an invalid mapping.")
            source = variable.get("from_env")
            target = variable.get("expose_as")
            _assert(
                isinstance(source, str) and isinstance(target, str),
                "Environment report contains an invalid mapping.",
            )
            arguments.extend(("--environment-map", f"{source}={target}"))
    return shlex.join(arguments)


def _hook_registration_proof(
    consumer: Path,
    *,
    copilot_authored: bytes,
    package_present: bool,
    hook_launcher: Path | None = None,
    environment: dict[str, Any] | None = None,
) -> None:
    files = _provider_hook_files(consumer)
    runtime_documents: dict[str, object] = {}
    for provider, path in files.items():
        _assert(path.is_file(), f"Hand-authored {provider} hook configuration is missing.")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SmokeFailure(
                f"Hand-authored {provider} hook configuration is invalid."
            ) from error
        runtime_documents[provider] = document
        commands = _commands(document)
        _assert(
            any(command == f"hand-authored-{provider}" for command in commands),
            f"APM did not preserve the hand-authored {provider} hook.",
        )
    _assert(
        files["copilot"].read_bytes() == copilot_authored,
        "APM modified the unrelated Copilot hook file.",
    )

    package_files = {
        "codex": consumer / ".codex" / "apm-hooks.json",
        "claude": consumer / ".claude" / "apm-hooks.json",
        "copilot": consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json",
    }
    if hook_launcher is not None:
        _assert(package_present, "A managed hook launcher requires an installed package.")
    for provider, path in package_files.items():
        if provider == "copilot":
            present = path.is_file()
            _assert(
                present is package_present,
                f"Unexpected package-owned Copilot hook file state: {present}.",
            )
            if present:
                document = json.loads(path.read_text(encoding="utf-8"))
                hooks = document.get("hooks") if isinstance(document, dict) else None
                _assert(isinstance(hooks, dict), "Copilot package hook has no hooks object.")
                expected_events = (
                    {"sessionStart", "userPromptSubmit"}
                    if hook_launcher is None
                    else {"sessionStart", "userPromptTransformed"}
                )
                _assert(
                    set(hooks) == expected_events,
                    "Copilot package hook has unsupported or missing events.",
                )
                for event_name in expected_events:
                    commands = _commands(hooks[event_name])
                    expected_command = _expected_hook_command(
                        hook_launcher, provider, event_name, environment
                    )
                    _assert(
                        commands == [expected_command],
                        f"Copilot {event_name} hook does not use the exact expected launcher.",
                    )
            continue
        present = path.is_file()
        _assert(
            present is package_present,
            f"Unexpected package-owned {provider} hook sidecar state: {present}.",
        )
        events = ("SessionStart", "UserPromptSubmit")
        if present:
            document = json.loads(path.read_text(encoding="utf-8"))
            groups_by_event = {event: _package_hook_groups(document, event) for event in events}
            _assert(
                all(len(groups) == 1 for groups in groups_by_event.values()),
                f"Unexpected package-owned {provider} hook state.",
            )
            _assert(
                all(
                    _commands(groups[0].get("hooks"))
                    == [_expected_hook_command(hook_launcher, provider, event_name, environment)]
                    for event_name, groups in groups_by_event.items()
                ),
                f"Package-owned {provider} hook does not use the exact expected launcher.",
            )
        runtime_document = runtime_documents[provider]
        expected_runtime_count = 1 if package_present else 0
        for event_name in events:
            expected_command = _expected_hook_command(
                hook_launcher, provider, event_name, environment
            )
            runtime_commands = _commands(_event_groups(runtime_document, event_name))
            _assert(
                runtime_commands.count(expected_command) == expected_runtime_count,
                f"Unexpected merged {provider} {event_name} package command state.",
            )
            if hook_launcher is not None:
                _assert(
                    _DESCRIPTOR_HOOK_COMMAND not in runtime_commands,
                    f"Merged {provider} {event_name} hook retained the descriptor marker.",
                )
        _assert(
            all("knowledge_discovery.py" not in command for command in _commands(document)),
            f"Retired hook shim remains registered for {provider}.",
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_consumer_files(root: Path, consumer: Path, package_root: Path) -> Path:
    consumer.mkdir(parents=True)
    shutil.copytree(root / "examples" / "knowledge", consumer / "knowledge")
    shutil.copy2(root / "examples" / "catalog.yaml", consumer / "catalog.yaml")
    (consumer / "knowledge-workspace.yaml").write_text(
        "\n".join(
            [
                "schema_version: knowledge-workspace.v1",
                "workspace_id: workspace:fresh-consumer",
                "applicable_scopes: [org:example, group:commerce, repo:orders-api]",
                "sources:",
                "  - id: example-knowledge",
                "    root: knowledge",
                "    catalog: catalog.yaml",
                "signal_storage:",
                "  scaffold_root: .",
                "  code_root: ..",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest = "\n".join(
        [
            "name: fresh-agent-knowledge-consumer",
            "version: 0.0.1",
            "description: Isolated consumer used by the neutral package contract.",
            "targets:",
            "  - codex",
            "  - claude",
            "  - copilot",
            "dependencies:",
            "  apm:",
            f"    - {_yaml_string(str(package_root))}",
            "",
        ]
    )
    (consumer / "apm.yml").write_text(manifest, encoding="utf-8")
    (consumer / ".codex").mkdir()
    (consumer / ".codex" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "hand-authored-codex",
                                    "timeout": 1,
                                }
                            ]
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "hand-authored-codex-stop",
                                    "timeout": 1,
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    (consumer / ".claude").mkdir()
    (consumer / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "startup",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "hand-authored-claude",
                                    "timeout": 1,
                                }
                            ],
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "hand-authored-claude-stop",
                                    "timeout": 1,
                                }
                            ]
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    copilot_hooks = consumer / ".github" / "hooks"
    copilot_hooks.mkdir(parents=True)
    (copilot_hooks / "hand-authored.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "sessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "hand-authored-copilot",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    return consumer / "knowledge-workspace.yaml"


def _write_signal(consumer: Path, *, session_id: str) -> Path:
    authored = consumer / "observation.md"
    authored.write_text(
        "\n".join(
            [
                "---",
                "schema_version: knowledge-signal.v1",
                "id: fresh-consumer-observation",
                "created_at: 2026-09-10T09:00:00Z",
                "kind_hint: limitation",
                "origin:",
                "  workspace_id: workspace:fresh-consumer",
                "  project_path: consumer",
                "  applicable_scopes: [org:example, group:commerce, repo:orders-api]",
                "  source_ids: [example-knowledge]",
                "  harness: codex",
                f"  session_id: {session_id}",
                "  automation_id: smoke-automation",
                "evidence:",
                "  - type: file",
                "    reference: consumer/docs/observation.md",
                "---",
                "",
                "# Preserve the observation",
                "",
                "The smoke run must retain origin provenance and drain only after disposition.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return authored


def _resource_proof(root: Path, describe: dict[str, Any], venv: Path) -> dict[str, Any]:
    _assert(describe.get("status") == "ok", "Installed describe did not succeed.")
    _assert(
        set(describe.get("kinds", []))
        == {
            "concept",
            "feature",
            "workflow",
            "system",
            "guidance",
            "runbook",
            "limitation",
            "incident",
        },
        "Installed describe does not expose the eight supported knowledge kinds.",
    )
    resources = describe.get("resources")
    _assert(isinstance(resources, dict), "Installed describe omitted resource metadata.")
    _assert(resources.get("status") == "ready", "Installed resources are not ready.")
    guide_value = resources.get("guide")
    templates_value = resources.get("templates")
    _assert(isinstance(guide_value, str), "Installed describe did not report a guide path.")
    _assert(isinstance(templates_value, list), "Installed describe did not report templates.")
    _assert(
        {Path(value).name for value in templates_value}
        == {
            "concept.md",
            "feature.md",
            "workflow.md",
            "system.md",
            "guidance.md",
            "runbook-procedure.md",
            "runbook-service.md",
            "limitation.md",
            "incident.md",
            "signal.md",
        },
        "Installed templates do not match the supported authoring contract.",
    )

    guide = Path(guide_value).resolve()
    expected_guide = (root / "docs" / "agent-contract.md").resolve()
    venv_root = venv.resolve()
    repository_root = root.resolve()
    _assert(guide.is_file(), f"Installed guide is missing: {guide}")
    _assert(
        guide.read_bytes() == expected_guide.read_bytes(),
        "Installed guide differs from source guide.",
    )
    _assert(
        guide.is_relative_to(venv_root), "Installed guide escaped the isolated Python environment."
    )
    _assert(
        not guide.is_relative_to(repository_root),
        "Installed guide fell back to a repository source path.",
    )

    source_templates_root = root / "src" / "agent_knowledge" / "resources" / "templates"
    source_templates = sorted(source_templates_root.rglob("*.md"))
    installed_templates = [
        Path(value).resolve() for value in templates_value if isinstance(value, str)
    ]
    _assert(
        len(installed_templates) == len(source_templates),
        "Installed template count differs from source.",
    )
    source_by_relative = {
        path.relative_to(source_templates_root): path for path in source_templates
    }
    template_checks: list[str] = []
    for installed in installed_templates:
        _assert(installed.is_file(), f"Installed template is missing: {installed}")
        _assert(
            installed.is_relative_to(venv_root), f"Installed template escaped the venv: {installed}"
        )
        _assert(
            not installed.is_relative_to(repository_root),
            f"Installed template fell back to source: {installed}",
        )
        try:
            marker = installed.parts.index("templates")
            relative = Path(*installed.parts[marker + 1 :])
        except (ValueError, IndexError):
            relative = Path(installed.name)
        source = source_by_relative.get(relative)
        if source is None:
            for candidate in source_templates:
                if (
                    candidate.name == installed.name
                    and candidate.read_bytes() == installed.read_bytes()
                ):
                    source = candidate
                    break
        _assert(source is not None, f"Could not map installed template: {installed}")
        _assert(
            source.read_bytes() == installed.read_bytes(), f"Template content differs: {installed}"
        )
        template_checks.append(str(installed))
    return {
        "guide": str(guide),
        "guide_sha256": _sha256(guide),
        "templates": template_checks,
    }


def _generated_projection_proof(root: Path, consumer: Path, instruction: Path) -> list[str]:
    installed = consumer / ".github" / "instructions" / instruction.name
    _assert(installed.is_file(), f"Installed instruction is missing: {installed}")
    _assert(
        installed.read_bytes() == instruction.read_bytes(),
        "Installed instruction differs from source.",
    )
    generated = [
        consumer / "AGENTS.md",
        consumer / "CLAUDE.md",
        consumer / ".github" / "copilot-instructions.md",
    ]
    for path in generated:
        _assert(path.is_file(), f"Compiled harness file is missing: {path}")
        body = path.read_text(encoding="utf-8")
        _assert("agent-knowledge" in body, f"Compiled file does not bind the CLI: {path}")
        _assert(
            "agent-knowledge describe" in body, f"Compiled file omits launcher discovery: {path}"
        )
        _assert(
            str(root) not in body, f"Compiled instruction leaked a source checkout path: {path}"
        )
    claude_name = instruction.name.removesuffix(".instructions.md") + ".md"
    claude_rule = consumer / ".claude" / "rules" / claude_name
    _assert(claude_rule.is_file(), f"Claude rule projection is missing: {claude_rule}")
    return [str(path) for path in generated] + [str(installed), str(claude_rule)]


def _live_cli_checks(env: dict[str, str], logs: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for name in ("codex", "claude", "copilot"):
        path = shutil.which(name)
        if path is None:
            checks.append({"name": name, "available": False, "reason": "not installed"})
            continue
        version_result = _run(
            [path, "--version"],
            cwd=logs.parent,
            env=env,
            logs=logs,
            label=f"{name}-version",
        )
        help_result = _run(
            [path, "--help"],
            cwd=logs.parent,
            env=env,
            logs=logs,
            label=f"{name}-help",
        )
        version_lines = (version_result.stdout or version_result.stderr).strip().splitlines()
        help_lines = (help_result.stdout or help_result.stderr).strip().splitlines()
        checks.append(
            {
                "name": name,
                "available": True,
                "path": path,
                "version": version_lines[0] if version_lines else "",
                "startup": "ok",
                "help_summary": help_lines[0] if help_lines else "",
            }
        )
    return checks


def run_smoke(*, keep: bool, live_cli: bool, python_request: str) -> dict[str, Any]:
    root = _repo_root()
    apm = _command("apm")
    uv = _command("uv")
    git = _command("git")
    python = _command("python3")
    package_root = root / "packages" / "knowledge-agent-pack"
    instruction = (
        package_root / ".apm" / "instructions" / "agent-knowledge-discovery.instructions.md"
    )
    _assert((package_root / "apm.yml").is_file(), "Neutral APM package manifest is missing.")
    _assert(instruction.is_file(), "Neutral discovery instruction is missing.")

    temp_root = Path(tempfile.mkdtemp(prefix="agent-knowledge-fresh-consumer.")).resolve()
    logs = temp_root / "logs"
    logs.mkdir()
    home = temp_root / "home"
    xdg = temp_root / "xdg"
    home.mkdir()
    xdg.mkdir()
    dist = temp_root / "dist"
    venv = temp_root / "venv"
    consumer = temp_root / "consumer"
    prerequisite_bin = temp_root / "prerequisite-bin"
    prerequisite_bin.mkdir()
    path_entries = [prerequisite_bin, apm.parent, uv.parent, git.parent]
    # Copilot is distributed as a Node launcher.  Keep the interpreter on the
    # deliberately minimal PATH so a version check exercises the installed
    # CLI rather than failing before the CLI starts.
    node = shutil.which("node")
    if node:
        path_entries.append(Path(node).resolve().parent)
    for name in ("codex", "claude", "copilot"):
        found = shutil.which(name)
        if found:
            path_entries.append(Path(found).resolve().parent)
    clean_env = _clean_environment(
        home=home,
        xdg_config=xdg,
        path_entries=path_entries,
    )

    try:
        workspace_config = _write_consumer_files(root, consumer, package_root)
        copilot_authored_hook = _provider_hook_files(consumer)["copilot"].read_bytes()
        _run([str(git), "init", "-q"], cwd=consumer, env=clean_env, logs=logs, label="git-init")
        (consumer / "ai" / "signals").mkdir(parents=True)
        _run(
            [str(uv), "build", "--out-dir", str(dist)],
            cwd=root,
            env=os.environ.copy(),
            logs=logs,
            label="build",
        )
        wheels = sorted(dist.glob("*.whl"))
        _assert(len(wheels) == 1, f"Expected one wheel in {dist}, found {len(wheels)}.")
        wheel = wheels[0]
        _run(
            [str(uv), "venv", "--python", python_request, "--no-python-downloads", str(venv)],
            cwd=root,
            env=os.environ.copy(),
            logs=logs,
            label="venv",
        )
        python_in_venv = venv / "bin" / "python"
        launcher = venv / "bin" / "agent-knowledge"
        _run(
            [str(uv), "pip", "install", "--python", str(python_in_venv), str(wheel)],
            cwd=root,
            env=os.environ.copy(),
            logs=logs,
            label="install-wheel",
        )
        prerequisite_python = python_in_venv.resolve()
        _assert(
            prerequisite_python.is_file(),
            "Outer wheel-test virtual environment did not expose a Python interpreter.",
        )
        _assert(
            not prerequisite_python.is_relative_to(venv.resolve()),
            "Fresh consumer prerequisite Python must resolve outside "
            "the outer wheel-test environment.",
        )
        prerequisite_check = _run(
            [
                str(prerequisite_python),
                "-c",
                "import sys; "
                "print(f'{sys.implementation.name} "
                "{sys.version_info.major}.{sys.version_info.minor}')",
            ],
            cwd=root,
            env=os.environ.copy(),
            logs=logs,
            label="verify-prerequisite-python",
        )
        implementation, version_text = prerequisite_check.stdout.strip().split()
        prerequisite_version = tuple(int(part) for part in version_text.split("."))
        _assert(
            implementation == "cpython" and prerequisite_version >= (3, 11),
            "Outer wheel-test environment did not resolve to CPython 3.11 or newer.",
        )
        prerequisite_entry = prerequisite_bin / "python3"
        prerequisite_entry.symlink_to(prerequisite_python)
        _assert(
            prerequisite_entry.resolve() == prerequisite_python,
            "Fresh consumer prerequisite Python did not preserve its verified interpreter path.",
        )
        _assert(
            [entry.name for entry in prerequisite_bin.iterdir()] == ["python3"],
            "Fresh consumer prerequisite directory exposed more than the selected Python.",
        )
        _assert(
            not (prerequisite_bin / _DESCRIPTOR_HOOK_COMMAND).exists(),
            "Fresh consumer prerequisite directory exposed an ambient hook launcher.",
        )
        _assert(
            str(venv / "bin") not in clean_env["PATH"].split(os.pathsep),
            "Fresh consumer must not resolve hooks from the outer wheel-test environment.",
        )
        _run(
            [
                str(apm),
                "install",
                "--refresh",
                "--no-policy",
                "--target",
                "codex,claude,copilot",
            ],
            cwd=consumer,
            env=clean_env,
            logs=logs,
            label="apm-install",
        )
        _run(
            [str(apm), "compile", "--target", "codex,claude,copilot", "--force-instructions"],
            cwd=consumer,
            env=clean_env,
            logs=logs,
            label="apm-compile",
        )
        _run(
            [str(apm), "audit", "--ci"],
            cwd=consumer,
            env=clean_env,
            logs=logs,
            label="apm-audit",
        )
        _hook_registration_proof(
            consumer,
            copilot_authored=copilot_authored_hook,
            package_present=True,
        )

        projection_paths = _generated_projection_proof(root, consumer, instruction)
        modules = consumer / "apm_modules"
        _assert(
            (modules / "_local" / package_root.name).is_dir(),
            "Neutral APM package was not installed.",
        )
        _assert(
            {path.name for path in (modules / "_local").iterdir() if path.is_dir()}
            == {package_root.name},
            "Unexpected APM package was installed.",
        )
        installed_package = modules / "_local" / package_root.name
        for skill in ("knowledge-setup", "knowledge-compound"):
            _assert(
                (installed_package / ".apm" / "skills" / skill / "SKILL.md").is_file(),
                f"Installed skill is missing: {skill}",
            )
            source_skill = package_root / ".apm" / "skills" / skill
            for authored in source_skill.rglob("*.md"):
                relative = authored.relative_to(source_skill)
                for deployed_root in (
                    installed_package / ".apm" / "skills",
                    consumer / ".agents" / "skills",
                    consumer / ".claude" / "skills",
                ):
                    deployed = deployed_root / skill / relative
                    _assert(
                        deployed.is_file() and deployed.read_bytes() == authored.read_bytes(),
                        f"Installed skill resource differs from its source: {deployed}",
                    )
        _assert(
            (
                installed_package
                / ".apm"
                / "skills"
                / "knowledge-setup"
                / "scripts"
                / "setup_runtime.py"
            ).is_file(),
            "Installed setup helper is missing.",
        )
        _assert(
            not (installed_package / ".apm" / "hooks" / "scripts").exists(),
            "The installed package still contains a standalone hook shim.",
        )

        describe = _run_json(
            [str(launcher), "describe"],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="describe",
        )
        resources = _resource_proof(root, describe, venv)
        doctor = _run_json(
            [str(launcher), "--config", str(workspace_config), "doctor"],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="doctor",
        )
        _assert(doctor.get("status") == "ok", "Installed doctor did not report success.")
        _assert(
            isinstance(doctor.get("readiness"), dict)
            and doctor["readiness"].get("read") == "ready",
            "Installed doctor did not report read readiness.",
        )
        context = _run_json(
            [str(launcher), "--config", str(workspace_config), "context"],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="context",
        )
        _assert(
            context.get("workspace_id") == "workspace:fresh-consumer",
            "Installed context used the wrong workspace.",
        )
        request = consumer / "search.yaml"
        request.write_text(
            "\n".join(
                [
                    "kind: [feature, workflow]",
                    "text:",
                    "  any: [order history]",
                    "limit: 10",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        search = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "search",
                "--request-file",
                str(request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="search",
        )
        _assert(search.get("status") == "ok", "Installed search did not report success.")
        _assert(int(search.get("returned", 0)) > 0, "Installed search returned no fixture matches.")

        setup_script = (
            package_root / ".apm" / "skills" / "knowledge-setup" / "scripts" / "setup_runtime.py"
        )
        profile_settings = home / ".config/agent-knowledge/config.yaml"
        work_profile_settings = home / ".config/agent-knowledge/work-config.yaml"
        profile_settings.parent.mkdir(parents=True)
        profile_canary = "fresh-profile-environment-canary"
        work_profile_canary = "fresh-work-profile-environment-canary"
        profile_environment = profile_settings.parent / "example.env"
        work_profile_environment = profile_settings.parent / "work.env"
        profile_environment.write_text(f"PROFILE_PROOF_TOKEN={profile_canary}\n", encoding="utf-8")
        work_profile_environment.write_text(
            f"WORK_PROFILE_PROOF_TOKEN={work_profile_canary}\n", encoding="utf-8"
        )
        profile_environment.chmod(0o600)
        work_profile_environment.chmod(0o600)
        profile_settings.write_text(
            json.dumps(
                {
                    "schema_version": "knowledge-profiles.v1",
                    "default_profile": "example",
                    "profiles": {
                        "example": {
                            "config": str(workspace_config),
                            "overrides": {"receipts": {"retention_days": 60}},
                            "environment": {
                                "file": str(profile_environment),
                                "variables": {
                                    "proof-token": {
                                        "from_env": "PROFILE_PROOF_TOKEN",
                                        "expose_as": "AGENT_KNOWLEDGE_PROOF_TOKEN",
                                        "description": "Disposable installed-consumer proof",
                                    }
                                },
                            },
                        },
                        "work": {
                            "config": str(workspace_config),
                            "environment": {
                                "file": str(work_profile_environment),
                                "variables": {
                                    "proof-token": {
                                        "from_env": "WORK_PROFILE_PROOF_TOKEN",
                                        "expose_as": "AGENT_KNOWLEDGE_WORK_PROOF_TOKEN",
                                        "description": "Alternate disposable installed proof",
                                    }
                                },
                            },
                        },
                    },
                }
            )
        )
        work_profile_settings.write_text(
            json.dumps(
                {
                    "schema_version": "knowledge-profiles.v1",
                    "default_profile": "work",
                    "profiles": {
                        "work": {
                            "config": str(workspace_config),
                            "environment": {
                                "file": str(work_profile_environment),
                                "variables": {
                                    "proof-token": {
                                        "from_env": "WORK_PROFILE_PROOF_TOKEN",
                                        "expose_as": "AGENT_KNOWLEDGE_WORK_PROOF_TOKEN",
                                        "description": "Alternate disposable installed proof",
                                    }
                                },
                            },
                        }
                    },
                }
            )
        )
        setup_args = [
            str(python),
            str(setup_script),
            "--workspace",
            str(workspace_config),
            "--package",
            str(wheel),
            "--consumer",
            str(consumer),
            "--settings",
            str(profile_settings),
            "--profile",
            "example",
        ]
        setup = _run_json(
            setup_args,
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="setup-runtime",
        )
        _assert(setup.get("status") == "ok", "Setup helper did not report success.")
        _assert(setup["selection"]["profile"] == "example", "Setup lost profile selection.")
        _assert(
            setup["configuration"]["values"]["receipts"]["retention_days"] == 60,
            "Setup lost effective overrides.",
        )
        _assert(
            setup.get("venv") == str((consumer / ".agent-knowledge-venv").resolve()),
            "Setup helper did not derive the scaffold-local virtual environment.",
        )
        _assert(
            (Path(setup["venv"]) / "bin" / "python").resolve() == prerequisite_python,
            "Setup did not use the selected installed prerequisite interpreter.",
        )
        _assert(
            setup.get("targets") == ["codex", "claude", "copilot"],
            "Setup helper did not target all supported APM harnesses by default.",
        )
        expected_doctor_command = shlex.join(
            [
                str(setup["launcher"]),
                "--settings",
                str(profile_settings),
                "--profile",
                "example",
                "doctor",
            ]
        )
        _assert(
            setup.get("doctor", {}).get("command") == expected_doctor_command,
            "Setup helper did not report the exact profile-aware doctor remediation.",
        )
        _assert(
            any(
                item.get("name") == "venv" and item.get("status") == "ok"
                for item in setup.get("steps", [])
                if isinstance(item, dict)
            ),
            "Setup helper did not create the requested virtual environment.",
        )
        _assert(
            isinstance(setup.get("hooks"), dict)
            and setup["hooks"].get("status") == "ready"
            and setup["hooks"].get("targets") == ["codex", "claude", "copilot"],
            "Setup helper did not verify all package-owned hook registrations.",
        )
        environment_report = setup.get("environment")
        _assert(
            isinstance(environment_report, dict)
            and environment_report.get("status") == "ready"
            and isinstance(environment_report.get("launcher"), str),
            "Setup helper did not prepare the selected profile environment.",
        )
        environment_launcher = Path(str(environment_report["launcher"])).resolve()
        _assert(environment_launcher.is_file(), "Setup environment launcher is missing.")
        _assert(
            profile_canary not in json.dumps(setup)
            and work_profile_canary not in json.dumps(setup)
            and profile_canary not in environment_launcher.read_text(encoding="utf-8")
            and work_profile_canary not in environment_launcher.read_text(encoding="utf-8"),
            "Setup report or generated launcher exposed a credential value.",
        )
        provider_bin = temp_root / "profile-provider-bin"
        provider_bin.mkdir()
        provider_codex = provider_bin / "codex"
        quoted_work_canary = shlex.quote(work_profile_canary)
        provider_codex.write_text(
            "#!/bin/sh\n"
            f'if [ "${{AGENT_KNOWLEDGE_PROOF_TOKEN-}}" = {shlex.quote(profile_canary)} ] '
            '&& [ -z "${AGENT_KNOWLEDGE_WORK_PROOF_TOKEN-}" ]; then\n'
            "  printf PERSONAL_ENVIRONMENT_PRESENT\n"
            f'elif [ "${{AGENT_KNOWLEDGE_WORK_PROOF_TOKEN-}}" = {quoted_work_canary} ] '
            '&& [ -z "${AGENT_KNOWLEDGE_PROOF_TOKEN-}" ]; then\n'
            "  printf WORK_ENVIRONMENT_PRESENT\n"
            "else\n"
            "  exit 2\n"
            "fi\n",
            encoding="utf-8",
        )
        provider_codex.chmod(0o700)
        provider_copilot = provider_bin / "copilot"
        provider_copilot.write_text(
            "#!/bin/sh\n"
            'test "$1" = --bash-env=on\n'
            'test "$2" = --secret-env-vars=_AK_COPILOT_VALUE_0\n'
            f'test "$_AK_COPILOT_VALUE_0" = {shlex.quote(profile_canary)}\n'
            'test -z "${AGENT_KNOWLEDGE_PROOF_TOKEN-}"\n'
            "unset _AK_COPILOT_VALUE_0\n"
            "exec /bin/bash -c "
            + shlex.quote(
                f'test "$AGENT_KNOWLEDGE_PROOF_TOKEN" = {shlex.quote(profile_canary)}; '
                'test -z "${_AK_COPILOT_VALUE_0-}"; '
                'test -z "${_AK_COPILOT_BASH_ENV-}"; '
                'test -z "${BASH_ENV-}"; '
                "printf COPILOT_ENVIRONMENT_PRESENT"
            )
            + "\n",
            encoding="utf-8",
        )
        provider_copilot.chmod(0o700)
        provider_environment = {
            **clean_env,
            "PATH": os.pathsep.join((str(provider_bin), clean_env["PATH"])),
        }
        positive = subprocess.run(
            [str(environment_launcher), "codex"],
            cwd=temp_root,
            env=provider_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(
            positive.returncode == 0 and positive.stdout == "PERSONAL_ENVIRONMENT_PRESENT",
            "Generated launcher did not expose only the selected mapped target.",
        )
        copilot_command = environment_report.get("providers", {}).get("copilot", {}).get("command")
        _assert(isinstance(copilot_command, str), "Setup reported no Copilot launch command.")
        copilot_positive = subprocess.run(
            shlex.split(copilot_command),
            cwd=temp_root,
            env=provider_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(
            copilot_positive.returncode == 0
            and copilot_positive.stdout == "COPILOT_ENVIRONMENT_PRESENT",
            "Generated Copilot launcher did not restore its redacted shell target.",
        )
        repeated_setup = _run_json(
            setup_args,
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="setup-runtime-repeat",
        )
        _assert(
            any(
                item.get("name") == "venv" and item.get("status") == "reused"
                for item in repeated_setup.get("steps", [])
                if isinstance(item, dict)
            ),
            "Setup helper did not reuse a complete virtual environment.",
        )
        _assert(
            isinstance(repeated_setup.get("hooks"), dict)
            and repeated_setup["hooks"].get("status") == "ready",
            "Repeated setup did not verify package-owned hook registrations.",
        )
        setup_hook_launcher = Path(str(setup["hook_launcher"]))
        _hook_registration_proof(
            consumer,
            copilot_authored=copilot_authored_hook,
            package_present=True,
            hook_launcher=setup_hook_launcher,
            environment=environment_report,
        )
        claude_environment_file = temp_root / "claude-session-environment.sh"
        hook_result = subprocess.run(
            [
                str(setup_hook_launcher),
                "--provider",
                "claude",
                "--environment-file",
                str(profile_environment),
                "--environment-map",
                "PROFILE_PROOF_TOKEN=AGENT_KNOWLEDGE_PROOF_TOKEN",
                "--environment-state-directory",
                str(environment_report["session_state_directory"]),
            ],
            cwd=temp_root,
            env={**clean_env, "CLAUDE_ENV_FILE": str(claude_environment_file)},
            input=(
                '{"hook_event_name":"SessionStart","source":"startup",'
                '"session_id":"environment-proof"}'
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(hook_result.returncode == 0, "Claude environment hook did not fail open.")
        claude_environment_text = claude_environment_file.read_text(encoding="utf-8")
        claude_positive = subprocess.run(
            [
                "bash",
                "-c",
                f". {shlex.quote(str(claude_environment_file))}; "
                'test "$AGENT_KNOWLEDGE_PROOF_TOKEN" = "$1"',
                "environment-proof",
                profile_canary,
            ],
            cwd=temp_root,
            env=clean_env,
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(
            "export AGENT_KNOWLEDGE_PROOF_TOKEN=" in claude_environment_text
            and claude_positive.returncode == 0
            and profile_canary not in hook_result.stdout
            and profile_canary not in hook_result.stderr,
            "Claude environment hook did not use its native export channel safely.",
        )
        claude_environment_file.unlink()

        work_setup_args = [
            str(python),
            str(setup_script),
            "--workspace",
            str(workspace_config),
            "--package",
            str(wheel),
            "--consumer",
            str(consumer),
            "--settings",
            str(work_profile_settings),
            "--profile",
            "work",
        ]
        work_setup = _run_json(
            work_setup_args,
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="setup-runtime-work-profile",
        )
        work_environment_report = work_setup.get("environment")
        _assert(
            isinstance(work_environment_report, dict)
            and work_environment_report.get("status") == "ready"
            and isinstance(work_environment_report.get("launcher"), str),
            "Setup helper did not prepare the alternate profile environment.",
        )
        work_environment_launcher = Path(str(work_environment_report["launcher"])).resolve()
        _assert(
            work_environment_launcher.is_file()
            and work_environment_launcher != environment_launcher,
            "Separate profiles did not receive separate content-addressed launchers.",
        )
        _assert(
            work_environment_report.get("session_state_directory")
            == environment_report.get("session_state_directory"),
            "Changing registries retargeted the consumer's Claude session-pin namespace.",
        )
        _assert(
            profile_canary not in json.dumps(work_setup)
            and work_profile_canary not in json.dumps(work_setup)
            and profile_canary not in work_environment_launcher.read_text(encoding="utf-8")
            and work_profile_canary not in work_environment_launcher.read_text(encoding="utf-8"),
            "Alternate setup report or loader exposed a credential value.",
        )
        work_positive = subprocess.run(
            [str(work_environment_launcher), "codex"],
            cwd=temp_root,
            env=provider_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(
            work_positive.returncode == 0 and work_positive.stdout == "WORK_ENVIRONMENT_PRESENT",
            "Alternate launcher did not isolate its selected mapped target.",
        )
        _hook_registration_proof(
            consumer,
            copilot_authored=copilot_authored_hook,
            package_present=True,
            hook_launcher=setup_hook_launcher,
            environment=work_environment_report,
        )

        resumed_environment_file = temp_root / "claude-resumed-environment.sh"
        resumed_hook = subprocess.run(
            [
                str(setup_hook_launcher),
                "--provider",
                "claude",
                "--environment-file",
                str(work_profile_environment),
                "--environment-map",
                "WORK_PROFILE_PROOF_TOKEN=AGENT_KNOWLEDGE_WORK_PROOF_TOKEN",
                "--environment-state-directory",
                str(work_environment_report["session_state_directory"]),
            ],
            cwd=temp_root,
            env={**clean_env, "CLAUDE_ENV_FILE": str(resumed_environment_file)},
            input=(
                '{"hook_event_name":"SessionStart","source":"resume",'
                '"session_id":"environment-proof"}'
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        resumed_positive = subprocess.run(
            [
                "bash",
                "-c",
                f". {shlex.quote(str(resumed_environment_file))}; "
                'test "$AGENT_KNOWLEDGE_PROOF_TOKEN" = "$1"; '
                'test -z "$AGENT_KNOWLEDGE_WORK_PROOF_TOKEN"',
                "environment-resume-proof",
                profile_canary,
            ],
            cwd=temp_root,
            env=clean_env,
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(
            resumed_hook.returncode == 0
            and resumed_positive.returncode == 0
            and profile_canary not in resumed_hook.stdout
            and work_profile_canary not in resumed_hook.stdout
            and profile_canary not in resumed_hook.stderr
            and work_profile_canary not in resumed_hook.stderr,
            "A resumed Claude session did not retain its first profile declaration.",
        )
        resumed_environment_file.unlink()

        work_claude_environment_file = temp_root / "claude-work-environment.sh"
        work_hook = subprocess.run(
            [
                str(setup_hook_launcher),
                "--provider",
                "claude",
                "--environment-file",
                str(work_profile_environment),
                "--environment-map",
                "WORK_PROFILE_PROOF_TOKEN=AGENT_KNOWLEDGE_WORK_PROOF_TOKEN",
                "--environment-state-directory",
                str(work_environment_report["session_state_directory"]),
            ],
            cwd=temp_root,
            env={**clean_env, "CLAUDE_ENV_FILE": str(work_claude_environment_file)},
            input=(
                '{"hook_event_name":"SessionStart","source":"startup",'
                '"session_id":"work-environment-proof"}'
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        work_claude_positive = subprocess.run(
            [
                "bash",
                "-c",
                f". {shlex.quote(str(work_claude_environment_file))}; "
                'test "$AGENT_KNOWLEDGE_WORK_PROOF_TOKEN" = "$1"; '
                'test -z "$AGENT_KNOWLEDGE_PROOF_TOKEN"',
                "work-environment-proof",
                work_profile_canary,
            ],
            cwd=temp_root,
            env=clean_env,
            capture_output=True,
            text=True,
            check=False,
        )
        _assert(
            work_hook.returncode == 0
            and work_claude_positive.returncode == 0
            and profile_canary not in work_hook.stdout
            and work_profile_canary not in work_hook.stdout
            and profile_canary not in work_hook.stderr
            and work_profile_canary not in work_hook.stderr,
            "A new Claude session did not activate the newly bound profile.",
        )
        work_claude_environment_file.unlink()
        hook_smoke = run_provider_hook_smoke(
            consumer, setup_hook_launcher, logs=logs, env=clean_env
        )
        setup_launcher = Path(str(setup["launcher"]))
        setup_describe = _run_json(
            [str(setup_launcher), "describe"],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="setup-launcher-describe",
        )
        _assert(setup_describe.get("status") == "ok", "Setup launcher is not usable.")
        copilot_hook = (
            consumer / ".github" / "hooks" / ("knowledge-agent-pack-knowledge-discovery.json")
        )
        copilot_hash = "sha256:" + _sha256(copilot_hook)
        lock_text = (consumer / "apm.lock.yaml").read_text(encoding="utf-8")
        _assert(
            lock_text.count(copilot_hash) == 2,
            "Setup did not reconcile both APM Copilot lockfile hashes.",
        )

        codex_hook = hook_smoke.get("providers", {}).get("codex")
        session_id = codex_hook.get("session_id") if isinstance(codex_hook, dict) else None
        _assert(
            isinstance(session_id, str) and session_id,
            "Provider hook smoke did not expose a Codex session ID for signal provenance.",
        )
        authored = _write_signal(consumer, session_id=session_id)
        record_request = consumer / "signal-record.yaml"
        record_request.write_text("file: observation.md\n", encoding="utf-8")
        recorded = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "signal",
                "record",
                "--request-file",
                str(record_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="signal-record",
        )
        _assert(recorded.get("status") == "ok", "Signal capture failed.")
        stored_signal = Path(str(recorded["local_path"]))
        _assert(
            stored_signal.read_bytes() == authored.read_bytes(), "Signal bytes were not preserved."
        )
        list_request = consumer / "signal-list.yaml"
        list_request.write_text(
            f"include_shared: false\nsession_id: {session_id}\n", encoding="utf-8"
        )
        listed = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "signal",
                "list",
                "--request-file",
                str(list_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="signal-list",
        )
        _assert(int(listed.get("returned", 0)) == 1, "Captured signal was not listed.")
        selected = listed["results"][0]
        _assert(isinstance(selected, dict), "Signal list did not return a preview object.")
        _assert(
            selected.get("origin", {}).get("session_id") == session_id,
            "Session-filtered signal preview lost the exact hook session ID.",
        )
        _assert(
            "Preserve the observation" not in json.dumps(selected),
            "Signal list returned the claim body instead of a metadata preview.",
        )
        mismatch_request = consumer / "signal-list-mismatch.yaml"
        mismatch_request.write_text(
            "include_shared: false\nsession_id: not-the-codex-session\n", encoding="utf-8"
        )
        mismatch = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "signal",
                "list",
                "--request-file",
                str(mismatch_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="signal-list-mismatch",
        )
        _assert(
            mismatch.get("returned") == 0 and mismatch.get("results") == [],
            "Signal session filtering returned a nonmatching session.",
        )
        start_request = consumer / "compound-start.json"
        start_request.write_text(
            json.dumps(
                {
                    "action": "start",
                    "workspace_id": "workspace:fresh-consumer",
                    "harness": "codex",
                    "session_id": session_id,
                    "automation_id": "smoke-automation",
                    "selected": [
                        {
                            "id": selected["id"],
                            "path": selected["local_path"],
                            "fingerprint": selected["fingerprint"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        started = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "compound",
                "--request-file",
                str(start_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="compound-start",
        )
        run_id = str(started["run_id"])
        drain_request = consumer / "compound-drain.json"
        drain_request.write_text(
            json.dumps(
                {
                    "action": "drain",
                    "run_id": run_id,
                    "selected": [
                        {
                            "id": selected["id"],
                            "path": selected["local_path"],
                            "fingerprint": selected["fingerprint"],
                        }
                    ],
                    "dispositions": [
                        {
                            "signal_id": selected["id"],
                            "decision": "keep",
                            "rationale": "The smoke observation is already represented.",
                        }
                    ],
                    "publication_verified": False,
                }
            ),
            encoding="utf-8",
        )
        drained = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "compound",
                "--request-file",
                str(drain_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="compound-drain",
        )
        _assert(
            drained.get("drained") == [selected["id"]],
            "Compound drain did not remove the handled signal.",
        )
        _assert(not stored_signal.exists(), "Handled signal remains after verified drain.")
        finish_request = consumer / "compound-finish.json"
        finish_request.write_text(
            json.dumps(
                {
                    "action": "finish",
                    "run_id": run_id,
                    "outcome": "no-update",
                    "dispositions": [
                        {
                            "signal_id": selected["id"],
                            "decision": "keep",
                            "rationale": "The smoke observation is already represented.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        finished = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "compound",
                "--request-file",
                str(finish_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="compound-finish",
        )
        _assert(
            finished.get("drained") == [selected["id"]],
            "Compound finish omitted drained provenance.",
        )
        # B5 installed proof: exact archived bytes survive drainage and export is local.
        usage_root = workspace_config.parent / "ai/usage"
        archives = list((usage_root / "compound" / run_id / "inputs").glob("*.md"))
        _assert(len(archives) == 1, "Compound start did not retain one immutable signal snapshot.")
        _assert(
            "sha256:" + hashlib.sha256(archives[0].read_bytes()).hexdigest()
            == selected["fingerprint"],
            "Archived signal bytes differ from the selected original.",
        )
        export_request = consumer / "usage-export.json"
        export_request.write_text(
            json.dumps(
                {
                    "since": "2000-01-01T00:00:00Z",
                    "until": "2100-01-01T00:00:00Z",
                    "destination": str(temp_root / "usage-export"),
                }
            ),
            encoding="utf-8",
        )
        exported = _run_json(
            [
                str(launcher),
                "--config",
                str(workspace_config),
                "usage",
                "export",
                "--request-file",
                str(export_request),
            ],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="usage-export",
        )
        _assert(exported.get("status") == "ok", "Installed usage export failed.")
        _assert(
            any((temp_root / "usage-export").rglob("*.md")), "Export omitted archived signal input."
        )
        activity = (consumer / "ai" / "signals" / "compound-activity.jsonl").read_text(
            encoding="utf-8"
        )
        _assert(
            session_id in activity and "smoke-automation" in activity,
            "Activity provenance was not recorded.",
        )
        missing = _run_json(
            [str(launcher), "--config", str(consumer / "missing.yaml"), "doctor"],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="doctor-missing-config",
            expected_exit=2,
        )
        _assert(missing.get("status") == "error", "Missing configuration was not diagnosed.")

        _run(
            [str(apm), "uninstall", "_local/knowledge-agent-pack"],
            cwd=consumer,
            env=clean_env,
            logs=logs,
            label="apm-uninstall-package",
        )
        _hook_registration_proof(
            consumer,
            copilot_authored=copilot_authored_hook,
            package_present=False,
        )
        # A strict consumer owns APM commands. Prepare must work without an
        # installed package, and unfinished credentials must not block reminders.
        profile_environment.write_text("PROFILE_PROOF_TOKEN=\n", encoding="utf-8")
        local_skill = consumer / ".apm/skills/consumer-review/SKILL.md"
        local_skill.parent.mkdir(parents=True)
        local_skill.write_text(
            "---\nname: consumer-review\ndescription: Review this fixture repository.\n---\n"
            "Use the repository's own review procedure.\n",
            encoding="utf-8",
        )
        prepared_files = {
            path: path.read_bytes()
            for path in [
                consumer / "apm.yml",
                local_skill,
                *_provider_hook_files(consumer).values(),
            ]
        }
        prepared = _run_json(
            [*setup_args, "--apm-mode", "prepare"],
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="staged-prepare",
        )
        _assert(prepared["hooks"]["status"] == "pending", "Prepare claimed hook installation.")
        _assert(prepared["targets"] == ["codex", "claude", "copilot"], "Prepare lost targets.")
        _assert(prepared["environment"]["status"] == "not-ready", "Blank credentials became ready.")
        _assert(
            all(path.read_bytes() == data for path, data in prepared_files.items()),
            "Prepare changed consumer-owned files.",
        )
        _assert(
            not (consumer / "apm_modules/_local/knowledge-agent-pack").exists(),
            "Prepare installed an APM dependency.",
        )
        _run(
            [
                str(apm),
                "install",
                "--no-policy",
                "--target",
                "codex,claude,copilot",
                str(package_root),
            ],
            cwd=consumer,
            env=clean_env,
            logs=logs,
            label="apm-reinstall-package",
        )
        _run(
            [str(apm), "compile", "--target", "codex,claude,copilot", "--force-instructions"],
            cwd=consumer,
            env=clean_env,
            logs=logs,
            label="repository-owned-compile",
        )
        protected_files = {
            path: path.read_bytes()
            for path in [
                consumer / "apm.yml",
                local_skill,
                *[consumer / value for value in projection_paths],
            ]
        }
        bind_args = [*setup_args, "--apm-mode", "bind"]
        bind_args[1] = str(
            installed_package / ".apm/skills/knowledge-setup/scripts/setup_runtime.py"
        )
        pending = _run_json(
            bind_args,
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="staged-bind-pending",
        )
        _assert(pending["hooks"]["status"] == "ready", "Blank credentials blocked hook binding.")
        _assert(
            pending["doctor"]["status"] == "error" and pending["doctor"]["diagnostics"],
            "Setup hid pending credential diagnostics.",
        )
        _assert(pending["environment"]["launcher"] is None, "Pending setup exposed activation.")
        _assert(
            "--environment-file" not in json.dumps(pending["hooks"]),
            "Pending credentials were bound into Claude reminders.",
        )
        _hook_registration_proof(
            consumer,
            copilot_authored=copilot_authored_hook,
            package_present=True,
            hook_launcher=Path(pending["hook_launcher"]),
            environment=pending["environment"],
        )
        pending_logs = logs / "pending-hooks"
        pending_logs.mkdir()
        pending_hook_smoke = run_provider_hook_smoke(
            consumer,
            Path(pending["hook_launcher"]),
            logs=pending_logs,
            env=clean_env,
        )
        profile_environment.write_text(f"PROFILE_PROOF_TOKEN={profile_canary}\n", encoding="utf-8")
        recovery_setup = _run_json(
            bind_args,
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="setup-runtime-recovery",
        )
        repeated_bind = _run_json(
            bind_args,
            cwd=temp_root,
            env=clean_env,
            logs=logs,
            label="staged-bind-repeat",
        )
        _assert(
            recovery_setup["hooks"] == repeated_bind["hooks"], "Repeat bind changed hook identity."
        )
        for phase in (prepared, pending, recovery_setup, repeated_bind):
            _assert(
                not any(step["name"] in {"apm-install", "apm-compile"} for step in phase["steps"]),
                "Staged setup invoked APM.",
            )
        _assert(
            all(path.read_bytes() == data for path, data in protected_files.items()),
            "Bind changed repository-owned instructions, manifest or local skills.",
        )
        _assert(
            any(
                item.get("name") == "venv" and item.get("status") == "reused"
                for item in recovery_setup.get("steps", [])
                if isinstance(item, dict)
            ),
            "Recovery setup did not reuse the managed virtual environment.",
        )
        _assert(
            isinstance(recovery_setup.get("hooks"), dict)
            and recovery_setup["hooks"].get("status") == "ready"
            and recovery_setup["hooks"].get("targets") == ["codex", "claude", "copilot"],
            "Recovery setup did not verify all package-owned hook registrations.",
        )
        recovery_hook_launcher = Path(str(recovery_setup["hook_launcher"])).resolve()
        recovery_environment = recovery_setup.get("environment")
        _assert(
            isinstance(recovery_environment, dict)
            and isinstance(recovery_environment.get("launcher"), str),
            "Recovery setup did not restore the profile environment launcher.",
        )
        _assert(
            recovery_hook_launcher == setup_hook_launcher.resolve(),
            "Recovery setup changed the managed hook launcher path.",
        )
        _hook_registration_proof(
            consumer,
            copilot_authored=copilot_authored_hook,
            package_present=True,
            hook_launcher=recovery_hook_launcher,
            environment=recovery_environment,
        )
        recovery_hook_smoke = run_provider_hook_smoke(
            consumer, recovery_hook_launcher, logs=logs, env=clean_env
        )
        portable_proof = _portable_binding_proof(
            consumer=consumer,
            bind_args=bind_args,
            clean_env=clean_env,
            profile_settings=profile_settings,
            runtime=Path(recovery_setup["venv"]),
            logs=logs,
        )
        leak_files = [
            *logs.rglob("*.log"),
            environment_launcher,
            work_environment_launcher,
            *Path(str(environment_report["session_state_directory"])).glob("*.json"),
            *consumer.glob(".claude/**/*.json"),
            *consumer.glob(".github/hooks/**/*.json"),
            *consumer.glob("ai/usage/**/*"),
        ]
        leak_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in leak_files
            if path.is_file()
        )
        _assert(
            profile_canary not in leak_text and work_profile_canary not in leak_text,
            "A disposable profile canary escaped into durable evidence or hook metadata.",
        )
    except Exception:
        raise
    live = _live_cli_checks(clean_env, logs) if live_cli else []
    report = {
        "schema": "fresh-consumer-smoke.v1",
        "status": "ok",
        "repository": str(root),
        "revision": _git_revision(root),
        "apm": str(apm),
        "uv": str(uv),
        "python": str(python_in_venv),
        "python_version": version_text,
        "consumer_root": str(consumer),
        "retained": keep,
        "targets": ["codex", "claude", "copilot"],
        "projections": projection_paths,
        "resources": resources,
        "setup": {
            "launcher": str(setup_launcher),
            "hook_launcher": str(setup_hook_launcher.resolve()),
            "targets": setup.get("targets", []),
            "first_venv": "ok",
            "repeat_venv": "reused",
            "hooks": setup.get("hooks", {}),
            "selection": setup.get("selection"),
            "environment": setup.get("environment"),
            "alternate_environment": work_setup.get("environment"),
            "apm_lock": setup.get("apm_lock", {}),
        },
        "recovery": {
            "launcher": recovery_setup.get("launcher"),
            "hook_launcher": str(recovery_hook_launcher),
            "hooks": recovery_hook_smoke,
        },
        "staged_integration": {
            "prepare": prepared["apm"],
            "pending_environment": pending["environment"],
            "pending_hooks": pending_hook_smoke,
            "bind": recovery_setup["apm"],
            "repeat_binding": "unchanged",
            "consumer_owned_files": "unchanged",
        },
        "portable_binding": portable_proof,
        "hooks": hook_smoke,
        "compounding": {
            "signal_id": selected["id"],
            "session_id": session_id,
            "activity": str(consumer / "ai" / "signals" / "compound-activity.jsonl"),
            "outcome": finished.get("outcome"),
            "drained": finished.get("drained", []),
        },
        "live_cli": live,
        "checks": [
            "isolated wheel build and install",
            "clean environment without organization variables",
            "APM install and multi-target compile",
            "fresh-consumer APM audit",
            "installed guide/template parity",
            "installed skill and reference parity across native catalogs",
            "explicit doctor/context/search",
            "setup helper creates and reuses a venv",
            "setup helper installs runtime and compiles APM targets",
            "setup helper verifies one owned hook per target",
            "staged prepare and bind preserve repository-owned installation and compilation",
            "blank credentials allow installed reminders; filling values activates on repeat bind",
            "two profile environment launchers expose only their declared targets",
            "Claude SessionStart persists only a value-free declaration pin",
            "setup helper reconciles Copilot lockfile hashes",
            "installed Codex, Claude and Copilot hooks emit one-channel reminders",
            "APM preserves unrelated hooks and setup rebinds absolute launchers after reinstall",
            "signal record/list and provenance",
            "compound start/drain/finish with guarded cleanup",
            "missing-config diagnostic",
        ],
    }
    if not keep:
        shutil.rmtree(temp_root, ignore_errors=True)
    return report


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_smoke(keep=args.keep, live_cli=args.live_cli, python_request=args.python)
    except SmokeFailure as error:
        payload: dict[str, Any] = {
            "schema": "fresh-consumer-smoke.v1",
            "status": "error",
            "diagnostic": str(error),
        }
        if error.log is not None:
            payload["log"] = str(error.log)
        rendered = json.dumps(payload, indent=2) + "\n"
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
