"""Verify strict metadata/query boundaries without file or process fixtures."""

import pytest

from agent_knowledge.domain.catalog import parse_catalogs
from agent_knowledge.domain.models import KnowledgeKind
from agent_knowledge.domain.schema import (
    parse_knowledge,
    parse_query,
    parse_signal,
    parse_validate_query,
)
from agent_knowledge.domain.validation import ValidationError
from tests.factories import catalog_data, knowledge_data, signal_data


def test_taxonomy_has_eight_document_kinds_including_guidance() -> None:
    """Expose record forms that support business and engineering knowledge."""
    assert {kind.value for kind in KnowledgeKind} == {
        "concept",
        "feature",
        "workflow",
        "system",
        "guidance",
        "runbook",
        "limitation",
        "incident",
    }


@pytest.mark.parametrize("kind", ["operating-rule", "qa-evidence"])
def test_retired_document_kinds_are_rejected(kind: str) -> None:
    """Require the new taxonomy without silently accepting old kind names."""
    with pytest.raises(ValidationError) as error:
        parse_knowledge(knowledge_data(kind=kind), parse_catalogs({"knowledge": catalog_data()}))
    assert error.value.path == "kind"


@pytest.mark.parametrize("kind", ["operating-rule", "qa-evidence"])
def test_retired_search_kinds_are_rejected(kind: str) -> None:
    """Do not turn a retired selector into a valid empty search."""
    with pytest.raises(ValidationError) as error:
        parse_query({"kind": [kind]}, parse_catalogs({"knowledge": catalog_data()}))
    assert error.value.path == "kind[0]"


@pytest.mark.parametrize("kind", ["operating-rule", "qa-evidence"])
def test_retired_signal_kind_hints_are_rejected(kind: str) -> None:
    """Keep compounding hints aligned with the supported document taxonomy."""
    with pytest.raises(ValidationError) as error:
        parse_signal(
            signal_data(kind_hint=kind),
            "A durable finding.",
            parse_catalogs({"knowledge": catalog_data()}),
        )
    assert error.value.path == "kind_hint"


def test_general_rule_preserves_explicit_unrestricted_applicability() -> None:
    """Keep any explicit, and leave absent entity metadata unclassified."""
    metadata = parse_knowledge(knowledge_data(), parse_catalogs({"knowledge": catalog_data()}))

    assert metadata.languages == ("any",)
    assert metadata.technologies == ("any",)
    assert metadata.entities is None


@pytest.mark.parametrize("field", ["languages", "technologies", "environments"])
def test_guidance_requires_explicit_applicability(field: str) -> None:
    """Reject a missing facet instead of inventing an always-applicable rule."""
    data = knowledge_data()
    del data[field]

    with pytest.raises(ValidationError) as error:
        parse_knowledge(data, parse_catalogs({"knowledge": catalog_data()}))

    assert error.value.code == "missing-field"
    assert error.value.path == field


def test_query_deduplicates_values_and_keeps_any_as_an_explicit_alternative() -> None:
    """Normalize duplicate requests without adding family or scope ancestors."""
    query = parse_query(
        {"scope": ["repo:orders"], "languages": ["any", "typescript", "any"]},
        parse_catalogs({"knowledge": catalog_data()}),
    )

    assert query.scope == ("repo:orders",)
    assert query.languages == ("any", "typescript")
    assert query.technologies is None


def test_unknown_identifier_is_a_validation_error_not_an_empty_query() -> None:
    """Keep misspelled vocabulary distinguishable from a successful no-match result."""
    with pytest.raises(ValidationError) as error:
        parse_query(
            {"entities": ["feature:histroy"]}, parse_catalogs({"knowledge": catalog_data()})
        )

    assert error.value.code == "unknown-identifier"


def test_signal_keeps_original_scope_and_body_without_promoting_a_claim() -> None:
    """Preserve provenance and advisory hints independently of canonical metadata."""
    body = "# Observation\n\nCheck the runner's transaction behavior before creating an index.\n"
    signal = parse_signal(signal_data(), body, parse_catalogs({"knowledge": catalog_data()}))

    assert signal.origin.project_path == "products/orders"
    assert signal.origin.applicable_scopes == ("org:example", "repo:orders")
    assert signal.technologies == ("postgresql",)
    assert signal.body == body


