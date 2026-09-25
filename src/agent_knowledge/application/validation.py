"""Validate selected authored documents and signals before publication.

Validation intentionally shares the workspace loader, strict Markdown codec,
catalog schema and link resolver used by retrieval.  It reports all content
diagnostics it can collect in one pass, while configuration and external-state
failures remain structured operation errors.
"""

import hashlib
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import TypedDict

from agent_knowledge.application.diagnostics import Diagnostic, from_error
from agent_knowledge.domain.models import DocumentReference
from agent_knowledge.domain.navigation import MarkdownNavigation, scan_markdown
from agent_knowledge.domain.schema import parse_signal, parse_validate_query
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import Workspace
from agent_knowledge.infrastructure.corpus import (
    Inventory,
    LoadedDocument,
    inventory,
    load_document,
)
from agent_knowledge.infrastructure.documents import DEFAULT_DOCUMENT_BYTES, parse_document
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import read_bytes, resolve_path
from agent_knowledge.infrastructure.links import resolve_links


class ValidationItem(TypedDict):
    """Expose validated file identity without returning authored claim bodies."""

    path: str
    local_path: str
    source: str | None
    kind: str
    fingerprint: str
    byte_count: int
    line_count: int
    link_count: int
    status: str


class ValidationResult(TypedDict):
    """Report a complete selected validation scan and any content diagnostics."""

    target: str
    valid: bool
    checked: int
    results: list[ValidationItem]
    diagnostics: list[dict[str, object]]
    fingerprint: str
    scan_status: str


def _navigation(document: LoadedDocument) -> MarkdownNavigation:
    start = (
        document.parsed.body_range[0]
        if document.parsed.body_range
        else document.parsed.line_count + 1
    )
    return scan_markdown(document.parsed.body, start_line=start)


def _validate_document(
    workspace: Workspace, document: LoadedDocument, diagnostics: list[Diagnostic]
) -> ValidationItem:
    """Build a metadata-only validation row and append broken-reference errors."""
    diagnostic_count = len(diagnostics)
    navigation = _navigation(document)
    links = resolve_links(workspace, document, navigation)
    for link in links:
        if link.status in {"missing", "unresolved", "unsafe"}:
            diagnostics.append(
                Diagnostic(
                    "broken-reference",
                    f"{document.local_path}:{link.start_line}",
                    link.reason or "The Markdown reference could not be resolved.",
                    "Repair the local knowledge link or label external evidence explicitly.",
                )
            )
        elif link.anchor_status == "missing":
            diagnostics.append(
                Diagnostic(
                    "missing-anchor",
                    f"{document.local_path}:{link.start_line}",
                    link.reason or "The local knowledge anchor is missing.",
                    "Update the anchor or link to an existing heading.",
                )
            )
    return ValidationItem(
        path=document.path,
        local_path=str(document.local_path),
        source=document.source_id,
        kind=document.metadata.kind.value,
        fingerprint=document.parsed.fingerprint,
        byte_count=document.parsed.byte_count,
        line_count=document.parsed.line_count,
        link_count=len(links),
        status="invalid" if len(diagnostics) > diagnostic_count else "valid",
    )


def _validation_error(error: ValidationError, path: Path | None = None) -> Diagnostic:
    """Attach a file path to a pure schema error without exposing a body."""
    if path is None or error.path.startswith(str(path)):
        return from_error(error)
    location = f"{path}:{error.path}" if error.path else str(path)
    return Diagnostic(error.code, location, error.message, from_error(error).remediation)


def _digest(workspace: Workspace, target: str, items: Iterable[ValidationItem]) -> str:
    """Bind a report to configuration, target selection and complete file bytes."""
    digest = hashlib.sha256()
    for value in (workspace.fingerprint, target):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for item in items:
        for value in (item["source"] or "", item["path"], item["fingerprint"]):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return "sha256:" + digest.hexdigest()


def _source_documents(
    workspace: Workspace, source_ids: tuple[str, ...]
) -> tuple[Inventory, tuple[tuple[str, str], ...]]:
    """Return a deterministic inventory and source-qualified file identities."""
    snapshot = inventory(workspace, source_ids)
    return snapshot, tuple((reference.source, reference.path) for reference in snapshot.files)


def _validate_canonical(
    workspace: Workspace,
    references: Iterable[tuple[str, str]],
    diagnostics: list[Diagnostic],
) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    for source, relative in references:
        try:
            document = load_document(workspace, DocumentReference(source, relative))
            item = _validate_document(workspace, document, diagnostics)
        except ValidationError as error:
            diagnostics.append(_validation_error(error))
            source_root = next(item.root for item in workspace.sources if item.id == source)
            item = ValidationItem(
                path=relative,
                local_path=str(source_root / relative),
                source=source,
                kind="",
                fingerprint="",
                byte_count=0,
                line_count=0,
                link_count=0,
                status="invalid",
            )
        items.append(item)
    return items


def _validate_signal(
    workspace: Workspace, authored_path: str, diagnostics: list[Diagnostic]
) -> ValidationItem:
    """Validate one authored signal envelope and return only location facts."""
    path = resolve_path(authored_path, base=workspace.path.parent)
    try:
        if path.suffix != ".md":
            raise ValidationError(
                "invalid-signal-extension", "signal_files", "Signal files must use .md."
            )
        data = read_bytes(path, max_bytes=DEFAULT_DOCUMENT_BYTES)
        parsed = parse_document(data, path=str(path))
        signal = parse_signal(parsed.metadata, parsed.body, workspace.catalog)
    except ValidationError as error:
        diagnostics.append(_validation_error(error, path))
        return ValidationItem(
            path=authored_path,
            local_path=str(path),
            source=None,
            kind="",
            fingerprint="",
            byte_count=0,
            line_count=0,
            link_count=0,
            status="invalid",
        )
    return ValidationItem(
        path=authored_path,
        local_path=str(path),
        source=None,
        kind=signal.kind_hint.value,
        fingerprint=parsed.fingerprint,
        byte_count=parsed.byte_count,
        line_count=parsed.line_count,
        link_count=0,
        status="valid",
    )


def validate_result(workspace: Workspace, value: object) -> ValidationResult:
    """Validate exactly the requested sources, canonical files or signal files."""
    query = parse_validate_query(value, workspace.catalog)
    diagnostics: list[Diagnostic] = []
    target: str
    items: list[ValidationItem]
    if query.sources is not None:
        target = "sources"
        source_snapshot, references = _source_documents(workspace, query.sources)
        items = _validate_canonical(workspace, references, diagnostics)
        if inventory(workspace, query.sources).fingerprint != source_snapshot.fingerprint:
            raise AdapterError(
                "scan-changed",
                "sources",
                "Sources changed during validation; results are incomplete.",
            )
    elif query.documents is not None:
        target = "documents"
        items = _validate_canonical(
            workspace,
            ((reference.source, reference.path) for reference in query.documents),
            diagnostics,
        )
    else:
        assert query.signal_files is not None
        target = "signal_files"
        items = [
            _validate_signal(workspace, authored_path, diagnostics)
            for authored_path in query.signal_files
        ]
    fingerprint = _digest(workspace, target, items)
    return ValidationResult(
        target=target,
        valid=not diagnostics,
        checked=len(items),
        results=items,
        diagnostics=[asdict(item) for item in diagnostics],
        fingerprint=fingerprint,
        scan_status="complete",
    )
