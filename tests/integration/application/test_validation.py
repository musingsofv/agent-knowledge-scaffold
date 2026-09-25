"""Exercise strict authoring validation over neutral temporary sources."""

from pathlib import Path

from agent_knowledge.application.validation import validate_result
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from tests.factories import knowledge_data, signal_data
from tests.integration.application.test_discovery import workspace_file


def test_source_validation_reports_invalid_metadata_and_broken_links_together(
    tmp_path: Path,
) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/valid.md").write_bytes(
        dump_document(knowledge_data(), "# Rule\n\n[Missing owner](missing.md)\n")
    )
    (tmp_path / "knowledge/invalid.md").write_bytes(
        dump_document(knowledge_data(entities=["feature:unknown"]), "# Invalid\n")
    )

    result = validate_result(load_workspace(config), {"sources": ["knowledge"]})

    assert result["target"] == "sources"
    assert result["checked"] == 2
    assert result["valid"] is False
    assert {item["status"] for item in result["results"]} == {"invalid"}
    assert {item["code"] for item in result["diagnostics"]} == {
        "broken-reference",
        "unknown-identifier",
    }


def test_document_validation_can_check_one_existing_owner_without_loading_links(
    tmp_path: Path,
) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/owner.md").write_bytes(
        dump_document(knowledge_data(), "# Owner\n\n[External](https://example.test/evidence)\n")
    )

    result = validate_result(
        load_workspace(config),
        {"documents": [{"source": "knowledge", "path": "owner.md"}]},
    )

    assert result["valid"] is True
    assert result["checked"] == 1
    assert result["results"][0]["link_count"] == 1
    assert result["diagnostics"] == []


def test_document_validation_reports_missing_same_file_anchor(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/owner.md").write_bytes(
        dump_document(knowledge_data(), "# Owner\n\n[Missing section](#does-not-exist)\n")
    )

    result = validate_result(
        load_workspace(config),
        {"documents": [{"source": "knowledge", "path": "owner.md"}]},
    )

    assert result["valid"] is False
    assert result["diagnostics"][0]["code"] == "missing-anchor"


def test_signal_validation_reuses_the_markdown_signal_schema(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "draft.md").write_bytes(
        dump_document(signal_data(), "# Durable observation\n\nKeep the evidence pointer.\n")
    )

    result = validate_result(load_workspace(config), {"signal_files": ["draft.md"]})

    assert result["valid"] is True
    assert result["results"][0]["kind"] == "runbook"
    assert result["results"][0]["source"] is None
