"""Inspect one selected profile environment without retaining credential values."""

import hashlib
import json
import os
import re
import shlex
import stat
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from agent_knowledge.domain.profiles import (
    PROFILE_ENVIRONMENT_SESSION_MAX_BYTES,
    EnvironmentVariable,
    is_safe_environment_target,
)
from agent_knowledge.domain.validation import ValidationError

from .errors import AdapterError
from .filesystem import open_directory
from .profiles import ResolvedProfileEnvironment

ENVIRONMENT_MAX_BYTES = 65_536
SESSION_PIN_MAX_BYTES = PROFILE_ENVIRONMENT_SESSION_MAX_BYTES
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True, slots=True)
class EnvironmentInspection:
    """Retain assignment names only; secret bytes die with the inspection call."""

    names: frozenset[str]


def inspect_environment(environment: ResolvedProfileEnvironment) -> EnvironmentInspection:
    """Validate a private dotenv file as data and return only its assignment names."""
    return EnvironmentInspection(frozenset(_parse_dotenv(_read_private_file(environment))))


def mapped_environment_values(
    environment: ResolvedProfileEnvironment,
) -> tuple[tuple[str, str], ...]:
    """Read declared values transiently for a provider's native environment channel."""
    assignments = _parse_dotenv(_read_private_file(environment))
    missing = [
        variable.from_env
        for variable in environment.variables
        if variable.from_env not in assignments
    ]
    if missing:
        raise ValidationError(
            "environment-variable-missing",
            "environment.variables",
            "A declared source environment variable is not assigned.",
        )
    return tuple(
        (variable.expose_as, assignments[variable.from_env]) for variable in environment.variables
    )


def shell_environment_exports(environment: ResolvedProfileEnvironment) -> bytes:
    """Render declared values as shell-safe exports for immediate, private capture."""
    return "".join(
        f"export {name}={shlex.quote(value)}\n"
        for name, value in mapped_environment_values(environment)
    ).encode("utf-8")


def pin_session_environment(
    environment: ResolvedProfileEnvironment, *, state_directory: Path, session_id: str
) -> ResolvedProfileEnvironment:
    """Bind a Claude session to its first value-free environment declaration."""
    if not state_directory.is_absolute() or not session_id:
        raise AdapterError(
            "environment-session-state-invalid",
            str(state_directory),
            "Claude environment session state is incomplete.",
        )
    _ensure_private_directory(state_directory)
    pin = state_directory / f"{hashlib.sha256(session_id.encode()).hexdigest()}.json"
    if not pin.exists():
        data = _session_pin_bytes(environment)
        if len(data) > SESSION_PIN_MAX_BYTES:
            raise AdapterError(
                "environment-session-state-invalid",
                str(pin),
                "Claude environment session state is oversized.",
            )
        _publish_session_pin(pin, data)
    return _read_session_pin(pin)


