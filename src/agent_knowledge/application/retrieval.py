"""Scan explicit sources and return previews/navigation without returning bodies."""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from time import monotonic_ns
from typing import Literal, TypedDict

from agent_knowledge.application.pagination import (
    Cursor,
    check_offset,
    decode_cursor,
    encode_cursor,
    request_fingerprint,
)
from agent_knowledge.domain.inspection import InspectQuery, parse_inspect_query
from agent_knowledge.domain.matching import PreparedTextQuery, prepare_query
from agent_knowledge.domain.models import DocumentReference, KnowledgeDocument
from agent_knowledge.domain.navigation import (
    Heading,
    MarkdownNavigation,
    scan_markdown,
    section_for_line,
)
from agent_knowledge.domain.schema import parse_query
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import Workspace, workspace_is_current
from agent_knowledge.infrastructure.corpus import (
    LoadedDocument,
    document_path,
    inventory,
    load_document,
)
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import open_directory
from agent_knowledge.infrastructure.links import ResolvedLink, resolve_links

MATCH_PAGE_SIZE = 20


class SectionView(TypedDict):
    """Locate a source heading and its complete enclosing section."""

    level: int
    title: str
    anchor: str
    start_line: int
    end_line: int


class MatchView(TypedDict):
    """Describe a contributing phrase location, not an extracted body snippet."""

    field: str
    group: str
    phrase_index: int
    start_line: int
    end_line: int
    precision: str
    section: SectionView | None


class Preview(TypedDict):
    """Return authored metadata and navigation facts for one fingerprinted file."""

    source: str
    path: str
    local_path: str
    title: str
    description: str
    kind: str
    scope: list[str]
    topics: list[str]
    entities: list[str] | None
    languages: list[str] | None
    technologies: list[str] | None
    environments: list[str] | None
    aliases: list[str]
    terms: list[str]
    byte_count: int
    line_count: int
    frontmatter_range: list[int]
    body_range: list[int] | None
    fingerprint: str
    metadata_only: bool | None
    link_count: int
    matches: list[MatchView]
    match_count: int
    matches_returned: int
    matches_truncated: bool
    match_continuation: str | None


class SearchResult(TypedDict):
    """Report complete predicate matching with independently pageable locations."""

    results: list[Preview]
    total_matches: int
    returned: int
    truncated: bool
    continuation: str | None
    fingerprint: str
    scan_status: str
    page_channel: str


class InspectResult(TypedDict):
    """Page only a selected document's outline and outgoing references."""

    view: Literal["navigation"]
    preview: Preview
    navigation: list[dict[str, object]]
    total_entries: int
    returned: int
    truncated: bool
    continuation: str | None
    fingerprint: str


class IncomingTarget(TypedDict):
    """Identify a selected safe path even after the document has been removed."""

    source: str
    path: str
    local_path: str
    status: Literal["resolved", "missing"]
    fingerprint: str | None


class IncomingReference(TypedDict):
    """Keep one authored link and its referring preview; never return body prose."""

    preview: Preview
    link: dict[str, object]


class IncomingScan(TypedDict):
    """Expose measured scan scope and conservative coverage limitations."""

    sources: list[str]
    documents: int
    byte_count: int
    elapsed_ms: float
    coverage: str
    catalog_references_included: Literal[False]
    diagnostics: list[dict[str, object]]
    diagnostic_count: int
    diagnostics_truncated: bool


class IncomingInspectResult(TypedDict):
    """Page authored incoming links independently of the target's outgoing outline."""

    view: Literal["incoming"]
    target: IncomingTarget
    references: list[IncomingReference]
    total_entries: int
    returned: int
    truncated: bool
    continuation: str | None
    fingerprint: str
    scan_status: Literal["complete", "incomplete"]
    scan: IncomingScan


def _section(heading: Heading | None) -> SectionView | None:
    if heading is None:
        return None
    return SectionView(
        level=heading.level,
        title=heading.title,
        anchor=heading.anchor,
        start_line=heading.start_line,
        end_line=heading.end_line,
    )


# Lightweight sortable locations; detailed section views are built only for a page.
Location = tuple[int, int, str, str, int]


def _metadata_locations(document: LoadedDocument, text: PreparedTextQuery) -> list[Location]:
    matches: list[Location] = []
    metadata = document.metadata
    for field, values in (
        ("title", (metadata.title,)),
        ("description", (metadata.description,)),
        ("aliases", metadata.aliases),
        ("terms", metadata.terms),
    ):
        seen: set[tuple[str, int]] = set()
        for value in values:
            for hit in text.occurrences(((1, value),)):
                if (hit.group, hit.phrase_index) in seen:
                    continue
                seen.add((hit.group, hit.phrase_index))
                start, end = document.parsed.field_ranges[field]
                matches.append((start, end, field, hit.group, hit.phrase_index))
    return matches


