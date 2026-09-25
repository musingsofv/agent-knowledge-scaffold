#!/usr/bin/env python3
"""Provision an explicit agent-knowledge runtime and optional APM consumer.

This helper is intentionally small and provider-neutral. It never writes shell
startup files, registers a scheduler or prints child-process output. Native
harness automation remains the responsibility of knowledge-setup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_TARGET_ORDER = ("codex", "claude", "copilot")
_TARGETS = frozenset(_TARGET_ORDER)
_COMMAND_TIMEOUT = 300
_DESCRIPTOR_HOOK_COMMAND = "agent-knowledge-hook"
_MINIMUM_PYTHON = (3, 11)
_LIFECYCLE_EVENTS = ("SessionStart", "UserPromptSubmit")
_COPILOT_EVENTS = ("sessionStart", "userPromptTransformed")
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SESSION_PIN_MAX_BYTES = 16_384
_RESERVED_ENVIRONMENT_TARGETS = frozenset(
    {
        "AGENT_KNOWLEDGE_SETTINGS",
        "BASHPID",
        "BASH_ARGC",
        "BASH_ARGV",
        "BASH_COMMAND",
        "BASH_LINENO",
        "BASH_SOURCE",
        "BASH_SUBSHELL",
        "BASH_VERSINFO",
        "BASHOPTS",
        "BASH_ENV",
        "BASH_XTRACEFD",
        "CDPATH",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_ENV_FILE",
        "CODEX_HOME",
        "COPILOT_HOME",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
        "EUID",
        "ENV",
        "FUNCNAME",
        "GLOBIGNORE",
        "GROUPS",
        "HOME",
        "HOSTNAME",
        "HOSTTYPE",
        "IFS",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "LINENO",
        "MACHTYPE",
        "NODE_OPTIONS",
        "OLDPWD",
        "OPTARG",
        "OPTIND",
        "OSTYPE",
        "PATH",
        "PIPESTATUS",
        "PERL5OPT",
        "PPID",
        "PROMPT_COMMAND",
        "PS0",
        "PS1",
        "PS2",
        "PS3",
        "PS4",
        "PYTHONHOME",
        "PYTHONINSPECT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PWD",
        "RANDOM",
        "REPLY",
        "RUBYOPT",
        "SECONDS",
        "SHELL",
        "SHELLOPTS",
        "SHLVL",
        "SRANDOM",
        "TEMP",
        "TMP",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_RUNTIME_DIR",
        "XDG_STATE_HOME",
        "ZDOTDIR",
        "UID",
        "_",
    }
)


def _is_safe_environment_target(name: str) -> bool:
    return (
        _ENVIRONMENT_NAME.fullmatch(name) is not None
        and not name.casefold().startswith("_ak_")
        and name not in _RESERVED_ENVIRONMENT_TARGETS
    )


@dataclass(frozen=True)
class Step:
    name: str
    status: str


class SetupFailure(RuntimeError):
    """A bounded setup failure that is safe to render to the caller."""

    def __init__(
        self,
        code: str,
        message: str,
        steps: list[Step],
        remediation: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.steps = steps
        self.remediation = remediation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install and verify an explicit agent-knowledge runtime."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--profile", help="Verify this explicit installed knowledge profile.")
    parser.add_argument("--settings", type=Path, help="Absolute profile registry path.")
    parser.add_argument(
        "--portable-hooks",
        action="store_true",
        help="Bind PATH-based hooks using --profile and each environment's local registry.",
    )
    parser.add_argument(
        "--venv",
        type=Path,
        help="Virtual environment path (default: <workspace-config-parent>/.agent-knowledge-venv).",
    )
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--consumer", type=Path, required=True)
    parser.add_argument(
        "--apm-mode",
        choices=("managed", "prepare", "bind"),
        default="managed",
        help="Manage APM, prepare runtime only, or bind a repository-managed APM installation.",
    )
    parser.add_argument(
        "--targets",
        default=",".join(_TARGET_ORDER),
        help="Comma-separated APM targets (default: codex,claude,copilot).",
    )
    return parser


def _absolute(value: Path, name: str) -> Path:
    if not value.is_absolute():
        raise SetupFailure("relative-path", f"{name} must be an absolute path.", [])
    return value.resolve(strict=False)


def _existing_file(value: Path, name: str) -> Path:
    path = _absolute(value, name)
    if not path.is_file():
        raise SetupFailure("missing-path", f"{name} does not name an existing file.", [])
    return path


def _existing_directory(value: Path, name: str) -> Path:
    path = _absolute(value, name)
    if not path.is_dir():
        raise SetupFailure("missing-path", f"{name} does not name an existing directory.", [])
    return path


def _targets(raw: str) -> tuple[str, ...]:
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    if len(values) != len(set(values)):
        raise SetupFailure("duplicate-target", "Targets must be unique.", [])
    unknown = sorted(set(values) - _TARGETS)
    if unknown:
        raise SetupFailure(
            "unsupported-target",
            "Unsupported APM target(s): " + ", ".join(unknown) + ".",
            [],
        )
    return tuple(item for item in _TARGET_ORDER if item in values)


def _venv_executables(venv: Path) -> tuple[Path, Path]:
    candidates = (
        (venv / "bin" / "python", venv / "bin" / "agent-knowledge"),
        (venv / "Scripts" / "python.exe", venv / "Scripts" / "agent-knowledge.exe"),
        (venv / "Scripts" / "python", venv / "Scripts" / "agent-knowledge"),
    )
    for python, launcher in candidates:
        if python.is_file():
            return python, launcher
    return candidates[0]


def _venv_hook_executable(venv: Path) -> Path:
    candidates = (
        venv / "bin" / "agent-knowledge-hook",
        venv / "Scripts" / "agent-knowledge-hook.exe",
        venv / "Scripts" / "agent-knowledge-hook",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0])


def _launcher_command(launcher: Path) -> str:
    """Render a provider command that invokes exactly one installed launcher."""
    return _shell_command([str(launcher)])


def _shell_command(arguments: list[str]) -> str:
    """Render trusted argv for a provider-owned command field."""
    if sys.platform == "win32":
        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)


def _provider_hook_command(
    launcher: Path,
    target: str,
    event_name: str,
    environment: dict[str, object] | None,
    *,
    portable_profile: str | None = None,
) -> str:
    if portable_profile is not None:
        return _shell_command(
            [_DESCRIPTOR_HOOK_COMMAND, "--provider", target, "--profile", portable_profile]
        )
    arguments = [str(launcher), "--provider", target]
    if target == "claude" and event_name == "SessionStart":
        arguments.extend(_claude_environment_arguments(environment))
    return _shell_command(arguments)


def _claude_environment_arguments(environment: dict[str, object] | None) -> list[str]:
    """Render the value-free metadata Claude's hook needs for native exports."""
    if environment is None or environment.get("status") != "ready":
        return []
    file_value = environment.get("environment_file")
    state_directory = environment.get("session_state_directory")
    variables = environment.get("variables")
    if (
        not isinstance(file_value, str)
        or not isinstance(state_directory, str)
        or not isinstance(variables, list)
        or not variables
    ):
        raise SetupFailure(
            "environment-contract-invalid",
            "The environment report cannot bind Claude's session hook.",
            [],
        )
    arguments = [
        "--environment-file",
        file_value,
        "--environment-state-directory",
        state_directory,
    ]
    for variable in variables:
        source = variable.get("from_env") if isinstance(variable, dict) else None
        target = variable.get("expose_as") if isinstance(variable, dict) else None
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or _ENVIRONMENT_NAME.fullmatch(source) is None
            or not _is_safe_environment_target(target)
        ):
            raise SetupFailure(
                "environment-contract-invalid",
                "The environment report contains an invalid Claude mapping.",
                [],
            )
        arguments.extend(("--environment-map", f"{source}={target}"))
    return arguments


