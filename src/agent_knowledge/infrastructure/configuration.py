"""Load only explicitly configured workspace/catalog files and resolve local paths."""

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from agent_knowledge.domain.catalog import Catalog, parse_catalogs
from agent_knowledge.domain.configuration import Publication, WorkspaceDefinition
from agent_knowledge.domain.models import CatalogDimension
from agent_knowledge.domain.profiles import workspace_mapping
from agent_knowledge.domain.validation import ValidationError

from .documents import load_mapping
from .errors import AdapterError
from .filesystem import read_bytes, resolve_path
from .profiles import ResolvedProfileEnvironment, Selection, prepare_workspace

CONFIG_MAX_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class Source:
    """Bind one configured source ID to its resolved paths and optional publication."""

    id: str
    root: Path
    catalog_path: Path
    publication: Publication | None = None


@dataclass(frozen=True, slots=True)
class SignalStorage:
    """Locate optional durable signal storage independently of read availability."""

    scaffold_root: Path
    code_root: Path
    signal_root: Path


@dataclass(frozen=True, slots=True)
class ReceiptStorage:
    """Locate diagnostics and required archives, including when diagnostics are disabled."""

    enabled: bool
    directory: Path
    retention_days: int


@dataclass(frozen=True, slots=True)
class Workspace:
    """Expose a validated catalog/context snapshot without scanning the corpus."""

    path: Path
    definition: WorkspaceDefinition
    sources: tuple[Source, ...]
    catalog: Catalog
    signal_storage: SignalStorage | None
    fingerprint: str
    receipts: ReceiptStorage
    selection: Selection
    field_origins: tuple[tuple[str, str], ...]
    overridden_fields: tuple[str, ...]
    environment: ResolvedProfileEnvironment | None = None


def load_workspace(path: Path) -> Workspace:
    """Load an explicit workspace without consulting profile settings."""
    return resolve_workspace(config=path)


def resolve_workspace(
    *, config: Path | None = None, settings: Path | None = None, profile: str | None = None
) -> Workspace:
    """Build one effective configuration and catalog snapshot for an invocation."""
    prepared = prepare_workspace(config=config, settings=settings, profile=profile)
    resolved = prepared.selection.config
    definition = prepared.definition
    sources = tuple(
        Source(
            id=source.id,
            root=resolve_path(source.root, base=resolved.parent),
            catalog_path=resolve_path(source.catalog, base=resolved.parent),
            publication=source.publication,
        )
        for source in definition.sources
    )
    for index, source in enumerate(sources):
        for previous in sources[:index]:
            if _overlap(source.root, previous.root):
                raise ValidationError(
                    "source-root-overlap",
                    f"workspace.sources[{index}].root",
                    f"Source roots overlap for {previous.id!r} and {source.id!r}.",
                )
    raw_catalogs: dict[str, object] = {}
    digest = hashlib.sha256()
    digest.update(_fingerprint_part(str(resolved).encode()))
    digest.update(_fingerprint_part(prepared.base_bytes))
    for source in sorted(sources, key=lambda item: item.id):
        catalog_bytes = read_bytes(source.catalog_path, max_bytes=CONFIG_MAX_BYTES)
        raw_catalogs[source.id] = load_mapping(catalog_bytes, path=str(source.catalog_path))
        for value in (
            source.id.encode(),
            str(source.root).encode(),
            str(source.catalog_path).encode(),
            catalog_bytes,
        ):
            digest.update(_fingerprint_part(value))
    catalog = parse_catalogs(raw_catalogs)
    for index, scope in enumerate(definition.applicable_scopes):
        catalog.require(CatalogDimension.SCOPES, scope, f"workspace.applicable_scopes[{index}]")
    storage = None
    if definition.signal_storage is not None:
        scaffold_root = resolve_path(definition.signal_storage.scaffold_root, base=resolved.parent)
        storage = SignalStorage(
            scaffold_root=scaffold_root,
            code_root=resolve_path(definition.signal_storage.code_root, base=resolved.parent),
            signal_root=scaffold_root / "ai/signals",
        )
    if storage is not None:
        for location in (storage.scaffold_root, storage.code_root, storage.signal_root):
            digest.update(_fingerprint_part(str(location).encode()))
    receipts = _receipt_storage(definition, resolved.parent, sources, storage)
    digest.update(_fingerprint_part(str(receipts.directory).encode()))
    definition = replace(
        definition,
        sources=tuple(
            replace(item, root=str(source.root), catalog=str(source.catalog_path))
            for item, source in zip(definition.sources, sources, strict=True)
        ),
        signal_storage=replace(
            definition.signal_storage,
            scaffold_root=str(storage.scaffold_root),
            code_root=str(storage.code_root),
        )
        if definition.signal_storage and storage
        else None,
        setup=replace(
            definition.setup, venv=str(resolve_path(definition.setup.venv, base=resolved.parent))
        )
        if definition.setup and definition.setup.venv
        else definition.setup,
        receipts=replace(definition.receipts, directory=str(receipts.directory)),
    )
    digest.update(
        _fingerprint_part(json.dumps(workspace_mapping(definition), sort_keys=True).encode())
    )
    return Workspace(
        resolved,
        definition,
        sources,
        catalog,
        storage,
        digest.hexdigest(),
        receipts,
        prepared.selection,
        prepared.origins,
        prepared.overridden_fields,
        prepared.environment,
    )