def append_claude_environment(destination: Path, environment: ResolvedProfileEnvironment) -> None:
    """Create or append Claude's private provider-owned session file."""
    if not destination.is_absolute():
        raise AdapterError(
            "claude-environment-file-unsafe",
            str(destination),
            "Claude's environment file must be an absolute private regular file.",
        )
    try:
        destination = destination.parent.resolve(strict=True) / destination.name
    except (OSError, RuntimeError) as error:
        raise AdapterError(
            "claude-environment-file-unavailable",
            str(destination),
            "Claude's environment file could not be resolved safely.",
        ) from error
    content = shell_environment_exports(environment)
    descriptor = -1
    original_size: int | None = None
    try:
        with open_directory(destination.parent) as directory:
            descriptor = _open_claude_environment(directory, destination.name)
            opened = os.fstat(descriptor)
            current = os.stat(destination.name, dir_fd=directory, follow_symlinks=False)
            _require_private_regular(opened, destination, "Claude environment file")
            if _identity(opened) != _identity(current):
                raise AdapterError(
                    "claude-environment-file-changed",
                    str(destination),
                    "Claude's environment file changed during access.",
                )
            original_size = opened.st_size
            _write_all(descriptor, content)
            os.fsync(descriptor)
            after = os.fstat(descriptor)
            current = os.stat(destination.name, dir_fd=directory, follow_symlinks=False)
            if _identity(after) != _identity(current):
                raise AdapterError(
                    "claude-environment-file-changed",
                    str(destination),
                    "Claude's environment file changed while being updated.",
                )
    except AdapterError:
        if descriptor >= 0 and original_size is not None:
            with suppress(OSError):
                os.ftruncate(descriptor, original_size)
        raise
    except OSError as error:
        if descriptor >= 0 and original_size is not None:
            with suppress(OSError):
                os.ftruncate(descriptor, original_size)
        raise AdapterError(
            "claude-environment-file-unavailable",
            str(destination),
            "Claude's environment file could not be updated safely.",
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _open_claude_environment(directory: int, name: str) -> int:
    existing_flags = os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    try:
        return os.open(name, existing_flags, dir_fd=directory)
    except FileNotFoundError:
        try:
            return os.open(
                name,
                existing_flags | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=directory,
            )
        except FileExistsError:
            return os.open(name, existing_flags, dir_fd=directory)


def parse_dotenv_names(data: bytes) -> frozenset[str]:
    """Parse a deliberately small dotenv grammar without evaluating any value."""
    return frozenset(_parse_dotenv(data))


def _parse_dotenv(data: bytes) -> dict[str, str]:
    """Parse strict literal assignments while keeping values inside the adapter."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(
            "environment-file-invalid", "environment.file", "Environment file must be UTF-8."
        ) from error
    if "\x00" in text:
        raise ValidationError(
            "environment-file-invalid", "environment.file", "Environment file contains NUL."
        )
    assignments: dict[str, str] = {}
    for number, authored in enumerate(text.splitlines(), start=1):
        if not authored.strip() or authored.startswith("#"):
            continue
        line = authored[7:] if authored.startswith("export ") else authored
        name, separator, value = line.partition("=")
        location = f"environment.file:{number}"
        if not separator or _NAME.fullmatch(name) is None:
            raise ValidationError(
                "environment-file-invalid", location, "Expected a NAME=value assignment."
            )
        if name in assignments:
            raise ValidationError(
                "environment-file-invalid", location, "Environment assignment is duplicated."
            )
        if not value:
            raise ValidationError(
                "environment-file-invalid", location, "Environment assignment is empty."
            )
        if value[0] in {"'", '"'} or value[-1] in {"'", '"'}:
            raise ValidationError(
                "environment-file-invalid",
                location,
                "Environment values are literal; remove quote wrappers.",
            )
        assignments[name] = value
    return assignments


def _read_private_file(environment: ResolvedProfileEnvironment) -> bytes:
    path = environment.file.absolute()
    descriptor = -1
    try:
        with open_directory(path.parent) as directory:
            descriptor = os.open(
                path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=directory,
            )
            before = os.fstat(descriptor)
            _require_private_regular(before, path, "Environment file")
            if before.st_size > ENVIRONMENT_MAX_BYTES:
                raise AdapterError(
                    "environment-file-too-large",
                    str(path),
                    f"Environment file exceeds {ENVIRONMENT_MAX_BYTES} bytes.",
                    exit_code=2,
                )
            chunks: list[bytes] = []
            remaining = ENVIRONMENT_MAX_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(16_384, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > ENVIRONMENT_MAX_BYTES:
                raise AdapterError(
                    "environment-file-too-large",
                    str(path),
                    f"Environment file exceeds {ENVIRONMENT_MAX_BYTES} bytes.",
                    exit_code=2,
                )
            after = os.fstat(descriptor)
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if _identity(before) != _identity(after) or _identity(after) != _identity(current):
                raise AdapterError(
                    "environment-file-changed",
                    str(path),
                    "Environment file changed while being inspected.",
                )
            return data
    except AdapterError:
        raise
    except OSError as error:
        raise AdapterError(
            "environment-file-unavailable",
            str(path),
            "Cannot safely read the configured environment file.",
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _require_private_regular(value: os.stat_result, path: Path, label: str) -> None:
    current_uid = getattr(os, "getuid", lambda: value.st_uid)()
    if not stat.S_ISREG(value.st_mode) or value.st_uid != current_uid:
        raise AdapterError(
            "environment-file-unsafe",
            str(path),
            f"{label} must be a current-user-owned regular file.",
            exit_code=2,
        )
    if stat.S_IMODE(value.st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
        raise AdapterError(
            "environment-file-permissions",
            str(path),
            f"{label} must not grant group or world permissions.",
            exit_code=2,
        )


def _ensure_private_directory(path: Path) -> None:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open_directory(path) as descriptor:
            value = os.fstat(descriptor)
            current_uid = getattr(os, "getuid", lambda: value.st_uid)()
            if value.st_uid != current_uid or stat.S_IMODE(value.st_mode) & (
                stat.S_IRWXG | stat.S_IRWXO
            ):
                raise AdapterError(
                    "environment-session-state-unsafe",
                    str(path),
                    "Claude environment session state must be private to the current user.",
                )
    except AdapterError:
        raise
    except OSError as error:
        raise AdapterError(
            "environment-session-state-unavailable",
            str(path),
            "Claude environment session state is unavailable.",
        ) from error


def _session_pin_bytes(environment: ResolvedProfileEnvironment) -> bytes:
    return json.dumps(
        {
            "schema": "profile-environment-session.v1",
            "file": str(environment.file),
            "variables": [
                {"from_env": variable.from_env, "expose_as": variable.expose_as}
                for variable in environment.variables
            ],
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _publish_session_pin(path: Path, data: bytes) -> None:
    if len(data) > SESSION_PIN_MAX_BYTES:
        raise AdapterError(
            "environment-session-state-invalid",
            str(path),
            "Claude environment session state is oversized.",
        )
    temporary = f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = -1
    try:
        with open_directory(path.parent) as directory:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory,
            )
            _write_all(descriptor, data)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            try:
                os.link(
                    temporary,
                    path.name,
                    src_dir_fd=directory,
                    dst_dir_fd=directory,
                    follow_symlinks=False,
                )
                os.fsync(directory)
            except FileExistsError:
                pass
            finally:
                os.unlink(temporary, dir_fd=directory)
    except AdapterError:
        raise
    except OSError as error:
        raise AdapterError(
            "environment-session-state-unavailable",
            str(path),
            "Claude environment session state could not be recorded.",
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_session_pin(path: Path) -> ResolvedProfileEnvironment:
    descriptor = -1
    try:
        with open_directory(path.parent) as directory:
            descriptor = os.open(
                path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=directory,
            )
            before = os.fstat(descriptor)
            _require_private_regular(before, path, "Claude environment session pin")
            if before.st_size > SESSION_PIN_MAX_BYTES:
                raise AdapterError(
                    "environment-session-state-invalid",
                    str(path),
                    "Claude environment session state is oversized.",
                )
            chunks: list[bytes] = []
            remaining = SESSION_PIN_MAX_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(4_096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            after = os.fstat(descriptor)
            current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if (
                len(data) > SESSION_PIN_MAX_BYTES
                or _identity(before) != _identity(after)
                or _identity(after) != _identity(current)
            ):
                raise AdapterError(
                    "environment-session-state-invalid",
                    str(path),
                    "Claude environment session state changed during access.",
                )
    except AdapterError:
        raise
    except OSError as error:
        raise AdapterError(
            "environment-session-state-unavailable",
            str(path),
            "Claude environment session state could not be read.",
        ) from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        value = json.loads(data, object_pairs_hook=_reject_duplicate_json_keys)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise AdapterError(
            "environment-session-state-invalid",
            str(path),
            "Claude environment session state is invalid.",
        ) from error
    if not isinstance(value, dict) or set(value) != {"schema", "file", "variables"}:
        raise AdapterError(
            "environment-session-state-invalid",
            str(path),
            "Claude environment session state is invalid.",
        )
    file_value = value.get("file")
    variables_value = value.get("variables")
    if (
        value.get("schema") != "profile-environment-session.v1"
        or not isinstance(file_value, str)
        or not Path(file_value).is_absolute()
        or not isinstance(variables_value, list)
        or not variables_value
    ):
        raise AdapterError(
            "environment-session-state-invalid",
            str(path),
            "Claude environment session state is invalid.",
        )
    variables: list[EnvironmentVariable] = []
    for index, item in enumerate(variables_value):
        if not isinstance(item, dict) or set(item) != {"from_env", "expose_as"}:
            raise AdapterError(
                "environment-session-state-invalid",
                str(path),
                "Claude environment session state is invalid.",
            )
        source = item.get("from_env")
        target = item.get("expose_as")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or _NAME.fullmatch(source) is None
            or not is_safe_environment_target(target)
        ):
            raise AdapterError(
                "environment-session-state-invalid",
                str(path),
                "Claude environment session state is invalid.",
            )
        variables.append(EnvironmentVariable(str(index), source, target, "provider binding"))
    if len({item.from_env for item in variables}) != len(variables) or len(
        {item.expose_as for item in variables}
    ) != len(variables):
        raise AdapterError(
            "environment-session-state-invalid",
            str(path),
            "Claude environment session state is invalid.",
        )
    return ResolvedProfileEnvironment(Path(file_value), tuple(variables))


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON object key")
        value[key] = item
    return value


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("short write")
        view = view[written:]


__all__ = [
    "ENVIRONMENT_MAX_BYTES",
    "EnvironmentInspection",
    "append_claude_environment",
    "inspect_environment",
    "mapped_environment_values",
    "parse_dotenv_names",
    "pin_session_environment",
    "shell_environment_exports",
]
