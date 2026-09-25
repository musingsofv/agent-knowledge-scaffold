"""In-memory examples of the public matching contract."""

from dataclasses import FrozenInstanceError, replace

import pytest

from agent_knowledge.domain.catalog import Catalog, CatalogRecord
from agent_knowledge.domain.matching import (
    TextOccurrence,
    matches,
    prepare_query,
    prepare_text_query,
)
from agent_knowledge.domain.models import (
    CatalogDimension,
    KnowledgeDocument,
    KnowledgeKind,
    KnowledgeMetadata,
    SearchQuery,
    TextQuery,
)


@pytest.fixture
def catalog() -> Catalog:
    return Catalog(
        records=(
            CatalogRecord(
                dimension=CatalogDimension.TECHNOLOGIES,
                id="postgresql",
                label="PostgreSQL",
                aliases=("Postgres",),
                technology_families=("relational-database",),
            ),
            CatalogRecord(
                dimension=CatalogDimension.TECHNOLOGIES,
                id="mysql",
                label="MySQL",
                technology_families=("relational-database",),
            ),
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="feature:order-history",
                label="Order history",
                description="View and filter previous orders.",
                aliases=("Purchase timeline",),
            ),
            CatalogRecord(
                dimension=CatalogDimension.SCOPES,
                id="repo:orders-api",
                label="Orders API repository",
                parents=("org:example",),
            ),
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="service:orders-api",
                label="Orders API",
                description="Serve and store commerce orders.",
            ),
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="feature:checkout",
                label="Checkout",
                description="Place an order.",
            ),
        )
        + tuple(
            CatalogRecord(dimension=dimension, id=identifier, label=label)
            for dimension, identifier, label in (
                (CatalogDimension.SCOPES, "org:example", "Example organization"),
                (CatalogDimension.TOPICS, "data-design", "Data design"),
                (CatalogDimension.TOPICS, "deployment", "Deployment"),
                (CatalogDimension.TOPICS, "testing", "Testing"),
                (CatalogDimension.LANGUAGES, "sql", "SQL"),
                (CatalogDimension.LANGUAGES, "typescript", "TypeScript"),
                (CatalogDimension.TECHNOLOGIES, "react", "React"),
                (
                    CatalogDimension.TECHNOLOGY_FAMILIES,
                    "relational-database",
                    "Relational database",
                ),
                (CatalogDimension.ENVIRONMENTS, "production", "Production"),
                (CatalogDimension.ENVIRONMENTS, "staging", "Staging"),
            )
        ),
        source_ids=("company", "commerce"),
    )


@pytest.fixture
def document() -> KnowledgeDocument:
    return KnowledgeDocument(
        source_id="commerce",
        metadata=KnowledgeMetadata(
            kind=KnowledgeKind.RUNBOOK,
            title="Orders database indexing",
            description="Plan an index for the orders API safely.",
            scope=("repo:orders-api",),
            topics=("data-design", "deployment"),
            entities=("service:orders-api", "feature:order-history"),
            languages=("sql",),
            technologies=("postgresql",),
            environments=("production",),
            aliases=("Index rollout",),
            terms=("Secondary index",),
        ),
        body="Check PostgreSQL index availability before deployment.",
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (SearchQuery(), True),
        (SearchQuery(kind=(KnowledgeKind.RUNBOOK, KnowledgeKind.LIMITATION)), True),
        (SearchQuery(kind=(KnowledgeKind.FEATURE, KnowledgeKind.WORKFLOW)), False),
        (SearchQuery(scope=("org:example", "repo:orders-api")), True),
        (SearchQuery(scope=("org:example",)), False),
        (SearchQuery(topics=("testing", "data-design")), True),
        (SearchQuery(topics=("testing",)), False),
        (SearchQuery(entities=("service:orders-api",)), True),
        (SearchQuery(entities=("feature:checkout",)), False),
        (SearchQuery(languages=("any", "sql")), True),
        (SearchQuery(languages=("any", "typescript")), False),
        (SearchQuery(technologies=("postgresql",)), True),
        (SearchQuery(technologies=("mysql",)), False),
        (SearchQuery(technologies=("family:relational-database",)), False),
        (SearchQuery(environments=("production", "staging")), True),
        (SearchQuery(environments=("staging",)), False),
        (SearchQuery(sources=("company", "commerce")), True),
        (SearchQuery(sources=("company",)), False),
        (
            SearchQuery(
                kind=(KnowledgeKind.RUNBOOK,),
                scope=("repo:orders-api",),
                topics=("data-design",),
                entities=("feature:order-history",),
                languages=("sql",),
                technologies=("postgresql",),
                environments=("production",),
                sources=("commerce",),
            ),
            True,
        ),
        (
            SearchQuery(
                kind=(KnowledgeKind.RUNBOOK,),
                technologies=("postgresql",),
                environments=("staging",),
            ),
            False,
        ),
    ],
)
def test_exact_filters(
    document: KnowledgeDocument, catalog: Catalog, query: SearchQuery, expected: bool
) -> None:
    assert matches(document, query, catalog) is expected


