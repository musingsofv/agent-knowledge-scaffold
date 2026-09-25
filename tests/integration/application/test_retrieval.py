"""Exercise preview-only search and progressive navigation against fictional knowledge."""

import json
import shutil
from pathlib import Path

import pytest

from agent_knowledge.application.discovery import catalog_result
from agent_knowledge.application.retrieval import inspect_result, search_result
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from tests.factories import knowledge_data
from tests.integration.application.test_discovery import workspace_file


def sample_workspace(tmp_path: Path) -> Path:
    """Copy the reviewed fictional fixtures, never an organizational corpus."""
    fixtures = Path(__file__).resolve().parents[3] / "ai/plans/cli-examples"
    shutil.copytree(fixtures, tmp_path / "fixture")
    return tmp_path / "fixture/orders-api/knowledge-workspace.yaml"


def test_business_topic_discovery_then_focused_guidance_search(tmp_path: Path) -> None:
    config = sample_workspace(tmp_path)
    topics = catalog_result(
        load_workspace(config), {"dimension": "topics", "text": {"any": ["prospecting"]}}
    )
    assert [row["id"] for row in topics["results"]] == ["lead-generation"]

    broad = search_result(load_workspace(config), {"kind": ["guidance"]})
    paths = {row["path"] for row in broad["results"]}
    assert {"guidance/lead-qualification.md", "guidance/testing.md"} <= paths

    focused = search_result(
        load_workspace(config), {"kind": ["guidance"], "topics": ["lead-generation"]}
    )
    assert [row["path"] for row in focused["results"]] == ["guidance/lead-qualification.md"]
    preview = focused["results"][0]
    assert preview["topics"] == ["lead-generation"]
    assert preview["technologies"] == ["any"]
    assert "body" not in preview
    inspected = inspect_result(
        load_workspace(config), {"document": {"source": preview["source"], "path": preview["path"]}}
    )
    assert inspected["preview"]["topics"] == ["lead-generation"]


def test_topics_use_or_while_other_facets_narrow_business_and_engineering_guidance(
    tmp_path: Path,
) -> None:
    config = sample_workspace(tmp_path)
    request = {"kind": ["guidance"], "topics": ["lead-generation", "testing"]}
    broad = search_result(load_workspace(config), request)
    assert {row["path"] for row in broad["results"]} == {
        "guidance/lead-qualification.md",
        "guidance/testing.md",
        "guidance/react-testing.md",
    }
    general = search_result(load_workspace(config), request | {"technologies": ["any"]})
    assert {row["path"] for row in general["results"]} == {
        "guidance/lead-qualification.md",
        "guidance/testing.md",
    }
    specific = search_result(load_workspace(config), request | {"technologies": ["react"]})
    assert [row["path"] for row in specific["results"]] == ["guidance/react-testing.md"]