def _locations(
    document: LoadedDocument,
    navigation: MarkdownNavigation,
    text: PreparedTextQuery | None,
    offset: int,
) -> tuple[list[MatchView], int, bool | None]:
    if text is None:
        check_offset(Cursor(offset), 0)
        return [], 0, None
    matches = _metadata_locations(document, text)
    body = text.occurrences(tuple((line.line, line.text) for line in navigation.lines))
    matches.extend(
        (hit.start_line, hit.end_line, "body", hit.group, hit.phrase_index) for hit in body
    )
    matches.sort()
    check_offset(Cursor(offset), len(matches))
    page = [
        MatchView(
            field=field,
            group=group,
            phrase_index=phrase_index,
            start_line=start,
            end_line=end,
            precision="line-range" if field == "body" else "field-range",
            section=_section(section_for_line(navigation, start, end_line=end))
            if field == "body"
            else None,
        )
        for start, end, field, group, phrase_index in matches[offset : offset + MATCH_PAGE_SIZE]
    ]
    return page, len(matches), not body


def _preview(
    document: LoadedDocument,
    navigation: MarkdownNavigation,
    matches: list[MatchView],
) -> Preview:
    metadata, parsed = document.metadata, document.parsed
    return Preview(
        source=document.source_id,
        path=document.path,
        local_path=str(document.local_path),
        title=metadata.title,
        description=metadata.description,
        kind=metadata.kind.value,
        scope=list(metadata.scope),
        topics=list(metadata.topics),
        entities=list(metadata.entities) if metadata.entities is not None else None,
        languages=list(metadata.languages) if metadata.languages is not None else None,
        technologies=list(metadata.technologies) if metadata.technologies is not None else None,
        environments=list(metadata.environments) if metadata.environments is not None else None,
        aliases=list(metadata.aliases),
        terms=list(metadata.terms),
        byte_count=parsed.byte_count,
        line_count=parsed.line_count,
        frontmatter_range=list(parsed.frontmatter_range),
        body_range=list(parsed.body_range) if parsed.body_range else None,
        fingerprint=parsed.fingerprint,
        metadata_only=None,
        link_count=len(navigation.links),
        matches=matches,
        match_count=len(matches),
        matches_returned=len(matches),
        matches_truncated=False,
        match_continuation=None,
    )


def _navigation(document: LoadedDocument) -> MarkdownNavigation:
    start = (
        document.parsed.body_range[0]
        if document.parsed.body_range
        else document.parsed.line_count + 1
    )
    return scan_markdown(document.parsed.body, start_line=start)


@dataclass(frozen=True, slots=True)
class _Candidate:
    reference: DocumentReference
    fingerprint: str
    metadata_hit: bool


def _key(reference: DocumentReference) -> str:
    # Keep tokens bounded even when a configured source or relative path is long.
    return hashlib.sha256(f"{reference.source}\0{reference.path}".encode()).hexdigest()


def _match_page(
    workspace: Workspace,
    candidate: _Candidate,
    text: PreparedTextQuery | None,
    offset: int,
    query_hash: str,
    snapshot: str,
) -> Preview:
    document = load_document(workspace, candidate.reference)
    if document.parsed.fingerprint != candidate.fingerprint:
        raise AdapterError("scan-changed", document.path, "Document changed during scan.")
    navigation = _navigation(document)
    matches, total, metadata_only = _locations(document, navigation, text, offset)
    preview = _preview(document, navigation, matches)
    end = offset + len(matches)
    more = end < total
    return {
        **preview,
        "metadata_only": metadata_only,
        "match_count": total,
        "matches_truncated": more,
        "match_continuation": encode_cursor(
            "search", query_hash, snapshot, Cursor(end, "matches", _key(candidate.reference))
        )
        if more
        else None,
    }


