"""Preserve captured history through configuration drift and unresolved metadata."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from agent_knowledge.application.signals import list_signal_result, record_signal_result
from agent_knowledge.application.validation import validate_result
from agent_knowledge.domain.compounding import CompoundDecision, SignalDisposition, SignalSnapshot
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.compound_evidence import archive_path, run_root
from agent_knowledge.infrastructure.compounding import drain_signals, finish_run, start_run
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document, parse_document
from tests.factories import signal_data
from tests.integration.application.test_signals import signal_workspace


@pytest.mark.parametrize("change", ["expand", "shrink", "rename"])
def test_history_survives_context_changes_through_exact_archive_and_no_write_drain(
    tmp_path: Path, change: str
) -> None:
    config, authored = signal_workspace(tmp_path)
    parsed = parse_document(authored.read_bytes())
    parsed.metadata["technologies"] = ["postgresql", "family:relational-database"]
    authored.write_bytes(dump_document(parsed.metadata, parsed.body))
    captured = record_signal_result(load_workspace(config), {"file": str(authored)})
    original = Path(captured["local_path"]).read_bytes()
    current = yaml.safe_load(config.read_text())
    catalog_path = tmp_path / "scaffold/catalog.yaml"
    catalog = yaml.safe_load(catalog_path.read_text())
    match change:
        case "expand":
            current["applicable_scopes"].append("repo:billing")
            catalog["scopes"]["repo:billing"] = {"label": "Billing"}
            extra = tmp_path / "extra-knowledge"
            extra.mkdir()
            current["sources"].append(
                {"id": "extra", "root": str(extra), "catalog": str(catalog_path)}
            )
        case "shrink":
            current["applicable_scopes"] = ["org:example"]
            del catalog["scopes"]["repo:orders"]
            current["sources"][0]["id"] = "current-knowledge"
            catalog["entities"] = {}
            catalog["technologies"] = {}
            catalog["technology_families"] = {}
        case "rename":
            current["applicable_scopes"] = ["org:current"]
            catalog["scopes"] = {"org:current": {"label": "Current"}}
            current["sources"][0]["id"] = "renamed-knowledge"
            catalog["entities"] = {
                "feature:orders": {"label": "Orders", "description": "Current order workflow."}
            }
            catalog["technologies"] = {"sqlite": {"label": "SQLite"}}
            catalog["technology_families"] = {}
    catalog_path.write_text(yaml.safe_dump(catalog))
    config.write_text(yaml.safe_dump(current))
    loaded = load_workspace(config)

    listed = list_signal_result(loaded, {})
    assert listed["scan_status"] == "complete"
    assert listed["results"] == [captured]
    assert listed["unresolved"] == []
    assert Path(captured["local_path"]).read_bytes() == original
    # A fresh capture must still describe the current context exactly.
    with pytest.raises(ValidationError) as caught:
        record_signal_result(loaded, {"file": str(authored)})
    assert caught.value.code == ("origin-mismatch" if change == "expand" else "unknown-identifier")
    if change != "expand":
        assert not validate_result(loaded, {"signal_files": [str(authored)]})["valid"]

    preview = listed["results"][0]
    selected = (SignalSnapshot(preview["id"], preview["local_path"], preview["fingerprint"]),)
    started = start_run(
        loaded,
        selected=selected,
        harness="codex",
        session_id="history-review-session",
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
    )
    archived = archive_path(loaded, started.run_id, selected[0])
    assert archived.read_bytes() == original
    no_write = (
        SignalDisposition(
            preview["id"], CompoundDecision.KEEP, "Reviewed historical evidence; no update needed."
        ),
    )
    report = drain_signals(loaded, selected, no_write, run_id=started.run_id)
    assert report.drained == (preview["id"],)
    assert report.retained == ()
    assert report.diagnostics == ()
    assert not Path(preview["local_path"]).exists()
    finished = finish_run(
        loaded,
        run_id=started.run_id,
        outcome="Reviewed without canonical changes.",
        dispositions=no_write,
        completion="completed",
    )
    assert not finished.active
    assert finished.drained == (preview["id"],)
    assert archived.read_bytes() == original
    assert authored.read_bytes() == original


def test_mixed_pages_keep_unresolved_records_visible_under_session_filter(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    bucket = tmp_path / "scaffold/ai/signals/projects/products/orders"
    bucket.mkdir(parents=True)
    original: dict[Path, bytes] = {}

    def store(name: str, metadata: object | None) -> None:
        path = bucket / name
        data = (
            b"malformed frontmatter\nPRIVATE CLAIM MARKER\n"
            if metadata is None
            else dump_document(metadata, "# PRIVATE CLAIM MARKER\n")
        )
        path.write_bytes(data)
        original[path] = data

    store("00-malformed.md", None)
    invalid_session = signal_data(id="invalid-session")
    invalid_session["origin"].update({"harness": "codex", "session_id": "other/session"})
    store("01-invalid-session.md", invalid_session)
    unknown_workspace = signal_data(id="unknown-workspace")
    del unknown_workspace["origin"]["workspace_id"]
    unknown_workspace["origin"]["session_id"] = "session-b"
    store("02-unknown-workspace.md", unknown_workspace)
    wrong_project = signal_data(id="wrong-project")
    wrong_project["origin"].update({"project_path": "products/billing", "session_id": "session-b"})
    store("03-wrong-project.md", wrong_project)
    selected = signal_data(id="selected")
    selected["origin"].update({"harness": "codex", "session_id": "session-a"})
    store("04-selected.md", selected)
    different_session = signal_data(id="different-session")
    different_session["origin"]["session_id"] = "session-b"
    store("05-different-session.md", different_session)
    foreign = signal_data(id="foreign")
    foreign["origin"]["workspace_id"] = "repo:billing"
    store("06-foreign.md", foreign)

    loaded = load_workspace(config)
    request = {"limit": 2, "session_id": "session-a"}
    first = list_signal_result(loaded, request)
    assert list_signal_result(loaded, request) == first
    pages = [first]
    while pages[-1]["continuation"] is not None:
        pages.append(
            list_signal_result(loaded, {**request, "continuation": pages[-1]["continuation"]})
        )
    assert len(pages) == 3
    assert pages[0]["results"] == []
    assert pages[0]["continuation"] is not None
    assert [item["id"] for page in pages for item in page["results"]] == ["selected"]
    unresolved = [item for page in pages for item in page["unresolved"]]
    assert [Path(item["local_path"]).name for item in unresolved] == [
        "00-malformed.md",
        "01-invalid-session.md",
        "02-unknown-workspace.md",
        "03-wrong-project.md",
    ]
    for page in pages:
        assert page["scan_status"] == "partial"
        assert page["total_matches"] == 1
        assert page["unresolved_count"] == 4
        assert page["other_workspaces"] == 1
        assert page["returned"] == len(page["results"])
        assert len(page["results"]) + len(page["unresolved"]) <= 2
        assert "PRIVATE CLAIM MARKER" not in json.dumps(page)
    for preview in unresolved:
        path = Path(preview["local_path"])
        assert set(preview) == {"local_path", "byte_count", "fingerprint", "diagnostics"}
        assert preview["byte_count"] == len(original[path])
        assert preview["fingerprint"] == "sha256:" + hashlib.sha256(original[path]).hexdigest()
    assert {path: path.read_bytes() for path in original} == original
    assert authored.exists()

    changed = bucket / "00-malformed.md"
    changed.write_bytes(original[changed] + b"Additional raw evidence.\n")
    with pytest.raises(ValidationError) as caught:
        list_signal_result(loaded, {**request, "continuation": first["continuation"]})
    assert caught.value.code == "stale-snapshot"
    assert changed.read_bytes().startswith(original[changed])


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "knowledge-signal.v2"),
        ("id", "Invalid ID"),
        ("created_at", "2026-02-30T12:00:00Z"),
        ("kind_hint", "unsupported"),
        ("evidence", []),
        ("entities", ["Invalid Entity"]),
        ("technologies", ["any", "postgresql"]),
        ("unexpected", "unrecognized metadata"),
        ("origin.workspace_id", "Invalid Workspace"),
        ("origin.project_path", "../orders"),
        ("origin.applicable_scopes", ["Invalid Scope"]),
        ("origin.applicable_scopes", ["any"]),
        ("origin.applicable_scopes", ["family:database"]),
        ("origin.applicable_scopes", ["org:example", "org:example"]),
        ("origin.source_ids", []),
        ("origin.source_ids", ["Invalid Source"]),
        ("origin.source_ids", ["any"]),
        ("origin.source_ids", ["family:database"]),
        ("origin.harness", "codex"),
        ("origin.session_id", "session/path"),
        ("origin.automation_id", "automation id"),
        ("origin.unexpected", "unrecognized origin metadata"),
        ("entities", ["any"]),
        ("entities", ["family:database"]),
        ("technologies", ["family:any"]),
        ("technologies", ["family:family:database"]),
    ],
)
def test_unresolved_schema_failures_are_visible_and_cannot_start_a_run(
    tmp_path: Path, field: str, value: object
) -> None:
    config, _ = signal_workspace(tmp_path)
    path = tmp_path / "scaffold/ai/signals/projects/products/orders/unresolved.md"
    path.parent.mkdir(parents=True)
    metadata = signal_data()
    if field.startswith("origin."):
        metadata["origin"][field.removeprefix("origin.")] = value
    else:
        metadata[field] = value
    raw = dump_document(metadata, "# Raw evidence stays pending.\n")
    path.write_bytes(raw)
    loaded = load_workspace(config)
    result = list_signal_result(loaded, {})
    assert result["results"] == []
    assert result["unresolved_count"] == 1
    preview = result["unresolved"][0]
    # Even a caller-supplied ID cannot make malformed bytes eligible for archival/drain.
    selected = (SignalSnapshot("index-observation", str(path), preview["fingerprint"]),)
    with pytest.raises(ValidationError):
        start_run(
            loaded,
            selected=selected,
            harness="codex",
            session_id="review-session",
            automation_id=None,
            workspace_id=loaded.definition.workspace_id,
        )
    assert path.read_bytes() == raw
    assert not run_root(loaded, "compound-" + "0" * 32).parent.exists()


def test_unresolved_diagnostic_output_is_bounded(tmp_path: Path) -> None:
    config, _ = signal_workspace(tmp_path)
    bucket = tmp_path / "scaffold/ai/signals/projects/products/orders"
    bucket.mkdir(parents=True)
    path = bucket / "oversized-metadata.md"
    raw = dump_document(signal_data(kind_hint="x" * 20_000), "# Body is never previewed.\n")
    path.write_bytes(raw)
    result = list_signal_result(load_workspace(config), {})
    diagnostic = result["unresolved"][0]["diagnostics"][0]
    assert len(diagnostic["message"]) <= 512
    assert len(diagnostic["path"]) <= 512
    assert path.read_bytes() == raw


@pytest.mark.parametrize("changed_field", ["applicable_scopes", "sources"])
def test_current_capture_keeps_exact_origin_equality_after_context_expansion(
    tmp_path: Path, changed_field: str
) -> None:
    config, authored = signal_workspace(tmp_path)
    raw = yaml.safe_load(config.read_text())
    if changed_field == "applicable_scopes":
        # Both IDs remain registered; catalog validation alone cannot detect this mismatch.
        raw["applicable_scopes"] = ["org:example"]
    else:
        extra = tmp_path / "extra-knowledge"
        extra.mkdir()
        raw["sources"].append(
            {"id": "extra", "root": str(extra), "catalog": raw["sources"][0]["catalog"]}
        )
    config.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValidationError) as caught:
        record_signal_result(load_workspace(config), {"file": str(authored)})
    assert caught.value.code == "origin-mismatch"
    assert caught.value.path.endswith(
        "origin.applicable_scopes" if changed_field == "applicable_scopes" else "origin.source_ids"
    )
    assert not (tmp_path / "scaffold/ai").exists()


def test_historical_read_does_not_unfreeze_routing_during_active_run(tmp_path: Path) -> None:
    config, authored = signal_workspace(tmp_path)
    captured = record_signal_result(load_workspace(config), {"file": str(authored)})
    selected = (SignalSnapshot(captured["id"], captured["local_path"], captured["fingerprint"]),)
    original = Path(captured["local_path"]).read_bytes()
    loaded = load_workspace(config)
    started = start_run(
        loaded,
        selected=selected,
        harness="codex",
        session_id="review-session",
        automation_id=None,
        workspace_id=loaded.definition.workspace_id,
    )
    archive = archive_path(loaded, started.run_id, selected[0])
    raw = yaml.safe_load(config.read_text())
    raw["applicable_scopes"] = ["org:example"]
    config.write_text(yaml.safe_dump(raw))
    reloaded = load_workspace(config)
    assert list_signal_result(reloaded, {})["results"] == [captured]
    receipts_before = {
        path: path.read_bytes() for path in loaded.receipts.directory.rglob("*") if path.is_file()
    }
    no_write = (SignalDisposition(captured["id"], CompoundDecision.KEEP, "Review complete."),)
    with pytest.raises(ValidationError) as caught:
        drain_signals(reloaded, selected, no_write, run_id=started.run_id)
    assert caught.value.code == "configuration-route-mismatch"
    assert Path(captured["local_path"]).read_bytes() == original
    assert archive.read_bytes() == original
    assert {path: path.read_bytes() for path in receipts_before} == receipts_before
