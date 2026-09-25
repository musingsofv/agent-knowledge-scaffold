"""Validate signal operation requests and explicit capture context in memory."""

from dataclasses import replace

import pytest

from agent_knowledge.domain.catalog import parse_catalogs
from agent_knowledge.domain.models import SignalOrigin
from agent_knowledge.domain.schema import parse_signal
from agent_knowledge.domain.signals import (
    SignalListQuery,
    SignalRecordQuery,
    parse_signal_list_query,
    parse_signal_record_query,
    signal_workspace_id,
    validate_signal_origin,
)
from agent_knowledge.domain.validation import ValidationError
from tests.factories import catalog_data, signal_data


@pytest.mark.parametrize("file", ["signal.md", "../drafts/index.md", "/tmp/draft signal.md"])
def test_record_retains_literal_authored_path(file: str) -> None:
    assert parse_signal_record_query({"file": file}) == SignalRecordQuery(file)


@pytest.mark.parametrize(
    ("value", "code", "path"),
    [
        (None, "invalid-type", ""),
        ({}, "missing-field", "file"),
        ({"file": None}, "invalid-type", "file"),
        ({"file": ""}, "invalid-value", "file"),
        ({"file": "draft\x00.md"}, "invalid-value", "file"),
        ({"file": "~/draft.md"}, "invalid-path", "file"),
        ({"file": "$DRAFT/signal.md"}, "invalid-path", "file"),
        ({"file": "https://example.com/draft.md"}, "invalid-path", "file"),
        ({"file": "draft\\signal.md"}, "invalid-path", "file"),
        ({"file": " draft.md"}, "invalid-path", "file"),
        ({"file": "draft\nsignal.md"}, "invalid-path", "file"),
        ({"file": "draft.md", "overwrite": True}, "unknown-field", "overwrite"),
    ],
)
def test_record_rejects_invalid_or_unsupported_requests(
    value: object, code: str, path: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_signal_record_query(value)
    assert (caught.value.code, caught.value.path) == (code, path)


def test_list_defaults_to_workspace_signals_and_standard_page_size() -> None:
    catalog = parse_catalogs({"knowledge": catalog_data()})
    assert parse_signal_list_query({}, catalog) == SignalListQuery()


def test_list_retains_explicit_shared_selection_and_pagination() -> None:
    catalog = parse_catalogs({"knowledge": catalog_data()})
    assert parse_signal_list_query(
        {"include_shared": True, "limit": 100, "continuation": "opaque-page"}, catalog
    ) == SignalListQuery(True, 100, "opaque-page")
    assert parse_signal_list_query({"include_shared": False, "limit": 1}, catalog) == (
        SignalListQuery(False, 1)
    )


def test_list_retains_an_exact_session_filter() -> None:
    catalog = parse_catalogs({"knowledge": catalog_data()})

    assert parse_signal_list_query(
        {"include_shared": True, "session_id": "claude-session-1", "limit": 20}, catalog
    ) == SignalListQuery(True, 20, None, "claude-session-1")


@pytest.mark.parametrize(
    ("value", "code", "path"),
    [
        ([], "invalid-type", ""),
        ({"include_shared": "true"}, "invalid-type", "include_shared"),
        ({"include_shared": 1}, "invalid-type", "include_shared"),
        ({"include_shared": None}, "invalid-type", "include_shared"),
        ({"limit": True}, "invalid-type", "limit"),
        ({"limit": "10"}, "invalid-type", "limit"),
        ({"limit": 0}, "invalid-value", "limit"),
        ({"limit": 101}, "invalid-value", "limit"),
        ({"continuation": None}, "invalid-type", "continuation"),
        ({"continuation": ""}, "invalid-value", "continuation"),
        ({"continuation": "\x00"}, "invalid-value", "continuation"),
        ({"session_id": None}, "invalid-type", "session_id"),
        ({"session_id": ""}, "invalid-value", "session_id"),
        ({"session_id": "session id"}, "invalid-value", "session_id"),
        ({"session_id": "session/id"}, "invalid-value", "session_id"),
        ({"scope": ["org:example"]}, "unknown-field", "scope"),
        ({"sources": ["knowledge"]}, "unknown-field", "sources"),
    ],
)
def test_list_rejects_invalid_pagination_and_unsupported_filters(
    value: object, code: str, path: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        parse_signal_list_query(value, parse_catalogs({"knowledge": catalog_data()}))
    assert (caught.value.code, caught.value.path) == (code, path)


def _origin() -> SignalOrigin:
    return parse_signal(
        signal_data(),
        "A reproducible indexing observation.",
        parse_catalogs({"knowledge": catalog_data()}),
    ).origin


def _validate(origin: SignalOrigin, *, project_path: str | None = "products/orders") -> None:
    validate_signal_origin(
        origin,
        workspace_id="repo:orders",
        applicable_scopes=("org:example", "repo:orders"),
        source_ids=("knowledge",),
        project_path=project_path,
    )


def test_origin_matches_loaded_workspace_without_requiring_authored_order() -> None:
    origin = replace(
        _origin(),
        applicable_scopes=("repo:orders", "org:example"),
        source_ids=("team", "knowledge"),
    )
    validate_signal_origin(
        origin,
        workspace_id="repo:orders",
        applicable_scopes=("org:example", "repo:orders"),
        source_ids=("knowledge", "team"),
        project_path="products/orders",
    )


def test_harness_origin_requires_a_session_id() -> None:
    metadata = signal_data()
    metadata["origin"] = {
        **metadata["origin"],
        "harness": "claude",
    }

    with pytest.raises(ValidationError) as caught:
        parse_signal(metadata, "A signal claim.", parse_catalogs({"knowledge": catalog_data()}))

    assert caught.value.code == "missing-field"
    assert caught.value.path == "origin.session_id"


def test_harness_origin_preserves_the_exact_session_id() -> None:
    metadata = signal_data()
    metadata["origin"] = {
        **metadata["origin"],
        "harness": "claude",
        "session_id": "claude-session-1",
    }

    signal = parse_signal(
        metadata, "A signal claim.", parse_catalogs({"knowledge": catalog_data()})
    )

    assert signal.origin.session_id == "claude-session-1"


def test_non_harness_origin_can_omit_a_session_id() -> None:
    signal = parse_signal(
        signal_data(), "A manual signal claim.", parse_catalogs({"knowledge": catalog_data()})
    )

    assert signal.origin.harness is None
    assert signal.origin.session_id is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workspace_id", "repo:other"),
        ("workspace_id", "repo:Orders"),
        ("project_path", "other/orders"),
        ("project_path", "products/Orders"),
        ("project_path", None),
        ("applicable_scopes", ("repo:orders",)),
        ("applicable_scopes", ("org:example", "repo:orders", "repo:other")),
        ("source_ids", ()),
        ("source_ids", ("knowledge", "other")),
        ("source_ids", ("other",)),
    ],
)
def test_origin_requires_exact_context_and_reports_mismatching_field(
    field: str, value: object
) -> None:
    origin = replace(_origin(), **{field: value})
    with pytest.raises(ValidationError) as caught:
        _validate(origin)
    assert caught.value.code == "origin-mismatch"
    assert caught.value.path == f"origin.{field}"
    assert caught.value.message


