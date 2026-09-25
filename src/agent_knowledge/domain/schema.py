"""Validate parsed frontmatter and explicit search requests using one catalog."""

import re
from collections.abc import Mapping
from datetime import datetime

from agent_knowledge.domain.catalog import Catalog
from agent_knowledge.domain.configuration import read_config_path
from agent_knowledge.domain.models import (
    CatalogDimension,
    EvidenceReference,
    KnowledgeKind,
    KnowledgeMetadata,
    KnowledgeSignal,
    SearchQuery,
    SignalOrigin,
    TextQuery,
    ValidateQuery,
)
from agent_knowledge.domain.validation import (
    ValidationError,
    read_document_reference,
    read_identifier,
    read_mapping,
    read_relative_path,
    read_string,
    read_strings,
)

_FACETS = {
    "scope": CatalogDimension.SCOPES,
    "topics": CatalogDimension.TOPICS,
    "entities": CatalogDimension.ENTITIES,
    "languages": CatalogDimension.LANGUAGES,
    "technologies": CatalogDimension.TECHNOLOGIES,
    "environments": CatalogDimension.ENVIRONMENTS,
}
_APPLICABILITY = frozenset({"languages", "technologies", "environments"})
_KNOWLEDGE_REQUIRED = frozenset({"kind", "title", "description", "scope", "topics"})
_KNOWLEDGE_OPTIONAL = frozenset(
    {"entities", "languages", "technologies", "environments", "aliases", "terms"}
)


def _versioned_fields(
    value: object, version: str, required: frozenset[str], optional: frozenset[str]
) -> dict[str, object]:
    """Reject a foreign schema before interpreting its fields as canonical metadata."""
    if isinstance(value, Mapping) and "schema_version" in value:
        actual = read_string(value["schema_version"], "schema_version")
        if actual != version:
            raise ValidationError("unsupported-schema", "schema_version", f"Expected {version}.")
    return read_mapping(value, "", required | {"schema_version"}, optional)


def _kind(value: object, path: str) -> KnowledgeKind:
    """Require an exact kind from the new taxonomy, without legacy aliases."""
    name = read_string(value, path)
    try:
        return KnowledgeKind(name)
    except ValueError as error:
        raise ValidationError("invalid-value", path, f"Unknown knowledge kind: {name}.") from error


def _facet(
    value: object, field: str, catalog: Catalog, *, query: bool = False, path: str | None = None
) -> tuple[str, ...]:
    """Resolve explicit identifiers while retaining literal applicability alternatives."""
    location = path if path is not None else field
    values = read_strings(value, location, unique=not query)
    if not query and field in _APPLICABILITY and "any" in values and len(values) != 1:
        raise ValidationError("invalid-value", location, "On a document, any must stand alone.")
    for index, identifier in enumerate(values):
        item_path = f"{location}[{index}]"
        if field in _APPLICABILITY and identifier == "any":
            continue
        if field == "technologies" and identifier.startswith("family:"):
            catalog.require(CatalogDimension.TECHNOLOGY_FAMILIES, identifier[7:], item_path)
        else:
            catalog.require(_FACETS[field], identifier, item_path)
    return tuple(dict.fromkeys(values))


def _optional_facet(
    fields: Mapping[str, object], field: str, catalog: Catalog, *, query: bool = False
) -> tuple[str, ...] | None:
    """Preserve omission while rejecting an explicitly null or empty restriction."""
    return _facet(fields[field], field, catalog, query=query) if field in fields else None


def _source_ids(
    value: object, catalog: Catalog, path: str, *, query: bool = False
) -> tuple[str, ...]:
    """Reject unknown source selection instead of silently searching a different source."""
    identifiers = read_strings(value, path, unique=not query)
    for index, identifier in enumerate(identifiers):
        if identifier not in catalog.source_ids:
            raise ValidationError(
                "unknown-identifier", f"{path}[{index}]", f"Unknown source: {identifier}."
            )
    return tuple(dict.fromkeys(identifiers))


