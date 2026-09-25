"""Parse immutable named profiles and apply one explicit workspace overlay."""

import re
from dataclasses import asdict, dataclass

from .configuration import (
    SourceDefinition,
    WorkspaceDefinition,
    parse_source,
    parse_workspace,
    read_config_path,
)
from .validation import ValidationError, read_identifier, read_mapping, read_string, read_strings


@dataclass(frozen=True, slots=True)
class Override:
    """Retain one validated leaf or atomic source/list replacement."""

    path: tuple[str, ...]
    value: str | bool | int | tuple[str, ...] | tuple[SourceDefinition, ...]


@dataclass(frozen=True, slots=True)
class EnvironmentVariable:
    """Map one declared dotenv name to the name expected by a tool."""

    label: str
    from_env: str
    expose_as: str
    description: str


@dataclass(frozen=True, slots=True)
class ProfileEnvironment:
    """Describe an external credential file without retaining any values."""

    file: str
    variables: tuple[EnvironmentVariable, ...]


@dataclass(frozen=True, slots=True)
class Profile:
    """Name one base workspace and immutable local overrides."""

    name: str
    config: str
    overrides: tuple[Override, ...] = ()
    environment: ProfileEnvironment | None = None


@dataclass(frozen=True, slots=True)
class Profiles:
    """Describe a registry without selecting an implicit first entry."""

    profiles: tuple[Profile, ...]
    default_profile: str | None


def profile_name(value: object, path: str) -> str:
    """Require a literal profile slug rather than normalizing caller intent."""
    name = read_string(value, path)
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
        raise ValidationError("invalid-profile-name", path, "Use a lowercase profile slug.")
    return name


def parse_profiles(value: object) -> Profiles:
    """Validate registry metadata without opening any referenced workspace."""
    fields = read_mapping(value, "settings", {"schema_version", "profiles"}, {"default_profile"})
    if fields["schema_version"] != "knowledge-profiles.v1":
        raise ValidationError(
            "unsupported-schema", "settings.schema_version", "Expected knowledge-profiles.v1."
        )
    entries = fields["profiles"]
    if not isinstance(entries, dict):
        raise ValidationError(
            "invalid-type", "settings.profiles", "Expected a mapping of profiles."
        )
    profiles: list[Profile] = []
    for key, raw in entries.items():
        name = profile_name(key, "settings.profiles")
        path = f"settings.profiles.{name}"
        entry = read_mapping(raw, path, {"config"}, {"overrides", "environment"})
        profiles.append(
            Profile(
                name,
                read_config_path(entry["config"], path + ".config"),
                _overrides(entry.get("overrides", {}), path + ".overrides"),
                _environment(entry["environment"], path + ".environment")
                if "environment" in entry
                else None,
            )
        )
    default = (
        profile_name(fields["default_profile"], "settings.default_profile")
        if "default_profile" in fields
        else None
    )
    result = Profiles(tuple(sorted(profiles, key=lambda item: item.name)), default)
    if default is not None:
        select_profile(result, default)
    return result