@pytest.mark.parametrize(
    "query",
    [
        SearchQuery(entities=("feature:order-history",)),
        SearchQuery(languages=("any", "sql")),
        SearchQuery(technologies=("any", "postgresql")),
        SearchQuery(environments=("any", "production")),
    ],
)
def test_missing_document_facet_is_not_any(
    document: KnowledgeDocument, catalog: Catalog, query: SearchQuery
) -> None:
    unspecified = replace(
        document,
        metadata=replace(
            document.metadata,
            entities=None,
            languages=None,
            technologies=None,
            environments=None,
        ),
    )
    assert matches(unspecified, SearchQuery(), catalog)
    assert not matches(unspecified, query, catalog)


@pytest.fixture
def rules(document: KnowledgeDocument) -> tuple[KnowledgeDocument, ...]:
    """Generic, relational-family and engine-specific guidance for one workspace."""
    return tuple(
        replace(
            document,
            source_id="company" if name == "general" else "commerce",
            metadata=replace(
                document.metadata,
                kind=KnowledgeKind.GUIDANCE,
                title=name,
                scope=("org:example",),
                topics=("testing", "data-design"),
                entities=None,
                languages=languages,
                technologies=technologies,
                environments=("any",),
            ),
            body="Verify the changed behavior.",
        )
        for name, languages, technologies in (
            ("general", ("any",), ("any",)),
            ("relational", ("any",), ("family:relational-database",)),
            ("postgres", ("any",), ("postgresql",)),
            ("both-engines", ("any",), ("postgresql", "mysql")),
            ("mysql", ("any",), ("mysql",)),
            ("react", ("typescript",), ("react",)),
        )
    )


@pytest.mark.parametrize(
    ("technologies", "expected"),
    [
        (("postgresql",), {"postgres", "both-engines"}),
        (("family:relational-database",), {"relational"}),
        (("any",), {"general"}),
        (
            ("any", "postgresql", "family:relational-database"),
            {"general", "relational", "postgres", "both-engines"},
        ),
    ],
)
def test_rule_applicability_needs_explicit_general_and_family_values(
    rules: tuple[KnowledgeDocument, ...],
    catalog: Catalog,
    technologies: tuple[str, ...],
    expected: set[str],
) -> None:
    query = SearchQuery(
        kind=(KnowledgeKind.GUIDANCE,),
        scope=("org:example", "repo:orders-api"),
        topics=("testing", "data-design"),
        languages=("any", "typescript"),
        technologies=technologies,
        environments=("any", "production"),
    )
    assert {rule.metadata.title for rule in rules if matches(rule, query, catalog)} == expected


def test_entity_filter_does_not_silently_keep_unassociated_rules(
    rules: tuple[KnowledgeDocument, ...], catalog: Catalog
) -> None:
    general = rules[0]
    assert matches(general, SearchQuery(kind=(KnowledgeKind.GUIDANCE,)), catalog)
    assert not matches(general, SearchQuery(entities=("feature:order-history",)), catalog)


def test_filter_algebra(rules: tuple[KnowledgeDocument, ...], catalog: Catalog) -> None:
    original = SearchQuery(technologies=("any", "postgresql"))
    extra_and = replace(original, sources=("commerce",))
    extra_or = replace(original, technologies=("any", "postgresql", "mysql"))
    reordered = replace(original, technologies=("postgresql", "any", "postgresql"))

    def selected(query: SearchQuery) -> set[str]:
        return {rule.metadata.title for rule in rules if matches(rule, query, catalog)}

    assert selected(extra_and) < selected(original)
    assert selected(extra_or) > selected(original)
    assert selected(reordered) == selected(original)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (TextQuery(any=("Orders database",)), True),
        (TextQuery(any=("index rollout",)), True),
        (TextQuery(any=("secondary index",)), True),
        (TextQuery(any=("safely",)), True),
        (TextQuery(any=("availability before deployment",)), True),
        (TextQuery(any=("unregistered nonsense",)), False),
        (TextQuery(any=("missing text", "secondary index")), True),
        (TextQuery(all=("secondary index", "availability")), True),
        (TextQuery(all=("secondary index", "missing text")), False),
        (TextQuery(any=("missing text",), all=("availability",)), False),
        (TextQuery(any=("index rollout",), all=("missing text",)), False),
        (TextQuery(any=("index rollout",), all=("availability",)), True),
        (TextQuery(any=("indexing plan",)), False),
        (TextQuery(any=("rollout secondary",)), False),
        (TextQuery(any=("index check",)), False),
        (TextQuery(any=("order history",)), False),
    ],
)
def test_text_groups_and_independent_search_surfaces(
    document: KnowledgeDocument, catalog: Catalog, text: TextQuery, expected: bool
) -> None:
    assert matches(document, SearchQuery(text=text), catalog) is expected


