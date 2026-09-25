"""Prove automatic terminal evidence through the public CLI boundary."""

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from agent_knowledge.entrypoints.cli.main import main
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.usage import canonical_json
from tests.factories import knowledge_data
from tests.integration.application.test_discovery import workspace_file


def invoke(
    config: Path, command: str, request: object, capsys: pytest.CaptureFixture[str], *context: str
) -> tuple[int, dict]:
    request_file = config.parent / "request.json"
    request_file.write_text(json.dumps(request))
    result = main(
        ["--config", str(config), *context, *command.split(), "--request-file", str(request_file)]
    )
    return result, json.loads(capsys.readouterr().out)


def records(root: Path) -> list[dict]:
    return [
        json.loads(line)
        for file in sorted((root / "ai/usage/retrieval").glob("*.jsonl"))
        for line in file.read_text().splitlines()
    ]


@pytest.mark.parametrize(
    ("command", "query", "expected"),
    [
        ("catalog", {"dimension": "topics", "limit": 1}, 0),
        ("search", {}, 0),
        ("search", {"text": {"any": ["not-present-in-file"]}}, 0),
        ("search", {"topics": ["unknown"]}, 2),
        ("inspect", {"document": {"source": "knowledge", "path": "rule.md"}}, 0),
        ("inspect", {"document": {"source": "knowledge", "path": "missing.md"}}, 2),
        (
            "inspect",
            {"document": {"source": "knowledge", "path": "rule.md"}, "view": "incoming"},
            0,
        ),
    ],
)
def test_terminal_receipt_preserves_complete_response_and_attempted_request(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    command: str,
    query: dict,
    expected: int,
) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/rule.md").write_bytes(
        dump_document(knowledge_data(), "# Procedure\n\nUseful body context.\n")
    )
    exit_code, response = invoke(
        config, command, query, capsys, "--harness", "claude", "--session-id", "exact-session-1"
    )
    assert exit_code == expected
    receipt = response.pop("receipt")
    assert receipt["status"] == "written"
    (event,) = records(tmp_path)
    assert event["schema_version"] == "knowledge-retrieval-receipt.v1"
    assert event["request"] == query
    assert event["response"] == response
    assert event["context"] == {
        "workspace_id": "repo:orders",
        "harness": "claude",
        "session_id": "exact-session-1",
        "compound_run_id": None,
    }
    assert event["measurements"]["response_bytes"] == len(canonical_json(response))
    assert event["measurements"]["elapsed_ms"] >= 0
    assert event["body_read"] == "unknown"
    descriptor = tmp_path / "ai/usage" / event["descriptor"]
    assert json.loads(descriptor.read_text())["workspace_id"] == "repo:orders"
    assert "Useful body context." not in json.dumps(event)