def reload_workspace(workspace: Workspace) -> Workspace:
    """Recheck the pinned selection, never the current default or just the base file."""
    selection = workspace.selection
    if selection.mode == "config":
        return load_workspace(selection.config)
    return resolve_workspace(settings=selection.settings, profile=selection.profile)


def workspace_is_current(workspace: Workspace) -> bool:
    """Compare effective semantics while ignoring unrelated registry edits."""
    return reload_workspace(workspace).fingerprint == workspace.fingerprint


def effective_configuration(workspace: Workspace) -> dict[str, object]:
    """Explain the values consumed by the operation and their authoring locations."""
    return {
        "values": workspace_mapping(workspace.definition),
        "field_origins": dict(workspace.field_origins),
        "overridden_fields": list(workspace.overridden_fields),
    }


def workspace_route(workspace: Workspace) -> dict[str, object]:
    """Bind compound routing without freezing normal catalog/document maintenance."""
    values = workspace_mapping(workspace.definition)
    values.pop("setup", None)
    values["receipts"] = {"directory": str(workspace.receipts.directory)}
    values["config_path"] = str(workspace.path)
    return values


def _receipt_storage(
    definition: WorkspaceDefinition,
    base: Path,
    sources: tuple[Source, ...],
    storage: SignalStorage | None,
) -> ReceiptStorage:
    configured = definition.receipts
    candidate = Path(configured.directory)
    if not candidate.is_absolute():
        candidate = base / candidate
    # Check the authored components before normalization, so even a symlink/..
    # traversal cannot hide a redirect. Config itself is already a resolved file.
    current = Path(candidate.anchor)
    try:
        for part in candidate.parts[1:]:
            current /= part
            if current.is_symlink():
                raise ValidationError(
                    "unsafe-receipt-path",
                    "workspace.receipts.directory",
                    "Usage storage cannot traverse symlinks.",
                )
    except OSError as error:
        raise AdapterError(
            "path-resolution-failed", str(candidate), "Cannot inspect the usage storage path."
        ) from error
    directory = Path(os.path.normpath(candidate))
    for source in sources:
        if _overlap(directory, source.root) or source.catalog_path.is_relative_to(directory):
            raise ValidationError(
                "receipt-root-overlap",
                "workspace.receipts.directory",
                f"Usage storage overlaps canonical source or catalog {source.id!r}.",
            )
    if storage is not None and _overlap(
        directory, resolve_path(str(storage.signal_root), base=base)
    ):
        raise ValidationError(
            "receipt-root-overlap",
            "workspace.receipts.directory",
            "Usage storage overlaps the signal inbox.",
        )
    return ReceiptStorage(configured.enabled, directory, configured.retention_days)


def validate_signal_storage(workspace: Workspace) -> SignalStorage | None:
    """Reject signal/canonical overlap in either direction, including symlink aliases.

    Missing roots are compared lexically after resolution; absence never excuses
    containment. Keep this separate so bad optional storage cannot hide read checks.
    Availability and a possible write probe remain doctor/capture responsibilities.
    """
    storage = workspace.signal_storage
    if storage is None:
        return None
    signal_root = resolve_path(str(storage.signal_root), base=workspace.path.parent)
    for source in workspace.sources:
        root = resolve_path(str(source.root), base=workspace.path.parent)
        if _overlap(signal_root, root):
            raise ValidationError(
                "signal-root-overlap",
                "workspace.signal_storage",
                f"Signal storage overlaps canonical source {source.id!r}.",
            )
    if signal_root != storage.signal_root:
        raise ValidationError(
            "unsafe-signal-path",
            "workspace.signal_storage",
            "Signal storage cannot traverse symlinks beneath its configured scaffold root.",
        )
    return SignalStorage(storage.scaffold_root, storage.code_root, signal_root)


def _overlap(first: Path, second: Path) -> bool:
    return first.is_relative_to(second) or second.is_relative_to(first)


def _fingerprint_part(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value
