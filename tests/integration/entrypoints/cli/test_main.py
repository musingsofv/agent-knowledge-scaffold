"""Check machine-facing command parsing and error categories in the real entrypoint."""

import hashlib
import io
import json
from pathlib import Path

import pytest
import yaml

from agent_knowledge.entrypoints.cli.main import main
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from tests.factories import knowledge_data, signal_data
from tests.integration.application.test_discovery import workspace_file
from tests.integration.application.test_signals import signal_workspace


def output(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """Decode exactly one machine response and reject stray stderr output."""
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert isinstance(result, dict)
    return result


def test_default_describe_does_not_read_stdin_or_require_configuration(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", None)

    assert main(["describe"]) == 0
    result = output(capsys)
    assert result["status"] == "ok"
    assert result["diagnostics"] == []
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


def test_explicit_stdin_accepts_json_and_returns_selected_field(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.stdin",
        io.TextIOWrapper(io.BytesIO(b'{"schema":"knowledge.v1","field":"technologies"}')),
    )

    assert main(["describe", "--request-file", "-"]) == 0
    assert "technologies" in output(capsys)["fields"]


def test_yaml_request_path_resolves_from_cwd_and_source_paths_from_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "configured"
    config_dir.mkdir()
    config = workspace_file(config_dir)
    (tmp_path / "request.yaml").write_text("dimension: technologies\nids: [postgresql]\n")
    monkeypatch.chdir(tmp_path)

    assert main(["--config", str(config), "catalog", "--request-file", "request.yaml"]) == 0
    assert output(capsys)["returned"] == 1


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["unknown"],
        ["describe", "--config", "elsewhere"],
        ["--output", "xml", "describe"],
        ["signal"],
        ["signal", "unknown"],
        ["signal", "--request-file", "request.yaml", "list"],
        ["signal", "record", "--config", "elsewhere"],
    ],
)
def test_invalid_command_syntax_is_structured_error(
    args: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(args) == 2
    result = output(capsys)
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"] == "invalid-arguments"


def test_missing_configuration_is_not_inferred_from_environment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KNOWLEDGE_ROOT", "/should/not/be/read")
    assert main(["context"]) == 2
    assert output(capsys)["diagnostics"][0]["code"] == "profile-settings-unavailable"


@pytest.mark.parametrize("command", ["record", "list"])
def test_signal_subcommands_require_resolvable_configuration(
    tmp_path: Path,
    command: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KNOWLEDGE_ROOT", "/should/not/be/read")

    assert main(["signal", command]) == 2
    assert output(capsys)["diagnostics"][0]["code"] == "profile-settings-unavailable"


@pytest.mark.parametrize("command", ["record", "list"])
def test_signal_subcommand_duplicate_request_keys_are_rejected_before_capture(
    command: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = tmp_path / "request.yaml"
    request.write_text("file: first.md\nfile: second.md\n")

    config, _ = signal_workspace(tmp_path)
    assert main(["--config", str(config), "signal", command, "--request-file", str(request)]) == 2
    result = output(capsys)
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"] == "duplicate-yaml-key"


def test_doctor_retains_runtime_details_when_configuration_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["doctor"]) == 2
    result = output(capsys)
    assert result["runtime"]["interpreter"]
    assert result["readiness"]["read"] == "not-ready"


def test_duplicate_request_keys_return_no_partial_response(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_file = tmp_path / "request.yaml"
    request_file.write_text("schema: knowledge.v1\nschema: knowledge-catalog.v1\n")
    assert main(["describe", "--request-file", str(request_file)]) == 2
    result = output(capsys)
    assert result["status"] == "error"
    assert "fields" not in result


def test_missing_request_file_has_an_explicit_diagnostic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["describe", "--request-file", str(tmp_path / "missing.yaml")]) == 2
    assert output(capsys)["status"] == "error"


def test_explicit_request_alias_is_resolved_before_guarded_read(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request_file = tmp_path / "request.yaml"
    request_file.write_text("schema: knowledge.v1\nfield: technologies\n")
    alias = tmp_path / "selected-request.yaml"
    alias.symlink_to(request_file)

    assert main(["describe", "--request-file", str(alias)]) == 0
    assert "technologies" in output(capsys)["fields"]


def test_text_output_renders_the_same_context_without_python_repr(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = workspace_file(tmp_path)
    assert main(["--config", str(config), "--output", "text", "context"]) == 0
    text = capsys.readouterr().out
    assert "repo:orders" in text
    assert "status: ok" in text
    assert "PosixPath(" not in text


def test_validate_returns_content_diagnostics_and_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/broken.md").write_bytes(
        dump_document(knowledge_data(entities=["feature:unknown"]), "# Broken\n")
    )
    request = tmp_path / "validate.json"
    request.write_text('{"sources":["knowledge"]}')

    assert (
        main(
            [
                "--config",
                str(config),
                "validate",
                "--request-file",
                str(request),
            ]
        )
        == 2
    )
    result = output(capsys)

    assert result["status"] == "error"
    assert result["valid"] is False
    assert result["diagnostics"][0]["code"] == "unknown-identifier"
    assert result["results"][0]["status"] == "invalid"


def test_compound_cli_records_run_and_drains_selected_signal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config, authored = signal_workspace(tmp_path)
    from agent_knowledge.application.signals import list_signal_result, record_signal_result

    recorded = record_signal_result(load_workspace(config), {"file": str(authored)})
    selected = {
        "id": recorded["id"],
        "path": recorded["local_path"],
        "fingerprint": recorded["fingerprint"],
    }
    start_request = tmp_path / "start.json"
    start_request.write_text(
        json.dumps(
            {
                "action": "start",
                "workspace_id": "repo:orders",
                "selected": [selected],
                "harness": "codex",
                "session_id": "session-1",
                "automation_id": "automation-1",
            }
        )
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "compound",
                "--request-file",
                str(start_request),
            ]
        )
        == 0
    )
    started = output(capsys)
    run_id = started["run_id"]

    drain_request = tmp_path / "drain.json"
    drain_request.write_text(
        json.dumps(
            {
                "action": "drain",
                "run_id": run_id,
                "selected": [selected],
                "dispositions": [
                    {
                        "signal_id": recorded["id"],
                        "decision": "keep",
                        "rationale": "The observation is already represented.",
                    }
                ],
            }
        )
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "compound",
                "--request-file",
                str(drain_request),
            ]
        )
        == 0
    )
    drained = output(capsys)
    assert drained["drained"] == [recorded["id"]]
    assert not Path(recorded["local_path"]).exists()

    finish_request = tmp_path / "finish.json"
    finish_request.write_text(
        json.dumps(
            {
                "action": "finish",
                "run_id": run_id,
                "outcome": "no-update",
                "dispositions": [
                    {
                        "signal_id": recorded["id"],
                        "decision": "keep",
                        "rationale": "The observation is already represented.",
                    }
                ],
            }
        )
    )
    assert (
        main(
            [
                "--config",
                str(config),
                "compound",
                "--request-file",
                str(finish_request),
            ]
        )
        == 0
    )
    finished = output(capsys)
    assert finished["drained"] == [recorded["id"]]
    status = list_signal_result(load_workspace(config), {})
    assert status["results"] == []


