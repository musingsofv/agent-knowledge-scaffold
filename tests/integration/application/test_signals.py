"""Exercise capture/list through explicit neutral workspaces and durable inboxes."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from agent_knowledge.application.signals import list_signal_result, record_signal_result
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document, parse_document
from tests.factories import catalog_data, signal_data


def signal_workspace(tmp_path: Path, *, project: bool = True) -> tuple[Path, Path]:
    """Create an independent producer checkout and explicit directory-only scaffold."""
    code = tmp_path / "code"
    code.mkdir()
    producer = code / "products/orders" if project else tmp_path / "context"
    producer.mkdir(parents=True)
    if project:
        subprocess.run(
            ["git", "init", "--initial-branch=main", str(producer)],
            check=True,
            capture_output=True,
            env={"PATH": os.defpath, "HOME": str(tmp_path)},
        )
    scaffold = tmp_path / "scaffold"
    (scaffold / "knowledge").mkdir(parents=True)
    (scaffold / ".gitignore").write_text("/ai/signals/\n")
    (scaffold / "catalog.yaml").write_text(yaml.safe_dump(catalog_data()))
    config = producer / "workspace.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [
                    {
                        "id": "knowledge",
                        "root": str(scaffold / "knowledge"),
                        "catalog": str(scaffold / "catalog.yaml"),
                    }
                ],
                "signal_storage": {"scaffold_root": str(scaffold), "code_root": str(code)},
            }
        )
    )
    data = signal_data()
    if not project:
        data["origin"]["project_path"] = None
    authored = producer / "observation.md"
    authored.write_bytes(dump_document(data, "# Observation\n\nPreserve this exact claim.\n"))
    return config, authored


def test_capture_preserves_authored_bytes_and_listing_returns_locations_not_claims(
    tmp_path: Path,
) -> None:
    config, authored = signal_workspace(tmp_path)
    original = authored.read_bytes()
    recorded = record_signal_result(load_workspace(config), {"file": "observation.md"})
    stored = Path(recorded["local_path"])
    assert stored.parent == tmp_path / "scaffold/ai/signals/projects/products/orders"
    assert stored.read_bytes() == authored.read_bytes() == original
    assert recorded["fingerprint"] == parse_document(original).fingerprint
    result = list_signal_result(load_workspace(config), {})
    assert result["results"] == [recorded]
    assert result["total_matches"] == 1
    assert "Preserve this exact claim" not in json.dumps(result)
    assert result["results"][0]["body_range"][0] > result["results"][0]["frontmatter_range"][1]


def test_listing_can_select_exact_signals_from_the_current_session(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    parsed = parse_document(authored.read_bytes())
    assert isinstance(parsed.metadata["origin"], dict)
    parsed.metadata["origin"].update({"harness": "claude", "session_id": "session-a"})
    authored.write_bytes(dump_document(parsed.metadata, parsed.body))
    first = record_signal_result(load_workspace(config), {"file": "observation.md"})

    second_metadata = parse_document(authored.read_bytes()).metadata
    assert isinstance(second_metadata["origin"], dict)
    second_metadata["origin"]["session_id"] = "session-b"
    authored.write_bytes(dump_document(second_metadata, parsed.body))
    second = record_signal_result(load_workspace(config), {"file": "observation.md"})

    selected = list_signal_result(load_workspace(config), {"session_id": "session-a"})
    assert [item["id"] for item in selected["results"]] == [first["id"]]
    assert selected["total_matches"] == 1
    assert list_signal_result(load_workspace(config), {"session_id": "SESSION-A"})["results"] == []
    assert list_signal_result(load_workspace(config), {"session_id": "session-b"})["results"] == [
        second
    ]


def test_empty_list_does_not_create_an_inbox(tmp_path: Path) -> None:
    config, _ = signal_workspace(tmp_path)
    result = list_signal_result(load_workspace(config), {})
    assert result["results"] == []
    assert not (tmp_path / "scaffold/ai").exists()


def test_shared_capture_and_listing_are_explicit_without_project_inference(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path, project=False)
    record = record_signal_result(load_workspace(config), {"file": str(authored)})
    assert Path(record["local_path"]).parent == tmp_path / "scaffold/ai/signals/shared"
    with pytest.raises(ValidationError) as error:
        list_signal_result(load_workspace(config), {})
    assert error.value.code == "project-origin-required"
    listed = list_signal_result(load_workspace(config), {"include_shared": True})
    assert listed["results"] == [record]


def test_project_listing_includes_shared_only_when_requested(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    record_signal_result(load_workspace(config), {"file": str(authored)})
    parsed = parse_document(authored.read_bytes())
    parsed.metadata["origin"]["project_path"] = None
    authored.write_bytes(dump_document(parsed.metadata, parsed.body))
    shared = record_signal_result(load_workspace(config), {"file": str(authored)})
    assert list_signal_result(load_workspace(config), {})["total_matches"] == 1
    assert (
        list_signal_result(load_workspace(config), {"include_shared": True})["total_matches"] == 2
    )
    assert Path(shared["local_path"]).parent.name == "shared"


@pytest.mark.parametrize(
    "field,value",
    [
        ("workspace_id", "repo:other"),
        ("project_path", "wrong/path"),
        ("applicable_scopes", ["org:example"]),
    ],
)
def test_inconsistent_origin_fails_before_any_capture(
    tmp_path: Path, field: str, value: object
) -> None:
    config, authored = signal_workspace(tmp_path)
    parsed = parse_document(authored.read_bytes())
    parsed.metadata["origin"][field] = value
    authored.write_bytes(dump_document(parsed.metadata, parsed.body))
    with pytest.raises(ValidationError):
        record_signal_result(load_workspace(config), {"file": str(authored)})
    assert authored.exists()
    assert not (tmp_path / "scaffold/ai").exists()


def test_canonical_misfiled_signal_is_not_captured(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    misplaced = tmp_path / "scaffold/knowledge/signal.md"
    misplaced.write_bytes(authored.read_bytes())
    with pytest.raises(ValidationError) as error:
        record_signal_result(load_workspace(config), {"file": str(misplaced)})
    assert error.value.code == "signal-in-canonical-root"
    assert not (tmp_path / "scaffold/ai").exists()


def test_signal_pages_are_bound_to_current_complete_bytes(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    first = record_signal_result(load_workspace(config), {"file": str(authored)})
    record_signal_result(load_workspace(config), {"file": str(authored)})
    page = list_signal_result(load_workspace(config), {"limit": 1})
    next_page = list_signal_result(
        load_workspace(config), {"limit": 1, "continuation": page["continuation"]}
    )
    assert page["results"][0]["local_path"] != next_page["results"][0]["local_path"]
    assert next_page["continuation"] is None
    target = Path(first["local_path"])
    target.write_bytes(target.read_bytes() + b"\nAdditional evidence.\n")
    with pytest.raises(ValidationError) as error:
        list_signal_result(
            load_workspace(config), {"limit": 1, "continuation": page["continuation"]}
        )
    assert error.value.code == "stale-snapshot"


def test_listing_preserves_invalid_selected_signal_and_reports_error(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    captured = record_signal_result(load_workspace(config), {"file": str(authored)})
    target = Path(captured["local_path"])
    target.write_text("invalid frontmatter")
    with pytest.raises(ValidationError):
        list_signal_result(load_workspace(config), {})
    assert target.read_text() == "invalid frontmatter"


def test_other_workspace_shared_signal_is_reported_without_wrong_catalog_validation(
    tmp_path: Path,
) -> None:
    config, authored = signal_workspace(tmp_path)
    parsed = parse_document(authored.read_bytes())
    parsed.metadata["origin"]["project_path"] = None
    authored.write_bytes(dump_document(parsed.metadata, parsed.body))
    captured = record_signal_result(load_workspace(config), {"file": str(authored)})
    foreign = Path(captured["local_path"]).with_name("foreign.md")
    parsed.metadata["origin"]["workspace_id"] = "repo:other"
    parsed.metadata["entities"] = ["feature:only-in-other-catalog"]
    foreign.write_bytes(dump_document(parsed.metadata, parsed.body))
    result = list_signal_result(load_workspace(config), {"include_shared": True})
    assert result["other_workspaces"] == 1
    assert result["total_matches"] == 1
    assert foreign.exists()


def test_invalid_signal_metadata_diagnostic_names_file_and_field(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    record = record_signal_result(load_workspace(config), {"file": str(authored)})
    target = Path(record["local_path"])
    parsed = parse_document(target.read_bytes())
    parsed.metadata["technologies"] = ["unknown-engine"]
    target.write_bytes(dump_document(parsed.metadata, parsed.body))
    with pytest.raises(ValidationError) as error:
        list_signal_result(load_workspace(config), {})
    assert str(target) in error.value.path
    assert "technologies[0]" in error.value.path
    assert target.exists()


def test_output_changed_during_capture_is_retained_and_reported_as_uncertain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.application import signals
    from agent_knowledge.infrastructure.errors import AdapterError

    config, authored = signal_workspace(tmp_path)
    original = signals.capture_signal
    captured = []

    def edited(*args):
        path = original(*args)
        path.write_bytes(path.read_bytes() + b"\nEdited during publication.\n")
        captured.append(path)
        return path

    monkeypatch.setattr(signals, "capture_signal", edited)
    with pytest.raises(AdapterError) as error:
        record_signal_result(load_workspace(config), {"file": str(authored)})
    assert error.value.code == "signal-publication-uncertain"
    assert captured[0].exists() and authored.exists()
    assert str(captured[0]) == error.value.path


def test_retargeting_storage_alias_invalidates_context_before_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.application import signals
    from agent_knowledge.infrastructure.errors import AdapterError

    config, authored = signal_workspace(tmp_path)
    alias = tmp_path / "storage-alias"
    alias.symlink_to(tmp_path / "scaffold", target_is_directory=True)
    alternate = tmp_path / "different-scaffold"
    alternate.mkdir()
    raw = yaml.safe_load(config.read_text())
    raw["signal_storage"]["scaffold_root"] = str(alias)
    config.write_text(yaml.safe_dump(raw))
    original = signals.resolve_project

    def retargeted(workspace):
        result = original(workspace)
        alias.unlink()
        alias.symlink_to(alternate, target_is_directory=True)
        return result

    monkeypatch.setattr(signals, "resolve_project", retargeted)
    with pytest.raises(AdapterError) as error:
        record_signal_result(load_workspace(config), {"file": str(authored)})
    assert error.value.code == "context-changed"
    assert not (alternate / "ai").exists()
    assert not (tmp_path / "scaffold/ai").exists()