def search_result(workspace: Workspace, value: object) -> SearchResult:
    """Validate a streamed scan, then build details only for the requested page."""
    query = parse_query(value, workspace.catalog)
    prepared = prepare_query(query, workspace.catalog)
    before = inventory(workspace, query.sources)
    digest = hashlib.sha256((workspace.fingerprint + before.fingerprint).encode())
    candidates: list[_Candidate] = []
    for reference in before.files:
        document = load_document(workspace, reference)
        digest.update(document.parsed.fingerprint.encode())
        raw = KnowledgeDocument(document.source_id, document.metadata)
        if not prepared.facets_match(raw):
            continue
        metadata_hit = False
        if prepared.text is not None:
            navigation = _navigation(document)
            rendered = "\n".join(line.text for line in navigation.lines)
            if not prepared.matches(
                KnowledgeDocument(document.source_id, document.metadata, rendered)
            ):
                continue
            metadata_hit = bool(_metadata_locations(document, prepared.text))
        candidates.append(_Candidate(reference, document.parsed.fingerprint, metadata_hit))
    snapshot = "sha256:" + digest.hexdigest()
    candidates.sort(
        key=lambda row: (not row.metadata_hit, row.reference.source, row.reference.path)
    )
    query_hash = request_fingerprint(asdict(query))
    cursor = decode_cursor(query.continuation, "search", query_hash, snapshot)
    if cursor.channel == "matches":
        selected = next((row for row in candidates if _key(row.reference) == cursor.target), None)
        if selected is None:
            raise ValidationError(
                "invalid-continuation", "continuation", "Unknown matched document."
            )
        row = _match_page(workspace, selected, prepared.text, cursor.offset, query_hash, snapshot)
        result = SearchResult(
            results=[row],
            total_matches=len(candidates),
            returned=1,
            truncated=row["matches_truncated"],
            continuation=row["match_continuation"],
            fingerprint=snapshot,
            scan_status="complete",
            page_channel="matches",
        )
    else:
        check_offset(cursor, len(candidates))
        page = candidates[cursor.offset : cursor.offset + query.limit]
        end = cursor.offset + len(page)
        more = end < len(candidates)
        result = SearchResult(
            results=[
                _match_page(workspace, row, prepared.text, 0, query_hash, snapshot) for row in page
            ],
            total_matches=len(candidates),
            returned=len(page),
            truncated=more,
            continuation=encode_cursor("search", query_hash, snapshot, Cursor(end))
            if more
            else None,
            fingerprint=snapshot,
            scan_status="complete",
            page_channel="items",
        )
    if inventory(
        workspace, query.sources
    ).fingerprint != before.fingerprint or not workspace_is_current(workspace):
        raise AdapterError(
            "scan-changed",
            "sources",
            "Sources/configuration changed during scan; results are incomplete.",
        )
    return result


