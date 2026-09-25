"""Capture and inventory authored observations without publishing or draining them."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from agent_knowledge.application.pagination import (
    Cursor,
    check_offset,
    decode_cursor,
    encode_cursor,
    request_fingerprint,
)
from agent_knowledge.domain.models import KnowledgeSignal
from agent_knowledge.domain.schema import parse_signal
from agent_knowledge.domain.signals import (
    parse_signal_list_query,
    parse_signal_record_query,
    signal_workspace_id,
    validate_signal_origin,
)
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import (
    Workspace,
    validate_signal_storage,
    workspace_is_current,
)
from agent_knowledge.infrastructure.documents import (
    DEFAULT_DOCUMENT_BYTES,
    ParsedDocument,
    parse_document,
)
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import read_bytes, resolve_path
from agent_knowledge.infrastructure.origin import check_durable_scaffold, resolve_project
from agent_knowledge.infrastructure.signals import capture_signal, inventory_signals


class OriginView(TypedDict):
    """Preserve configured capture context independently of canonical applicability."""

    workspace_id: str
    project_path: str | None
    applicable_scopes: list[str]
    source_ids: list[str]
    harness: str | None
    session_id: str | None
    automation_id: str | None


class EvidenceView(TypedDict):
    """Return an authored evidence pointer without fetching its target."""

    type: str
    reference: str


class SignalPreview(TypedDict):
    """Locate exact signal bytes without returning the Markdown claim."""

    id: str
    created_at: str
    kind_hint: str
    origin: OriginView
    entities: list[str] | None
    technologies: list[str] | None
    evidence: list[EvidenceView]
    local_path: str
    byte_count: int
    line_count: int
    frontmatter_range: list[int]
    body_range: list[int]
    fingerprint: str


class SignalListResult(TypedDict):
    """Page selected-workspace signals and expose foreign-workspace omissions."""

    results: list[SignalPreview]
    total_matches: int
    returned: int
    truncated: bool
    continuation: str | None
    fingerprint: str
    other_workspaces: int


def _preview(path: Path, parsed: ParsedDocument, signal: KnowledgeSignal) -> SignalPreview:
    # parse_signal has required a nonblank body, so the codec must provide a range.
    assert parsed.body_range is not None
    origin = signal.origin
    return SignalPreview(
        id=signal.id,
        created_at=signal.created_at,
        kind_hint=signal.kind_hint.value,
        origin=OriginView(
            workspace_id=origin.workspace_id,
            project_path=origin.project_path,
            applicable_scopes=list(origin.applicable_scopes),
            source_ids=list(origin.source_ids),
            harness=origin.harness,
            session_id=origin.session_id,
            automation_id=origin.automation_id,
        ),
        entities=list(signal.entities) if signal.entities is not None else None,
        technologies=list(signal.technologies) if signal.technologies is not None else None,
        evidence=[
            EvidenceView(type=item.type, reference=item.reference) for item in signal.evidence
        ],
        local_path=str(path),
        byte_count=parsed.byte_count,
        line_count=parsed.line_count,
        frontmatter_range=list(parsed.frontmatter_range),
        body_range=list(parsed.body_range),
        fingerprint=parsed.fingerprint,
    )


def _validate_origin(signal: KnowledgeSignal, workspace: Workspace, project: str | None) -> None:
    validate_signal_origin(
        signal.origin,
        workspace_id=workspace.definition.workspace_id,
        applicable_scopes=workspace.definition.applicable_scopes,
        source_ids=tuple(source.id for source in workspace.sources),
        project_path=project,
    )


@contextmanager
def _signal_errors(path: Path) -> Iterator[None]:
    """Attach the signal path to field diagnostics from pure schema/origin checks."""
    try:
        yield
    except ValidationError as error:
        raise ValidationError(error.code, f"{path}:{error.path}", error.message) from error


def _check_context(workspace: Workspace) -> None:
    if not workspace_is_current(workspace):
        raise AdapterError(
            "context-changed", str(workspace.path), "Configuration changed during signal operation."
        )


def record_signal_result(workspace: Workspace, value: object) -> SignalPreview:
    """Validate authoring and durable origin, then capture exact bytes without overwriting."""
    query = parse_signal_record_query(value)
    if validate_signal_storage(workspace) is None:
        raise ValidationError(
            "signal-storage-required", "signal_storage", "Configure signal storage."
        )
    authored = resolve_path(query.file, base=workspace.path.parent)
    if authored.suffix != ".md":
        raise ValidationError(
            "invalid-signal-extension", "file", "Use an authored Markdown .md file."
        )
    if any(authored.is_relative_to(source.root) for source in workspace.sources):
        raise ValidationError(
            "signal-in-canonical-root", "file", "Signals must be authored outside canonical roots."
        )
    data = read_bytes(authored, max_bytes=DEFAULT_DOCUMENT_BYTES)
    parsed = parse_document(data, path=str(authored))
    with _signal_errors(authored):
        signal = parse_signal(parsed.metadata, parsed.body, workspace.catalog)
        # A null project is deliberately shared, even when the config lives inside Git.
        project = resolve_project(workspace) if signal.origin.project_path is not None else None
        _validate_origin(signal, workspace, project)
    check_durable_scaffold(workspace)
    _check_context(workspace)
    stored = capture_signal(workspace, project, data)
    try:
        confirmed = read_bytes(stored, max_bytes=DEFAULT_DOCUMENT_BYTES)
        if confirmed != data:
            raise AdapterError("signal-changed", str(stored), "Stored signal bytes changed.")
    except AdapterError as error:
        raise AdapterError(
            "signal-publication-uncertain",
            str(stored),
            "Could not verify the captured bytes; retain and inspect this file before retrying.",
        ) from error
    return _preview(stored, parsed, signal)


def list_signal_result(workspace: Workspace, value: object) -> SignalListResult:
    """Validate selected-context signals without creating an inbox or returning claims."""
    query = parse_signal_list_query(value, workspace.catalog)
    storage = validate_signal_storage(workspace)
    if storage is None:
        raise ValidationError(
            "signal-storage-required", "signal_storage", "Configure signal storage."
        )
    project = resolve_project(workspace)
    if project is None and not query.include_shared:
        raise ValidationError(
            "project-origin-required",
            "origin.project_path",
            "No Git project is associated with this config; explicitly include shared signals.",
        )
    before = inventory_signals(workspace, project, include_shared=query.include_shared)
    digest = hashlib.sha256((workspace.fingerprint + before.fingerprint).encode())
    rows: list[SignalPreview] = []
    other_workspaces = 0
    for signal_path in before.files:
        parsed = parse_document(
            read_bytes(signal_path, max_bytes=DEFAULT_DOCUMENT_BYTES), path=str(signal_path)
        )
        digest.update(parsed.fingerprint.encode())
        with _signal_errors(signal_path):
            if signal_workspace_id(parsed.metadata) != workspace.definition.workspace_id:
                other_workspaces += 1
                continue
            signal = parse_signal(parsed.metadata, parsed.body, workspace.catalog)
            expected = None if signal_path.parent == storage.signal_root / "shared" else project
            _validate_origin(signal, workspace, expected)
            if query.session_id is not None and signal.origin.session_id != query.session_id:
                continue
        rows.append(_preview(signal_path, parsed, signal))
    _check_context(workspace)
    if inventory_signals(workspace, project, include_shared=query.include_shared) != before:
        raise AdapterError(
            "scan-changed", str(storage.signal_root), "Signal inbox changed during listing."
        )
    snapshot = "sha256:" + digest.hexdigest()
    query_hash = request_fingerprint(asdict(query))
    cursor = decode_cursor(query.continuation, "signal list", query_hash, snapshot)
    if cursor.channel != "items":
        raise ValidationError(
            "invalid-continuation", "continuation", "Expected a signal-list cursor."
        )
    check_offset(cursor, len(rows))
    page = rows[cursor.offset : cursor.offset + query.limit]
    end = cursor.offset + len(page)
    more = end < len(rows)
    return SignalListResult(
        results=page,
        total_matches=len(rows),
        returned=len(page),
        truncated=more,
        continuation=encode_cursor("signal list", query_hash, snapshot, Cursor(end))
        if more
        else None,
        fingerprint=snapshot,
        other_workspaces=other_workspaces,
    )