def test_keyboard_interruption_returns_incomplete_error(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupted(_: object) -> object:
        raise KeyboardInterrupt

    monkeypatch.setattr("agent_knowledge.entrypoints.cli.main.describe", interrupted)
    assert main(["describe"]) == 3
    assert output(capsys)["diagnostics"][0]["code"] == "interrupted"


@pytest.mark.parametrize("request_format", ["yaml", "json"])
def test_search_then_inspect_through_cli_returns_navigation_without_procedure_prose(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    request_format: str,
) -> None:
    config = workspace_file(tmp_path)
    document = tmp_path / "knowledge/index-change.md"
    document.write_bytes(
        dump_document(
            knowledge_data(kind="runbook", title="Index change procedure"),
            "# Index maintenance\n\n## Adding an index\n"
            "Measure the production workload before applying this change.\n",
        )
    )
    request_file = tmp_path / f"request.{request_format}"
    search = {"kind": ["runbook"], "text": {"any": ["index"]}, "limit": 2}
    encode = yaml.safe_dump if request_format == "yaml" else json.dumps
    request_file.write_text(encode(search))

    assert main(["--config", str(config), "search", "--request-file", str(request_file)]) == 0
    result = output(capsys)
    assert result["status"] == "ok"
    assert result["diagnostics"] == []
    assert result["scan_status"] == "complete"
    assert result["returned"] == result["total_matches"] == 1
    preview = result["results"][0]
    assert preview["source"] == "knowledge"
    assert preview["path"] == "index-change.md"
    assert preview["local_path"] == str(document)
    assert preview["matches"]
    assert preview["body_range"][0] > preview["frontmatter_range"][1]
    assert "body" not in preview
    assert "Measure the production workload" not in json.dumps(result)

    # A direct inspection must not scan unrelated document bodies.
    (tmp_path / "knowledge/unrelated.md").write_text("malformed unrelated document")
    request_file.write_text(
        encode(
            {
                "document": {"source": preview["source"], "path": preview["path"]},
                "expected_fingerprint": preview["fingerprint"],
                "limit": 10,
            }
        )
    )
    assert main(["--config", str(config), "inspect", "--request-file", str(request_file)]) == 0
    inspected = output(capsys)
    assert inspected["status"] == "ok"
    assert inspected["preview"]["fingerprint"] == preview["fingerprint"]
    assert [entry["title"] for entry in inspected["navigation"]] == [
        "Index maintenance",
        "Adding an index",
    ]
    assert "body" not in inspected["preview"]
    assert "Measure the production workload" not in json.dumps(inspected)


def test_cli_search_valid_empty_response_is_distinct_from_unknown_identifier(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = workspace_file(tmp_path)
    request_file = tmp_path / "request.yaml"
    request_file.write_text("kind: [limitation]\nentities: [feature:history]\n")

    assert main(["--config", str(config), "search", "--request-file", str(request_file)]) == 0
    empty = output(capsys)
    assert empty["status"] == "ok"
    assert empty["diagnostics"] == []
    assert empty["results"] == []
    assert empty["returned"] == empty["total_matches"] == 0
    assert empty["scan_status"] == "complete"
    assert empty["continuation"] is None

    request_file.write_text("kind: [limitation]\nentities: [feature:misspelled]\n")
    assert main(["--config", str(config), "search", "--request-file", str(request_file)]) == 2
    invalid = output(capsys)
    assert invalid["status"] == "error"
    assert invalid["diagnostics"][0]["code"] == "unknown-identifier"
    assert "results" not in invalid
    assert "scan_status" not in invalid


def test_cli_inspect_rejects_stale_preview_without_partial_navigation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = workspace_file(tmp_path)
    (tmp_path / "knowledge/rule.md").write_bytes(
        dump_document(knowledge_data(), "# Updated testing guidance\nCurrent procedure.\n")
    )
    request = {
        "document": {"source": "knowledge", "path": "rule.md"},
        "expected_fingerprint": "sha256:" + "0" * 64,
    }
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(request).encode())))

    assert main(["--config", str(config), "inspect", "--request-file", "-"]) == 2
    result = output(capsys)
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"] == "stale-document"
    assert "preview" not in result
    assert "navigation" not in result