def _read_python_version(python: Path, steps: list[Step]) -> tuple[int, int, int]:
    """Read the interpreter's actual version, rather than trusting venv metadata."""
    try:
        result = subprocess.run(
            [str(python), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SetupFailure(
            "python-unavailable",
            "Python 3.11 or newer is required, but the selected interpreter could not be run. "
            "Install Python 3.11 or newer and retry setup.",
            steps,
        ) from error
    if result.returncode:
        raise SetupFailure(
            "python-unavailable",
            "Python 3.11 or newer is required, but the selected interpreter failed "
            "its version check. "
            "Install Python 3.11 or newer and retry setup.",
            steps,
        )
    output = (result.stdout or result.stderr).strip()
    _, separator, version_text = output.partition("Python ")
    if not separator:
        raise SetupFailure(
            "python-version-unknown",
            "The selected interpreter did not report a Python version. "
            "Install Python 3.11 or newer "
            "and retry setup.",
            steps,
        )
    parts = version_text.split(".")
    try:
        version = (int(parts[0]), int(parts[1]), int(parts[2].split()[0]))
    except (IndexError, ValueError) as error:
        raise SetupFailure(
            "python-version-unknown",
            "The selected interpreter reported an unreadable Python version. Install Python "
            "3.11 or newer and retry setup.",
            steps,
        ) from error
    return version


def _require_supported_python(python: Path, steps: list[Step], *, source: str) -> None:
    version = _read_python_version(python, steps)
    if version[:2] < _MINIMUM_PYTHON:
        rendered = ".".join(str(part) for part in version)
        raise SetupFailure(
            "python-version-mismatch",
            f"{source} uses Python {rendered}; Python 3.11 or newer is required. "
            "Install Python 3.11 or newer and remove or replace this environment "
            "before retrying setup.",
            steps,
        )
    steps.append(Step("python", f"{version[0]}.{version[1]}.{version[2]}"))


def _find_supported_python(uv: str, steps: list[Step]) -> Path:
    """Find an installed CPython 3.11+ without downloading another runtime."""
    try:
        result = subprocess.run(
            [
                uv,
                "python",
                "find",
                "cpython>=3.11",
                "--no-project",
                "--system",
                "--no-python-downloads",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SetupFailure(
            "python-version-unavailable",
            "Python 3.11 or newer is required and could not be located. "
            "Install Python 3.11 or newer "
            "(for example, with `uv python install 3.11`) and retry setup.",
            steps,
        ) from error
    if result.returncode:
        raise SetupFailure(
            "python-version-unavailable",
            "Python 3.11 or newer is required but is not installed. Install Python 3.11 or newer "
            "(for example, with `uv python install 3.11`) and retry setup.",
            steps,
        )
    output = result.stdout.strip().splitlines()
    candidate = Path(output[-1]).expanduser() if output else Path()
    if not candidate.is_file():
        raise SetupFailure(
            "python-version-unavailable",
            "Python 3.11 or newer is required but no usable interpreter was found. "
            "Install Python 3.11 or newer and retry setup.",
            steps,
        )
    candidate = candidate.resolve()
    _require_supported_python(candidate, steps, source="The selected Python interpreter")
    return candidate


def _prepare_venv(venv: Path, uv: str, steps: list[Step]) -> tuple[Path, Path]:
    path = _absolute(venv, "--venv")
    validated = False
    if path.exists():
        if not path.is_dir():
            raise SetupFailure("invalid-venv", "The selected venv path is not a directory.", steps)
        python, _ = _venv_executables(path)
        marker = path / "pyvenv.cfg"
        if marker.is_file() and python.is_file():
            _require_supported_python(python, steps, source="The existing virtual environment")
            validated = True
            steps.append(Step("venv", "reused"))
        elif any(path.iterdir()):
            raise SetupFailure(
                "partial-venv",
                "The selected venv directory is partial; inspect or remove it before retrying.",
                steps,
            )
        else:
            python_source = _find_supported_python(uv, steps)
            _run(
                [uv, "venv", "--python", str(python_source), str(path)],
                cwd=path.parent,
                name="venv",
                steps=steps,
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        python_source = _find_supported_python(uv, steps)
        _run(
            [uv, "venv", "--python", str(python_source), str(path)],
            cwd=path.parent,
            name="venv",
            steps=steps,
        )
    python, launcher = _venv_executables(path)
    if not python.is_file():
        raise SetupFailure(
            "invalid-venv",
            "The virtual environment has no usable Python executable.",
            steps,
        )
    # Validate the interpreter produced by uv as well as the source selected above.
    if not validated:
        _require_supported_python(python, steps, source="The created virtual environment")
    return python, launcher


def _run(
    command: list[str],
    *,
    cwd: Path,
    name: str,
    steps: list[Step],
    env: dict[str, str] | None = None,
    allow_nonzero: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SetupFailure(
            "command-unavailable" if isinstance(error, OSError) else "command-timeout",
            f"{name} could not complete.",
            steps,
        ) from error
    if result.returncode and not allow_nonzero:
        raise SetupFailure("command-failed", f"{name} failed with exit {result.returncode}.", steps)
    steps.append(Step(name, "ok" if result.returncode == 0 else "not-ready"))
    return result


def _only_environment_pending(value: dict[str, Any]) -> bool:
    """Allow a readable workspace with independently diagnosed credential failures."""
    readiness = value.get("readiness")
    diagnostics = value.get("diagnostics")
    checks = value.get("checks")
    environment_codes = {
        "environment-file-unavailable",
        "environment-file-unsafe",
        "environment-file-permissions",
        "environment-file-too-large",
        "environment-file-invalid",
        "environment-file-changed",
        "environment-variable-missing",
    }
    return (
        value.get("status") == "error"
        and isinstance(readiness, dict)
        and readiness.get("read") == "ready"
        and readiness.get("environment") == "not-ready"
        and readiness.get("write") in ("ready", "unverified", "not-configured")
        and readiness.get("receipts") in ("ready", "unverified", "not-configured")
        and isinstance(diagnostics, list)
        and bool(diagnostics)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("code"), str)
            and item["code"] in environment_codes
            for item in diagnostics
        )
        and isinstance(checks, list)
        and bool(checks)
        and all(
            isinstance(item, dict)
            and (
                item.get("status") in ("passed", "unverified", "skipped")
                or (
                    item.get("status") == "failed"
                    and isinstance(item.get("name"), str)
                    and (
                        item["name"] == "environment-file"
                        or item["name"].startswith("environment:")
                    )
                )
            )
            for item in checks
        )
        and any(item.get("status") == "failed" for item in checks)
    )


def _json_result(
    command: list[str],
    *,
    cwd: Path,
    name: str,
    steps: list[Step],
    allow_error: bool = False,
    allow_environment_pending: bool = False,
) -> dict[str, Any]:
    result = _run(
        command,
        cwd=cwd,
        name=name,
        steps=steps,
        allow_nonzero=allow_error,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SetupFailure("invalid-output", f"{name} did not return JSON.", steps) from error
    if not isinstance(value, dict):
        raise SetupFailure("invalid-output", f"{name} did not return a JSON object.", steps)
    if (
        allow_environment_pending
        and result.returncode in (2, 3)
        and _only_environment_pending(value)
    ):
        return value
    if value.get("status") != "ok":
        if allow_error:
            diagnostics = value.get("diagnostics")
            diagnostic = diagnostics[0] if isinstance(diagnostics, list) and diagnostics else None
            if isinstance(diagnostic, dict):
                code = diagnostic.get("code")
                message = diagnostic.get("message")
                remediation = diagnostic.get("remediation")
                raise SetupFailure(
                    code if isinstance(code, str) else "doctor-not-ready",
                    message if isinstance(message, str) else f"{name} did not report readiness.",
                    steps,
                    remediation if isinstance(remediation, str) else None,
                )
        raise SetupFailure("verification-failed", f"{name} did not report success.", steps)
    if result.returncode:
        raise SetupFailure("verification-failed", f"{name} exited without success.", steps)
    return value


def _hook_package(consumer: Path, *, python: Path = Path(sys.executable)) -> tuple[str, Path]:
    """Find the unique lock-registered package that owns the discovery hook bundle."""
    modules = consumer / "apm_modules"
    lock = consumer / "apm.lock.yaml"
    if not lock.is_file():
        raise SetupFailure(
            "lockfile-missing", "Rerun APM install to create apm.lock.yaml before binding.", []
        )
    # Use the verified runtime's YAML parser: the bootstrap interpreter need
    # not have PyYAML, and APM can wrap/quote paths in its generated lock.
    try:
        document = _json_result(
            [
                str(python),
                "-I",
                "-c",
                "import json, pathlib, sys, yaml; "
                "data = yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')); "
                "print(json.dumps({'status': 'ok', 'dependencies': data['dependencies']}))",
                str(lock),
            ],
            cwd=consumer,
            name="apm-lock-read",
            steps=[],
        )
    except SetupFailure as error:
        raise SetupFailure(
            "lockfile-invalid",
            "Cannot read APM dependencies; rerun APM install before binding.",
            [],
        ) from error
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, dict) for item in dependencies
    ):
        raise SetupFailure("lockfile-invalid", "APM dependencies must be a list of records.", [])
    candidates: list[tuple[str, Path]] = []
    for dependency in dependencies:
        repo = dependency.get("repo_url")
        if not isinstance(repo, str) or not repo:
            continue
        if dependency.get("source") == "local":
            local = dependency.get("local_path")
            if not isinstance(local, str) or not local:
                continue
            name = Path(local).name
            if dependency.get("declaring_parent"):
                anchor = dependency.get("anchored_local_path") or local
                if not isinstance(anchor, str):
                    continue
                name = f"{hashlib.sha256(anchor.encode()).hexdigest()[:12]}/{name}"
            source = f"_local/{name}"
            relative = source
        else:
            virtual = dependency.get("virtual_path") if dependency.get("is_virtual") else ""
            materialized = dependency.get("materialization_repo_url") or repo
            if not isinstance(virtual, str) or not isinstance(materialized, str):
                continue
            source = f"{repo}/{virtual}" if virtual else repo
            relative = f"{materialized}/{virtual}" if virtual else materialized
        package = modules / relative
        descriptor = package / ".apm/hooks/knowledge-discovery.json"
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise SetupFailure("hook-package-invalid", "APM package path escapes apm_modules.", [])
        if not descriptor.is_file():
            continue
        if not descriptor.resolve().is_relative_to(modules.resolve()):
            raise SetupFailure("hook-package-invalid", "APM hook escapes apm_modules.", [])
        candidates.append((source, package))
    if len(candidates) != 1:
        raise SetupFailure(
            "hook-package-missing",
            "APM installed no unique package-owned discovery hook bundle.",
            [],
        )
    return candidates[0]


def _hook_command(entry: object, *, launcher: Path | None = None) -> bool:
    if not isinstance(entry, dict):
        return False
    command = entry.get("command")
    if not isinstance(command, str):
        return False
    try:
        arguments = shlex.split(command, posix=sys.platform != "win32")
    except ValueError:
        return False
    if not arguments:
        return False
    if launcher is None:
        return arguments[0] == _DESCRIPTOR_HOOK_COMMAND
    return arguments[0].strip('"') == str(launcher)


def _owned_hook_groups(
    value: object,
    source: str,
    *,
    event_name: str = "SessionStart",
    launcher: Path | None = None,
    include_descriptor: bool = False,
) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    groups = value.get(event_name)
    if groups is None and isinstance(value.get("hooks"), dict):
        groups = value["hooks"].get(event_name)
    if not isinstance(groups, list):
        return []
    owned: list[dict[str, object]] = []
    for group in groups:
        if not isinstance(group, dict) or group.get("_apm_source") != source:
            continue
        hooks = group.get("hooks")
        if isinstance(hooks, list) and any(
            _hook_command(entry, launcher=launcher) or (include_descriptor and _hook_command(entry))
            for entry in hooks
        ):
            owned.append(group)
    return owned


def _read_hook_document(path: Path, target: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SetupFailure(
            "hook-registration-invalid",
            f"The {target} hook registration is not valid JSON.",
            [],
        ) from error


def _write_hook_document(path: Path, document: object) -> None:
    try:
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise SetupFailure(
            "hook-registration-write-failed",
            f"The package-owned hook registration could not be updated: {path}.",
            [],
        ) from error


def _active_hook_path(consumer: Path, target: str) -> Path:
    if target == "codex":
        return consumer / ".codex" / "hooks.json"
    if target == "claude":
        return consumer / ".claude" / "settings.json"
    return consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"


def _normalize_active_hook(
    path: Path, target: str, launcher: Path, event_name: str, command: str
) -> None:
    """Bind one active provider hook and remove duplicate package markers."""
    if not path.is_file():
        return
    document = _read_hook_document(path, target)
    hook_config = document.get("hooks") if isinstance(document, dict) else None
    groups = hook_config.get(event_name) if isinstance(hook_config, dict) else None
    if not isinstance(groups, list):
        raise SetupFailure(
            "hook-registration-invalid",
            f"The active {target} hook configuration has no {event_name} groups.",
            [],
        )
    found = False
    changed = False
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        retained: list[object] = []
        for entry in group["hooks"]:
            if not isinstance(entry, dict) or not (
                _hook_command(entry) or _hook_command(entry, launcher=launcher)
            ):
                retained.append(entry)
                continue
            if found:
                changed = True
                continue
            found = True
            if entry.get("command") != command:
                entry["command"] = command
                changed = True
            retained.append(entry)
        if len(retained) != len(group["hooks"]):
            group["hooks"] = retained
    if not found:
        raise SetupFailure(
            "hook-registration-missing",
            f"The active {target} hook configuration has no package-owned discovery hook.",
            [],
        )
    if changed:
        _write_hook_document(path, document)


def _active_hook_count(document: object, launcher: Path, event_name: str, command: str) -> int:
    if not isinstance(document, dict):
        return 0
    groups = document.get("hooks")
    groups = document.get(event_name) if not isinstance(groups, dict) else groups.get(event_name)
    if not isinstance(groups, list):
        return 0
    return sum(
        1
        for group in groups
        if isinstance(group, dict) and isinstance(group.get("hooks"), list)
        for entry in group["hooks"]
        if isinstance(entry, dict)
        and (_hook_command(entry, launcher=launcher) or _hook_command(entry))
        and entry.get("command") == command
    )


def _matching_hook_entries(group: object, launcher: Path) -> list[dict[str, object]]:
    if not isinstance(group, dict):
        return []
    hooks = group.get("hooks")
    if not isinstance(hooks, list):
        return []
    return [
        entry
        for entry in hooks
        if isinstance(entry, dict)
        and (_hook_command(entry) or _hook_command(entry, launcher=launcher))
    ]


def _configure_copilot_hooks(
    path: Path,
    launcher: Path,
    environment: dict[str, object] | None,
    *,
    portable_profile: str | None = None,
) -> dict[str, str]:
    """Replace APM's compatibility projection with Copilot's native schema."""
    document = _read_hook_document(path, "Copilot")
    if not isinstance(document, dict):
        raise SetupFailure(
            "hook-registration-invalid",
            "The Copilot hook configuration is not an object.",
            [],
        )
    hooks = document.get("hooks")
    if not isinstance(hooks, dict):
        raise SetupFailure(
            "hook-registration-invalid",
            "The Copilot hook configuration has no hooks object.",
            [],
        )
    commands = {
        event_name: _provider_hook_command(
            launcher, "copilot", event_name, environment, portable_profile=portable_profile
        )
        for event_name in _COPILOT_EVENTS
    }
    native_hooks = {
        event_name: [
            {
                "type": "command",
                "command": commands[event_name],
                "timeoutSec": 3,
            }
        ]
        for event_name in _COPILOT_EVENTS
    }
    if hooks != native_hooks or document.get("version") != 1:
        document["version"] = 1
        document["hooks"] = native_hooks
        _write_hook_document(path, document)
    return commands


def _bind_package_hook(package: Path, launcher: Path, *, portable: bool = False) -> None:
    """Declare the selected installed or PATH-based command in the owned descriptor."""
    path = package / ".apm" / "hooks" / "knowledge-discovery.json"
    document = _read_hook_document(path, "package")
    hooks = document.get("hooks") if isinstance(document, dict) else None
    command = _DESCRIPTOR_HOOK_COMMAND if portable else _launcher_command(launcher)
    changed = False
    for event_name in _LIFECYCLE_EVENTS:
        groups = hooks.get(event_name) if isinstance(hooks, dict) else None
        entries = [
            entry for group in groups or [] for entry in _matching_hook_entries(group, launcher)
        ]
        if len(entries) != 1:
            raise SetupFailure(
                "hook-registration-ambiguous",
                f"Expected one package-owned {event_name} descriptor hook command; "
                f"found {len(entries)}.",
                [],
            )
        if entries[0].get("command") != command:
            entries[0]["command"] = command
            changed = True
    if changed:
        _write_hook_document(path, document)


def _configure_hook_registrations(
    consumer: Path,
    targets: tuple[str, ...],
    launcher: Path,
    *,
    environment: dict[str, object] | None = None,
    python: Path = Path(sys.executable),
    portable_profile: str | None = None,
) -> dict[str, object]:
    """Replace the descriptor marker with the installed venv hook launcher."""
    if not targets:
        return {"status": "disabled", "targets": []}
    source, package = _hook_package(consumer, python=python)
    for target in targets:
        if target in {"codex", "claude"}:
            path = consumer / f".{target}" / "apm-hooks.json"
            if not path.is_file():
                raise SetupFailure(
                    "hook-registration-missing",
                    f"APM did not write the {target} hook registration.",
                    [],
                )
            document = _read_hook_document(path, target)
            for event_name in _LIFECYCLE_EVENTS:
                command = _provider_hook_command(
                    launcher, target, event_name, environment, portable_profile=portable_profile
                )
                owned = _owned_hook_groups(
                    document,
                    source,
                    event_name=event_name,
                    launcher=launcher,
                    include_descriptor=True,
                )
                if len(owned) != 1:
                    raise SetupFailure(
                        "hook-registration-ambiguous",
                        f"Expected one package-owned {target} {event_name} registration; "
                        f"found {len(owned)}.",
                        [],
                    )
                entries = _matching_hook_entries(owned[0], launcher)
                if len(entries) != 1:
                    raise SetupFailure(
                        "hook-registration-ambiguous",
                        f"Expected one package-owned {target} {event_name} hook command; "
                        f"found {len(entries)}.",
                        [],
                    )
                if entries[0].get("command") != command:
                    entries[0]["command"] = command
                    _write_hook_document(path, document)
            for event_name in _LIFECYCLE_EVENTS:
                command = _provider_hook_command(
                    launcher, target, event_name, environment, portable_profile=portable_profile
                )
                _normalize_active_hook(
                    _active_hook_path(consumer, target),
                    target,
                    launcher,
                    event_name,
                    command,
                )
            continue

        path = consumer / ".github" / "hooks" / f"{package.name}-knowledge-discovery.json"
        if not path.is_file():
            raise SetupFailure(
                "hook-registration-missing",
                "APM did not write the Copilot hook registration.",
                [],
            )
        _configure_copilot_hooks(path, launcher, environment, portable_profile=portable_profile)
    return _verify_hook_registrations(
        consumer,
        targets,
        launcher=launcher,
        environment=environment,
        python=python,
        portable_profile=portable_profile,
    )


def _lock_scalar(line: str, key: str, *, indent: str = "  ") -> str | None:
    """Read one simple generated-lock scalar without requiring a YAML runtime."""
    prefix = f"{indent}{key}:"
    if not line.startswith(prefix):
        return None
    value = line[len(prefix) :].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _deployment_blocks(lines: list[str]) -> list[list[tuple[int, str]]]:
    """Return top-level deployment blocks from APM's generated lock format."""
    blocks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] | None = None
    in_deployments = False
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if not in_deployments:
            if stripped == "deployments:":
                in_deployments = True
            continue
        if stripped and not stripped.startswith((" ", "-")):
            break
        if stripped.startswith("- kind:"):
            if current is not None:
                blocks.append(current)
            current = []
        if current is not None:
            current.append((index, line))
    if current is not None:
        blocks.append(current)
    return blocks


def _first_lock_scalar(block: list[tuple[int, str]], key: str) -> str | None:
    for _, line in block:
        value = _lock_scalar(line, key)
        if value is not None:
            return value
    return None


def _update_copilot_lock_hash(consumer: Path, hook_path: Path, steps: list[Step]) -> dict[str, str]:
    """Reconcile APM's Copilot deployment hash after binding its launcher.

    APM tracks standalone Copilot hook files by byte hash. Setup intentionally
    changes the package-owned command from its descriptor marker to the
    verified venv launcher, so the lock entry must describe those resulting
    bytes before a later package-only uninstall can safely remove the file.
    """
    lock_path = consumer / "apm.lock.yaml"
    if not lock_path.is_file():
        raise SetupFailure(
            "lockfile-missing",
            "APM did not write apm.lock.yaml; rerun APM install before setup.",
            steps,
        )
    try:
        lines = lock_path.read_text(encoding="utf-8").splitlines(keepends=True)
        relative = hook_path.resolve().relative_to(consumer.resolve()).as_posix()
        digest = "sha256:" + hashlib.sha256(hook_path.read_bytes()).hexdigest()
    except (OSError, ValueError) as error:
        raise SetupFailure(
            "lockfile-read-failed",
            "The Copilot hook or apm.lock.yaml could not be read for hash reconciliation.",
            steps,
        ) from error

    deployment_start = next(
        (index for index, line in enumerate(lines) if line.rstrip("\r\n") == "deployments:"),
        len(lines),
    )
    dependency_matches = [
        (index, line)
        for index, line in enumerate(lines[:deployment_start])
        if _lock_scalar(line, relative, indent="    ") is not None
    ]
    if len(dependency_matches) != 1:
        raise SetupFailure(
            "lockfile-entry-missing" if not dependency_matches else "lockfile-entry-ambiguous",
            f"Expected one package hash entry for {relative}; found {len(dependency_matches)}.",
            steps,
        )

    matches: list[tuple[int, str]] = []
    for block in _deployment_blocks(lines):
        target = _first_lock_scalar(block, "target")
        value = _first_lock_scalar(block, "value")
        if target != "copilot" or value != relative:
            continue
        hash_line = next(
            (
                (index, line)
                for index, line in block
                if _lock_scalar(line, "content_hash") is not None
            ),
            None,
        )
        if hash_line is None:
            raise SetupFailure(
                "lockfile-entry-invalid",
                f"The Copilot deployment entry for {relative} has no content_hash.",
                steps,
            )
        matches.append(hash_line)

    if len(matches) != 1:
        raise SetupFailure(
            "lockfile-entry-missing" if not matches else "lockfile-entry-ambiguous",
            f"Expected one Copilot deployment entry for {relative}; found {len(matches)}.",
            steps,
        )

    index, line = matches[0]
    dependency_index, dependency_line = dependency_matches[0]
    current = _lock_scalar(line, "content_hash")
    dependency_current = _lock_scalar(dependency_line, relative, indent="    ")
    if current != digest or dependency_current != digest:
        ending = "\n" if line.endswith("\n") else ""
        lines[index] = f"  content_hash: {digest}{ending}"
        dependency_ending = "\n" if dependency_line.endswith("\n") else ""
        lines[dependency_index] = f"    {relative}: {digest}{dependency_ending}"
        try:
            lock_path.write_text("".join(lines), encoding="utf-8")
        except OSError as error:
            raise SetupFailure(
                "lockfile-write-failed",
                f"The Copilot deployment hash could not be updated: {lock_path}.",
                steps,
            ) from error
        status = "updated"
    else:
        status = "current"
    steps.append(Step("apm-lock", status))
    return {"status": status, "path": str(lock_path.resolve()), "content_hash": digest}


def _verify_hook_registrations(
    consumer: Path,
    targets: tuple[str, ...],
    *,
    launcher: Path,
    environment: dict[str, object] | None = None,
    python: Path = Path(sys.executable),
    portable_profile: str | None = None,
) -> dict[str, object]:
    """Verify one APM-owned registration exists for every requested target."""
    if not targets:
        return {"status": "disabled", "targets": []}
    source, package = _hook_package(consumer, python=python)
    registrations: dict[str, object] = {}
    for target in targets:
        if target in {"codex", "claude"}:
            path = consumer / f".{target}" / "apm-hooks.json"
            if not path.is_file():
                raise SetupFailure(
                    "hook-registration-missing",
                    f"APM did not write the {target} hook registration.",
                    [],
                )
            document = _read_hook_document(path, target)
            commands: dict[str, str] = {}
            for event_name in _LIFECYCLE_EVENTS:
                command = _provider_hook_command(
                    launcher, target, event_name, environment, portable_profile=portable_profile
                )
                commands[event_name] = command
                owned = _owned_hook_groups(
                    document,
                    source,
                    event_name=event_name,
                    launcher=launcher,
                    include_descriptor=portable_profile is not None,
                )
                if len(owned) != 1:
                    raise SetupFailure(
                        "hook-registration-ambiguous",
                        f"Expected one package-owned {target} {event_name} registration; "
                        f"found {len(owned)}.",
                        [],
                    )
                entries = _matching_hook_entries(owned[0], launcher)
                if len(entries) != 1 or entries[0].get("command") != command:
                    raise SetupFailure(
                        "hook-registration-mismatch",
                        f"The package-owned {target} {event_name} command is not current.",
                        [],
                    )
            active_path = _active_hook_path(consumer, target)
            if active_path.is_file():
                active_document = _read_hook_document(active_path, target)
                for event_name in _LIFECYCLE_EVENTS:
                    active_count = _active_hook_count(
                        active_document, launcher, event_name, commands[event_name]
                    )
                    if active_count != 1:
                        raise SetupFailure(
                            "hook-registration-ambiguous",
                            f"Expected one active package-owned {target} {event_name} hook "
                            f"command; found {active_count}.",
                            [],
                        )
            registrations[target] = {
                "path": str(path.resolve()),
                "source": source,
                "owned": 1,
                "events": list(_LIFECYCLE_EVENTS),
                "commands": commands,
            }
            continue

        path = consumer / ".github" / "hooks" / f"{package.name}-knowledge-discovery.json"
        if not path.is_file():
            raise SetupFailure(
                "hook-registration-missing",
                "APM did not write the Copilot hook registration.",
                [],
            )
        document = _read_hook_document(path, "Copilot")
        hooks = document.get("hooks") if isinstance(document, dict) else None
        commands: dict[str, str] = {}
        for event_name in _COPILOT_EVENTS:
            entries = hooks.get(event_name) if isinstance(hooks, dict) else None
            if not isinstance(entries, list) or len(entries) != 1:
                raise SetupFailure(
                    "hook-registration-ambiguous",
                    f"Expected one package-owned Copilot {event_name} registration; "
                    f"found {len(entries) if isinstance(entries, list) else 0}.",
                    [],
                )
            command = _provider_hook_command(
                launcher, "copilot", event_name, environment, portable_profile=portable_profile
            )
            commands[event_name] = command
            entry = entries[0]
            if (
                not (_hook_command(entry, launcher=launcher) or _hook_command(entry))
                or entry.get("command") != command
                or entry.get("type") != "command"
                or entry.get("timeoutSec") != 3
            ):
                raise SetupFailure(
                    "hook-registration-mismatch",
                    f"The package-owned Copilot {event_name} command is not current.",
                    [],
                )
        if not isinstance(hooks, dict) or set(hooks) != set(_COPILOT_EVENTS):
            raise SetupFailure(
                "hook-registration-unsupported-event",
                "Copilot registration contains unsupported or missing events.",
                [],
            )
        registrations[target] = {
            "path": str(path.resolve()),
            "source": source,
            "owned": 1,
            "events": list(_COPILOT_EVENTS),
            "commands": commands,
        }
    return {
        "status": "ready",
        "mode": "portable" if portable_profile is not None else "absolute",
        "targets": list(targets),
        "registrations": registrations,
    }


def _environment_launcher(
    context: dict[str, Any],
    venv: Path,
    steps: list[Step],
    *,
    consumer: Path,
    targets: tuple[str, ...] = _TARGET_ORDER,
    environment_readiness: str | None = None,
    portable_profile: str | None = None,
) -> dict[str, object]:
    """Create one content-addressed provider launcher containing no values."""
    raw = context.get("environment")
    if environment_readiness == "not-ready":
        if not isinstance(raw, dict) or raw.get("status") not in {"ready", "not-ready"}:
            raise SetupFailure(
                "environment-contract-invalid",
                "Context returned no profile environment.",
                steps,
            )
        return {
            "status": "not-ready",
            "session_policy": "one-profile-per-session",
            "environment_file": raw.get("file"),
            "launcher": None,
            "providers": {
                target: {"status": "pending" if target in targets else "not-bound"}
                for target in _TARGET_ORDER
            },
            "remediation": "Repair the private environment file using the doctor diagnostics, "
            "then rerun setup with the same selection and targets before activating credentials.",
        }
    if raw is None:
        return {
            "status": "not-configured",
            "session_policy": "one-profile-per-session",
            "launcher": None,
            "providers": _provider_activation(None, targets),
        }
    if not isinstance(raw, dict) or raw.get("status") != "ready":
        raise SetupFailure(
            "environment-not-ready",
            "The selected profile environment is not ready; run doctor and repair it first.",
            steps,
        )
    file_value = raw.get("file")
    variables_value = raw.get("variables")
    if not isinstance(file_value, str) or not Path(file_value).is_absolute():
        raise SetupFailure(
            "environment-contract-invalid",
            "Context returned no absolute environment file.",
            steps,
        )
    if not isinstance(variables_value, list) or not variables_value:
        raise SetupFailure(
            "environment-contract-invalid",
            "Context returned no environment mappings.",
            steps,
        )
    mappings: list[tuple[str, str, str]] = []
    safe_variables: list[dict[str, str]] = []
    for value in variables_value:
        if not isinstance(value, dict):
            raise SetupFailure(
                "environment-contract-invalid",
                "Context returned an invalid mapping.",
                steps,
            )
        label = value.get("label")
        source = value.get("from_env")
        target = value.get("expose_as")
        description = value.get("description")
        if (
            not isinstance(label, str)
            or not isinstance(source, str)
            or not isinstance(target, str)
            or not isinstance(description, str)
            or _ENVIRONMENT_NAME.fullmatch(source) is None
            or not _is_safe_environment_target(target)
        ):
            raise SetupFailure(
                "environment-contract-invalid",
                "Context returned an invalid mapping.",
                steps,
            )
        mappings.append((label, source, target))
        safe_variables.append(
            {
                "label": label,
                "from_env": source,
                "expose_as": target,
                "description": description,
            }
        )
    pin = json.dumps(
        {
            "schema": "profile-environment-session.v1",
            "file": file_value,
            "variables": [
                {"from_env": source, "expose_as": target} for _, source, target in mappings
            ],
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(pin) > _SESSION_PIN_MAX_BYTES:
        raise SetupFailure(
            "environment-contract-invalid",
            "The selected environment has too many mappings for Claude session state.",
            steps,
        )
    if portable_profile is not None:
        return _portable_environment_report(portable_profile, targets, file_value, safe_variables)
    declaration = {
        "file": file_value,
        "variables": safe_variables,
        "selection": context.get("selection"),
    }
    digest = hashlib.sha256(
        json.dumps(declaration, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    directory = venv / "agent-knowledge-environments"
    state_key = hashlib.sha256(str(consumer.resolve(strict=True)).encode("utf-8")).hexdigest()[:24]
    state_directory = Path.home() / ".cache" / "agent-knowledge" / "claude-environments" / state_key
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory.chmod(0o700)
        state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        state_directory.chmod(0o700)
    except OSError as error:
        raise SetupFailure(
            "environment-launcher-write-failed",
            "Could not prepare the environment launcher.",
            steps,
        ) from error
    path = directory / f"profile-{digest}.sh"
    content = _render_environment_launcher(Path(file_value), mappings, _venv_hook_executable(venv))
    current = path.read_text(encoding="utf-8") if path.is_file() else None
    if current == content:
        status = "current"
        path.chmod(0o700)
    else:
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory, delete=False
            ) as stream:
                temporary = stream.name
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o700)
            os.replace(temporary, path)
            status = "created"
        except OSError as error:
            raise SetupFailure(
                "environment-launcher-write-failed",
                "Could not publish the environment launcher.",
                steps,
            ) from error
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
    steps.append(Step("environment-launcher", status))
    selection = context.get("selection")
    profile = selection.get("profile") if isinstance(selection, dict) else None
    return {
        "status": "ready",
        "profile": profile,
        "environment_file": file_value,
        "session_state_directory": str(state_directory),
        "session_policy": "one-profile-per-session",
        "launcher": str(path),
        "variables": safe_variables,
        "providers": _provider_activation(path, targets),
    }


def _render_environment_launcher(
    environment_file: Path,
    mappings: list[tuple[str, str, str]],
    hook_launcher: Path,
) -> str:
    arguments = [
        str(hook_launcher),
        "--environment-file",
        str(environment_file),
    ]
    for _, source, target in mappings:
        arguments.extend(("--environment-map", f"{source}={target}"))
    command = _shell_command(arguments)
    return (
        "#!/bin/sh\n"
        "# Generated by knowledge-setup. Contains no credential values.\n"
        "set -eu\n"
        '[ "$#" -ge 1 ] || exit 2\n'
        "_ak_provider=$1\n"
        "shift\n"
        'case "$_ak_provider" in\n'
        f'  codex) exec {command} --launch-provider codex -- "$@" ;;\n'
        f'  copilot) exec {command} --launch-provider copilot -- "$@" ;;\n'
        "  *) exit 2 ;;\n"
        "esac\n"
    )


def _provider_activation(
    loader: Path | None,
    targets: tuple[str, ...] = _TARGET_ORDER,
) -> dict[str, object]:
    if loader is None:
        return {target: {"status": "not-configured"} for target in _TARGET_ORDER}
    quoted = shlex.quote(str(loader))
    active: dict[str, dict[str, str]] = {
        "claude": {
            "status": "native-session-start",
            "detail": "Setup binds one credential profile for new Claude sessions in this "
            "consumer through CLAUDE_ENV_FILE; use a separate consumer/project or a native "
            "provider environment for concurrent scheduled profiles.",
        },
        "codex": {
            "status": "cli-launch",
            "command": f"{quoted} codex",
            "app": "No generic per-task env-file injection; use native stores or "
            "explicit credentialed-command sourcing.",
        },
        "copilot": {
            "status": "cli-launch",
            "command": f"{quoted} copilot",
            "app": "No generic per-session arbitrary env-file injection; use native stores "
            "or explicit credentialed-command sourcing.",
        },
    }
    return {
        target: active[target]
        if target in targets
        else {
            "status": "not-bound",
            "detail": "Rerun knowledge-setup with this harness target before using it.",
        }
        for target in _TARGET_ORDER
    }


def _verify_selection(
    context: dict[str, Any], workspace: Path, venv: Path, steps: list[Step]
) -> None:
    """Use the installed core's effective values; never parse/merge profile YAML here."""
    selection = context.get("selection")
    if not isinstance(selection, dict) or selection.get("config_path") != str(workspace):
        raise SetupFailure(
            "profile-workspace-mismatch",
            "Selected profile must resolve to the bootstrap --workspace path.",
            steps,
        )
    configuration = context.get("configuration")
    values = configuration.get("values") if isinstance(configuration, dict) else None
    setup = values.get("setup") if isinstance(values, dict) else None
    configured_venv = setup.get("venv") if isinstance(setup, dict) else None
    if configured_venv is not None and configured_venv != str(venv):
        raise SetupFailure(
            "profile-venv-mismatch",
            "Pass --venv matching effective setup.venv before binding hooks.",
            steps,
        )


def _verify_portable_runtime(
    context: dict[str, Any], launcher: Path, hook_launcher: Path, steps: list[Step]
) -> None:
    """Verify the PATH runtime and registry that the unchanged hook will use."""
    for name, expected in (
        ("agent-knowledge", launcher),
        (_DESCRIPTOR_HOOK_COMMAND, hook_launcher),
    ):
        found = shutil.which(name)
        if found is None or Path(found).resolve() != expected.resolve():
            raise SetupFailure(
                "portable-launcher-unavailable",
                f"PATH must resolve {name} to the selected runtime before portable binding.",
                steps,
                "Put the selected venv bin directory on PATH in the harness/container environment.",
            )
    selection = context.get("selection")
    assert isinstance(selection, dict) and isinstance(selection.get("profile"), str)
    try:
        actual = _json_result(
            [str(launcher), "--profile", selection["profile"], "context"],
            cwd=Path.cwd(),
            name="portable-profile",
            steps=steps,
        )
        if actual.get("selection") == selection:
            return
    except SetupFailure:
        pass
    raise SetupFailure(
        "portable-registry-mismatch",
        "The portable hook's runtime registry does not resolve the verified profile selection.",
        steps,
        "Use the standard user registry or set AGENT_KNOWLEDGE_SETTINGS to the selected absolute "
        "registry path in this environment. Explicit --settings is not embedded in portable hooks.",
    )


def _portable_environment_report(
    profile: str, targets: tuple[str, ...], file_value: str, variables: list[dict[str, str]]
) -> dict[str, object]:
    """Report runtime-resolved activation without writing machine-specific launchers."""
    providers: dict[str, object] = {}
    for target in _TARGET_ORDER:
        if target not in targets:
            providers[target] = {"status": "not-bound"}
        elif target == "claude":
            providers[target] = {
                "status": "native-session-start",
                "detail": "New sessions resolve the named local profile through CLAUDE_ENV_FILE; "
                "resumed sessions retain their first credential declaration.",
            }
        else:
            providers[target] = {
                "status": "cli-launch",
                "command": _shell_command(
                    [
                        _DESCRIPTOR_HOOK_COMMAND,
                        "--profile",
                        profile,
                        "--launch-provider",
                        target,
                        "--",
                    ]
                ),
                "app": "No generic per-task env-file injection; use native stores or "
                "explicit credentialed-command sourcing.",
            }
    return {
        "status": "ready",
        "profile": profile,
        "environment_file": file_value,
        "variables": variables,
        "session_policy": "one-profile-per-session",
        "launcher": None,
        "providers": providers,
    }


def run_setup(
    *,
    workspace: Path,
    venv: Path | None,
    package: Path,
    consumer: Path,
    target_text: str,
    profile: str | None = None,
    settings: Path | None = None,
    apm_mode: str = "managed",
    portable_hooks: bool = False,
) -> dict[str, Any]:
    steps: list[Step] = []
    if apm_mode not in {"managed", "prepare", "bind"}:
        raise SetupFailure("unsupported-apm-mode", "Choose managed, prepare or bind.", steps)
    if portable_hooks and profile is None:
        raise SetupFailure(
            "portable-profile-required", "Portable hooks require an explicit --profile.", steps
        )
    workspace_path = _existing_file(workspace, "--workspace")
    if settings is not None and profile is None:
        raise SetupFailure(
            "profile-required",
            "Setup requires an explicit --profile with --settings.",
            steps,
        )
    settings_path = _existing_file(settings, "--settings") if settings is not None else None
    venv_path = venv if venv is not None else workspace_path.parent / ".agent-knowledge-venv"
    package_path = _absolute(package, "--package")
    if not package_path.is_file() and not package_path.is_dir():
        raise SetupFailure("missing-path", "--package does not exist.", steps)
    consumer_path = _existing_directory(consumer, "--consumer")
    targets = _targets(target_text)
    uv = shutil.which("uv")
    if uv is None:
        raise SetupFailure("uv-unavailable", "Install uv and retry setup.", steps)
    apm = shutil.which("apm") if targets and apm_mode == "managed" else None
    if targets and apm_mode == "managed" and apm is None:
        raise SetupFailure("apm-unavailable", "Install the APM CLI and retry setup.", steps)

    python, launcher = _prepare_venv(venv_path, uv, steps)
    _run(
        [uv, "pip", "install", "--python", str(python), str(package_path)],
        cwd=consumer_path,
        name="runtime-install",
        steps=steps,
    )
    _, launcher = _venv_executables(_absolute(venv_path, "--venv"))
    if not launcher.is_file():
        raise SetupFailure(
            "launcher-missing",
            "The installed environment has no agent-knowledge launcher.",
            steps,
        )
    hook_launcher = _venv_hook_executable(_absolute(venv_path, "--venv"))
    if not hook_launcher.is_file():
        raise SetupFailure(
            "hook-launcher-missing",
            "The installed environment has no agent-knowledge-hook launcher. "
            "Reinstall the package into the verified Python 3.11+ environment and retry setup.",
            steps,
        )
    describe = _json_result(
        [str(launcher), "describe"], cwd=consumer_path, name="describe", steps=steps
    )
    selector = ["--config", str(workspace_path)]
    if profile is not None:
        selector = ["--profile", profile]
        if settings_path is not None:
            selector = ["--settings", str(settings_path), *selector]
    context = _json_result(
        [str(launcher), *selector, "context"],
        cwd=consumer_path,
        name="context",
        steps=steps,
    )
    _verify_selection(context, workspace_path, _absolute(venv_path, "--venv"), steps)
    doctor = _json_result(
        [str(launcher), *selector, "doctor"],
        cwd=consumer_path,
        name="doctor",
        steps=steps,
        allow_error=True,
        allow_environment_pending=True,
    )
    readiness = doctor.get("readiness")
    if not isinstance(readiness, dict) or readiness.get("read") != "ready":
        raise SetupFailure(
            "doctor-not-ready",
            "Configured doctor did not report read readiness.",
            steps,
        )
    if portable_hooks and apm_mode != "prepare":
        _verify_portable_runtime(context, launcher, hook_launcher, steps)
    environment_report = _environment_launcher(
        context,
        _absolute(venv_path, "--venv"),
        steps,
        consumer=consumer_path,
        targets=() if apm_mode == "prepare" else targets,
        environment_readiness=readiness.get("environment"),
        portable_profile=profile if portable_hooks and apm_mode != "prepare" else None,
    )
    hook_report: dict[str, object] = {"status": "disabled", "targets": []}
    lock_report: dict[str, str] = {"status": "disabled"}
    if targets and apm_mode == "prepare":
        hook_report = {"status": "pending", "targets": list(targets)}
    elif targets:
        target_arg = ",".join(targets)
        if apm_mode == "managed":
            assert apm is not None
            _run(
                [apm, "install", "--target", target_arg, "--no-policy"],
                cwd=consumer_path,
                name="apm-install",
                steps=steps,
            )
        _, installed_package = _hook_package(consumer_path, python=python)
        _bind_package_hook(installed_package, hook_launcher, portable=portable_hooks)
        if apm_mode == "managed":
            assert apm is not None
            _run(
                [apm, "compile", "--target", target_arg, "--force-instructions"],
                cwd=consumer_path,
                name="apm-compile",
                steps=steps,
            )
        hook_report = _configure_hook_registrations(
            consumer_path,
            targets,
            hook_launcher,
            environment=environment_report,
            python=python,
            portable_profile=profile if portable_hooks else None,
        )
        if "copilot" in targets:
            registrations = hook_report.get("registrations")
            copilot_registration = (
                registrations.get("copilot") if isinstance(registrations, dict) else None
            )
            copilot_value = (
                copilot_registration.get("path") if isinstance(copilot_registration, dict) else None
            )
            if not isinstance(copilot_value, str):
                raise SetupFailure(
                    "hook-registration-missing",
                    "Setup could not resolve the configured Copilot hook path.",
                    steps,
                )
            copilot_path = Path(copilot_value)
            lock_report = _update_copilot_lock_hash(consumer_path, copilot_path, steps)

    return {
        "schema": "knowledge-setup-runtime.v1",
        "status": "ok",
        "workspace": str(workspace_path),
        "selection": context.get("selection"),
        "configuration": context.get("configuration"),
        "venv": str(_absolute(venv_path, "--venv")),
        "launcher": str(launcher),
        "hook_launcher": str(hook_launcher),
        "consumer": str(consumer_path),
        "targets": list(targets),
        "apm": {
            "mode": apm_mode,
            "status": hook_report["status"],
            "installation_owner": "setup" if apm_mode == "managed" else "repository",
            "compilation_owner": "setup" if apm_mode == "managed" else "repository",
            "instruction_verification": "apm-compile"
            if apm_mode == "managed" and targets
            else "repository-required",
        },
        "describe": {
            "status": describe.get("status"),
            "resources": describe.get("resources"),
        },
        "doctor": {
            "status": doctor.get("status"),
            "readiness": readiness,
            "diagnostics": doctor.get("diagnostics", []),
            "command": _shell_command([str(launcher), *selector, "doctor"]),
        },
        "environment": environment_report,
        "steps": [asdict(step) for step in steps],
        "automation_registration": "native-harness",
        "hooks": hook_report,
        "apm_lock": lock_report,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        report = run_setup(
            workspace=args.workspace,
            venv=args.venv,
            package=args.package,
            consumer=args.consumer,
            target_text=args.targets,
            profile=args.profile,
            settings=args.settings,
            apm_mode=args.apm_mode,
            portable_hooks=args.portable_hooks,
        )
    except SetupFailure as error:
        diagnostic = {"code": error.code, "message": str(error)}
        if error.remediation is not None:
            diagnostic["remediation"] = error.remediation
        payload = {
            "schema": "knowledge-setup-runtime.v1",
            "status": "error",
            "diagnostic": diagnostic,
            "steps": [asdict(step) for step in error.steps],
        }
        print(
            json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
