from copy import deepcopy

import pytest

from agent_knowledge.domain.catalog import parse_catalogs
from agent_knowledge.domain.models import CatalogDimension, DocumentReference
from agent_knowledge.domain.validation import ValidationError


def empty_catalog() -> dict[str, object]:
    return {
        "schema_version": "knowledge-catalog.v1",
        **{dimension.value: {} for dimension in CatalogDimension},
    }


def catalog_with(dimension: str, records: object) -> dict[str, object]:
    return {**empty_catalog(), dimension: records}


def test_empty_catalogs_are_valid() -> None:
    catalog = parse_catalogs({"org": empty_catalog()})
    assert catalog.records == ()
    assert catalog.source_ids == ("org",)


def test_definitions_coalesce_with_deterministic_source_provenance() -> None:
    definition = catalog_with("languages", {"python": {"label": "Python"}})
    catalog = parse_catalogs({"team": definition, "org": deepcopy(definition)})
    assert len(catalog.records) == 1
    record = catalog.require(CatalogDimension.LANGUAGES, "python", "query.languages[0]")
    assert record.label == "Python"
    assert record.source_ids == ("org", "team")


def test_same_identifier_can_exist_in_different_dimensions() -> None:
    definition = {
        **empty_catalog(),
        "scopes": {"project:checkout": {"label": "Checkout project"}},
        "entities": {
            "project:checkout": {
                "label": "Checkout",
                "description": "The purchase-completion project.",
            }
        },
    }
    catalog = parse_catalogs({"org": definition})
    assert len(catalog.records) == 2


def test_lookup_unknown_id_reports_the_callers_path() -> None:
    catalog = parse_catalogs({"org": empty_catalog()})
    with pytest.raises(ValidationError) as error:
        catalog.require(CatalogDimension.LANGUAGES, "typscript", "query.languages[0]")
    assert error.value.code == "unknown-identifier"
    assert error.value.path == "query.languages[0]"


def test_family_and_entity_references_resolve_across_sources() -> None:
    catalog = parse_catalogs(
        {
            "team": {
                **empty_catalog(),
                "technologies": {
                    "postgresql": {
                        "label": "PostgreSQL",
                        "aliases": ["Postgres"],
                        "technology_families": ["relational-database"],
                    }
                },
                "entities": {
                    "service:orders": {
                        "label": "Orders",
                        "description": "Stores customer orders.",
                        "documents": [{"source": "org", "path": "systems/orders.md"}],
                    }
                },
            },
            "org": catalog_with(
                "technology_families",
                {"relational-database": {"description": "Relational database engines."}},
            ),
        }
    )
    postgres = catalog.require(CatalogDimension.TECHNOLOGIES, "postgresql", "test")
    assert postgres.technology_families == ("relational-database",)
    assert postgres.aliases == ("Postgres",)
    orders = catalog.require(CatalogDimension.ENTITIES, "service:orders", "test")
    assert orders.documents == (DocumentReference("org", "systems/orders.md"),)


def test_scope_ancestors_are_explicit_and_support_diamonds() -> None:
    catalog = parse_catalogs(
        {
            "org": catalog_with(
                "scopes",
                {
                    "org:example": {"label": "Example", "parents": []},
                    "team:platform": {"label": "Platform", "parents": ["org:example"]},
                    "project:checkout": {"label": "Checkout", "parents": ["org:example"]},
                },
            ),
            "team": catalog_with(
                "scopes",
                {
                    "repo:orders": {
                        "label": "Orders",
                        "parents": ["team:platform", "project:checkout"],
                    }
                },
            ),
        }
    )
    assert catalog.scope_ancestors("repo:orders") == (
        "org:example",
        "project:checkout",
        "team:platform",
    )
    assert catalog.scope_ancestors("org:example") == ()
    assert catalog.require(CatalogDimension.SCOPES, "repo:orders", "test").parents == (
        "team:platform",
        "project:checkout",
    )


def test_scope_hierarchy_is_not_inferred_from_names() -> None:
    catalog = parse_catalogs(
        {
            "org": catalog_with(
                "scopes", {"org:example": {"label": "Example"}, "repo:orders": {"label": "Orders"}}
            )
        }
    )
    assert catalog.scope_ancestors("repo:orders") == ()


