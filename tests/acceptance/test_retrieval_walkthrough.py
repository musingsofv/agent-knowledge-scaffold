"""Exercise the end-to-end retrieval decisions against a neutral corpus.

These cases intentionally read only through the application boundary.  They
describe what an agent should discover for business and engineering tasks while
leaving query planning and ordinary body reads to the caller.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent_knowledge.application.retrieval import inspect_result, search_result
from agent_knowledge.application.validation import validate_result
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document


def _catalog() -> dict[str, object]:
    return {
        "schema_version": "knowledge-catalog.v1",
        "scopes": {
            "org:example": {"label": "Example organization"},
            "tribe:commerce": {"label": "Commerce tribe", "parents": ["org:example"]},
            "repo:orders-api": {"label": "Orders API", "parents": ["tribe:commerce"]},
        },
        "entities": {
            "feature:order-history": {
                "label": "Order history",
                "description": "Customer access to previous orders and their current status.",
                "aliases": ["past orders"],
            },
            "service:orders": {
                "label": "Orders service",
                "description": "Stores and serves customer orders.",
            },
        },
        "topics": {
            key: {"label": value}
            for key, value in {
                "product-behavior": "Product behavior",
                "architecture": "Architecture",
                "data-design": "Data design",
                "testing": "Testing",
                "reliability": "Reliability",
                "performance": "Performance",
                "technology-choice": "Technology choice",
                "provisioning": "Provisioning",
            }.items()
        },
        "languages": {"typescript": {"label": "TypeScript"}},
        "technologies": {
            "postgresql": {
                "label": "PostgreSQL",
                "aliases": ["Postgres"],
                "technology_families": ["relational-database"],
            },
            "mysql": {
                "label": "MySQL",
                "technology_families": ["relational-database"],
            },
            "react": {"label": "React"},
        },
        "technology_families": {
            "relational-database": {"label": "Relational database"},
        },
        "environments": {
            "dev": {"label": "Development"},
            "prod": {"label": "Production"},
        },
    }


def _document(
    kind: str,
    title: str,
    description: str,
    scope: list[str],
    topics: list[str],
    **extra: object,
) -> bytes:
    body = extra.pop("body", "# " + title + "\n")
    metadata: dict[str, object] = {
        "schema_version": "knowledge.v1",
        "kind": kind,
        "title": title,
        "description": description,
        "scope": scope,
        "topics": topics,
    }
    metadata.update(extra)
    assert isinstance(body, str)
    return dump_document(metadata, body)


def _workspace(tmp_path: Path) -> Path:
    source = tmp_path / "knowledge"
    for relative in (
        "product/features",
        "product/workflows",
        "systems",
        "runbooks",
        "guidance",
        "limitations",
    ):
        (source / relative).mkdir(parents=True)
    (tmp_path / "catalog.yaml").write_text(
        yaml.safe_dump(_catalog(), sort_keys=False), encoding="utf-8"
    )
    (source / "product/features/order-history.md").write_bytes(
        _document(
            "feature",
            "Order history",
            "Customer order-history capability and its behavior owner.",
            ["tribe:commerce"],
            ["product-behavior"],
            entities=["feature:order-history", "service:orders"],
            aliases=["past orders"],
            body=(
                "# Order history\n\nCustomers review their own orders in reverse chronological "
                "order.\n\n"
                "## Related Knowledge\n\n- [Workflow](../workflows/order-history.md)\n"
            ),
        )
    )
    (source / "product/workflows/order-history.md").write_bytes(
        _document(
            "workflow",
            "Browse order history",
            "Tenant isolation, ordering and pagination expected for past orders.",
            ["tribe:commerce"],
            ["product-behavior", "testing"],
            entities=["feature:order-history", "service:orders"],
            body=(
                "# Browse order history\n\nOnly the customer's own orders appear.\n\n"
                "## Preconditions\n\nThe customer is authenticated.\n\n"
                "## Related Knowledge\n\n- [Orders system](../../systems/orders.md)\n"
                "- [Orders runbook](../../runbooks/orders.md)\n"
            ),
        )
    )
    (source / "systems/orders.md").write_bytes(
        _document(
            "system",
            "Orders service",
            "TypeScript orders API and PostgreSQL storage used by order history.",
            ["repo:orders-api"],
            ["architecture", "data-design", "reliability"],
            entities=["service:orders", "feature:order-history"],
            languages=["typescript"],
            technologies=["postgresql"],
            environments=["dev", "prod"],
            body=(
                "# Orders service\n\nThe API stores orders in PostgreSQL.\n\n"
                "## Related Knowledge\n\n- [Service runbook](../runbooks/orders.md)\n"
            ),
        )
    )
    runbook_body = (
        "# Orders service runbook\n\n"
        "## Preconditions\n\nConfirm the current schema and migration runner before "
        "changing an index.\n\n"
        "## Adding a secondary index\n\n"
        "Measure the tenant, status and ordering predicates on representative data.\n\n"
        "## Production warning\n\n"
        "Check transaction duration and lock behavior before scheduling the rollout.\n\n"
        "## Recovery\n\nUse the migration recovery procedure agreed with the owner.\n\n"
        "## Related Knowledge\n\n- [Orders system](../systems/orders.md)\n"
        "- [Pagination limitation](../limitations/pagination.md)\n"
    )
    (source / "runbooks/orders.md").write_bytes(
        _document(
            "runbook",
            "Orders service runbook",
            "Prerequisites, rollout checks and recovery for the orders service.",
            ["repo:orders-api"],
            ["reliability", "data-design", "performance"],
            entities=["service:orders", "feature:order-history"],
            languages=["typescript"],
            technologies=["postgresql"],
            environments=["dev", "prod"],
            body=runbook_body,
        )
    )
    (source / "limitations/pagination.md").write_bytes(
        _document(
            "limitation",
            "Stable pagination is required",
            "Boundary to preserve when adding order-history filters.",
            ["repo:orders-api"],
            ["reliability", "product-behavior"],
            entities=["feature:order-history"],
            languages=["typescript"],
            technologies=["postgresql"],
            environments=["prod"],
            body=(
                "# Stable pagination is required\n\nConcurrent inserts can move page boundaries.\n"
            ),
        )
    )
    rules = (
        (
            "testing.md",
            "Test observable behavior",
            ["testing"],
            ["any"],
            ["any"],
            "For changed behavior, cover isolation, ordering and empty states.\n",
        ),
        (
            "index-family.md",
            "Evaluate index benefits and maintenance costs",
            ["performance", "data-design"],
            ["any"],
            ["family:relational-database"],
            "Measure query benefit and write/storage costs for the database family.\n",
        ),
        (
            "postgresql.md",
            "Plan PostgreSQL index rollout",
            ["data-design", "reliability"],
            ["any"],
            ["postgresql"],
            "Check migration transaction and production rollout constraints.\n",
        ),
        (
            "react.md",
            "Test React interaction states",
            ["testing"],
            ["typescript"],
            ["react"],
            "Exercise loading, empty and error states through user interactions.\n",
        ),
    )
    for filename, title, topics, languages, technologies, body in rules:
        (source / "guidance" / filename).write_bytes(
            _document(
                "guidance",
                title,
                "Engineering guidance for the selected topic.",
                ["org:example"],
                topics,
                languages=languages,
                technologies=technologies,
                environments=["any"],
                body="# " + title + "\n\n" + body,
            )
        )
    config = tmp_path / "knowledge-workspace.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "workspace:acceptance",
                "applicable_scopes": ["org:example", "tribe:commerce", "repo:orders-api"],
                "sources": [{"id": "example", "root": "knowledge", "catalog": "catalog.yaml"}],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config


def test_feature_extension_walkthrough_finds_behavior_system_and_operations(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    initial = search_result(
        load_workspace(config),
        {
            "kind": ["feature", "workflow"],
            "text": {"any": ["order history", "past orders"]},
        },
    )
    assert {row["path"] for row in initial["results"]} == {
        "product/features/order-history.md",
        "product/workflows/order-history.md",
    }
    assert all("body" not in row for row in initial["results"])

    workflow = inspect_result(
        load_workspace(config),
        {"document": {"source": "example", "path": "product/workflows/order-history.md"}},
    )
    links = [entry for entry in workflow["navigation"] if entry["type"] == "link"]
    assert {entry["status"] for entry in links} == {"resolved"}
    assert {entry["target"] for entry in links} == {
        "../../systems/orders.md",
        "../../runbooks/orders.md",
    }

    engineering = search_result(
        load_workspace(config),
        {
            "kind": ["system", "runbook", "guidance", "limitation"],
            "entities": ["feature:order-history"],
            "topics": [
                "architecture",
                "data-design",
                "testing",
                "reliability",
            ],
            "languages": ["any", "typescript"],
            "technologies": ["any", "postgresql", "family:relational-database"],
            "environments": ["any", "prod"],
        },
    )
    paths = {row["path"] for row in engineering["results"]}
    assert "systems/orders.md" in paths
    assert "runbooks/orders.md" in paths
    assert "limitations/pagination.md" in paths
    assert "guidance/testing.md" not in paths


def test_explicit_applicability_keeps_general_family_and_engine_rules(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    result = search_result(
        load_workspace(config),
        {
            "kind": ["guidance"],
            "topics": ["testing", "data-design", "performance", "reliability"],
            "languages": ["any", "typescript"],
            "technologies": ["any", "postgresql", "family:relational-database"],
            "environments": ["any", "prod"],
        },
    )
    paths = {row["path"] for row in result["results"]}
    assert paths == {
        "guidance/testing.md",
        "guidance/index-family.md",
        "guidance/postgresql.md",
    }
    assert "guidance/react.md" not in paths


def test_large_runbook_returns_location_then_agent_reads_selected_sections(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    result = search_result(
        load_workspace(config),
        {"kind": ["runbook"], "text": {"any": ["production warning"]}},
    )
    row = result["results"][0]
    assert row["path"] == "runbooks/orders.md"
    assert row["matches"]
    match = row["matches"][0]
    assert match["section"]["title"] == "Production warning"
    assert "Measure the tenant" not in yaml.safe_dump(row)
    assert "Check transaction duration" not in yaml.safe_dump(row)

    selected = inspect_result(
        load_workspace(config),
        {
            "document": {"source": "example", "path": row["path"]},
            "limit": 10,
        },
    )
    warning = next(
        item for item in selected["navigation"] if item.get("title") == "Production warning"
    )
    body_lines = (
        (tmp_path / "knowledge/runbooks/orders.md").read_text(encoding="utf-8").splitlines()
    )
    excerpt = "\n".join(body_lines[warning["start_line"] - 1 : warning["end_line"]])
    assert "transaction duration" in excerpt
    assert "## Recovery" not in excerpt


def test_authoring_validation_uses_same_catalog_and_reports_invalid_identifiers(
    tmp_path: Path,
) -> None:
    config = _workspace(tmp_path)
    invalid = tmp_path / "knowledge/guidance/invalid.md"
    invalid.write_bytes(
        _document(
            "guidance",
            "Unknown topic",
            "An invalid authoring example.",
            ["org:example"],
            ["not-registered"],
            languages=["any"],
            technologies=["any"],
            environments=["any"],
        )
    )
    report = validate_result(
        load_workspace(config),
        {"documents": [{"source": "example", "path": "guidance/invalid.md"}]},
    )
    assert report["valid"] is False
    assert any(item["code"] == "unknown-identifier" for item in report["diagnostics"])


@pytest.mark.parametrize(
    "query",
    [
        {"kind": ["runbook"], "text": {"any": ["not present"]}},
        {"scope": ["repo:orders-api"], "topics": ["technology-choice"]},
    ],
)
def test_no_match_is_truthful_and_bounded(tmp_path: Path, query: dict[str, object]) -> None:
    result = search_result(load_workspace(_workspace(tmp_path)), query)
    assert result["results"] == []
    assert result["scan_status"] == "complete"
    assert result["continuation"] is None