def test_shared_origin_requires_explicit_absence_of_project() -> None:
    _validate(replace(_origin(), project_path=None), project_path=None)
    with pytest.raises(ValidationError) as caught:
        _validate(_origin(), project_path=None)
    assert caught.value.path == "origin.project_path"


def test_empty_configured_scope_set_is_compared_without_inference() -> None:
    origin = replace(_origin(), applicable_scopes=(), project_path=None)
    validate_signal_origin(
        origin,
        workspace_id="repo:orders",
        applicable_scopes=(),
        source_ids=("knowledge",),
        project_path=None,
    )


def test_workspace_routing_does_not_apply_the_current_workspaces_catalog() -> None:
    metadata = {
        "schema_version": "knowledge-signal.v1",
        "origin": {"workspace_id": "repo:other", "source_ids": ["foreign-source"]},
        "technologies": ["foreign-engine"],
        "uninspected_field": {"future": "payload"},
    }
    assert signal_workspace_id(metadata) == "repo:other"


@pytest.mark.parametrize(
    ("metadata", "code", "path"),
    [
        ([], "invalid-type", ""),
        ({}, "missing-field", "schema_version"),
        ({"schema_version": "knowledge.v1"}, "unsupported-schema", "schema_version"),
        ({"schema_version": None}, "invalid-type", "schema_version"),
        ({"schema_version": "knowledge-signal.v1"}, "missing-field", "origin"),
        (
            {"schema_version": "knowledge-signal.v1", "origin": []},
            "invalid-type",
            "origin",
        ),
        (
            {"schema_version": "knowledge-signal.v1", "origin": {}},
            "missing-field",
            "origin.workspace_id",
        ),
        (
            {"schema_version": "knowledge-signal.v1", "origin": {"workspace_id": None}},
            "invalid-type",
            "origin.workspace_id",
        ),
        (
            {"schema_version": "knowledge-signal.v1", "origin": {"workspace_id": "Repo A"}},
            "invalid-identifier",
            "origin.workspace_id",
        ),
    ],
)
def test_workspace_routing_rejects_unidentifiable_signal_envelopes(
    metadata: object, code: str, path: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        signal_workspace_id(metadata)
    assert (caught.value.code, caught.value.path) == (code, path)
