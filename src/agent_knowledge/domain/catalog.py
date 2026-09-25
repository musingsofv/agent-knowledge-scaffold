"""Validate configured vocabulary without reading files or inferring applicability."""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType

from .models import CatalogDimension, DocumentReference
from .validation import (
    ValidationError,
    read_document_reference,
    read_identifier,
    read_mapping,
    read_string,
    read_strings,
)


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    """Own one vocabulary definition and the sources that declare it identically."""

    dimension: CatalogDimension
    id: str
    label: str | None = None
    description: str | None = None
    aliases: tuple[str, ...] = ()
    technology_families: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    documents: tuple[DocumentReference, ...] = ()
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Catalog:
    """Store validated vocabulary with exact identifier lookup and explicit ancestry."""

    records: tuple[CatalogRecord, ...]
    source_ids: tuple[str, ...]
    _by_key: Mapping[tuple[CatalogDimension, str], CatalogRecord] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Build an immutable lookup index without retaining mutable input mappings."""
        object.__setattr__(
            self,
            "_by_key",
            MappingProxyType({(record.dimension, record.id): record for record in self.records}),
        )

    def require(self, dimension: CatalogDimension, identifier: str, path: str) -> CatalogRecord:
        """Resolve an exact registered identifier or diagnose the caller's input field."""
        record = self._by_key.get((dimension, identifier))
        if record is None:
            raise ValidationError(
                "unknown-identifier", path, f"Unknown {dimension.value} identifier: {identifier!r}."
            )
        return record

    def scope_ancestors(self, scope_id: str) -> tuple[str, ...]:
        """Return explicit transitive parents; calling this never alters search filters."""
        scope = self.require(CatalogDimension.SCOPES, scope_id, "scope")
        ancestors: set[str] = set()
        pending = list(scope.parents)
        while pending:
            identifier = pending.pop()
            if identifier not in ancestors:
                ancestors.add(identifier)
                pending.extend(self.require(CatalogDimension.SCOPES, identifier, "scope").parents)
        return tuple(sorted(ancestors))


def parse_catalogs(sources: Mapping[str, object]) -> Catalog:
    """Validate parsed catalogs together so declarations may cross source boundaries."""
    source_definitions = _read_registry(sources, "catalogs")
    records: dict[tuple[CatalogDimension, str], CatalogRecord] = {}
    paths: dict[tuple[CatalogDimension, str], str] = {}
    required = {"schema_version", *(dimension.value for dimension in CatalogDimension)}
    for source_id, raw_catalog in sorted(source_definitions.items()):
        catalog_path = f"catalogs.{source_id}"
        definition = read_mapping(raw_catalog, catalog_path, required=required)
        schema_version = read_string(definition["schema_version"], f"{catalog_path}.schema_version")
        if schema_version != "knowledge-catalog.v1":
            raise ValidationError(
                "unsupported-schema",
                f"{catalog_path}.schema_version",
                "Expected knowledge-catalog.v1.",
            )
        for dimension in CatalogDimension:
            dimension_path = f"{catalog_path}.{dimension.value}"
            for identifier, raw_record in sorted(
                _read_registry(definition[dimension.value], dimension_path).items()
            ):
                record_path = f"{dimension_path}.{identifier}"
                record = _parse_record(dimension, identifier, raw_record, record_path, source_id)
                key = (dimension, identifier)
                previous = records.get(key)
                if previous is not None:
                    if _definition(previous) != _definition(record):
                        raise ValidationError(
                            "catalog-conflict",
                            record_path,
                            f"Conflicting {dimension.value} identifier {identifier!r} "
                            f"in sources {', '.join((*previous.source_ids, source_id))}.",
                        )
                    record = replace(previous, source_ids=(*previous.source_ids, source_id))
                records[key] = record
                paths.setdefault(key, record_path)
    catalog = Catalog(
        records=tuple(records[key] for key in sorted(records)),
        source_ids=tuple(sorted(source_definitions)),
    )
    _validate_references(catalog, paths)
    _validate_scope_cycles(catalog, paths)
    return catalog


def _read_registry(value: object, path: str) -> dict[str, object]:
    """Validate identifier keys while leaving record shapes to their dimension parser."""
    if not isinstance(value, Mapping):
        raise ValidationError("invalid-type", path, "Expected a mapping of registered identifiers.")
    return {read_identifier(key, path): item for key, item in value.items()}