def test_harness_signal_without_session_id_is_rejected() -> None:
    data = signal_data()
    assert isinstance(data["origin"], dict)
    data["origin"]["harness"] = "codex"

    with pytest.raises(ValidationError) as error:
        parse_signal(data, "# Observation\n", parse_catalogs({"knowledge": catalog_data()}))

    assert error.value.code == "missing-field"
    assert error.value.path == "origin.session_id"


@pytest.mark.parametrize("session_id", ["", " ", "\t"])
def test_harness_origin_rejects_blank_session_id(session_id: str) -> None:
    data = signal_data()
    assert isinstance(data["origin"], dict)
    data["origin"].update({"harness": "codex", "session_id": session_id})

    with pytest.raises(ValidationError) as error:
        parse_signal(data, "# Observation\n", parse_catalogs({"knowledge": catalog_data()}))

    assert error.value.code == "invalid-value"
    assert error.value.path == "origin.session_id"


@pytest.mark.parametrize(
    "kind",
    [
        "concept",
        "feature",
        "workflow",
        "system",
        "runbook",
        "limitation",
        "incident",
    ],
)
def test_other_knowledge_kinds_can_leave_technology_unclassified(kind: str) -> None:
    """Preserve a missing optional restriction instead of inserting any."""
    data = knowledge_data(kind=kind)
    for field in ("languages", "technologies", "environments"):
        del data[field]

    metadata = parse_knowledge(data, parse_catalogs({"knowledge": catalog_data()}))

    assert metadata.languages is None
    assert metadata.technologies is None
    assert metadata.environments is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("scopes", ["org:example"]),
        ("subjects", ["feature:history"]),
        ("concerns", ["testing"]),
        ("engineering_concerns", ["testing"]),
        ("activity", ["planning"]),
        ("strength", "required"),
    ],
)
def test_obsolete_metadata_fields_are_rejected(field: str, value: object) -> None:
    """Prevent silently reviving the earlier retrieval contract."""
    with pytest.raises(ValidationError) as error:
        parse_knowledge(
            knowledge_data(**{field: value}), parse_catalogs({"knowledge": catalog_data()})
        )

    assert error.value.code == "unknown-field"


def test_old_topic_query_field_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        parse_query(
            {"engineering_concerns": ["testing"]}, parse_catalogs({"knowledge": catalog_data()})
        )
    assert (error.value.code, error.value.path) == ("unknown-field", "engineering_concerns")


def test_old_catalog_dimension_is_rejected() -> None:
    data = catalog_data() | {"engineering_concerns": {"testing": {"label": "Testing"}}}
    with pytest.raises(ValidationError) as error:
        parse_catalogs({"knowledge": data})
    assert (error.value.code, error.value.path) == (
        "unknown-field",
        "catalogs.knowledge.engineering_concerns",
    )


def test_guidance_signal_needs_no_topic_metadata() -> None:
    signal = parse_signal(
        signal_data(kind_hint="guidance"),
        "A durable finding.",
        parse_catalogs({"knowledge": catalog_data()}),
    )
    assert signal.kind_hint is KnowledgeKind.GUIDANCE


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", []),
        ("scope", "org:example"),
        ("scope", None),
        ("scope", ["org:example", "org:example"]),
        ("technologies", ["any", "postgresql"]),
        ("technologies", ["family:missing"]),
        ("entities", ["feature:unknown"]),
        ("topics", ["unknown-topic"]),
        ("languages", ["any", "typescript"]),
        ("title", 5),
        ("title", "  "),
        ("description", "x" * 601),
        ("kind", "issue"),
        ("schema_version", "knowledge.v2"),
    ],
)
def test_invalid_authored_metadata_fails_explicitly(field: str, value: object) -> None:
    """Reject coercion, mixed wildcard values and unregistered applicability."""
    with pytest.raises(ValidationError):
        parse_knowledge(
            knowledge_data(**{field: value}), parse_catalogs({"knowledge": catalog_data()})
        )


def test_signal_schema_cannot_be_accepted_as_canonical_knowledge() -> None:
    """Preserve the schema boundary even though both files use frontmatter."""
    with pytest.raises(ValidationError) as error:
        parse_knowledge(signal_data(), parse_catalogs({"knowledge": catalog_data()}))

    assert error.value.code == "unsupported-schema"