def parse_knowledge(value: object, catalog: Catalog) -> KnowledgeMetadata:
    """Validate knowledge.v1 frontmatter already decoded by a format adapter."""
    fields = _versioned_fields(value, "knowledge.v1", _KNOWLEDGE_REQUIRED, _KNOWLEDGE_OPTIONAL)
    kind = _kind(fields["kind"], "kind")
    if kind is KnowledgeKind.GUIDANCE:
        for field in sorted(_APPLICABILITY):
            if field not in fields:
                raise ValidationError(
                    "missing-field", field, "Guidance requires explicit applicability."
                )
    description = read_string(fields["description"], "description")
    if len(description) > 600:
        raise ValidationError(
            "invalid-value", "description", "Descriptions must be at most 600 characters."
        )
    return KnowledgeMetadata(
        kind=kind,
        title=read_string(fields["title"], "title"),
        description=description,
        scope=_facet(fields["scope"], "scope", catalog),
        topics=_facet(fields["topics"], "topics", catalog),
        entities=_optional_facet(fields, "entities", catalog),
        languages=_optional_facet(fields, "languages", catalog),
        technologies=_optional_facet(fields, "technologies", catalog),
        environments=_optional_facet(fields, "environments", catalog),
        aliases=read_strings(fields["aliases"], "aliases") if "aliases" in fields else (),
        terms=read_strings(fields["terms"], "terms") if "terms" in fields else (),
    )


def _phrases(value: object, path: str) -> tuple[str, ...]:
    """Normalize surrounding query whitespace without rewriting authored metadata."""
    if isinstance(value, list):
        value = [item.strip() if isinstance(item, str) else item for item in value]
    return tuple(dict.fromkeys(read_strings(value, path, unique=False)))


def parse_text_query(value: object) -> TextQuery:
    """Require at least one nonempty group of explicit literal text phrases."""
    fields = read_mapping(value, "text", set(), {"any", "all"})
    if not fields:
        raise ValidationError("invalid-value", "text", "Supply any, all, or both phrase groups.")
    return TextQuery(
        any=_phrases(fields["any"], "text.any") if "any" in fields else (),
        all=_phrases(fields["all"], "text.all") if "all" in fields else (),
    )


def parse_query(value: object, catalog: Catalog) -> SearchQuery:
    """Validate exact filters before any search can report matching or absent knowledge."""
    fields = read_mapping(
        value, "", set(), set(_FACETS) | {"kind", "sources", "text", "limit", "continuation"}
    )
    limit = fields.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValidationError("invalid-type", "limit", "Expected an integer between 1 and 100.")
    if not 1 <= limit <= 100:
        raise ValidationError("invalid-value", "limit", "Expected an integer between 1 and 100.")
    kinds = None
    if "kind" in fields:
        kinds = tuple(
            dict.fromkeys(
                _kind(item, f"kind[{index}]")
                for index, item in enumerate(read_strings(fields["kind"], "kind", unique=False))
            )
        )
    return SearchQuery(
        kind=kinds,
        scope=_optional_facet(fields, "scope", catalog, query=True),
        topics=_optional_facet(fields, "topics", catalog, query=True),
        entities=_optional_facet(fields, "entities", catalog, query=True),
        languages=_optional_facet(fields, "languages", catalog, query=True),
        technologies=_optional_facet(fields, "technologies", catalog, query=True),
        environments=_optional_facet(fields, "environments", catalog, query=True),
        sources=_source_ids(fields["sources"], catalog, "sources", query=True)
        if "sources" in fields
        else None,
        text=parse_text_query(fields["text"]) if "text" in fields else None,
        limit=limit,
        continuation=read_string(fields["continuation"], "continuation")
        if "continuation" in fields
        else None,
    )


def parse_validate_query(value: object, catalog: Catalog) -> ValidateQuery:
    """Require one explicit source, document or authored-signal selection."""
    fields = read_mapping(value, "", set(), {"sources", "documents", "signal_files"})
    selected = [key for key in ("sources", "documents", "signal_files") if key in fields]
    if len(selected) != 1:
        raise ValidationError(
            "invalid-value",
            "",
            "Supply exactly one of sources, documents or signal_files.",
        )
    target = selected[0]
    if target == "sources":
        values = read_strings(fields[target], target)
        for index, source in enumerate(values):
            if source not in catalog.source_ids:
                raise ValidationError(
                    "unknown-source",
                    f"{target}[{index}]",
                    f"Unknown configured source: {source!r}.",
                )
        return ValidateQuery(sources=values)
    if target == "documents":
        raw_documents = fields[target]
        if not isinstance(raw_documents, list):
            raise ValidationError("invalid-type", target, "Expected a list of document references.")
        if not raw_documents:
            raise ValidationError("invalid-value", target, "An explicit list must not be empty.")
        documents = tuple(
            read_document_reference(item, f"{target}[{index}]")
            for index, item in enumerate(raw_documents)
        )
        if len(documents) != len(set(documents)):
            raise ValidationError("duplicate-value", target, "Document references must be unique.")
        for index, document in enumerate(documents):
            if document.source not in catalog.source_ids:
                raise ValidationError(
                    "unknown-source",
                    f"{target}[{index}].source",
                    f"Unknown configured source: {document.source!r}.",
                )
        return ValidateQuery(documents=documents)
    paths = read_strings(fields[target], target)
    return ValidateQuery(
        signal_files=tuple(
            read_config_path(path, f"{target}[{index}]") for index, path in enumerate(paths)
        )
    )


