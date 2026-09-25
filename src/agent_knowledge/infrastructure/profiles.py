"""Read one registry and retain path provenance for the selected workspace."""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from agent_knowledge.domain.configuration import WorkspaceDefinition, parse_workspace
from agent_knowledge.domain.profiles import (
    EnvironmentVariable,
    Profiles,
    merge_overrides,
    parse_profiles,
    select_profile,
    validate_environment_session_declaration,
    workspace_mapping,
)
from agent_knowledge.domain.validation import ValidationError

from .documents import load_mapping
from .errors import AdapterError
from .filesystem import read_bytes, resolve_path
from .usage import usage_lock


@dataclass(frozen=True, slots=True)
class Selection:
    """Pin the chosen name, independently of subsequent default changes."""

    mode: Literal["config", "profile", "default"]
    config: Path
    settings: Path | None = None
    profile: str | None = None

    def summary(self, fingerprint: str | None = None) -> dict[str, object]:
        return {
            "mode": self.mode,
            "profile": self.profile,
            "settings_path": str(self.settings) if self.settings else None,
            "config_path": str(self.config),
            "effective_fingerprint": fingerprint,
        }


@dataclass(frozen=True, slots=True)
class PreparedWorkspace:
    """Carry validated effective values before checking filesystem readiness."""

    selection: Selection
    base_bytes: bytes
    definition: WorkspaceDefinition
    origins: tuple[tuple[str, str], ...]
    overridden_fields: tuple[str, ...]
    environment: "ResolvedProfileEnvironment | None" = None


@dataclass(frozen=True, slots=True)
class ResolvedProfileEnvironment:
    """Resolve a selected profile's secret-free environment declaration."""

    file: Path
    variables: tuple[EnvironmentVariable, ...]


def settings_path(path: Path | None) -> Path:
    """Locate one explicit registry or the documented user-owned config file."""
    return resolve_path(
        str(path or Path.home() / ".config/agent-knowledge/config.yaml"), base=Path.cwd()
    )


def read_profiles(path: Path) -> Profiles:
    try:
        data = read_bytes(path, max_bytes=1_048_576)
    except AdapterError as error:
        raise AdapterError(
            "profile-settings-unavailable",
            str(path),
            "Cannot read the selected profile registry.",
            error.exit_code,
        ) from error
    return parse_profiles(load_mapping(data, path=str(path)))


def replace_registry(path: Path, candidate: bytes, *, expected_sha256: str | None) -> None:
    """Publish reviewed YAML bytes after checking the inspected registry is unchanged.

    The author preserves comments and unrelated entries in the candidate. This
    adapter validates the same core schema without reserializing those bytes.
    None means creation only. Cooperating setup writers share a short file lock.
    """
    parse_profiles(load_mapping(candidate, path=str(path), max_bytes=1_048_576))
    path = path.absolute()

    def check_current() -> None:
        if path.is_symlink():
            raise AdapterError("unsafe-path", str(path), "Registry must be a regular file.")
        current = read_bytes(path, max_bytes=1_048_576) if path.exists() else None
        actual = hashlib.sha256(current).hexdigest() if current is not None else None
        if actual != expected_sha256:
            raise ValidationError(
                "registry-changed", str(path), "Reinspect the registry before applying this edit."
            )

    with usage_lock(path.with_name(path.name + ".lock")):
        check_current()
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = stream.name
                stream.write(candidate)
                stream.flush()
                os.fsync(stream.fileno())
            check_current()
            if expected_sha256 is None:
                # Creation must not overwrite an independently created registry.
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        except OSError as error:
            raise AdapterError(
                "registry-write-failed", str(path), "Could not publish the reviewed registry."
            ) from error
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)


def list_profiles(path: Path | None = None) -> dict[str, object]:
    """List metadata without opening any profile's workspace or catalog."""
    resolved = settings_path(path)
    registry = read_profiles(resolved)
    return {
        "settings_path": str(resolved),
        "default_profile": registry.default_profile,
        "profiles": [
            {
                "name": item.name,
                "config_path": str(resolve_path(item.config, base=resolved.parent)),
                "default": item.name == registry.default_profile,
                "overridden_fields": [".".join(override.path) for override in item.overrides],
                "environment": (
                    {
                        "file": str(_authored_path(item.environment.file, resolved.parent)),
                        "session_policy": "one-profile-per-session",
                        "variables": [
                            {
                                "label": variable.label,
                                "from_env": variable.from_env,
                                "expose_as": variable.expose_as,
                                "description": variable.description,
                            }
                            for variable in item.environment.variables
                        ],
                    }
                    if item.environment is not None
                    else None
                ),
            }
            for item in registry.profiles
        ],
    }


def prepare_workspace(
    *, config: Path | None = None, settings: Path | None = None, profile: str | None = None
) -> PreparedWorkspace:
    """Select once, validate the base, and resolve each path from its authoring file."""
    if config is not None and (settings is not None or profile is not None):
        raise ValidationError(
            "invalid-arguments", "config", "Use --config or profile settings, not both."
        )
    selected = None
    registry_path = None
    if config is not None:
        base_path = resolve_path(str(config), base=Path.cwd())
        selection = Selection("config", base_path)
    else:
        registry_path = settings_path(settings)
        selected = select_profile(read_profiles(registry_path), profile)
        base_path = resolve_path(selected.config, base=registry_path.parent)
        selection = Selection(
            "profile" if profile is not None else "default", base_path, registry_path, selected.name
        )
    base_bytes = read_bytes(base_path, max_bytes=1_048_576)
    base = parse_workspace(load_mapping(base_bytes, path=str(base_path)))
    effective = merge_overrides(base, selected) if selected is not None else base
    overridden = (
        tuple(override.path for override in selected.overrides) if selected is not None else ()
    )
    origins: list[tuple[str, str]] = []

    def resolve_values(value: object, prefix: tuple[str, ...] = ()) -> object:
        if isinstance(value, dict):
            return {key: resolve_values(item, prefix + (key,)) for key, item in value.items()}
        if isinstance(value, list):
            return [resolve_values(item, prefix + (str(i),)) for i, item in enumerate(value)]
        owner = (
            registry_path
            if any(prefix[: len(field)] == field for field in overridden)
            else base_path
        )
        assert owner is not None
        origins.append((".".join(prefix), str(owner)))
        path_field = prefix[-1] in {
            "root",
            "catalog",
            "scaffold_root",
            "code_root",
            "directory",
            "venv",
        }
        if path_field and isinstance(value, str):
            # Preserve authored components until receipt-storage symlink checks run.
            return str(owner.parent / value) if not Path(value).is_absolute() else value
        return value

    definition = parse_workspace(resolve_values(workspace_mapping(effective)))
    environment = None
    if selected is not None and selected.environment is not None and registry_path is not None:
        environment = ResolvedProfileEnvironment(
            _authored_path(selected.environment.file, registry_path.parent),
            selected.environment.variables,
        )
        validate_environment_session_declaration(
            str(environment.file),
            environment.variables,
            f"settings.profiles.{selected.name}.environment",
        )
    return PreparedWorkspace(
        selection,
        base_bytes,
        definition,
        tuple(origins),
        tuple(".".join(field) for field in overridden),
        environment,
    )


def _authored_path(value: str, base: Path) -> Path:
    """Make a literal path absolute without following any symlink component."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    return Path(os.path.abspath(candidate))