@pytest.mark.parametrize("request_format", ["yaml", "json"])
def test_cli_signal_capture_then_list_preserves_claim_and_exposes_read_locations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    request_format: str,
) -> None:
    config, authored = signal_workspace(tmp_path)
    original = authored.read_bytes()
    request = tmp_path / f"request.{request_format}"
    encode = yaml.safe_dump if request_format == "yaml" else json.dumps
    request.write_text(encode({"file": authored.name}))
    monkeypatch.chdir(tmp_path)

    assert main(["--config", str(config), "signal", "record", "--request-file", request.name]) == 0
    recorded = output(capsys)
    assert recorded["status"] == "ok"
    assert recorded["diagnostics"] == []
    stored = Path(recorded["local_path"])
    assert stored.parent == tmp_path / "scaffold/ai/signals/projects/products/orders"
    assert stored.read_bytes() == authored.read_bytes() == original
    assert recorded["origin"]["project_path"] == "products/orders"
    assert recorded["byte_count"] == len(original)
    assert recorded["body_range"][0] > recorded["frontmatter_range"][1]
    assert "Preserve this exact claim" not in json.dumps(recorded)

    request.write_text(encode({"include_shared": False, "limit": 1}))
    assert main(["--config", str(config), "signal", "list", "--request-file", request.name]) == 0
    listed = output(capsys)
    assert listed["status"] == "ok"
    assert listed["diagnostics"] == []
    assert listed["results"][0] == {
        key: value
        for key, value in recorded.items()
        if key not in {"status", "diagnostics", "selection"}
    }
    assert listed["returned"] == listed["total_matches"] == 1
    assert listed["truncated"] is False
    assert listed["continuation"] is None
    assert listed["other_workspaces"] == 0
    assert "Preserve this exact claim" not in json.dumps(listed)