@pytest.mark.parametrize("value", [None, [], "metadata", 2, True])
def test_non_object_metadata_is_not_coerced(value: object) -> None:
    """Fail invalid roots before downstream matching can suggest absence."""
    with pytest.raises(ValidationError) as error:
        parse_knowledge(value, parse_catalogs({"knowledge": catalog_data()}))

    assert error.value.code == "invalid-type"


@pytest.mark.parametrize(
    "query_data",
    [
        {"scope": []},
        {"scope": None},
        {"scope": "repo:orders"},
        {"kind": ["issue"]},
        {"sources": ["unknown"]},
        {"sources": []},
        {"technologies": ["family:unknown"]},
        {"scope": ["any"]},
        {"limit": True},
        {"limit": 1.5},
        {"limit": 0},
        {"limit": 101},
        {"limit": "10"},
        {"text": {}},
        {"text": {"any": []}},
        {"text": {"any": [""]}},
        {"text": {"any": [False]}},
        {"text": {"query": "history"}},
        {"text": "history"},
        {"continuation": None},
        {"continuation": ""},
        {"subjects": ["feature:history"]},
        {"activity": "planning"},
    ],
)
def test_invalid_requests_do_not_become_broadened_queries(query_data: object) -> None:
    """Reject unknown fields, empty clauses and pagination type coercions."""
    with pytest.raises(ValidationError):
        parse_query(query_data, parse_catalogs({"knowledge": catalog_data()}))


def test_empty_query_has_no_implicit_context_or_applicability_filters() -> None:
    """Allow bounded enumeration without guessing a project, family or activity."""
    query = parse_query({}, parse_catalogs({"knowledge": catalog_data()}))

    assert query.kind is None
    assert query.scope is None
    assert query.sources is None
    assert query.text is None
    assert query.limit == 10


def test_query_accepts_explicit_family_and_normalizes_phrase_outer_whitespace() -> None:
    """Normalize input phrases while preserving each explicit clause."""
    query = parse_query(
        {
            "technologies": ["any", "postgresql", "family:relational-database"],
            "text": {"any": ["  Order history  ", "Order history"], "all": ["status"]},
            "limit": 100,
            "continuation": "opaque-cursor",
        },
        parse_catalogs({"knowledge": catalog_data()}),
    )

    assert query.technologies == ("any", "postgresql", "family:relational-database")
    assert query.text is not None and query.text.any == ("Order history",)
    assert query.text.all == ("status",)
    assert query.limit == 100
    assert query.continuation == "opaque-cursor"


@pytest.mark.parametrize(
    "created_at", ["2026-09-09", "2026-09-09T12:00:00", "2026-02-30T12:00:00Z", "tomorrow", 123]
)
def test_signal_timestamp_requires_an_explicit_valid_instant(created_at: object) -> None:
    """Validate supplied timestamps without consulting the current clock."""
    with pytest.raises(ValidationError):
        parse_signal(
            signal_data(created_at=created_at),
            "Claim",
            parse_catalogs({"knowledge": catalog_data()}),
        )


@pytest.mark.parametrize(
    "project_path",
    [
        "../orders",
        "/tmp/orders",
        "orders/../other",
        "C:/orders",
        "orders\\api",
        "orders//api",
        "orders/./api",
    ],
)
def test_signal_origin_cannot_traverse_or_name_an_absolute_project(project_path: str) -> None:
    """Reject unsafe placement inputs before a filesystem adapter sees them."""
    data = signal_data()
    origin = data["origin"]
    assert isinstance(origin, dict)
    origin["project_path"] = project_path

    with pytest.raises(ValidationError) as error:
        parse_signal(data, "Claim", parse_catalogs({"knowledge": catalog_data()}))

    assert error.value.code == "invalid-path"


def test_explicit_shared_origin_remains_non_project_provenance() -> None:
    """Accept an explicit null project association without inventing a shared scope."""
    data = signal_data()
    origin = data["origin"]
    assert isinstance(origin, dict)
    origin["project_path"] = None

    signal = parse_signal(
        data, "A durable cross-project observation.", parse_catalogs({"knowledge": catalog_data()})
    )

    assert signal.origin.project_path is None
    assert "shared" not in signal.origin.applicable_scopes


