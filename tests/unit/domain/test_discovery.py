"""Pure catalog-discovery requests and stable candidate selection."""

from dataclasses import FrozenInstanceError, replace

import pytest

from agent_knowledge.domain.catalog import Catalog, parse_catalogs
from agent_knowledge.domain.discovery import CatalogQuery, parse_catalog_query, select_catalog
from agent_knowledge.domain.models import CatalogDimension, TextQuery
from agent_knowledge.domain.validation import ValidationError


def empty_catalog() -> dict[str, object]:
    return {
        "schema_version": "knowledge-catalog.v1",
        **{dimension.value: {} for dimension in CatalogDimension},
    }


@pytest.fixture
def catalog() -> Catalog:
    order_history = {
        "label": "Order history",
        "description": "Inspect and filter completed orders by status.",
        "aliases": ["Past orders", "Purchase timeline"],
    }
    postgresql = {
        "label": "PostgreSQL",
        "description": "The orders persistence engine.",
        "aliases": ["Postgres"],
        "technology_families": ["relational-database"],
    }
    return parse_catalogs(
        {
            "org": {
                **empty_catalog(),
                "entities": {
                    "feature:order-history": order_history,
                    "feature:order-archive": {
                        "label": "Order archive",
                        "description": "Inspect retained purchase records.",
                        "aliases": ["Past orders"],
                    },
                },
                "technologies": {
                    "postgresql": postgresql,
                    "mysql": {"label": "MySQL", "description": "Another database engine."},
                },
                "technology_families": {
                    "relational-database": {"label": "Relational database"},
                },
            },
            "commerce": {
                **empty_catalog(),
                "entities": {
                    "feature:order-history": order_history,
                    "service:orders-api": {
                        "label": "Orders API",
                        "description": "Retrieve and store customer orders.",
                        "documents": [{"source": "org", "path": "systems/orders.md"}],
                    },
                },
                "technologies": {"postgresql": postgresql},
            },
            "empty": empty_catalog(),
        }
    )


def test_parse_defaults_and_required_dimension(catalog: Catalog) -> None:
    assert parse_catalog_query({"dimension": "entities"}, catalog) == CatalogQuery(
        dimension=CatalogDimension.ENTITIES
    )


def test_parse_preserves_explicit_selectors_and_normalizes_duplicates(catalog: Catalog) -> None:
    query = parse_catalog_query(
        {
            "dimension": "technologies",
            "ids": ["postgresql", "mysql", "postgresql"],
            "sources": ["commerce", "org", "commerce"],
            "text": {"any": [" Postgres ", "Postgres"], "all": ["engine"]},
            "limit": 100,
            "continuation": "opaque-cursor",
        },
        catalog,
    )
    assert query == CatalogQuery(
        dimension=CatalogDimension.TECHNOLOGIES,
        ids=("postgresql", "mysql"),
        sources=("commerce", "org"),
        text=TextQuery(any=("Postgres",), all=("engine",)),
        limit=100,
        continuation="opaque-cursor",
    )


@pytest.mark.parametrize("field", ("dimension", "ids", "text", "limit"))
def test_query_is_immutable(catalog: Catalog, field: str) -> None:
    query = parse_catalog_query({"dimension": "entities"}, catalog)
    with pytest.raises(FrozenInstanceError):
        setattr(query, field, None)


@pytest.mark.parametrize(
    ("raw_request", "code", "path"),
    [
        (None, "invalid-type", ""),
        ([], "invalid-type", ""),
        ({}, "missing-field", "dimension"),
        ({"dimension": "subjects"}, "invalid-value", "dimension"),
        ({"dimension": "Entities"}, "invalid-value", "dimension"),
        ({"dimension": " entities "}, "invalid-value", "dimension"),
        ({"dimension": None}, "invalid-type", "dimension"),
        ({"dimension": ["entities"]}, "invalid-type", "dimension"),
        ({"dimension": "entities", "scope": ["org:example"]}, "unknown-field", "scope"),
        ({"dimension": "entities", "ids": []}, "invalid-value", "ids"),
        ({"dimension": "entities", "ids": "feature:order-history"}, "invalid-type", "ids"),
        ({"dimension": "entities", "ids": None}, "invalid-type", "ids"),
        ({"dimension": "entities", "ids": [False]}, "invalid-type", "ids[0]"),
        ({"dimension": "entities", "ids": [" "]}, "invalid-value", "ids[0]"),
        ({"dimension": "entities", "ids": ["postgresql"]}, "unknown-identifier", "ids[0]"),
        ({"dimension": "entities", "ids": ["Past orders"]}, "unknown-identifier", "ids[0]"),
        (
            {"dimension": "entities", "ids": ["feature:order-history"] * 2 + ["missing"]},
            "unknown-identifier",
            "ids[2]",
        ),
        ({"dimension": "entities", "sources": []}, "invalid-value", "sources"),
        ({"dimension": "entities", "sources": "org"}, "invalid-type", "sources"),
        ({"dimension": "entities", "sources": ["org", None]}, "invalid-type", "sources[1]"),
        (
            {"dimension": "entities", "sources": ["org", "org", "missing"]},
            "unknown-identifier",
            "sources[2]",
        ),
        ({"dimension": "entities", "text": {}}, "invalid-value", "text"),
        ({"dimension": "entities", "text": "orders"}, "invalid-type", "text"),
        ({"dimension": "entities", "text": {"any": []}}, "invalid-value", "text.any"),
        ({"dimension": "entities", "text": {"all": [False]}}, "invalid-type", "text.all[0]"),
        ({"dimension": "entities", "text": {"query": "orders"}}, "unknown-field", "text.query"),
        ({"dimension": "entities", "limit": True}, "invalid-type", "limit"),
        ({"dimension": "entities", "limit": 10.0}, "invalid-type", "limit"),
        ({"dimension": "entities", "limit": "10"}, "invalid-type", "limit"),
        ({"dimension": "entities", "limit": 0}, "invalid-value", "limit"),
        ({"dimension": "entities", "limit": 101}, "invalid-value", "limit"),
        ({"dimension": "entities", "continuation": None}, "invalid-type", "continuation"),
        ({"dimension": "entities", "continuation": " "}, "invalid-value", "continuation"),
    ],
)
def test_invalid_requests_report_original_input_locations(
    catalog: Catalog, raw_request: object, code: str, path: str
) -> None:
    with pytest.raises(ValidationError) as error:
        parse_catalog_query(raw_request, catalog)
    assert error.value.code == code
    assert error.value.path == path


