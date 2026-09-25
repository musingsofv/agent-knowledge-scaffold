"""Compose explicit local configuration and domain discovery for the CLI."""

from dataclasses import asdict
from typing import TypedDict

from agent_knowledge.application.pagination import (
    Cursor,
    check_offset,
    decode_cursor,
    encode_cursor,
    request_fingerprint,
)
from agent_knowledge.domain.catalog import CatalogRecord
from agent_knowledge.domain.discovery import parse_catalog_query, select_catalog
from agent_knowledge.domain.validation import ValidationError, read_mapping
from agent_knowledge.infrastructure.configuration import Workspace, effective_configuration
from agent_knowledge.infrastructure.environment import inspect_environment
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import check_directory


class PublicationView(TypedDict):
    """Expose configured publication data without contacting a remote."""

    repository: str
    base_branch: str
    branch_prefix: str


class SourceView(TypedDict):
    """Expose source handles resolved relative to the selected configuration."""

    id: str
    root: str
    catalog: str
    publication: PublicationView | None


class SignalStorageView(TypedDict):
    """Show configured storage without creating or probing it."""

    scaffold_root: str
    code_root: str
    signal_root: str


class AutomationView(TypedDict):
    """Expose setup preferences without provider task IDs or credentials."""

    name: str
    cadence: str
    timezone: str


class SetupView(TypedDict):
    """Expose the non-secret setup choices supplied by a workspace."""

    venv: str | None
    harnesses: list[str]
    automation: AutomationView | None


class ReceiptStorageView(TypedDict):
    """Describe diagnostic policy and the shared mandatory-evidence destination."""

    enabled: bool
    directory: str
    retention_days: int


class EnvironmentVariableView(TypedDict):
    """Expose declared names and availability without retaining a value."""

    label: str
    from_env: str
    expose_as: str
    description: str
    available: bool


class EnvironmentView(TypedDict):
    """Describe one profile environment and its session boundary."""

    file: str
    status: str
    session_policy: str
    variables: list[EnvironmentVariableView]


class ContextView(TypedDict):
    """Describe explicit membership and locations, not inferred policy."""

    workspace_id: str
    config_path: str
    applicable_scopes: list[str]
    sources: list[SourceView]
    signal_storage: SignalStorageView | None
    receipts: ReceiptStorageView
    setup: SetupView | None
    environment: EnvironmentView | None
    fingerprint: str
    configuration: dict[str, object]


class CatalogView(TypedDict):
    """Expose canonical vocabulary and its declared relationships/provenance."""

    id: str
    dimension: str
    label: str | None
    description: str | None
    aliases: list[str]
    technology_families: list[str]
    parents: list[str]
    documents: list[dict[str, str]]
    source_ids: list[str]


class CatalogPage(TypedDict):
    """Return honest totals and an opaque snapshot-bound next page."""

    results: list[CatalogView]
    total_matches: int
    returned: int
    truncated: bool
    continuation: str | None
    fingerprint: str


def _readable_workspace(workspace: Workspace) -> Workspace:
    """Check all configured sources before returning successful discovery."""
    for source in workspace.sources:
        check_directory(source.root)
    return workspace


def context_result(workspace: Workspace, value: object) -> ContextView:
    """Load explicit context without enumerating documents or probing writes."""
    read_mapping(value, "", set())
    workspace = _readable_workspace(workspace)
    storage = workspace.signal_storage
    environment = workspace.environment
    available: frozenset[str] = frozenset()
    environment_status = "not-configured"
    if environment is not None:
        try:
            available = inspect_environment(environment).names
        except (ValidationError, AdapterError):
            environment_status = "not-ready"
        else:
            environment_status = "ready"
    return ContextView(
        workspace_id=workspace.definition.workspace_id,
        config_path=str(workspace.path),
        applicable_scopes=list(workspace.definition.applicable_scopes),
        sources=[
            SourceView(
                id=source.id,
                root=str(source.root),
                catalog=str(source.catalog_path),
                publication=PublicationView(
                    repository=source.publication.repository,
                    base_branch=source.publication.base_branch,
                    branch_prefix=source.publication.branch_prefix,
                )
                if source.publication
                else None,
            )
            for source in workspace.sources
        ],
        signal_storage=SignalStorageView(
            scaffold_root=str(storage.scaffold_root),
            code_root=str(storage.code_root),
            signal_root=str(storage.signal_root),
        )
        if storage
        else None,
        receipts=ReceiptStorageView(
            enabled=workspace.receipts.enabled,
            directory=str(workspace.receipts.directory),
            retention_days=workspace.receipts.retention_days,
        ),
        setup=SetupView(
            venv=workspace.definition.setup.venv,
            harnesses=list(workspace.definition.setup.harnesses),
            automation=AutomationView(
                name=workspace.definition.setup.automation.name,
                cadence=workspace.definition.setup.automation.cadence,
                timezone=workspace.definition.setup.automation.timezone,
            )
            if workspace.definition.setup.automation
            else None,
        )
        if workspace.definition.setup
        else None,
        environment=EnvironmentView(
            file=str(environment.file),
            status=environment_status,
            session_policy="one-profile-per-session",
            variables=[
                EnvironmentVariableView(
                    label=variable.label,
                    from_env=variable.from_env,
                    expose_as=variable.expose_as,
                    description=variable.description,
                    available=variable.from_env in available,
                )
                for variable in environment.variables
            ],
        )
        if environment is not None
        else None,
        fingerprint=workspace.fingerprint,
        configuration=effective_configuration(workspace),
    )


def _catalog_view(record: CatalogRecord) -> CatalogView:
    """Render validated records without losing ambiguous candidates or provenance."""
    return CatalogView(
        id=record.id,
        dimension=record.dimension.value,
        label=record.label,
        description=record.description,
        aliases=list(record.aliases),
        technology_families=list(record.technology_families),
        parents=list(record.parents),
        documents=[{"source": ref.source, "path": ref.path} for ref in record.documents],
        source_ids=list(record.source_ids),
    )


def catalog_result(workspace: Workspace, value: object) -> CatalogPage:
    """Apply domain selection then page within the loaded catalog snapshot."""
    workspace = _readable_workspace(workspace)
    query = parse_catalog_query(value, workspace.catalog)
    records = select_catalog(query, workspace.catalog)
    query_hash = request_fingerprint(asdict(query))
    position = decode_cursor(query.continuation, "catalog", query_hash, workspace.fingerprint)
    if position.channel != "items":
        raise ValidationError(
            "invalid-continuation", "continuation", "Expected catalog page cursor."
        )
    check_offset(position, len(records))
    start = position.offset
    page = records[start : start + query.limit]
    end = start + len(page)
    more = end < len(records)
    cursor = None
    if more:
        cursor = encode_cursor("catalog", query_hash, workspace.fingerprint, Cursor(end))
    return CatalogPage(
        results=[_catalog_view(record) for record in page],
        total_matches=len(records),
        returned=len(page),
        truncated=more,
        continuation=cursor,
        fingerprint=workspace.fingerprint,
    )
