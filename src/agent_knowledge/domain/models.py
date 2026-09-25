"""Represent validated knowledge and requests as immutable, I/O-free values.

Use the schema parsers at untrusted boundaries. Direct constructors are for
already-validated internal values; they are not a second raw-input parser.
"""

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeKind(StrEnum):
    """Name the closed initial knowledge taxonomy."""

    CONCEPT = "concept"
    FEATURE = "feature"
    WORKFLOW = "workflow"
    SYSTEM = "system"
    GUIDANCE = "guidance"
    RUNBOOK = "runbook"
    LIMITATION = "limitation"
    INCIDENT = "incident"


class CatalogDimension(StrEnum):
    """Name the configurable vocabulary dimensions."""

    SCOPES = "scopes"
    ENTITIES = "entities"
    TOPICS = "topics"
    LANGUAGES = "languages"
    TECHNOLOGIES = "technologies"
    TECHNOLOGY_FAMILIES = "technology_families"
    ENVIRONMENTS = "environments"


@dataclass(frozen=True, slots=True)
class DocumentReference:
    """Identify a file inside a configured knowledge source."""

    source: str
    path: str


@dataclass(frozen=True, slots=True)
class KnowledgeMetadata:
    """Preserve authored applicability, including absent optional dimensions."""

    kind: KnowledgeKind
    title: str
    description: str
    scope: tuple[str, ...]
    topics: tuple[str, ...]
    entities: tuple[str, ...] | None = None
    languages: tuple[str, ...] | None = None
    technologies: tuple[str, ...] | None = None
    environments: tuple[str, ...] | None = None
    aliases: tuple[str, ...] = ()
    terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Supply a validated document and text to matching without reading a file."""

    source_id: str
    metadata: KnowledgeMetadata
    body: str = ""


@dataclass(frozen=True, slots=True)
class TextQuery:
    """Express literal phrase alternatives and jointly required phrases."""

    any: tuple[str, ...] = ()
    all: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Retain explicit filters without injecting scopes, families or any."""

    kind: tuple[KnowledgeKind, ...] | None = None
    scope: tuple[str, ...] | None = None
    topics: tuple[str, ...] | None = None
    entities: tuple[str, ...] | None = None
    languages: tuple[str, ...] | None = None
    technologies: tuple[str, ...] | None = None
    environments: tuple[str, ...] | None = None
    sources: tuple[str, ...] | None = None
    text: TextQuery | None = None
    limit: int = 10
    continuation: str | None = None


@dataclass(frozen=True, slots=True)
class ValidateQuery:
    """Select exactly one explicit validation target family."""

    sources: tuple[str, ...] | None = None
    documents: tuple[DocumentReference, ...] | None = None
    signal_files: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SignalOrigin:
    """Keep capture context separate from a future document's applicability."""

    workspace_id: str
    project_path: str | None
    applicable_scopes: tuple[str, ...]
    source_ids: tuple[str, ...]
    harness: str | None = None
    session_id: str | None = None
    automation_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """Carry an evidence pointer without fetching or certifying its content."""

    type: str
    reference: str


@dataclass(frozen=True, slots=True)
class KnowledgeSignal:
    """Preserve a signal's supplied timestamp, provenance, hints and exact body."""

    id: str
    created_at: str
    kind_hint: KnowledgeKind
    origin: SignalOrigin
    evidence: tuple[EvidenceReference, ...]
    body: str
    entities: tuple[str, ...] | None = None
    technologies: tuple[str, ...] | None = None