def test_cli_feature_discovery_keeps_ambiguous_candidates(catalog: Catalog) -> None:
    query = parse_catalog_query(
        {"dimension": "entities", "text": {"any": ["past orders", "order history"]}, "limit": 10},
        catalog,
    )
    records = select_catalog(query, catalog)
    assert [(record.id, record.label) for record in records] == [
        ("feature:order-archive", "Order archive"),
        ("feature:order-history", "Order history"),
    ]


def test_cli_technology_lookup_returns_family_and_full_provenance(catalog: Catalog) -> None:
    query = parse_catalog_query(
        {"dimension": "technologies", "ids": ["postgresql"], "limit": 10}, catalog
    )
    (record,) = select_catalog(query, catalog)
    assert record.label == "PostgreSQL"
    assert record.aliases == ("Postgres",)
    assert record.technology_families == ("relational-database",)
    assert record.source_ids == ("commerce", "org")


@pytest.mark.parametrize(
    ("raw_request", "expected"),
    [
        (
            {"dimension": "entities"},
            ("feature:order-archive", "feature:order-history", "service:orders-api"),
        ),
        ({"dimension": "technologies"}, ("mysql", "postgresql")),
        ({"dimension": "scopes"}, ()),
        (
            {"dimension": "entities", "sources": ["commerce"]},
            ("feature:order-history", "service:orders-api"),
        ),
        ({"dimension": "entities", "sources": ["empty"]}, ()),
        ({"dimension": "technologies", "ids": ["mysql"], "sources": ["commerce"]}, ()),
        ({"dimension": "technologies", "ids": ["mysql", "postgresql"]}, ("mysql", "postgresql")),
        ({"dimension": "technologies", "text": {"any": ["Postgres"]}}, ("postgresql",)),
        ({"dimension": "technologies", "text": {"any": ["persistence engine"]}}, ("postgresql",)),
        (
            {"dimension": "entities", "text": {"any": ["feature:order-history"]}},
            ("feature:order-history",),
        ),
        ({"dimension": "technologies", "text": {"any": ["not present"]}}, ()),
        ({"dimension": "technologies", "text": {"any": ["relational database"]}}, ()),
        ({"dimension": "entities", "text": {"any": ["systems/orders.md"]}}, ()),
        ({"dimension": "entities", "text": {"any": ["commerce"]}}, ()),
        (
            {"dimension": "technologies", "text": {"any": ["Postgres"], "all": ["persistence"]}},
            ("postgresql",),
        ),
        ({"dimension": "technologies", "text": {"any": ["Postgres"], "all": ["another"]}}, ()),
        (
            {
                "dimension": "entities",
                "ids": ["service:orders-api"],
                "text": {"any": ["past orders"]},
            },
            (),
        ),
    ],
)
def test_catalog_filters_and_text_surfaces(
    catalog: Catalog, raw_request: object, expected: tuple[str, ...]
) -> None:
    records = select_catalog(parse_catalog_query(raw_request, catalog), catalog)
    assert tuple(record.id for record in records) == expected


def test_filtering_a_source_does_not_rewrite_record_provenance(catalog: Catalog) -> None:
    query = CatalogQuery(
        dimension=CatalogDimension.TECHNOLOGIES, ids=("postgresql",), sources=("commerce",)
    )
    assert select_catalog(query, catalog)[0].source_ids == ("commerce", "org")


def test_selection_is_stable_and_leaves_pagination_to_application(catalog: Catalog) -> None:
    query = CatalogQuery(dimension=CatalogDimension.ENTITIES)
    expected = select_catalog(query, catalog)
    assert (
        select_catalog(query, replace(catalog, records=tuple(reversed(catalog.records))))
        == expected
    )
    assert select_catalog(replace(query, limit=1, continuation="opaque"), catalog) == expected
    assert len(expected) == 3


def test_catalog_filter_algebra(catalog: Catalog) -> None:
    original = CatalogQuery(dimension=CatalogDimension.ENTITIES, sources=("commerce",))
    extra_and = replace(original, ids=("feature:order-history",))
    extra_or = replace(original, sources=("commerce", "org"))
    reordered = replace(extra_or, sources=("org", "commerce", "org"))

    def identifiers(query: CatalogQuery) -> set[str]:
        return {record.id for record in select_catalog(query, catalog)}

    assert identifiers(extra_and) < identifiers(original)
    assert identifiers(original) < identifiers(extra_or)
    assert identifiers(reordered) == identifiers(extra_or)
