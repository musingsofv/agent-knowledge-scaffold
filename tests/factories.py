"""Build neutral, in-memory authoring inputs for domain tests."""


def catalog_data() -> dict[str, object]:
    """Return a small registered vocabulary with general and engine-specific concepts."""
    return {
        "schema_version": "knowledge-catalog.v1",
        "scopes": {
            "org:example": {"label": "Example"},
            "repo:orders": {"label": "Orders", "parents": ["org:example"]},
        },
        "entities": {
            "feature:history": {"label": "Order history", "description": "Past order access."},
        },
        "topics": {"testing": {"label": "Testing"}},
        "languages": {"typescript": {"label": "TypeScript"}},
        "technologies": {
            "postgresql": {
                "label": "PostgreSQL",
                "aliases": ["Postgres"],
                "technology_families": ["relational-database"],
            },
        },
        "technology_families": {"relational-database": {"description": "Relational engines."}},
        "environments": {"prod": {"label": "Production"}},
    }


def knowledge_data(**overrides: object) -> dict[str, object]:
    """Return valid general guidance metadata with optional overrides."""
    return {
        "schema_version": "knowledge.v1",
        "kind": "guidance",
        "title": "Test observable behavior",
        "description": "Preserve ordering, isolation and pagination when changing queries.",
        "scope": ["org:example"],
        "topics": ["testing"],
        "languages": ["any"],
        "technologies": ["any"],
        "environments": ["any"],
    } | overrides


def signal_data(**overrides: object) -> dict[str, object]:
    """Return signal metadata whose origin is distinct from canonical applicability."""
    return {
        "schema_version": "knowledge-signal.v1",
        "id": "index-observation",
        "created_at": "2026-09-09T12:00:00Z",
        "kind_hint": "runbook",
        "origin": {
            "workspace_id": "repo:orders",
            "project_path": "products/orders",
            "applicable_scopes": ["org:example", "repo:orders"],
            "source_ids": ["knowledge"],
        },
        "entities": ["feature:history"],
        "technologies": ["postgresql"],
        "evidence": [{"type": "file", "reference": "repo:orders/docs/measurements.md"}],
    } | overrides
