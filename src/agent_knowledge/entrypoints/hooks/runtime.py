"""Run the installed provider adapter as a bounded advisory hook."""

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
from collections.abc import Sequence
from pathlib import Path
from typing import Never, cast

from agent_knowledge.domain.hooks import HookEventType, HookProvider
from agent_knowledge.domain.profiles import EnvironmentVariable, is_safe_environment_target
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.entrypoints.hooks.adapters import adapt_payload, render_decision
from agent_knowledge.infrastructure.environment import (
    append_claude_environment,
    mapped_environment_values,
    pin_session_environment,
    pinned_session_environment,
)
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.profiles import (
    ResolvedProfileEnvironment,
    resolve_profile_environment,
)
from agent_knowledge.resources.hook_messages import CREDENTIAL_ACTIVATION_FAILURE_MESSAGE

_MAX_INPUT_BYTES = 1_048_576
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Parser(argparse.ArgumentParser):
    """Keep optional diagnostics out of provider stdout."""

    def error(self, message: str) -> Never:
        raise ValueError(message)


def _parser() -> Parser:
    parser = Parser(prog="agent-knowledge-hook", description="Advisory lifecycle hook.")
    parser.add_argument("--provider", choices=[provider.value for provider in HookProvider])
    parser.add_argument("--profile", help="Exact profile name resolved when the provider starts.")
    parser.add_argument("--settings", type=Path, help="Explicit local profile registry.")
    parser.add_argument("--environment-file", type=Path)
    parser.add_argument("--environment-state-directory", type=Path)
    parser.add_argument(
        "--environment-map",
        action="append",
        default=[],
        metavar="SOURCE=TARGET",
        help="Map one strict dotenv source name into Claude's session environment.",
    )
    parser.add_argument("--launch-provider", choices=("codex", "copilot"), help=argparse.SUPPRESS)
    parser.add_argument("provider_arguments", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return parser


def _read_payload() -> object | None:
    try:
        data = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    except (AttributeError, OSError):
        return None
    if len(data) > _MAX_INPUT_BYTES:
        return None
    try:
        return cast(object, json.loads(data))
    except (TypeError, json.JSONDecodeError):
        return None


def main(argv: Sequence[str] | None = None) -> int:
    """Emit one JSON response when eligible; every failure remains fail-open."""
    try:
        args = _parser().parse_args(argv)
        if args.launch_provider is not None:
            return _launch_provider(
                args.launch_provider,
                args.environment_file,
                args.environment_map,
                args.provider_arguments,
                profile=args.profile,
                settings=args.settings,
            )
        adapted = adapt_payload(_read_payload(), provider=args.provider)
        if adapted is None:
            return 0
        activation_failed = False
        if (
            adapted.provider is HookProvider.CLAUDE
            and adapted.event.event is HookEventType.SESSION_START
            and (
                args.profile is not None
                or args.settings is not None
                or (
                    args.environment_file is not None
                    and args.environment_state_directory is not None
                )
            )
        ):
            try:
                _activate_claude_environment(args, adapted.event.session_id or "")
            except (AdapterError, OSError, ValidationError, ValueError, TypeError):
                # Credential activation is fail-closed without suppressing the
                # advisory discovery/reflection response.
                activation_failed = True
        result = render_decision(adapted)
        if activation_failed:
            _append_activation_failure(result)
        if result:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    except (AdapterError, BrokenPipeError, OSError, ValidationError, ValueError, TypeError):
        return 0
    return 0


def _validate_environment_arguments(
    path: Path | None, mappings: Sequence[str], profile: str | None, settings: Path | None
) -> None:
    if settings is not None and profile is None:
        raise ValueError("Hook --settings requires an explicit --profile.")
    if profile is not None and (path is not None or mappings):
        raise ValueError("Use --profile or explicit environment arguments, not both.")


def _activate_claude_environment(args: argparse.Namespace, session_id: str) -> None:
    _validate_environment_arguments(
        args.environment_file, args.environment_map, args.profile, args.settings
    )
    state = args.environment_state_directory
    if state is None:
        state = Path.home() / ".local/state/agent-knowledge/claude-environment"
    environment = None
    if args.profile is not None:
        if session_id:
            environment = pinned_session_environment(state_directory=state, session_id=session_id)
        if environment is None:
            environment = resolve_profile_environment(args.settings, args.profile)
    else:
        environment = _hook_environment(args.environment_file, args.environment_map)
    if environment is None:
        return
    environment = pin_session_environment(environment, state_directory=state, session_id=session_id)
    destination = os.environ.get("CLAUDE_ENV_FILE")
    if not destination:
        raise ValueError("Claude did not provide its environment channel.")
    append_claude_environment(Path(destination), environment)


def _launch_provider(
    provider: str,
    path: Path | None,
    mappings: Sequence[str],
    arguments: Sequence[str],
    *,
    profile: str | None = None,
    settings: Path | None = None,
) -> int:
    """Load mapped values and replace this process with one supported provider."""
    if path is None and profile is None:
        return 2
    try:
        _validate_environment_arguments(path, mappings, profile, settings)
        environment = dict(os.environ)
        if profile is not None:
            selected = resolve_profile_environment(settings, profile)
        else:
            assert path is not None
            selected = _hook_environment(path, mappings)
        values = mapped_environment_values(selected) if selected is not None else ()
        for name in tuple(environment):
            if name.casefold().startswith("_ak_"):
                environment.pop(name)
        executable = shutil.which(provider, path=environment.get("PATH"))
        if executable is None:
            print(CREDENTIAL_ACTIVATION_FAILURE_MESSAGE, file=sys.stderr)
            return 2
        forwarded = list(arguments)
        if forwarded[:1] == ["--"]:
            forwarded.pop(0)
        if provider == "copilot" and values:
            return _run_copilot(executable, forwarded, environment, values)
        environment.update(values)
        os.execve(executable, [executable, *forwarded], environment)
    except (AdapterError, OSError, ValidationError, ValueError, TypeError):
        print(CREDENTIAL_ACTIVATION_FAILURE_MESSAGE, file=sys.stderr)
        return 2
    return 2


def _run_copilot(
    executable: str,
    arguments: Sequence[str],
    environment: dict[str, str],
    values: Sequence[tuple[str, str]],
) -> int:
    """Restore targets in Bash while exposing only protected internal aliases upstream."""
    protected = ",".join(f"_AK_COPILOT_VALUE_{index}" for index, _ in enumerate(values))
    if any(
        argument == "--no-bash-env"
        or argument.startswith("--bash-env")
        or argument.startswith("--secret-env-vars")
        for argument in arguments
    ):
        raise ValueError("Copilot environment protection flags are setup-owned.")
    protected_arguments = [
        "--bash-env=on",
        f"--secret-env-vars={protected}",
        *arguments,
    ]
    descriptor, raw_path = tempfile.mkstemp(prefix="agent-knowledge-copilot-", suffix=".sh")
    path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write("set +x\n")
            for name, value in values:
                stream.write(f"{name}={shlex.quote(value)}\nexport {name}\n")
            stream.write("unset BASH_ENV\n")
            stream.flush()
            os.fsync(stream.fileno())
        for index, (_, value) in enumerate(values):
            environment[f"_AK_COPILOT_VALUE_{index}"] = value
        environment["BASH_ENV"] = str(path)
        completed = subprocess.run(
            [executable, *protected_arguments],
            env=environment,
            check=False,
        )
        return completed.returncode
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)