def test_unparseable_request_is_null_without_leaking_raw_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    request = tmp_path / "invalid.yaml"
    request.write_text("text: private-marker\ntext: secret-marker\n")
    assert main(["--config", str(config), "search", "--request-file", str(request)]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["receipt"]["status"] == "written"
    (event,) = records(tmp_path)
    assert event["request"] is None
    assert "private-marker" not in json.dumps(event)
    assert "secret-marker" not in json.dumps(event)


def test_invalid_configuration_never_guesses_usage_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "missing-config.yaml"
    code, response = invoke(config, "search", {}, capsys)
    assert code != 0
    assert response["receipt"]["status"] == "unavailable"
    assert not (tmp_path / "ai").exists()


def test_disabled_receipts_leave_successful_result_and_unknown_context_is_not_invented(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    _, result = invoke(config, "search", {}, capsys)
    assert result["receipt"]["status"] == "written"
    assert records(tmp_path)[0]["context"]["session_id"] is None
    raw = yaml.safe_load(config.read_text())
    raw["receipts"] = {"enabled": False}
    config.write_text(yaml.safe_dump(raw))
    code, response = invoke(config, "search", {}, capsys)
    assert code == 0
    assert response["receipt"] == {"status": "disabled"}
    assert len(records(tmp_path)) == 1


def test_logging_failure_does_not_turn_retrieval_into_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = workspace_file(tmp_path)

    def fail(*args: object) -> None:
        raise AdapterError("write-failed", "usage", "Unavailable")

    monkeypatch.setattr("agent_knowledge.infrastructure.receipts.append_event", fail)
    code, response = invoke(config, "search", {}, capsys)
    assert code == 0
    assert response["status"] == "ok"
    assert response["receipt"]["status"] == "failed"


def test_handled_interrupt_writes_a_terminal_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    config = workspace_file(tmp_path)

    def interrupt(*args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("agent_knowledge.entrypoints.cli.main.search_result", interrupt)
    code, response = invoke(config, "search", {}, capsys)
    assert code == 3
    assert response["receipt"]["status"] == "written"
    assert records(tmp_path)[0]["response"]["diagnostics"][0]["code"] == "interrupted"


def test_descriptor_records_catalog_bytes_without_claiming_document_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    invoke(config, "search", {}, capsys)
    (event,) = records(tmp_path)
    descriptor = json.loads((tmp_path / "ai/usage" / event["descriptor"]).read_text())
    catalog = descriptor["sources"][0]
    assert (
        catalog["catalog_fingerprint"]
        == "sha256:" + hashlib.sha256(Path(catalog["catalog_path"]).read_bytes()).hexdigest()
    )
    assert catalog["source_version"] == "unavailable"


def test_compound_context_defaults_and_validation_are_joined_to_recorded_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agent_knowledge.application.compounding import compound_result
    from tests.integration.application.test_signals import signal_workspace

    config, _ = signal_workspace(tmp_path)
    started = compound_result(
        load_workspace(config),
        {
            "action": "start",
            "workspace_id": "repo:orders",
            "harness": "claude",
            "session_id": "compound-session",
        },
    )
    run_id = started["run_id"]
    code, response = invoke(config, "search", {}, capsys, "--compound-run-id", run_id)
    assert code == 0
    assert response["receipt"]["status"] == "written"
    (event,) = records(config.parent)
    assert event["context"]["compound_run_id"] == run_id
    assert event["context"]["session_id"] == "compound-session"
    assert event["context"]["harness"] == "claude"
    code, response = invoke(
        config, "validate", {"sources": ["knowledge"]}, capsys, "--compound-run-id", run_id
    )
    assert code == 0
    events = [json.loads(row) for row in Path(response["receipt"]["path"]).read_text().splitlines()]
    assert events[-1]["operation"] == "validate"
    assert events[-1]["response"]["valid"] is True
    assert events[-1]["context"] == event["context"]


def test_foreign_or_conflicting_context_cannot_append_to_another_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agent_knowledge.application.compounding import compound_result
    from tests.integration.application.test_signals import signal_workspace

    config, _ = signal_workspace(tmp_path)
    started = compound_result(
        load_workspace(config),
        {
            "action": "start",
            "workspace_id": "repo:orders",
            "harness": "claude",
            "session_id": "correct-session",
        },
    )
    run_id = started["run_id"]
    path = config.parent / "ai/usage/compound" / run_id / "events.jsonl"
    original = path.read_bytes()
    code, response = invoke(
        config, "search", {}, capsys, "--compound-run-id", run_id, "--session-id", "wrong-session"
    )
    assert code == 2
    assert response["diagnostics"][0]["code"] == "context-mismatch"
    assert path.read_bytes() == original
    other = config.parent / "other-workspace.yaml"
    definition = yaml.safe_load(config.read_text())
    definition["workspace_id"] = "workspace:other"
    other.write_text(yaml.safe_dump(definition))
    code, response = invoke(other, "search", {}, capsys, "--compound-run-id", run_id)
    assert code == 2
    assert response["diagnostics"][0]["code"] == "workspace-mismatch"
    assert path.read_bytes() == original
    assert records(config.parent)[-1]["context"]["compound_run_id"] is None


def test_unknown_cli_flag_still_records_terminal_error_with_safe_configuration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = workspace_file(tmp_path)
    assert main(["--config", str(config), "search", "--unsupported"]) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["receipt"]["status"] == "written"
    assert records(tmp_path)[0]["request"] is None


def test_lifecycle_body_run_id_does_not_bypass_invocation_consistency(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from agent_knowledge.application.compounding import compound_result
    from tests.integration.application.test_signals import signal_workspace

    config, _ = signal_workspace(tmp_path)
    started = compound_result(
        load_workspace(config),
        {
            "action": "start",
            "workspace_id": "repo:orders",
            "harness": "claude",
            "session_id": "recorded-session",
        },
    )
    code, response = invoke(
        config,
        "compound",
        {"action": "finish", "run_id": started["run_id"], "outcome": "no-update"},
        capsys,
        "--harness",
        "codex",
        "--session-id",
        "other-session",
    )
    assert code == 2
    assert response["diagnostics"][0]["code"] == "context-mismatch"
    assert compound_result(load_workspace(config), {"action": "status"})["active"]
