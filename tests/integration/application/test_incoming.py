"""Exercise bounded incoming Markdown discovery without inferring graph edges."""

import json
from pathlib import Path

import pytest
import yaml

from agent_knowledge.application import retrieval
from agent_knowledge.application.retrieval import IncomingInspectResult, inspect_result
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.corpus import Inventory, inventory
from agent_knowledge.infrastructure.documents import dump_document
from agent_knowledge.infrastructure.errors import AdapterError
from tests.factories import catalog_data, knowledge_data
from tests.integration.application.test_discovery import workspace_file


def document(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.parent.mkdir(exist_ok=True, parents=True)
    path.write_bytes(dump_document(knowledge_data(title=name), body))
    return path


def incoming(config: Path, **changes: object) -> IncomingInspectResult:
    result = inspect_result(
        load_workspace(config),
        {"document": {"source": "knowledge", "path": "target.md"}, "view": "incoming"} | changes,
    )
    assert result["view"] == "incoming"
    return result


def other_source(config: Path) -> Path:
    data = yaml.safe_load(config.read_text())
    data["sources"].append({"id": "other", "root": "other", "catalog": "catalog.yaml"})
    config.write_text(yaml.safe_dump(data))
    root = config.parent / "other"
    root.mkdir()
    return root


def test_incoming_reports_links_and_anchors_without_reciprocal_metadata_or_body(
    tmp_path: Path,
) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    target = document(root, "target.md", "# Target\n## Prerequisites\n[Self](#prerequisites)\n")
    document(
        root,
        "limitation.md",
        "# Limitation\nPrivate body text.\n[Constraint](target.md#prerequisites)\n"
        "[Retired step](target.md#removed)\n[Whole file](target.md)\n",
    )
    document(root, "unrelated.md", "# Same topic\nShared metadata does not imply a link.\n")
    result = incoming(config)
    assert result["target"]["status"] == "resolved"
    assert result["target"]["fingerprint"].startswith("sha256:")
    assert result["target"]["local_path"] == str(target)
    assert result["total_entries"] == 3
    assert [row["preview"]["path"] for row in result["references"]] == ["limitation.md"] * 3
    links = [row["link"] for row in result["references"]]
    assert [link["anchor_status"] for link in links] == ["resolved", "missing", "not-present"]
    assert all(link["status"] == "resolved" for link in links)
    lines = (root / "limitation.md").read_text().splitlines()
    for link in links:
        assert link["label"] in lines[link["start_line"] - 1]
    assert "Private body text" not in json.dumps(result)
    assert result["scan_status"] == "complete"
    assert result["scan"]["sources"] == ["knowledge"]
    assert result["scan"]["documents"] == 3
    assert result["scan"]["byte_count"] == sum(path.stat().st_size for path in root.glob("*.md"))
    assert result["scan"]["elapsed_ms"] >= 0


def test_cross_source_scans_only_requested_sources_and_does_not_recurse(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    other = other_source(config)
    document(root, "target.md", "# Target\n[Cycle](local.md)\n")
    document(root, "local.md", "[Target](target.md)\n")
    document(
        other,
        "cross.md",
        "[Cross source](../knowledge/target.md)\n[Local](../knowledge/local.md)\n",
    )
    document(other, "indirect.md", "[Indirect](cross.md)\n")
    all_sources = incoming(config)
    assert [row["preview"]["path"] for row in all_sources["references"]] == ["local.md", "cross.md"]
    selected = incoming(config, sources=["other"])
    assert selected["scan"]["sources"] == ["other"]
    assert selected["scan"]["documents"] == 2
    assert selected["target"]["source"] == "knowledge"
    assert [row["preview"]["path"] for row in selected["references"]] == ["cross.md"]


def test_missing_target_and_parent_are_valid_only_for_incoming(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    document(tmp_path / "knowledge", "ref.md", "[Old procedure](retired/target.md#step)\n")
    request = {"document": {"source": "knowledge", "path": "retired/target.md"}}
    result = incoming(config, **request)
    assert result["target"]["status"] == "missing"
    assert result["target"]["fingerprint"] is None
    assert result["references"][0]["link"]["anchor_status"] == "unverified"
    assert result["references"][0]["link"]["status"] == "missing"
    with pytest.raises(AdapterError):
        inspect_result(load_workspace(config), request)
    with pytest.raises(ValidationError, match="Document changed"):
        incoming(config, **request, expected_fingerprint="sha256:" + "0" * 64)


def test_incoming_pages_individual_links_in_stable_order(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    document(root, "target.md", "# Target\n")
    document(root, "z.md", "[Z](target.md)\n")
    document(root, "a.md", "[One](target.md) [Two](target.md)\n[Three](target.md#target)\n")
    page = incoming(config, limit=1)
    found = list(page["references"])
    while page["continuation"]:
        page = incoming(config, limit=1, continuation=page["continuation"])
        found.extend(page["references"])
    assert len(found) == page["total_entries"] == 4
    assert [row["preview"]["path"] for row in found] == ["a.md", "a.md", "a.md", "z.md"]
    assert len({(row["preview"]["path"], row["link"]["label"]) for row in found}) == 4


@pytest.mark.parametrize(
    "mutation", ["edit", "add", "remove", "target-add", "target-edit", "target-remove"]
)
def test_continuation_covers_selected_sources_and_target_outside_scan(
    tmp_path: Path, mutation: str
) -> None:
    config = workspace_file(tmp_path)
    other = other_source(config)
    target = tmp_path / "knowledge/target.md"
    if mutation != "target-add":
        document(target.parent, target.name, "# Target\n")
    first = document(other, "a.md", "[A](../knowledge/target.md)\n")
    document(other, "b.md", "[B](../knowledge/target.md)\n")
    page = incoming(config, sources=["other"], limit=1)
    match mutation:
        case "edit":
            first.write_bytes(first.read_bytes() + b"Changed.\n")
        case "add":
            document(other, "c.md", "[C](../knowledge/target.md)\n")
        case "remove":
            first.unlink()
        case "target-add" | "target-edit":
            document(target.parent, target.name, "# Replaced\n")
        case "target-remove":
            target.unlink()
    with pytest.raises(ValidationError) as error:
        incoming(config, sources=["other"], limit=1, continuation=page["continuation"])
    assert error.value.code == "stale-snapshot"


@pytest.mark.parametrize("unsafe", ["target-link", "parent-link", "not-markdown", "git"])
def test_missing_target_does_not_bypass_path_guards(tmp_path: Path, unsafe: str) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    path = "target.md"
    match unsafe:
        case "target-link":
            (root / path).symlink_to(tmp_path / "absent.md")
        case "parent-link":
            (root / "alias").symlink_to(tmp_path / "absent")
            path = "alias/target.md"
        case "not-markdown":
            path = "target.yaml"
        case "git":
            path = ".git/target.md"
    with pytest.raises((ValidationError, AdapterError)):
        incoming(config, document={"source": "knowledge", "path": path})


@pytest.mark.parametrize("failure", ["source-missing", "invalid-file", "symlink", "unreadable"])
def test_unavailable_or_invalid_scan_cannot_return_clean_empty(
    tmp_path: Path, failure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    match failure:
        case "source-missing":
            root.rmdir()
        case "invalid-file":
            (root / "bad.md").write_text("---\ninvalid: [\n---\n")
        case "symlink":
            (root / "bad.md").symlink_to(tmp_path / "absent.md")
        case "unreadable":

            def denied(*args: object, **kwargs: object) -> Inventory:
                raise AdapterError("directory-unreadable", str(root), "Cannot enumerate.")

            monkeypatch.setattr(retrieval, "inventory", denied)
    with pytest.raises((ValidationError, AdapterError)):
        incoming(config)


def test_unresolved_local_link_produces_bounded_diagnostic_not_clean_empty(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    document(tmp_path / "knowledge", "a.md", "[Unknown][missing]\n[Unknown2][missing2]\n")
    result = incoming(config, limit=1)
    assert result["references"] == []
    assert result["scan_status"] == "incomplete"
    assert result["scan"]["diagnostic_count"] == 2
    assert result["scan"]["diagnostics_truncated"]
    assert len(result["scan"]["diagnostics"]) == 1


def test_catalog_document_references_remain_separate_coverage(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    data = catalog_data()
    data["entities"]["feature:history"]["documents"] = [
        {"source": "knowledge", "path": "target.md"}
    ]
    (tmp_path / "catalog.yaml").write_text(yaml.safe_dump(data))
    document(tmp_path / "knowledge", "target.md", "# Target\n")
    result = incoming(config)
    assert result["references"] == []
    assert result["scan_status"] == "complete"
    assert result["scan"]["catalog_references_included"] is False


def test_scan_race_and_interrupt_never_return_partial_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    document(root, "a.md", "[Old](target.md)\n")
    calls = 0

    def changing(workspace: Workspace, sources: tuple[str, ...] | None = None) -> Inventory:
        nonlocal calls
        calls += 1
        if calls == 2:
            document(root, "new.md", "[New](target.md)\n")
        return inventory(workspace, sources)

    monkeypatch.setattr(retrieval, "inventory", changing)
    with pytest.raises(AdapterError) as error:
        incoming(config)
    assert error.value.code == "scan-changed"

    def interrupted(*args: object, **kwargs: object) -> Inventory:
        raise KeyboardInterrupt

    monkeypatch.setattr(retrieval, "inventory", interrupted)
    with pytest.raises(KeyboardInterrupt):
        incoming(config)


def test_unselected_source_is_outside_scan_coverage_and_cursor_identity(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    other = other_source(config)
    document(root, "a.md", "[A](target.md)\n[B](target.md)\n")
    page = incoming(config, sources=["knowledge"], limit=1)
    (other / "invalid.md").write_text("An unselected invalid file is outside coverage.\n")
    next_page = incoming(config, sources=["knowledge"], limit=1, continuation=page["continuation"])
    assert next_page["returned"] == 1
    assert next_page["fingerprint"] == page["fingerprint"]


def test_navigation_cursor_is_not_accepted_for_incoming(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    document(tmp_path / "knowledge", "target.md", "# Target\n## Procedure\n")
    page = inspect_result(
        load_workspace(config),
        {"document": {"source": "knowledge", "path": "target.md"}, "limit": 1},
    )
    with pytest.raises(ValidationError) as error:
        incoming(config, limit=1, continuation=page["continuation"])
    assert error.value.code == "invalid-continuation"


def test_target_changed_while_scanning_cannot_return_stale_anchors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = workspace_file(tmp_path)
    root = tmp_path / "knowledge"
    document(root, "target.md", "# Original\n")
    other = other_source(config)
    document(other, "ref.md", "[Step](../knowledge/target.md#original)\n")
    original_resolver = retrieval.resolve_links

    def change_target(*args: object, **kwargs: object) -> object:
        found = original_resolver(*args, **kwargs)
        document(root, "target.md", "# Changed\n")
        return found

    monkeypatch.setattr(retrieval, "resolve_links", change_target)
    with pytest.raises(AdapterError) as error:
        incoming(config, sources=["other"])
    assert error.value.code == "scan-changed"


def test_unsupported_destination_is_diagnosed_and_external_evidence_is_not_fetched(
    tmp_path: Path,
) -> None:
    config = workspace_file(tmp_path)
    document(
        tmp_path / "knowledge",
        "ref.md",
        "[Malformed](target.md%XX)\n[External](https://example.invalid/no-request)\n",
    )
    result = incoming(config)
    assert result["references"] == []
    assert result["scan_status"] == "incomplete"
    assert result["scan"]["diagnostic_count"] == 1
    assert result["scan"]["diagnostics"][0]["link"]["label"] == "Malformed"
