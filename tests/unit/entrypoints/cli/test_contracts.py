"""Check that schema discovery describes only available behavior and resources."""

from pathlib import Path

import pytest

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.entrypoints.cli.contracts import describe


def test_default_description_exposes_available_commands_and_authoring_resources() -> None:
    result = describe({})

    assert set(result["commands"]) == {
        "describe",
        "doctor",
        "context",
        "catalog",
        "search",
        "inspect",
        "validate",
        "signal record",
        "signal list",
        "compound",
        "usage export",
        "profiles list",
    }
    assert result["planned_commands"] == []
    resources = result["resources"]
    assert resources["status"] == "ready"
    assert resources["guide"] is not None
    assert {Path(path).name for path in resources["templates"]} == {
        "concept.md",
        "feature.md",
        "workflow.md",
        "system.md",
        "guidance.md",
        "runbook-procedure.md",
        "runbook-service.md",
        "limitation.md",
        "incident.md",
        "signal.md",
    }
    assert all(path.endswith(".md") for path in resources["templates"])
    assert "knowledge.v1" in result["schemas"]
    assert set(result["kinds"]) == {
        "concept",
        "feature",
        "workflow",
        "system",
        "guidance",
        "runbook",
        "limitation",
        "incident",
    }


@pytest.mark.parametrize("schema", ["knowledge.v1", "knowledge-catalog.v1", "search"])
def test_topics_are_discoverable_in_authoring_catalog_and_queries(schema: str) -> None:
    fields = describe({"schema": schema})["fields"]
    assert "topics" in fields
    assert "engineering_concerns" not in fields


def test_compound_contract_describes_activity_and_drain_fields() -> None:
    result = describe({"schema": "compound"})

    assert {
        "action",
        "workspace_id",
        "selected",
        "run_id",
        "outcome",
        "publication",
        "dispositions",
        "publication_verified",
    }.issubset(result["fields"])
    assert "unchanged" in result["fields"]["selected"]["description"]


def test_signal_capture_and_inventory_requests_are_discoverable() -> None:
    record = describe({"schema": "signal record"})
    listing = describe({"schema": "signal list"})

    assert set(record["fields"]) == {"file"}
    assert record["fields"]["file"]["required"] is True
    assert "Markdown" in record["fields"]["file"]["description"]
    assert set(listing["fields"]) == {"include_shared", "session_id", "limit", "continuation"}
    assert listing["fields"]["include_shared"]["type"] == "boolean"
    assert listing["fields"]["include_shared"]["required"] is False
    assert "false" in listing["fields"]["include_shared"]["description"]
    assert listing["fields"]["session_id"]["required"] is False
    assert "exact" in listing["fields"]["session_id"]["description"]


def test_agent_can_discover_technology_applicability_without_a_catalog() -> None:
    result = describe({"schema": "knowledge.v1", "field": "technologies"})

    assert set(result["fields"]) == {"technologies"}
    assert "family:<id>" in result["fields"]["technologies"]["description"]
    assert "[any]" in result["fields"]["technologies"]["description"]


def test_validation_targets_are_discoverable() -> None:
    result = describe({"schema": "validate"})

    assert set(result["fields"]) == {"sources", "documents", "signal_files"}
    assert "broken" not in result["fields"]["documents"]["description"]


@pytest.mark.parametrize(
    ("query_data", "code", "path"),
    [
        ({"field": "technologies"}, "missing-field", "schema"),
        ({"schema": "made-up"}, "invalid-value", "schema"),
        ({"schema": "knowledge.v1", "field": "concerns"}, "unknown-field", "field"),
        ({"schema": None}, "invalid-type", "schema"),
        ({"query": "all things"}, "unknown-field", "query"),
    ],
)
def test_description_rejects_unknown_selectors(query_data: object, code: str, path: str) -> None:
    with pytest.raises(ValidationError) as caught:
        describe(query_data)
    assert (caught.value.code, caught.value.path) == (code, path)