@pytest.mark.parametrize(
    ("body", "phrase", "expected"),
    [
        ("STRASSE", "Stra\u00dfe", True),
        ("caf\u00e9", "cafe\u0301", True),
        ("\uff30\uff4f\uff53\uff54\uff47\uff52\uff45\uff53", "Postgres", True),
        ("An order\n\t history exists.", "order history", True),
        ("An order historian exists.", "order history", False),
        ("Reindex the table.", "index", False),
        ("Index the table.", "index", True),
        ("C", "C++", False),
        ("C++", "C++", True),
        ("C++", "C", True),
        ("node.js", "node js", False),
        ("node.js", "node.js", True),
        ("order-history", "order history", False),
        ("order-history", "order-history", True),
        ("anything at all", ".*", False),
        ("Match the literal .* characters.", ".*", True),
        ("a b", "a|b", False),
        ("a|b", "a|b", True),
        ("[index]", "[index]", True),
        ("index", "[index]", False),
    ],
)
def test_literal_unicode_token_sequences(
    document: KnowledgeDocument,
    catalog: Catalog,
    body: str,
    phrase: str,
    expected: bool,
) -> None:
    text_only = replace(
        document,
        metadata=replace(
            document.metadata,
            title="Example",
            description="Demonstration.",
            aliases=(),
            terms=(),
        ),
        body=body,
    )
    assert matches(text_only, SearchQuery(text=TextQuery(any=(phrase,))), catalog) is expected


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Postgres", True),
        ("Postgres index", True),
        ("Check Postgres index availability", True),
        ("Postgres indexed", False),
        ("Postgresindex", False),
        ("MySQL index", False),
        ("relational database", False),
    ],
)
def test_aliases_are_literal_alternatives_inside_a_phrase(
    document: KnowledgeDocument, catalog: Catalog, phrase: str, expected: bool
) -> None:
    assert matches(document, SearchQuery(text=TextQuery(any=(phrase,))), catalog) is expected