def _append_activation_failure(result: dict[str, object]) -> None:
    """Add one value-free remediation to the provider's existing context channel."""
    specific = result.get("hookSpecificOutput")
    if isinstance(specific, dict):
        current = specific.get("additionalContext")
        if isinstance(current, str):
            specific["additionalContext"] = current + "\n\n" + CREDENTIAL_ACTIVATION_FAILURE_MESSAGE
            return
    current = result.get("additionalContext")
    if isinstance(current, str):
        result["additionalContext"] = current + "\n\n" + CREDENTIAL_ACTIVATION_FAILURE_MESSAGE


def _hook_environment(path: Path, mappings: Sequence[str]) -> ResolvedProfileEnvironment:
    """Validate setup-authored value-free hook arguments before reading the env file."""
    if not path.is_absolute() or not mappings:
        raise ValueError("Incomplete profile environment hook arguments.")
    variables: list[EnvironmentVariable] = []
    for index, mapping in enumerate(mappings):
        source, separator, target = mapping.partition("=")
        if (
            not separator
            or _ENVIRONMENT_NAME.fullmatch(source) is None
            or not is_safe_environment_target(target)
        ):
            raise ValueError("Invalid profile environment mapping.")
        variables.append(EnvironmentVariable(str(index), source, target, "provider binding"))
    if len({item.from_env for item in variables}) != len(variables) or len(
        {item.expose_as for item in variables}
    ) != len(variables):
        raise ValueError("Duplicate profile environment mapping.")
    return ResolvedProfileEnvironment(path, tuple(variables))


if __name__ == "__main__":
    raise SystemExit(main())
