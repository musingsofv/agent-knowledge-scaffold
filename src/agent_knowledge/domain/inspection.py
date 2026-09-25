"""Validate explicit direct-file navigation requests without reading files."""

import re
from dataclasses import dataclass
from typing import Literal

from .catalog import Catalog
from .models import DocumentReference
from .schema import parse_query
from .validation import ValidationError, read_document_reference, read_mapping, read_string


@dataclass(frozen=True, slots=True)
class InspectQuery:
    """Identify one file and optional expected content/page identity."""

    document: DocumentReference
    expected_fingerprint: str | None = None
    limit: int = 10
    continuation: str | None = None
    view: Literal["navigation", "incoming"] = "navigation"
    sources: tuple[str, ...] | None = None


def parse_inspect_query(value: object, catalog: Catalog) -> InspectQuery:
    """Reuse page validation and require a configured, source-qualified document."""
    fields = read_mapping(
        value,
        "",
        {"document"},
        {"expected_fingerprint", "limit", "continuation", "view", "sources"},
    )
    document = read_document_reference(fields["document"], "document")
    if document.source not in catalog.source_ids:
        raise ValidationError("unknown-identifier", "document.source", "Unknown configured source.")
    expected = None
    if "expected_fingerprint" in fields:
        expected = read_string(fields["expected_fingerprint"], "expected_fingerprint")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
            raise ValidationError(
                "invalid-value",
                "expected_fingerprint",
                "Expected sha256:<64 lowercase hex digits>.",
            )
    view: Literal["navigation", "incoming"]
    match fields.get("view", "navigation"):
        case "navigation":
            view = "navigation"
            if "sources" in fields:
                raise ValidationError(
                    "invalid-field", "sources", "Scan sources are only valid for the incoming view."
                )
        case "incoming":
            view = "incoming"
        case _:
            raise ValidationError("invalid-value", "view", "Expected navigation or incoming.")
    page = parse_query(
        {key: fields[key] for key in ("limit", "continuation", "sources") if key in fields},
        catalog,
    )
    return InspectQuery(document, expected, page.limit, page.continuation, view, page.sources)