def test_unknown_topic_fails_instead_of_returning_empty_discovery(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as caught:
        search_result(load_workspace(sample_workspace(tmp_path)), {"topics": ["lead-generaton"]})
    assert (caught.value.code, caught.value.path) == ("unknown-identifier", "topics[0]")


def test_explicit_guidance_query_keeps_general_family_engine_and_rejects_others(
    tmp_path: Path,
) -> None:
    result = search_result(
        load_workspace(sample_workspace(tmp_path)),
        {
            "kind": ["guidance"],
            "scope": ["org:example", "group:commerce", "repo:orders-api"],
            "topics": ["testing", "performance", "data-design", "reliability"],
            "languages": ["any", "typescript"],
            "technologies": ["any", "postgresql", "family:relational-database"],
            "environments": ["any", "prod"],
        },
    )

    assert {row["path"] for row in result["results"]} == {
        "guidance/testing.md",
        "guidance/index-cost.md",
        "guidance/postgresql-index.md",
    }
    assert result["total_matches"] == 3
    assert all("body" not in row for row in result["results"])


def test_order_history_text_discovery_returns_previews_and_truthful_locations(
    tmp_path: Path,
) -> None:
    result = search_result(
        load_workspace(sample_workspace(tmp_path)),
        {
            "kind": ["feature", "workflow"],
            "text": {"any": ["order history", "past orders"]},
        },
    )

    assert result["total_matches"] == 2
    for row in result["results"]:
        assert row["local_path"].endswith(row["path"])
        assert row["fingerprint"].startswith("sha256:")
        assert row["match_count"] >= 1
        assert row["matches"]
        assert row["body_range"][0] > row["frontmatter_range"][1]


def test_fixture_runbook_inspect_preserves_exact_lines_and_resolves_useful_links(
    tmp_path: Path,
) -> None:
    result = inspect_result(
        load_workspace(sample_workspace(tmp_path)),
        {
            "document": {"source": "commerce-knowledge", "path": "runbooks/postgresql-index.md"},
            "limit": 20,
        },
    )

    preview = result["preview"]
    assert (preview["byte_count"], preview["line_count"]) == (1381, 41)
    assert preview["frontmatter_range"] == [1, 11]
    assert preview["body_range"] == [12, 41]
    headings = [row for row in result["navigation"] if row["type"] == "heading"]
    procedure = next(row for row in headings if row["title"] == "Adding a status index")
    assert (procedure["start_line"], procedure["end_line"]) == (21, 32)
    links = [row for row in result["navigation"] if row["type"] == "link"]
    assert len(links) == 3
    assert all(row["status"] == "resolved" for row in links)
    assert "Identify" not in json.dumps(result)


def test_stale_direct_read_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as caught:
        inspect_result(
            load_workspace(sample_workspace(tmp_path)),
            {
                "document": {
                    "source": "commerce-knowledge",
                    "path": "runbooks/postgresql-index.md",
                },
                "expected_fingerprint": "sha256:" + "0" * 64,
            },
        )
    assert caught.value.code == "stale-document"


def test_empty_search_and_bad_id_remain_different(tmp_path: Path) -> None:
    config = sample_workspace(tmp_path)
    empty = search_result(
        load_workspace(config), {"kind": ["limitation"], "entities": ["feature:order-history"]}
    )
    assert empty["results"] == []
    assert empty["scan_status"] == "complete"
    assert empty["continuation"] is None
    with pytest.raises(ValidationError) as caught:
        search_result(load_workspace(config), {"entities": ["feature:order-histroy"]})
    assert caught.value.code == "unknown-identifier"


def test_metadata_only_hit_does_not_invent_a_body_location(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    path = tmp_path / "knowledge/rule.md"
    path.write_bytes(
        dump_document(knowledge_data(title="Needle title"), "# Ordinary\nNothing else.\n")
    )
    row = search_result(load_workspace(config), {"text": {"any": ["needle"]}})["results"][0]
    assert row["metadata_only"] is True
    assert all(hit["field"] == "title" for hit in row["matches"])
    assert all(hit["end_line"] <= row["frontmatter_range"][1] for hit in row["matches"])


def test_formatting_is_searchable_and_section_location_does_not_return_body(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    path = tmp_path / "knowledge/runbook.md"
    path.write_bytes(
        dump_document(
            knowledge_data(),
            "# Procedure\n\n## Add index\nUse **cost**\nanalysis here.\n## Recovery\nUndo.\n",
        )
    )
    row = search_result(load_workspace(config), {"text": {"all": ["cost analysis"]}})["results"][0]
    body = [hit for hit in row["matches"] if hit["field"] == "body"]
    assert body[0]["end_line"] == body[0]["start_line"] + 1
    assert body[0]["section"]["title"] == "Add index"
    assert "analysis here" not in json.dumps(row)


def test_selected_preview_pages_bind_to_the_whole_scanned_snapshot(tmp_path: Path) -> None:
    config = sample_workspace(tmp_path)
    first = search_result(load_workspace(config), {"limit": 1})
    first_file = Path(first["results"][0]["local_path"])
    first_file.write_bytes(first_file.read_bytes() + b"\nChanged after preview.\n")
    with pytest.raises(ValidationError) as caught:
        search_result(load_workspace(config), {"limit": 1, "continuation": first["continuation"]})
    assert caught.value.code == "stale-snapshot"


def test_many_matches_are_bounded_and_can_be_paged_without_new_query_fields(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/rule.md").write_bytes(
        dump_document(
            knowledge_data(),
            "# Evidence\n" + "needle\n" * 45,
        )
    )
    query = {"text": {"any": ["needle"]}}
    first = search_result(load_workspace(config), query)["results"][0]
    assert first["match_count"] == 45
    assert len(first["matches"]) == 20
    assert first["matches_truncated"] is True
    assert first["match_continuation"]
    seen = list(first["matches"])
    token = first["match_continuation"]
    while token:
        next_row = search_result(load_workspace(config), query | {"continuation": token})[
            "results"
        ][0]
        seen += next_row["matches"]
        token = next_row["match_continuation"]
    assert len(seen) == 45
    assert len({row["start_line"] for row in seen}) == 45


def test_inspect_pages_headings_and_links_in_physical_order(tmp_path: Path) -> None:
    config = sample_workspace(tmp_path)
    query = {
        "document": {"source": "commerce-knowledge", "path": "runbooks/postgresql-index.md"},
        "limit": 2,
    }
    page = inspect_result(load_workspace(config), query)
    entries = list(page["navigation"])
    while page["continuation"]:
        page = inspect_result(
            load_workspace(config), query | {"continuation": page["continuation"]}
        )
        entries += page["navigation"]
    assert len(entries) == page["total_entries"]
    assert [entry["start_line"] for entry in entries] == sorted(
        entry["start_line"] for entry in entries
    )


def test_invalid_file_cannot_be_filtered_into_a_false_absence(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/broken.md").write_text("not frontmatter\n")
    with pytest.raises(ValidationError):
        search_result(load_workspace(config), {"kind": ["limitation"]})


def test_section_encloses_the_entire_cross_heading_phrase(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/rule.md").write_bytes(
        dump_document(knowledge_data(), "# Parent\n## Safety\nindex\n## cost\nLater text\n")
    )
    row = search_result(load_workspace(config), {"text": {"any": ["index cost"]}})["results"][0]
    assert row["matches"][0]["section"]["title"] == "Parent"
    assert row["matches"][0]["end_line"] > row["matches"][0]["start_line"]


def test_detailed_locations_are_built_only_for_the_selected_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.application import retrieval

    config = workspace_file(tmp_path)
    for index in range(4):
        (tmp_path / f"knowledge/rule-{index}.md").write_bytes(
            dump_document(knowledge_data(), "# Evidence\n" + "needle\n" * 200)
        )
    original_locations = retrieval._locations
    original_section = retrieval.section_for_line
    detailed_files = []
    section_calls = []

    def locations(document, *args):
        detailed_files.append(document.path)
        return original_locations(document, *args)

    def section(navigation, line, **kwargs):
        section_calls.append(line)
        return original_section(navigation, line, **kwargs)

    monkeypatch.setattr(retrieval, "_locations", locations)
    monkeypatch.setattr(retrieval, "section_for_line", section)
    result = search_result(load_workspace(config), {"text": {"any": ["needle"]}, "limit": 1})
    assert result["total_matches"] == 4
    assert detailed_files == ["rule-0.md"]
    assert len(section_calls) == 20
    assert result["results"][0]["match_count"] == 200


def test_source_change_while_building_previews_cannot_return_complete_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.application import retrieval
    from agent_knowledge.infrastructure.errors import AdapterError

    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/rule.md").write_bytes(dump_document(knowledge_data(), "# Evidence\n"))
    original = retrieval._match_page

    def changed(*args):
        preview = original(*args)
        (tmp_path / "knowledge/new.md").write_bytes(dump_document(knowledge_data(), "# New\n"))
        return preview

    monkeypatch.setattr(retrieval, "_match_page", changed)
    with pytest.raises(AdapterError) as caught:
        search_result(load_workspace(config), {})
    assert caught.value.code == "scan-changed"


def test_long_source_identifier_still_produces_a_usable_match_cursor(tmp_path: Path) -> None:
    import yaml

    config = workspace_file(tmp_path)
    raw = yaml.safe_load(config.read_text())
    raw["sources"][0]["id"] = "source" + "x" * 4000
    config.write_text(yaml.safe_dump(raw))
    (tmp_path / "knowledge/rule.md").write_bytes(
        dump_document(knowledge_data(), "# Evidence\n" + "needle\n" * 21)
    )
    query = {"text": {"any": ["needle"]}}
    first = search_result(load_workspace(config), query)
    cursor = first["results"][0]["match_continuation"]
    assert len(cursor) < 4096
    second = search_result(load_workspace(config), query | {"continuation": cursor})
    assert second["results"][0]["matches_returned"] == 1
    assert second["results"][0]["match_continuation"] is None


@pytest.mark.parametrize("operation", ["search", "inspect"])
def test_selected_source_does_not_require_an_unrelated_corpus_to_be_available(
    tmp_path: Path, operation: str
) -> None:
    import yaml

    config = workspace_file(tmp_path)
    raw = yaml.safe_load(config.read_text())
    raw["sources"].append({"id": "offline", "root": "offline", "catalog": "catalog.yaml"})
    config.write_text(yaml.safe_dump(raw))
    (tmp_path / "knowledge/rule.md").write_bytes(dump_document(knowledge_data(), "# Local\n"))
    if operation == "search":
        result = search_result(load_workspace(config), {"sources": ["knowledge"]})
        assert result["returned"] == 1
    else:
        inspected = inspect_result(
            load_workspace(config), {"document": {"source": "knowledge", "path": "rule.md"}}
        )
        assert inspected["preview"]["path"] == "rule.md"