def test_signal_origin_preserves_explicit_empty_workspace_scopes() -> None:
    """Capture an unscoped workspace without inventing applicability for its claim."""
    data = signal_data()
    origin = data["origin"]
    assert isinstance(origin, dict)
    origin["applicable_scopes"] = []
    origin["project_path"] = None

    signal = parse_signal(
        data, "An unscoped observation.", parse_catalogs({"knowledge": catalog_data()})
    )

    assert signal.origin.applicable_scopes == ()
    assert signal.origin.source_ids == ("knowledge",)


@pytest.mark.parametrize("field,value", [("applicable_scopes", None), ("source_ids", [])])
def test_empty_workspace_scopes_do_not_relax_other_origin_requirements(
    field: str, value: object
) -> None:
    data = signal_data()
    origin = data["origin"]
    assert isinstance(origin, dict)
    origin[field] = value

    with pytest.raises(ValidationError) as caught:
        parse_signal(data, "Claim", parse_catalogs({"knowledge": catalog_data()}))
    assert caught.value.path == f"origin.{field}"


@pytest.mark.parametrize("body", ["", " \n\t", None, 12])
def test_signal_cannot_have_an_empty_or_non_text_claim(body: object) -> None:
    """Require authored claim text without attempting semantic truth validation."""
    with pytest.raises(ValidationError):
        parse_signal(signal_data(), body, parse_catalogs({"knowledge": catalog_data()}))


def test_mutating_input_lists_does_not_change_validated_metadata() -> None:
    """Take owned immutable values at the input boundary."""
    data = knowledge_data()
    metadata = parse_knowledge(data, parse_catalogs({"knowledge": catalog_data()}))
    scopes = data["scope"]
    assert isinstance(scopes, list)
    scopes.append("repo:orders")

    assert metadata.scope == ("org:example",)


def test_folded_yaml_description_can_retain_its_final_newline() -> None:
    """Accept the decoded text produced by ordinary YAML block descriptions."""
    description = "Review index benefits and maintenance costs.\n"

    metadata = parse_knowledge(
        knowledge_data(description=description), parse_catalogs({"knowledge": catalog_data()})
    )

    assert metadata.description == description


def test_signal_timestamp_rejects_an_overflowing_timezone_minute() -> None:
    """Do not accept Python's normalization of an invalid ISO offset."""
    with pytest.raises(ValidationError):
        parse_signal(
            signal_data(created_at="2026-09-09T12:00:00+01:99"),
            "A durable observation.",
            parse_catalogs({"knowledge": catalog_data()}),
        )


@pytest.mark.parametrize(
    "field,valid",
    [("technologies", "postgresql"), ("sources", "knowledge"), ("kind", "runbook")],
)
def test_query_error_indices_refer_to_original_input_before_deduplication(
    field: str, valid: str
) -> None:
    """Point at the invalid value rather than an earlier duplicated valid identifier."""
    with pytest.raises(ValidationError) as error:
        parse_query(
            {field: [valid, valid, "missing"]}, parse_catalogs({"knowledge": catalog_data()})
        )

    assert error.value.path == f"{field}[2]"


def test_validate_query_selects_one_explicit_target_family() -> None:
    catalog = parse_catalogs({"knowledge": catalog_data()})

    source_target = parse_validate_query({"sources": ["knowledge"]}, catalog)
    document_target = parse_validate_query(
        {"documents": [{"source": "knowledge", "path": "owner.md"}]}, catalog
    )
    signal_target = parse_validate_query({"signal_files": ["draft.md"]}, catalog)

    assert source_target.sources == ("knowledge",)
    assert document_target.documents is not None
    assert document_target.documents[0].path == "owner.md"
    assert signal_target.signal_files == ("draft.md",)


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"sources": ["knowledge"], "documents": []},
        {"sources": ["missing"]},
        {"documents": [{"source": "knowledge", "path": "owner.md"}] * 2},
        {"signal_files": []},
    ],
)
def test_validate_query_rejects_ambiguous_unknown_or_empty_targets(value: object) -> None:
    with pytest.raises(ValidationError):
        parse_validate_query(value, parse_catalogs({"knowledge": catalog_data()}))