def test_aliases_are_alternatives_not_additional_required_phrases(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    query = SearchQuery(text=TextQuery(all=("Postgres index", "availability")))
    assert matches(document, query, catalog)
    assert not matches(document, replace(query, technologies=("mysql",)), catalog)


def test_aliases_can_replace_multiple_tokens_without_recursive_expansion(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    history = replace(document, body="The order history includes a PostgreSQL index.")
    query = SearchQuery(text=TextQuery(all=("purchase timeline includes a Postgres index",)))
    assert matches(history, query, catalog)


def test_many_alias_occurrences_are_matched_without_building_phrase_products(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    repeated = replace(document, body=" ".join(["PostgreSQL"] * 24))
    query = SearchQuery(text=TextQuery(any=(" ".join(["Postgres"] * 24),)))
    assert matches(repeated, query, catalog)
    assert not matches(
        replace(repeated, body=repeated.body + " unavailable"),
        replace(query, text=TextQuery(any=(" ".join(["Postgres"] * 25),))),
        catalog,
    )


def test_ambiguous_aliases_keep_both_candidates_without_transitive_aliases(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    ambiguous = replace(
        catalog,
        records=catalog.records
        + (
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="feature:returns",
                label="Return tracking",
                description="Follow the status of a returned order.",
                aliases=("Mercury",),
            ),
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="feature:payments",
                label="Payment management",
                description="Manage payment collection and refunds.",
                aliases=("Mercury",),
            ),
        ),
    )
    returns = replace(document, body="Return tracking workflow.")
    payments = replace(document, body="Payment management workflow.")
    ambiguous_query = SearchQuery(text=TextQuery(any=("Mercury workflow",)))
    assert matches(returns, ambiguous_query, ambiguous)
    assert matches(payments, ambiguous_query, ambiguous)
    assert not matches(
        payments, SearchQuery(text=TextQuery(any=("Return tracking workflow",))), ambiguous
    )


def test_catalog_descriptions_and_facets_do_not_become_document_text(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    unrelated = replace(
        catalog,
        records=catalog.records
        + (
            CatalogRecord(
                dimension=CatalogDimension.TECHNOLOGIES,
                id="dynamodb",
                label="Amazon DynamoDB",
                description="Provision a global secondary index.",
            ),
        ),
    )
    for phrase in ("global secondary", "repo:orders-api", "production", "Amazon DynamoDB"):
        assert not matches(document, SearchQuery(text=TextQuery(any=(phrase,))), unrelated)


def test_text_predicates_preserve_and_or_algebra(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    matching = TextQuery(any=("missing", "Postgres"), all=("index",))
    assert matches(document, SearchQuery(text=matching), catalog)
    assert matches(
        document,
        SearchQuery(text=TextQuery(any=("Postgres", "missing", "Postgres"), all=("index",))),
        catalog,
    )
    assert not matches(
        document,
        SearchQuery(text=replace(matching, all=("index", "absent phrase"))),
        catalog,
    )


@pytest.mark.parametrize(
    "query",
    [
        SearchQuery(),
        SearchQuery(technologies=("any", "postgresql")),
        SearchQuery(entities=("feature:order-history",)),
        SearchQuery(text=TextQuery(any=("Postgres index", "testing"))),
        SearchQuery(text=TextQuery(all=("Postgres", "index"))),
        SearchQuery(text=TextQuery(any=("absent",), all=("index",))),
        SearchQuery(technologies=("mysql",), text=TextQuery(any=("Postgres",))),
    ],
)
def test_prepared_query_preserves_single_document_contract(
    document: KnowledgeDocument,
    rules: tuple[KnowledgeDocument, ...],
    catalog: Catalog,
    query: SearchQuery,
) -> None:
    prepared = prepare_query(query, catalog)
    documents = (document, *rules)
    assert [prepared.matches(item) for item in documents] == [
        matches(item, query, catalog) for item in documents
    ]
    assert [prepared.matches(item) for item in reversed(documents)] == [
        matches(item, query, catalog) for item in reversed(documents)
    ]


@pytest.mark.parametrize("field", ("query", "text"))
def test_prepared_query_is_immutable(
    document: KnowledgeDocument, catalog: Catalog, field: str
) -> None:
    prepared = prepare_query(SearchQuery(text=TextQuery(any=("Postgres index",))), catalog)
    with pytest.raises(FrozenInstanceError):
        setattr(prepared, field, None)
    assert prepared.matches(document)


def test_prepared_text_query_keeps_any_all_and_separate_surface_semantics(
    catalog: Catalog,
) -> None:
    prepared = prepare_text_query(
        TextQuery(any=("Postgres index",), all=("availability",)), catalog
    )
    assert prepared.matches(("PostgreSQL index", "Check availability."))
    assert not prepared.matches(("PostgreSQL", "index availability"))
    assert not prepared.matches(("PostgreSQL index", "No status supplied."))


def test_prepared_query_reuses_relevant_aliases_with_large_unrelated_catalog(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    large_catalog = replace(
        catalog,
        records=catalog.records
        + tuple(
            CatalogRecord(
                dimension=CatalogDimension.TECHNOLOGIES,
                id=f"engine-{index}",
                label=f"Technology {index}",
                aliases=(f"Engine {index}",),
            )
            for index in range(5000)
        ),
    )
    prepared = prepare_query(
        SearchQuery(text=TextQuery(any=("Postgres index",), all=("availability",))),
        large_catalog,
    )
    documents = tuple(
        replace(document, body="PostgreSQL index availability.")
        if index % 2 == 0
        else replace(document, body="Technology 3000 database maintenance.")
        for index in range(100)
    )
    assert [prepared.matches(item) for item in documents] == [
        index % 2 == 0 for index in range(100)
    ]


@pytest.mark.parametrize(
    ("phrase", "lines", "expected"),
    [
        ("secondary index", ((14, "Create a secondary"), (15, "index safely.")), ((14, 15),)),
        ("secondary index", ((14, "secondary"), (15, ""), (16, "index")), ((14, 16),)),
        ("secondary index", ((14, "secondary"), (16, "index")), ()),
        ("Postgres index", ((8, "PostgreSQL"), (9, "index")), ((8, 9),)),
        ("purchase timeline", ((5, "order"), (6, "history")), ((5, 6),)),
        ("order history", ((5, "purchase timeline"),), ((5, 5),)),
        ("C++", ((2, "C"), (3, "++")), ((2, 3),)),
        ("C++", ((2, "C"),), ()),
        ("node.js", ((2, "node"), (3, ".js")), ((2, 3),)),
        ("node js", ((2, "node.js"),), ()),
        ("café", ((29, "The cafe\u0301 service."),), ((29, 29),)),
        ("strasse", ((17, "Straße"),), ((17, 17),)),
        ("ff", ((31, "\ufb00"),), ((31, 31),)),
        ("index", (), ()),
        ("index", ((7, ""), (8, " ")), ()),
    ],
)
def test_occurrences_follow_original_physical_lines(
    catalog: Catalog,
    phrase: str,
    lines: tuple[tuple[int, str], ...],
    expected: tuple[tuple[int, int], ...],
) -> None:
    prepared = prepare_text_query(TextQuery(any=(phrase,)), catalog)
    assert prepared.occurrences(lines) == tuple(
        TextOccurrence("any", 0, start, end) for start, end in expected
    )


def test_occurrences_keep_all_groups_in_physical_order_and_deduplicate_line_spans(
    catalog: Catalog,
) -> None:
    prepared = prepare_text_query(
        TextQuery(any=("absent", "index"), all=("Postgres", "index")), catalog
    )
    assert prepared.occurrences(
        ((20, "index index PostgreSQL index"), (21, "Postgres"), (22, "index"))
    ) == (
        TextOccurrence("all", 0, 20, 20),
        TextOccurrence("all", 1, 20, 20),
        TextOccurrence("any", 1, 20, 20),
        TextOccurrence("all", 0, 21, 21),
        TextOccurrence("all", 1, 22, 22),
        TextOccurrence("any", 1, 22, 22),
    )


def test_occurrences_do_not_require_query_to_match_the_local_surface(catalog: Catalog) -> None:
    prepared = prepare_text_query(
        TextQuery(any=("order history",), all=("Postgres", "availability")), catalog
    )
    assert prepared.matches(("order history", "PostgreSQL availability"))
    assert not prepared.matches(("PostgreSQL availability",))
    assert prepared.occurrences(((50, "PostgreSQL availability"),)) == (
        TextOccurrence("all", 0, 50, 50),
        TextOccurrence("all", 1, 50, 50),
    )


def test_occurrences_do_not_expand_transitive_aliases(catalog: Catalog) -> None:
    ambiguous = replace(
        catalog,
        records=catalog.records
        + (
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="feature:refunds",
                label="Refund timeline",
                aliases=("purchase timeline",),
            ),
        ),
    )
    prepared = prepare_text_query(TextQuery(any=("order history",)), ambiguous)
    assert prepared.occurrences(((4, "Refund timeline"),)) == ()
    assert prepared.occurrences(((4, "purchase timeline"),)) == (TextOccurrence("any", 0, 4, 4),)


def test_occurrences_preserve_all_variable_length_alias_matches(catalog: Catalog) -> None:
    ambiguous = replace(
        catalog,
        records=catalog.records
        + (
            CatalogRecord(
                dimension=CatalogDimension.ENTITIES,
                id="feature:index",
                label="Index",
                aliases=("index index",),
            ),
        ),
    )
    prepared = prepare_text_query(TextQuery(any=("index",)), ambiguous)
    assert prepared.occurrences(((2, "index"), (3, "index"), (4, "index"))) == (
        TextOccurrence("any", 0, 2, 2),
        TextOccurrence("any", 0, 2, 3),
        TextOccurrence("any", 0, 3, 3),
        TextOccurrence("any", 0, 3, 4),
        TextOccurrence("any", 0, 4, 4),
    )


def test_occurrences_avoid_alias_phrase_products(catalog: Catalog) -> None:
    prepared = prepare_text_query(TextQuery(any=(" ".join(["Postgres"] * 24),)), catalog)
    assert prepared.occurrences(tuple((i + 1, "PostgreSQL") for i in range(25))) == (
        TextOccurrence("any", 0, 1, 24),
        TextOccurrence("any", 0, 2, 25),
    )


def test_occurrences_are_immutable() -> None:
    occurrence = TextOccurrence("any", 0, 7, 9)
    with pytest.raises(FrozenInstanceError):
        occurrence.start_line = 1  # type: ignore[misc]


def test_prepared_facet_check_does_not_require_body_match(
    document: KnowledgeDocument, catalog: Catalog
) -> None:
    prepared = prepare_query(
        SearchQuery(technologies=("postgresql",), text=TextQuery(all=("absent",))), catalog
    )
    assert prepared.facets_match(document)
    assert not prepared.matches(document)
    assert not prepared.facets_match(
        replace(document, metadata=replace(document.metadata, technologies=("mysql",)))
    )