def test_deep_valid_scope_hierarchy_does_not_depend_on_recursion_limit() -> None:
    scopes = {
        f"scope:{index}": {"label": str(index), "parents": [f"scope:{index - 1}"] if index else []}
        for index in range(1200)
    }
    catalog = parse_catalogs({"org": catalog_with("scopes", scopes)})
    assert len(catalog.scope_ancestors("scope:1199")) == 1199


def test_reordered_relationships_coalesce_without_losing_source_provenance() -> None:
    first = {
        **empty_catalog(),
        "technologies": {
            "postgresql": {"label": "PostgreSQL", "technology_families": ["sql", "database"]}
        },
        "technology_families": {"sql": {"label": "SQL"}, "database": {"label": "Database"}},
    }
    second = {
        **first,
        "technologies": {
            "postgresql": {"label": "PostgreSQL", "technology_families": ["database", "sql"]}
        },
    }
    catalog = parse_catalogs({"org": first, "team": second})
    assert catalog.require(CatalogDimension.TECHNOLOGIES, "postgresql", "test").source_ids == (
        "org",
        "team",
    )


def test_unknown_relationship_diagnostic_uses_authored_index() -> None:
    definition = {
        **empty_catalog(),
        "technologies": {
            "postgresql": {"label": "PostgreSQL", "technology_families": ["sql", "absent"]}
        },
        "technology_families": {"sql": {"label": "SQL"}},
    }
    with pytest.raises(ValidationError) as error:
        parse_catalogs({"org": definition})
    assert error.value.path == "catalogs.org.technologies.postgresql.technology_families[1]"


def test_empty_explicit_technology_membership_is_valid() -> None:
    catalog = parse_catalogs(
        {
            "org": catalog_with(
                "technologies", {"postgresql": {"label": "PostgreSQL", "technology_families": []}}
            )
        }
    )
    assert (
        catalog.require(CatalogDimension.TECHNOLOGIES, "postgresql", "test").technology_families
        == ()
    )


def test_input_changes_cannot_mutate_validated_catalog() -> None:
    families = ["relational-database"]
    definition = {
        **empty_catalog(),
        "technologies": {"postgresql": {"label": "PostgreSQL", "technology_families": families}},
        "technology_families": {"relational-database": {"label": "Relational databases"}},
    }
    catalog = parse_catalogs({"org": definition})
    families.append("unexpected")
    assert catalog.require(
        CatalogDimension.TECHNOLOGIES, "postgresql", "test"
    ).technology_families == ("relational-database",)


def test_ambiguous_aliases_preserve_separate_canonical_records() -> None:
    catalog = parse_catalogs(
        {
            "org": catalog_with(
                "entities",
                {
                    "feature:order-history": {
                        "label": "Customer order history",
                        "description": "The customer order history screen.",
                        "aliases": ["history"],
                    },
                    "feature:audit-history": {
                        "label": "Operator audit history",
                        "description": "The operator action audit trail.",
                        "aliases": ["history"],
                    },
                },
            )
        }
    )
    assert [record.id for record in catalog.records if "history" in record.aliases] == [
        "feature:audit-history",
        "feature:order-history",
    ]


@pytest.mark.parametrize(
    "definition",
    [
        [],
        {"schema_version": "knowledge-catalog.v1"},
        {**empty_catalog(), "schema_version": "knowledge-catalog.v2"},
        {**empty_catalog(), "subjects": {}},
        catalog_with("technologies", []),
        catalog_with("scopes", {42: {"label": "Invalid key"}}),
        catalog_with("languages", {"TypeScript": {"label": "TypeScript"}}),
        catalog_with("languages", {"any": {"label": "Any"}}),
        catalog_with("technologies", {"family:sql": {"label": "SQL"}}),
        catalog_with("languages", {"python": "Python"}),
        catalog_with("languages", {"python": {}}),
        catalog_with("languages", {"python": {"label": ""}}),
        catalog_with("languages", {"python": {"label": 42}}),
        catalog_with("languages", {"python": {"description": "x" * 601}}),
        catalog_with("languages", {"python": {"label": " \t "}}),
        catalog_with("languages", {"python": {"label": "Python", "aliases": "py"}}),
        catalog_with("languages", {"python": {"label": "Python", "aliases": []}}),
        catalog_with("languages", {"python": {"label": "Python", "aliases": ["py", "py"]}}),
        catalog_with("languages", {"python": {"label": "Python", "unexpected": True}}),
        catalog_with("entities", {"service:orders": {"label": "Orders"}}),
        catalog_with(
            "technology_families", {"sql": {"label": "SQL", "technology_families": ["database"]}}
        ),
        catalog_with(
            "technologies",
            {"postgresql": {"label": "PostgreSQL", "technology_families": ["missing"]}},
        ),
        catalog_with("scopes", {"repo:orders": {"label": "Orders", "parents": ["missing"]}}),
    ],
)
def test_invalid_catalog_shapes_and_references_are_errors(definition: object) -> None:
    with pytest.raises(ValidationError):
        parse_catalogs({"org": definition})