_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PROFILE_ENVIRONMENT_SESSION_MAX_BYTES = 16_384
_RESERVED_ENVIRONMENT_TARGETS = frozenset(
    {
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


def is_safe_environment_target(name: str) -> bool:
    """Exclude names that control the provider, runtime or launcher process."""
    return (
        _ENVIRONMENT_NAME.fullmatch(name) is not None
        and not name.casefold().startswith("_ak_")
        and name not in _RESERVED_ENVIRONMENT_TARGETS
    )


def _json_string_size(value: str) -> int:
    """Measure json.dumps(..., ensure_ascii=True) without a serialization dependency."""
    size = 2
    for character in value:
        codepoint = ord(character)
        if character in {'"', "\\"} or character in {"\b", "\t", "\n", "\f", "\r"}:
            size += 2
        elif codepoint < 0x20 or 0x7F < codepoint <= 0xFFFF:
            size += 6
        elif codepoint > 0xFFFF:
            size += 12
        else:
            size += 1
    return size


def environment_session_pin_size(file: str, variables: tuple[EnvironmentVariable, ...]) -> int:
    """Measure the canonical value-free declaration without serializing it."""
    size = len(b'{"file":') + _json_string_size(file)
    size += len(b',"schema":"profile-environment-session.v1","variables":[')
    for index, variable in enumerate(variables):
        if index:
            size += 1
        size += len(b'{"expose_as":') + _json_string_size(variable.expose_as)
        size += len(b',"from_env":') + _json_string_size(variable.from_env) + 1
    return size + len(b"]}")


def validate_environment_session_declaration(
    file: str, variables: tuple[EnvironmentVariable, ...], path: str
) -> None:
    """Reject declarations that Claude could only fail-open at session start."""
    if environment_session_pin_size(file, variables) > PROFILE_ENVIRONMENT_SESSION_MAX_BYTES:
        raise ValidationError(
            "environment-session-state-too-large",
            path,
            "Environment mappings exceed the Claude session declaration limit.",
        )


def _environment(value: object, path: str) -> ProfileEnvironment:
    fields = read_mapping(value, path, {"file", "variables"})
    raw_variables = fields["variables"]
    if not isinstance(raw_variables, dict) or not raw_variables:
        raise ValidationError(
            "invalid-value", path + ".variables", "Configure at least one named variable."
        )
    variables: list[EnvironmentVariable] = []
    for raw_label, raw in raw_variables.items():
        label = profile_name(raw_label, path + ".variables")
        item_path = f"{path}.variables.{label}"
        item = read_mapping(raw, item_path, {"from_env", "expose_as", "description"})
        source = _environment_name_value(item["from_env"], item_path + ".from_env")
        target = _environment_target_value(item["expose_as"], item_path + ".expose_as")
        description = read_string(item["description"], item_path + ".description")
        if (
            description != description.strip()
            or len(description) > 600
            or any(character in description for character in ("\n", "\r"))
        ):
            raise ValidationError(
                "invalid-value",
                item_path + ".description",
                "Use at most 600 characters of single-line nonblank text.",
            )
        variables.append(EnvironmentVariable(label, source, target, description))
    sources = [item.from_env for item in variables]
    targets = [item.expose_as for item in variables]
    if len(set(sources)) != len(sources):
        raise ValidationError(
            "duplicate-value", path + ".variables", "Source environment names must be unique."
        )
    if len(set(targets)) != len(targets):
        raise ValidationError(
            "duplicate-value", path + ".variables", "Exposed environment names must be unique."
        )
    result = ProfileEnvironment(
        file=read_config_path(fields["file"], path + ".file"),
        variables=tuple(sorted(variables, key=lambda item: item.label)),
    )
    validate_environment_session_declaration(result.file, result.variables, path)
    return result


def _environment_name_value(value: object, path: str) -> str:
    name = read_string(value, path)
    if _ENVIRONMENT_NAME.fullmatch(name) is None:
        raise ValidationError(
            "invalid-environment-name", path, "Use an exact POSIX environment variable name."
        )
    return name


def _environment_target_value(value: object, path: str) -> str:
    name = _environment_name_value(value, path)
    if not is_safe_environment_target(name):
        raise ValidationError(
            "reserved-environment-name",
            path,
            "Choose a tool credential name that does not control the provider or runtime.",
        )
    return name


def select_profile(registry: Profiles, name: str | None) -> Profile:
    """Choose an exact explicit name or the declared default, never a fallback."""
    selected = name if name is not None else registry.default_profile
    if selected is None:
        raise ValidationError(
            "default-profile-required",
            "settings.default_profile",
            "Choose a profile or configure a default.",
        )
    for profile in registry.profiles:
        if profile.name == selected:
            return profile
    raise ValidationError("unknown-profile", "profile", f"Unknown profile {selected!r}.")


_GROUPS = {
    (): {"applicable_scopes", "sources", "signal_storage", "receipts", "setup"},
    ("signal_storage",): {"scaffold_root", "code_root"},
    ("receipts",): {"enabled", "directory", "retention_days"},
    ("setup",): {"venv", "harnesses", "automation"},
    ("setup", "automation"): {"name", "cadence", "timezone"},
}


def _overrides(value: object, path: str, prefix: tuple[str, ...] = ()) -> tuple[Override, ...]:
    fields = read_mapping(value, path, set(), _GROUPS[prefix])
    result: list[Override] = []
    for key, raw in sorted(fields.items()):
        location, field = prefix + (key,), path + "." + key
        if location in _GROUPS:
            result.extend(_overrides(raw, field, location))
            continue
        match key:
            case "sources":
                if not isinstance(raw, list) or not raw:
                    raise ValidationError(
                        "invalid-value", field, "Configure at least one complete source."
                    )
                parsed_sources = tuple(
                    parse_source(item, f"{field}[{i}]") for i, item in enumerate(raw)
                )
                if len({source.id for source in parsed_sources}) != len(parsed_sources):
                    raise ValidationError("duplicate-source", field, "Source IDs must be unique.")
                parsed: str | bool | int | tuple[str, ...] | tuple[SourceDefinition, ...] = (
                    parsed_sources
                )
            case "applicable_scopes" | "harnesses":
                values = (
                    () if raw == [] and key == "applicable_scopes" else read_strings(raw, field)
                )
                parsed = tuple(read_identifier(item, field) for item in values)
                if len(set(parsed)) != len(parsed):
                    raise ValidationError("duplicate-value", field, "Values must be unique.")
            case "scaffold_root" | "code_root" | "directory" | "venv":
                parsed = read_config_path(raw, field)
            case "enabled":
                if not isinstance(raw, bool):
                    raise ValidationError("invalid-type", field, "Expected a boolean.")
                parsed = raw
            case "retention_days":
                if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
                    raise ValidationError(
                        "invalid-value", field, "Retention must be a positive integer."
                    )
                parsed = raw
            case _:
                parsed = read_string(raw, field)
                if any(char in parsed for char in ("\n", "\r", "\x00")):
                    raise ValidationError("invalid-value", field, "Controls are unsupported.")
        result.append(Override(location, parsed))
    return tuple(result)


def _plain(value: object) -> object:
    if isinstance(value, SourceDefinition):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items() if item is not None}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    return value


def workspace_mapping(definition: WorkspaceDefinition) -> dict[str, object]:
    """Materialize workspace defaults for a single validated overlay and diagnostics."""
    result = _plain(asdict(definition))
    assert isinstance(result, dict)
    result["schema_version"] = "knowledge-workspace.v1"
    setup = result.get("setup")
    if isinstance(setup, dict) and setup.get("harnesses") == []:
        del setup["harnesses"]
    return result


def merge_overrides(base: WorkspaceDefinition, profile: Profile) -> WorkspaceDefinition:
    """Merge known mapping leaves and replace whole lists without mutating the base."""
    value = workspace_mapping(base)
    for override in profile.overrides:
        parent = value
        for key in override.path[:-1]:
            child = parent.setdefault(key, {})
            assert isinstance(child, dict)
            parent = child
        parent[override.path[-1]] = _plain(override.value)
    return parse_workspace(value)