def _parse_record(
    dimension: CatalogDimension, identifier: str, value: object, path: str, source_id: str
) -> CatalogRecord:
    """Validate a closed record shape and retain authored list order for diagnostics."""
    if identifier == "any" or identifier.startswith("family:"):
        raise ValidationError(
            "reserved-identifier", path, f"{identifier!r} is reserved applicability syntax."
        )
    required = {"label", "description"} if dimension == CatalogDimension.ENTITIES else set()
    optional = {"label", "description", "aliases"} - required
    if dimension == CatalogDimension.SCOPES:
        optional.add("parents")
    elif dimension == CatalogDimension.TECHNOLOGIES:
        optional.add("technology_families")
    elif dimension == CatalogDimension.ENTITIES:
        optional.add("documents")
    fields = read_mapping(value, path, required=required, optional=optional)
    if "label" not in fields and "description" not in fields:
        raise ValidationError(
            "missing-field", path, "A catalog record needs a label or description."
        )
    label = read_string(fields["label"], f"{path}.label") if "label" in fields else None
    description = (
        read_string(fields["description"], f"{path}.description")
        if "description" in fields
        else None
    )
    if description is not None and len(description) > 600:
        raise ValidationError(
            "description-too-long", f"{path}.description", "Description exceeds 600 characters."
        )
    aliases = read_strings(fields["aliases"], f"{path}.aliases") if "aliases" in fields else ()
    families = _read_relationships(fields, "technology_families", path)
    parents = _read_relationships(fields, "parents", path)
    documents = (
        _read_documents(fields["documents"], f"{path}.documents") if "documents" in fields else ()
    )
    return CatalogRecord(
        dimension=dimension,
        id=identifier,
        label=label,
        description=description,
        aliases=aliases,
        technology_families=families,
        parents=parents,
        documents=documents,
        source_ids=(source_id,),
    )


def _read_relationships(fields: Mapping[str, object], name: str, path: str) -> tuple[str, ...]:
    """Read explicit identifier relationships, permitting an intentionally empty list."""
    if name not in fields or fields[name] == []:
        return ()
    values = read_strings(fields[name], f"{path}.{name}")
    return tuple(
        read_identifier(value, f"{path}.{name}[{index}]") for index, value in enumerate(values)
    )


def _read_documents(value: object, path: str) -> tuple[DocumentReference, ...]:
    """Read unique source-qualified pointers without accessing their target files."""
    if not isinstance(value, list):
        raise ValidationError("invalid-type", path, "Expected a list of document references.")
    if not value:
        raise ValidationError("invalid-value", path, "An explicit document list must not be empty.")
    documents = tuple(
        read_document_reference(item, f"{path}[{index}]") for index, item in enumerate(value)
    )
    if len(documents) != len(set(documents)):
        raise ValidationError("duplicate-value", path, "Document references must be unique.")
    return documents


def _definition(record: CatalogRecord) -> CatalogRecord:
    """Compare set-valued definitions while preserving authored order in diagnostics."""
    return replace(
        record,
        source_ids=(),
        aliases=tuple(sorted(record.aliases)),
        technology_families=tuple(sorted(record.technology_families)),
        parents=tuple(sorted(record.parents)),
        documents=tuple(
            sorted(record.documents, key=lambda document: (document.source, document.path))
        ),
    )


def _validate_references(
    catalog: Catalog, paths: Mapping[tuple[CatalogDimension, str], str]
) -> None:
    """Resolve family, parent and source references after all source catalogs merge."""
    for record in catalog.records:
        path = paths[(record.dimension, record.id)]
        for index, family in enumerate(record.technology_families):
            catalog.require(
                CatalogDimension.TECHNOLOGY_FAMILIES, family, f"{path}.technology_families[{index}]"
            )
        for index, parent in enumerate(record.parents):
            catalog.require(CatalogDimension.SCOPES, parent, f"{path}.parents[{index}]")
        for index, document in enumerate(record.documents):
            if document.source not in catalog.source_ids:
                raise ValidationError(
                    "unknown-source",
                    f"{path}.documents[{index}].source",
                    f"Unknown document source: {document.source!r}.",
                )


def _validate_scope_cycles(
    catalog: Catalog, paths: Mapping[tuple[CatalogDimension, str], str]
) -> None:
    """Use iterative topological traversal so long valid hierarchies cannot overflow."""
    scopes = [record for record in catalog.records if record.dimension == CatalogDimension.SCOPES]
    unresolved = {record.id: len(record.parents) for record in scopes}
    children: dict[str, list[str]] = {record.id: [] for record in scopes}
    for record in scopes:
        for parent in record.parents:
            children[parent].append(record.id)
    pending = deque(identifier for identifier, count in unresolved.items() if count == 0)
    resolved_count = 0
    while pending:
        identifier = pending.popleft()
        resolved_count += 1
        for child in children[identifier]:
            unresolved[child] -= 1
            if unresolved[child] == 0:
                pending.append(child)
    if resolved_count != len(scopes):
        identifier = next(identifier for identifier, count in unresolved.items() if count)
        raise ValidationError(
            "scope-cycle",
            f"{paths[(CatalogDimension.SCOPES, identifier)]}.parents",
            f"Scope ancestry contains a cycle affecting {identifier!r}.",
        )
