"""Validate explicit workspace definitions without consulting files or environment."""

import re
from dataclasses import dataclass

from .validation import ValidationError, read_identifier, read_mapping, read_string, read_strings


@dataclass(frozen=True, slots=True)
class Publication:
    """Configure a future Git publication target without accessing Git or credentials."""

    repository: str
    base_branch: str
    branch_prefix: str


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """Retain authored paths until an adapter resolves them against the config file."""

    id: str
    root: str
    catalog: str
    publication: Publication | None = None


@dataclass(frozen=True, slots=True)
class SignalStorageDefinition:
    """Declare durable signal and originating code roots independently of knowledge."""

    scaffold_root: str
    code_root: str


@dataclass(frozen=True, slots=True)
class AutomationDefinition:
    """Describe a native harness task without storing provider credentials."""

    name: str
    cadence: str
    timezone: str


@dataclass(frozen=True, slots=True)
class SetupDefinition:
    """Keep first-run bootstrap preferences separate from runtime state."""

    venv: str | None = None
    harnesses: tuple[str, ...] = ()
    automation: AutomationDefinition | None = None


@dataclass(frozen=True, slots=True)
class ReceiptDefinition:
    """Configure diagnostics while retaining required compounding evidence."""

    enabled: bool = True
    directory: str = "./ai/usage"
    retention_days: int = 30


@dataclass(frozen=True, slots=True)
class WorkspaceDefinition:
    """Record explicitly assigned scopes and sources without inferring membership."""

    workspace_id: str
    applicable_scopes: tuple[str, ...]
    sources: tuple[SourceDefinition, ...]
    signal_storage: SignalStorageDefinition | None = None
    setup: SetupDefinition | None = None
    receipts: ReceiptDefinition = ReceiptDefinition()


def parse_workspace(value: object) -> WorkspaceDefinition:
    """Validate a decoded workspace; leave availability and catalog checks to adapters."""
    fields = read_mapping(
        value,
        "workspace",
        {"schema_version", "workspace_id", "applicable_scopes", "sources"},
        {"signal_storage", "setup", "receipts"},
    )
    if (
        read_string(fields["schema_version"], "workspace.schema_version")
        != "knowledge-workspace.v1"
    ):
        raise ValidationError(
            "unsupported-schema", "workspace.schema_version", "Expected knowledge-workspace.v1."
        )
    raw_scopes = fields["applicable_scopes"]
    scopes = () if raw_scopes == [] else read_strings(raw_scopes, "workspace.applicable_scopes")
    applicable_scopes = tuple(
        _registered_id(scope, f"workspace.applicable_scopes[{index}]")
        for index, scope in enumerate(scopes)
    )
    raw_sources = fields["sources"]
    if not isinstance(raw_sources, list):
        raise ValidationError("invalid-type", "workspace.sources", "Expected a list of sources.")
    if not raw_sources:
        raise ValidationError(
            "invalid-value",
            "workspace.sources",
            "Configure at least one source; its corpus may be empty.",
        )
    sources: list[SourceDefinition] = []
    source_ids: set[str] = set()
    for index, raw_source in enumerate(raw_sources):
        source = parse_source(raw_source, f"workspace.sources[{index}]")
        if source.id in source_ids:
            raise ValidationError(
                "duplicate-source", f"workspace.sources[{index}].id", "Source IDs must be unique."
            )
        source_ids.add(source.id)
        sources.append(source)
    storage = None
    if "signal_storage" in fields:
        raw_storage = read_mapping(
            fields["signal_storage"], "workspace.signal_storage", {"scaffold_root", "code_root"}
        )
        storage = SignalStorageDefinition(
            scaffold_root=read_config_path(
                raw_storage["scaffold_root"], "workspace.signal_storage.scaffold_root"
            ),
            code_root=read_config_path(
                raw_storage["code_root"], "workspace.signal_storage.code_root"
            ),
        )
    setup = _parse_setup(fields["setup"], "workspace.setup") if "setup" in fields else None
    return WorkspaceDefinition(
        workspace_id=read_identifier(fields["workspace_id"], "workspace.workspace_id"),
        applicable_scopes=applicable_scopes,
        sources=tuple(sources),
        signal_storage=storage,
        setup=setup,
        receipts=_parse_receipts(fields.get("receipts", {})),
    )


def _parse_receipts(value: object) -> ReceiptDefinition:
    path = "workspace.receipts"
    fields = read_mapping(value, path, set(), {"enabled", "directory", "retention_days"})
    enabled = fields.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValidationError("invalid-type", f"{path}.enabled", "Expected a boolean.")
    retention_days = fields.get("retention_days", 30)
    if isinstance(retention_days, bool) or not isinstance(retention_days, int):
        raise ValidationError("invalid-type", f"{path}.retention_days", "Expected an integer.")
    if retention_days < 1:
        raise ValidationError(
            "invalid-value", f"{path}.retention_days", "Retention must be at least one day."
        )
    return ReceiptDefinition(
        enabled=enabled,
        directory=read_config_path(fields.get("directory", "./ai/usage"), f"{path}.directory"),
        retention_days=retention_days,
    )