def inspect_result(workspace: Workspace, value: object) -> InspectResult | IncomingInspectResult:
    """Inspect one file, exposing only bounded headings/references and its preview."""
    query = parse_inspect_query(value, workspace.catalog)
    if query.view == "incoming":
        return _incoming_result(workspace, query)
    document = load_document(workspace, query.document)
    if (
        query.expected_fingerprint is not None
        and document.parsed.fingerprint != query.expected_fingerprint
    ):
        raise ValidationError(
            "stale-document", "expected_fingerprint", "Document changed; refresh the preview."
        )
    navigation = _navigation(document)
    links = resolve_links(workspace, document, navigation)
    entries: list[dict[str, object]] = [
        {"type": "heading", **asdict(heading)} for heading in navigation.headings
    ] + [{"type": "link", **asdict(link)} for link in links]
    entries.sort(key=lambda entry: (int(str(entry["start_line"])), str(entry["type"])))
    snapshot = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                {
                    "workspace": workspace.fingerprint,
                    "document": document.parsed.fingerprint,
                    "navigation": entries,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    # Recheck the selected file/config; this does not promise an atomic later harness read.
    if load_document(
        workspace, query.document
    ).parsed.fingerprint != document.parsed.fingerprint or not workspace_is_current(workspace):
        raise AdapterError(
            "scan-changed", document.path, "Document/configuration changed during inspection."
        )
    query_hash = request_fingerprint(asdict(query))
    cursor = decode_cursor(query.continuation, "inspect", query_hash, snapshot)
    if cursor.channel != "items":
        raise ValidationError(
            "invalid-continuation", "continuation", "Expected navigation page cursor."
        )
    check_offset(cursor, len(entries))
    page = entries[cursor.offset : cursor.offset + query.limit]
    end = cursor.offset + len(page)
    more = end < len(entries)
    result = InspectResult(
        view="navigation",
        preview=_preview(document, navigation, []),
        navigation=page,
        total_entries=len(entries),
        returned=len(page),
        truncated=more,
        continuation=encode_cursor("inspect", query_hash, snapshot, Cursor(end)) if more else None,
        fingerprint=snapshot,
    )
    return result


def _incoming_target(
    workspace: Workspace, reference: DocumentReference
) -> tuple[IncomingTarget, LoadedDocument | None]:
    """Allow an absent file, but never conflate an unavailable source with deletion."""
    local_path = document_path(workspace, reference)
    source = next(source for source in workspace.sources if source.id == reference.source)
    with open_directory(source.root):
        pass
    try:
        document = load_document(workspace, reference)
    except AdapterError as error:
        if error.code not in {"file-missing", "directory-missing"}:
            raise
        document = None
    return (
        IncomingTarget(
            source=reference.source,
            path=reference.path,
            local_path=str(local_path),
            status="resolved" if document is not None else "missing",
            fingerprint=document.parsed.fingerprint if document is not None else None,
        ),
        document,
    )


def _incoming_link(
    link: ResolvedLink, target: IncomingTarget, anchors: frozenset[str]
) -> ResolvedLink:
    """Verify selected-target anchors against its already loaded supported outline."""
    if target["status"] == "missing":
        return replace(
            link,
            status="missing",
            anchor_status="unverified" if link.anchor else "not-present",
            reason="The selected target is missing; any target anchor remains unverified.",
        )
    if link.anchor is None:
        return replace(link, status="resolved", reason=None)
    present = link.anchor in anchors
    return replace(
        link,
        status="resolved",
        anchor_status="resolved" if present else "missing",
        reason=None
        if present
        else "The anchor is absent from the selected target's supported heading outline.",
    )


def _incoming_result(workspace: Workspace, query: InspectQuery) -> IncomingInspectResult:
    """Scan once per request, retaining only previews and authored reference locations.

    Inventory checks detect concurrent file/directory changes, while content hashes
    bind continuations to exact bytes. No successful response asserts an atomic
    filesystem snapshot or knowledge outside the selected Markdown sources.
    """
    started = monotonic_ns()
    target, document = _incoming_target(workspace, query.document)
    if (
        query.expected_fingerprint is not None
        and target["fingerprint"] != query.expected_fingerprint
    ):
        raise ValidationError(
            "stale-document", "expected_fingerprint", "Document changed; refresh the target."
        )
    anchors = (
        frozenset(heading.anchor for heading in _navigation(document).headings)
        if document
        else frozenset()
    )
    selected = tuple(sorted(query.sources or workspace.catalog.source_ids))
    before = inventory(workspace, selected)
    digest = hashlib.sha256(
        (workspace.fingerprint + before.fingerprint + json.dumps(target, sort_keys=True)).encode()
    )
    references: list[IncomingReference] = []
    diagnostics: list[dict[str, object]] = []
    diagnostic_count = 0
    byte_count = 0
    for reference in before.files:
        referring = load_document(workspace, reference)
        digest.update(referring.parsed.fingerprint.encode())
        byte_count += referring.parsed.byte_count
        # Self references belong to the ordinary navigation outline. Shared tags
        # and catalog entity documents are deliberately not authored link edges.
        if reference == query.document:
            continue
        navigation = _navigation(referring)
        preview: Preview | None = None
        for link in resolve_links(workspace, referring, navigation):
            if link.document == query.document and link.status in {"resolved", "missing"}:
                if preview is None:
                    preview = _preview(referring, navigation, [])
                references.append(
                    IncomingReference(
                        preview=preview, link=asdict(_incoming_link(link, target, anchors))
                    )
                )
            elif link.status in {"unsafe", "unresolved"}:
                diagnostic_count += 1
                if len(diagnostics) < query.limit:
                    diagnostics.append({"document": asdict(reference), "link": asdict(link)})
    references.sort(
        key=lambda row: (
            row["preview"]["source"],
            row["preview"]["path"],
            int(str(row["link"]["start_line"])),
            int(str(row["link"]["end_line"])),
            str(row["link"]["target"]),
            str(row["link"]["label"]),
        )
    )
    snapshot = "sha256:" + digest.hexdigest()
    # A target outside the selected scan roots is still part of snapshot identity.
    refreshed_target, _ = _incoming_target(workspace, query.document)
    if (
        refreshed_target != target
        or inventory(workspace, selected).fingerprint != before.fingerprint
        or not workspace_is_current(workspace)
    ):
        raise AdapterError(
            "scan-changed",
            "sources",
            "Incoming sources/target/configuration changed; retry the scan.",
        )
    query_hash = request_fingerprint(asdict(query))
    cursor = decode_cursor(query.continuation, "inspect", query_hash, snapshot)
    if cursor.channel != "items":
        raise ValidationError(
            "invalid-continuation", "continuation", "Expected incoming page cursor."
        )
    check_offset(cursor, len(references))
    page = references[cursor.offset : cursor.offset + query.limit]
    end = cursor.offset + len(page)
    more = end < len(references)
    return IncomingInspectResult(
        view="incoming",
        target=target,
        references=page,
        total_entries=len(references),
        returned=len(page),
        truncated=more,
        continuation=encode_cursor("inspect", query_hash, snapshot, Cursor(end)) if more else None,
        fingerprint=snapshot,
        scan_status="incomplete" if diagnostic_count else "complete",
        scan=IncomingScan(
            sources=list(selected),
            documents=len(before.files),
            byte_count=byte_count,
            elapsed_ms=(monotonic_ns() - started) / 1_000_000,
            coverage=(
                "Supported authored Markdown links in the selected sources only; "
                "unresolved or unsafe destinations may conceal additional references."
            ),
            catalog_references_included=False,
            diagnostics=diagnostics,
            diagnostic_count=diagnostic_count,
            diagnostics_truncated=diagnostic_count > len(diagnostics),
        ),
    )
