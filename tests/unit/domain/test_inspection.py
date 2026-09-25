"""Check strict direct-navigation input before any file access."""

import pytest

from agent_knowledge.domain.catalog import parse_catalogs
from agent_knowledge.domain.inspection import parse_inspect_query
from agent_knowledge.domain.validation import ValidationError
from tests.factories import catalog_data


@pytest.mark.parametrize(
    "changes",
    [
        {"document": {"source": "unknown", "path": "a.md"}},
        {"document": {"source": "knowledge", "path": "../a.md"}},
        {"expected_fingerprint": "whatever"},
        {"expected_fingerprint": None},
        {"limit": True},
        {"limit": 101},
        {"continuation": ""},
        {"text": "no"},
        {"view": "reverse"},
        {"view": None},
        {"sources": ["knowledge"]},
        {"view": "navigation", "sources": ["knowledge"]},
        {"view": "incoming", "sources": ["unknown"]},
        {"view": "incoming", "sources": []},
        {"view": "incoming", "sources": "knowledge"},
    ],
)
def test_bad_inspection_requests_are_rejected(changes: dict[str, object]) -> None:
    catalog = parse_catalogs({"knowledge": catalog_data()})
    value = {"document": {"source": "knowledge", "path": "runbook.md"}} | changes
    with pytest.raises(ValidationError):
        parse_inspect_query(value, catalog)


def test_inspection_retains_explicit_page_and_identity() -> None:
    query = parse_inspect_query(
        {
            "document": {"source": "knowledge", "path": "runbook.md"},
            "expected_fingerprint": "sha256:" + "a" * 64,
            "limit": 20,
        },
        parse_catalogs({"knowledge": catalog_data()}),
    )
    assert query.document.path == "runbook.md"
    assert query.limit == 20
    assert query.continuation is None
    assert query.view == "navigation"
    assert query.sources is None


def test_incoming_keeps_target_identity_separate_from_scan_sources() -> None:
    query = parse_inspect_query(
        {
            "document": {"source": "knowledge", "path": "removed.md"},
            "view": "incoming",
            "sources": ["other"],
        },
        parse_catalogs({"knowledge": catalog_data(), "other": catalog_data()}),
    )
    assert query.view == "incoming"
    assert query.document.source == "knowledge"
    assert query.sources == ("other",)
