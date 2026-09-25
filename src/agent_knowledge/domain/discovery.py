"""Validate catalog discovery and select candidates without I/O or pagination."""

from dataclasses import dataclass

from agent_knowledge.domain.catalog import Catalog, CatalogRecord
from agent_knowledge.domain.matching import prepare_text_query
from agent_knowledge.domain.models import CatalogDimension, TextQuery
from agent_knowledge.domain.schema import parse_text_query
from agent_knowledge.domain.validation import (
    ValidationError,
    read_mapping,
    read_string,
    read_strings,
)


@dataclass(frozen=True, slots=True)
class CatalogQuery:
    """Preserve explicit catalog selectors and opaque application pagination inputs."""

    dimension: CatalogDimension
    text: TextQuery | None = None
    ids: tuple[str, ...] | None = None
    sources: tuple[str, ...] | None = None
    limit: int = 10
    continuation: str | None = None


def parse_catalog_query(value: object, catalog: Catalog) -> CatalogQuery:
    """Reject invalid selectors before a caller can report an empty result."""
    fields = read_mapping(
        value, "", {"dimension"}, {"text", "ids", "sources", "limit", "continuation"}
    )
    dimension_name = read_string(fields["dimension"], "dimension")
    try:
        dimension = CatalogDimension(dimension_name)
    except ValueError as error:
        raise ValidationError(
            "invalid-value", "dimension", f"Unknown catalog dimension: {dimension_name}."
        ) from error
    ids = None
    if "ids" in fields:
        values = read_strings(fields["ids"], "ids", unique=False)
        for index, identifier in enumerate(values):
            catalog.require(dimension, identifier, f"ids[{index}]")
        ids = tuple(dict.fromkeys(values))
    sources = None
    if "sources" in fields:
        values = read_strings(fields["sources"], "sources", unique=False)
        for index, identifier in enumerate(values):
            if identifier not in catalog.source_ids:
                raise ValidationError(
                    "unknown-identifier", f"sources[{index}]", f"Unknown source: {identifier}."
                )
        sources = tuple(dict.fromkeys(values))
    limit = fields.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValidationError("invalid-type", "limit", "Expected an integer between 1 and 100.")
    if not 1 <= limit <= 100:
        raise ValidationError("invalid-value", "limit", "Expected an integer between 1 and 100.")
    return CatalogQuery(
        dimension=dimension,
        text=parse_text_query(fields["text"]) if "text" in fields else None,
        ids=ids,
        sources=sources,
        limit=limit,
        continuation=read_string(fields["continuation"], "continuation")
        if "continuation" in fields
        else None,
    )


def select_catalog(query: CatalogQuery, catalog: Catalog) -> tuple[CatalogRecord, ...]:
    """Return every matching record in ID order; the application owns cursor slicing.

    Sources filter a record's provenance without rewriting it. Text searches
    only the ID, label, description and aliases; family memberships, document
    references and other records are not silently added to the text surface.
    """
    ids = set(query.ids) if query.ids is not None else None
    sources = set(query.sources) if query.sources is not None else None
    records = tuple(
        record
        for record in catalog.records
        if record.dimension == query.dimension
        and (ids is None or record.id in ids)
        and (sources is None or sources.intersection(record.source_ids))
    )
    if query.text is not None and records:
        prepared = prepare_text_query(query.text, catalog)
        records = tuple(
            record
            for record in records
            if prepared.matches(
                (record.id, record.label or "", record.description or "", *record.aliases)
            )
        )
    return tuple(sorted(records, key=lambda record: record.id))