def test_cli_compound_drain_retains_foreign_signal_and_runtime_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _ = signal_workspace(tmp_path)
    signal_root = tmp_path / "scaffold/ai/signals"
    foreign = signal_root / "projects/products/orders/foreign.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_bytes(
        dump_document(
            signal_data(
                id="foreign-signal",
                origin={
                    "workspace_id": "repo:other",
                    "project_path": "products/orders",
                    "applicable_scopes": ["org:example", "repo:orders"],
                    "source_ids": ["knowledge"],
                },
            ),
            "# Foreign observation\n\nKeep this pending evidence.\n",
        )
    )
    activity = signal_root / "compound-activity.jsonl"
    activity.write_text('{"schema":"compound-activity.v1"}\n')
    request = {
        "action": "drain",
        "selected": [
            {
                "id": "foreign-signal",
                "path": str(foreign),
                "fingerprint": "sha256:" + hashlib.sha256(foreign.read_bytes()).hexdigest(),
            },
            {
                "id": "activity-log",
                "path": str(activity),
                "fingerprint": "sha256:" + hashlib.sha256(activity.read_bytes()).hexdigest(),
            },
        ],
        "dispositions": [
            {
                "signal_id": "foreign-signal",
                "decision": "keep",
                "rationale": "The current workspace must not process another workspace's signal.",
            },
            {
                "signal_id": "activity-log",
                "decision": "keep",
                "rationale": "Runtime activity is not a signal input.",
            },
        ],
    }
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(request).encode())))

    assert main(["--config", str(config), "compound", "--request-file", "-"]) == 2

    result = output(capsys)
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"] == "missing-field"
    assert foreign.exists()
    assert activity.exists()


@pytest.mark.parametrize(
    ("command", "request_data", "code"),
    [
        ("record", {}, "missing-field"),
        ("record", {"file": "observation.md", "overwrite": True}, "unknown-field"),
        ("list", {"include_shared": "true"}, "invalid-type"),
        ("list", {"limit": 0}, "invalid-value"),
    ],
)
def test_cli_signal_request_errors_are_structured_and_do_not_create_inbox(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    request_data: object,
    code: str,
) -> None:
    config, authored = signal_workspace(tmp_path)
    monkeypatch.setattr(
        "sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(request_data).encode()))
    )

    assert main(["--config", str(config), "signal", command, "--request-file", "-"]) == 2
    result = output(capsys)
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"] == code
    assert "local_path" not in result
    assert "results" not in result
    assert authored.exists()
    assert not (tmp_path / "scaffold/ai").exists()