def read_config_path(value: object, path: str) -> str:
    """Accept literal POSIX paths, including parent traversal, without expansion syntax."""
    result = read_string(value, path)
    if (
        result != result.strip()
        or result.startswith("~")
        or any(character in result for character in ("\\", "$", "\n", "\r"))
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", result)
    ):
        raise ValidationError(
            "invalid-path",
            path,
            "Use a literal local POSIX path; shell variables, home expansion "
            "and URLs are unsupported.",
        )
    return result


def _registered_id(value: object, path: str) -> str:
    identifier = read_identifier(value, path)
    if identifier == "any" or identifier.startswith("family:"):
        raise ValidationError(
            "reserved-identifier",
            path,
            "Reserved applicability syntax cannot identify a scope or source.",
        )
    return identifier


def parse_source(value: object, path: str) -> SourceDefinition:
    """Validate one complete source record, including its optional publication."""
    fields = read_mapping(value, path, {"id", "root", "catalog"}, {"publication"})
    return SourceDefinition(
        id=_registered_id(fields["id"], f"{path}.id"),
        root=read_config_path(fields["root"], f"{path}.root"),
        catalog=read_config_path(fields["catalog"], f"{path}.catalog"),
        publication=_parse_publication(fields["publication"], f"{path}.publication")
        if "publication" in fields
        else None,
    )


def _parse_publication(value: object, path: str) -> Publication:
    fields = read_mapping(value, path, {"repository", "base_branch", "branch_prefix"})
    repository = read_string(fields["repository"], f"{path}.repository")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repository):
        raise ValidationError(
            "invalid-repository",
            f"{path}.repository",
            "Use an owner/repository identifier, not a URL or credentials.",
        )
    base_branch = read_string(fields["base_branch"], f"{path}.base_branch")
    branch_prefix = read_string(fields["branch_prefix"], f"{path}.branch_prefix")
    _validate_branch(base_branch, f"{path}.base_branch")
    _validate_branch(f"{branch_prefix}example", f"{path}.branch_prefix")
    return Publication(repository, base_branch, branch_prefix)


def _parse_setup(value: object, path: str) -> SetupDefinition:
    """Validate non-secret bootstrap preferences while leaving registration native."""
    fields = read_mapping(value, path, set(), {"venv", "harnesses", "automation"})
    venv = read_config_path(fields["venv"], f"{path}.venv") if "venv" in fields else None
    harnesses: tuple[str, ...] = ()
    if "harnesses" in fields:
        raw_harnesses = read_strings(fields["harnesses"], f"{path}.harnesses")
        harnesses = tuple(
            read_identifier(value, f"{path}.harnesses[{index}]")
            for index, value in enumerate(raw_harnesses)
        )
        if len(harnesses) != len(set(harnesses)):
            raise ValidationError(
                "duplicate-value", f"{path}.harnesses", "Harness IDs must be unique."
            )
    automation = None
    if "automation" in fields:
        automation_fields = read_mapping(
            fields["automation"], f"{path}.automation", {"name", "cadence", "timezone"}
        )
        name = read_string(automation_fields["name"], f"{path}.automation.name")
        cadence = read_string(automation_fields["cadence"], f"{path}.automation.cadence")
        timezone = read_string(automation_fields["timezone"], f"{path}.automation.timezone")
        if any(character in name for character in ("\n", "\r", "\x00")):
            raise ValidationError(
                "invalid-value",
                f"{path}.automation.name",
                "Automation name cannot contain controls.",
            )
        if any(character in cadence for character in ("\n", "\r", "\x00")):
            raise ValidationError(
                "invalid-value", f"{path}.automation.cadence", "Cadence cannot contain controls."
            )
        if any(character in timezone for character in ("\n", "\r", "\x00")):
            raise ValidationError(
                "invalid-value", f"{path}.automation.timezone", "Timezone cannot contain controls."
            )
        automation = AutomationDefinition(name=name, cadence=cadence, timezone=timezone)
    return SetupDefinition(venv=venv, harnesses=harnesses, automation=automation)


def _validate_branch(value: str, path: str) -> None:
    if (
        value.startswith(("-", "/"))
        or value.endswith((".", "/"))
        or value == "@"
        or ".." in value
        or "@{" in value
        or "//" in value
        or any(
            ord(character) < 33 or ord(character) == 127 or character in "~^:?*[\\"
            for character in value
        )
        or any(part.startswith(".") or part.endswith(".lock") for part in value.split("/"))
    ):
        raise ValidationError(
            "invalid-branch", path, "Expected a valid literal branch name or prefix."
        )