@pytest.mark.parametrize("parents", [["repo:orders"], ["team:commerce"]])
def test_scope_cycles_are_rejected(parents: list[str]) -> None:
    definition = catalog_with(
        "scopes",
        {
            "repo:orders": {"label": "Orders", "parents": parents},
            "team:commerce": {"label": "Commerce", "parents": ["repo:orders"]},
        },
    )
    with pytest.raises(ValidationError) as error:
        parse_catalogs({"org": definition})
    assert error.value.code == "scope-cycle"


def test_conflicting_source_definitions_are_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        parse_catalogs(
            {
                "org": catalog_with("languages", {"python": {"label": "Python"}}),
                "team": catalog_with("languages", {"python": {"label": "CPython only"}}),
            }
        )
    assert error.value.code == "catalog-conflict"
    assert "python" in error.value.message
    assert "org" in error.value.message
    assert "team" in error.value.message


@pytest.mark.parametrize(
    "path",
    [
        "/secrets.md",
        "../outside.md",
        "runbooks/../outside.md",
        "a\\b.md",
        "a//b.md",
        "a/./b.md",
        "https://example.com/a.md",
        "a.md#heading",
    ],
)
def test_entity_references_require_safe_source_relative_paths(path: str) -> None:
    definition = catalog_with(
        "entities",
        {
            "service:orders": {
                "label": "Orders",
                "description": "Stores orders.",
                "documents": [{"source": "org", "path": path}],
            }
        },
    )
    with pytest.raises(ValidationError):
        parse_catalogs({"org": definition})


def test_entity_reference_to_unknown_source_is_rejected() -> None:
    definition = catalog_with(
        "entities",
        {
            "service:orders": {
                "label": "Orders",
                "description": "Stores orders.",
                "documents": [{"source": "absent", "path": "systems/orders.md"}],
            }
        },
    )
    with pytest.raises(ValidationError) as error:
        parse_catalogs({"org": definition})
    assert error.value.code == "unknown-source"


@pytest.mark.parametrize(
    "references",
    [
        [],
        "systems/orders.md",
        [{"source": "org"}],
        [{"source": "org", "path": "systems/orders.md", "anchor": "overview"}],
    ],
)
def test_invalid_entity_document_reference_shapes_are_rejected(references: object) -> None:
    definition = catalog_with(
        "entities",
        {
            "service:orders": {
                "label": "Orders",
                "description": "Stores orders.",
                "documents": references,
            }
        },
    )
    with pytest.raises(ValidationError):
        parse_catalogs({"org": definition})


def test_duplicate_entity_document_references_are_rejected() -> None:
    reference = {"source": "org", "path": "systems/orders.md"}
    definition = catalog_with(
        "entities",
        {
            "service:orders": {
                "label": "Orders",
                "description": "Stores orders.",
                "documents": [reference, reference],
            }
        },
    )
    with pytest.raises(ValidationError) as error:
        parse_catalogs({"org": definition})
    assert error.value.code == "duplicate-value"


@pytest.mark.parametrize("schema_version", [None, 1, True, [], {}])
def test_schema_version_requires_a_string(schema_version: object) -> None:
    definition = {**empty_catalog(), "schema_version": schema_version}
    with pytest.raises(ValidationError) as error:
        parse_catalogs({"org": definition})
    assert error.value.code == "invalid-type"
    assert error.value.path == "catalogs.org.schema_version"