def _origin(value: object, catalog: Catalog) -> SignalOrigin:
    """Validate captured origin without asserting a live checkout identity."""
    fields = read_mapping(
        value,
        "origin",
        {"workspace_id", "project_path", "applicable_scopes", "source_ids"},
        {"harness", "session_id", "automation_id"},
    )
    project_path = (
        None
        if fields["project_path"] is None
        else read_relative_path(fields["project_path"], "origin.project_path")
    )
    return SignalOrigin(
        workspace_id=read_identifier(fields["workspace_id"], "origin.workspace_id"),
        project_path=project_path,
        applicable_scopes=()
        if fields["applicable_scopes"] == []
        else _facet(fields["applicable_scopes"], "scope", catalog, path="origin.applicable_scopes"),
        source_ids=_source_ids(fields["source_ids"], catalog, "origin.source_ids"),
        harness=(
            read_identifier(fields["harness"], "origin.harness") if "harness" in fields else None
        ),
        session_id=(
            _opaque_handle(fields["session_id"], "origin.session_id")
            if "session_id" in fields
            else None
        ),
        automation_id=(
            _opaque_handle(fields["automation_id"], "origin.automation_id")
            if "automation_id" in fields
            else None
        ),
    )


def _opaque_handle(value: object, path: str) -> str:
    """Accept a bounded provider handle without accepting paths or credentials."""
    result = read_string(value, path)
    if (
        not result.strip()
        or len(result) > 256
        or any(
            character.isspace() or ord(character) < 32 or character in ("/", "\\", "$", "`")
            for character in result
        )
    ):
        raise ValidationError(
            "invalid-value",
            path,
            "Expected a short opaque handle without whitespace, paths or shell syntax.",
        )
    return result


def _timestamp(value: object) -> str:
    """Validate a supplied timezone-qualified ISO instant without reading a clock."""
    timestamp = read_string(value, "created_at")
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)",
        timestamp,
    ):
        raise ValidationError(
            "invalid-value", "created_at", "Expected an ISO timestamp with explicit timezone."
        )
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(
            "invalid-value", "created_at", "Timestamp is not a valid calendar instant."
        ) from error
    return timestamp


def _evidence(value: object) -> tuple[EvidenceReference, ...]:
    """Validate evidence-pointer structure without fetching or asserting its truth."""
    if not isinstance(value, list):
        raise ValidationError("invalid-type", "evidence", "Expected a list of evidence references.")
    if not value:
        raise ValidationError(
            "invalid-value", "evidence", "At least one evidence reference is required."
        )
    references = []
    for index, item in enumerate(value):
        path = f"evidence[{index}]"
        fields = read_mapping(item, path, {"type", "reference"})
        references.append(
            EvidenceReference(
                type=read_identifier(fields["type"], f"{path}.type"),
                reference=read_string(fields["reference"], f"{path}.reference"),
            )
        )
    if len(set(references)) != len(references):
        raise ValidationError("duplicate-value", "evidence", "Evidence references must be unique.")
    return tuple(references)


def parse_signal(value: object, body: object, catalog: Catalog) -> KnowledgeSignal:
    """Validate signal metadata and retain the exact supplied Markdown claim body."""
    fields = _versioned_fields(
        value,
        "knowledge-signal.v1",
        frozenset({"id", "created_at", "kind_hint", "origin", "evidence"}),
        frozenset({"entities", "technologies"}),
    )
    if not isinstance(body, str):
        raise ValidationError("invalid-type", "body", "Expected a Markdown claim body.")
    if not body.strip():
        raise ValidationError("invalid-value", "body", "A signal must contain a nonempty claim.")
    origin = _origin(fields["origin"], catalog)
    if origin.harness is not None and origin.session_id is None:
        raise ValidationError(
            "missing-field",
            "origin.session_id",
            "Harness-origin signals require the provider session ID.",
        )
    return KnowledgeSignal(
        id=read_identifier(fields["id"], "id"),
        created_at=_timestamp(fields["created_at"]),
        kind_hint=_kind(fields["kind_hint"], "kind_hint"),
        origin=origin,
        evidence=_evidence(fields["evidence"]),
        body=body,
        entities=_optional_facet(fields, "entities", catalog),
        technologies=_optional_facet(fields, "technologies", catalog),
    )
