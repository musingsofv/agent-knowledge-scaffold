"""Prove effective selection across a complete authoring and compounding workflow."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_knowledge.entrypoints.cli.main import main
from agent_knowledge.infrastructure.documents import dump_document, parse_document
from tests.factories import knowledge_data
from tests.integration.application.test_signals import signal_workspace
from tests.integration.entrypoints.cli.test_main import output
from tests.integration.infrastructure.test_profiles import write_registry


def test_every_configured_operation_uses_profile_snapshot_and_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, authored = signal_workspace(tmp_path)
    scaffold = tmp_path / "override"
    source = scaffold / "knowledge"
    source.mkdir(parents=True)
    (scaffold / "ai/usage").mkdir(parents=True)
    (scaffold / "ai/signals").mkdir(parents=True)
    catalog = tmp_path / "scaffold/catalog.yaml"
    (source / "rule.md").write_bytes(dump_document(knowledge_data(), "# Rule\n\nUse fixtures.\n"))
    settings = write_registry(
        tmp_path,
        config,
        {
            "sources": [{"id": "knowledge", "root": str(source), "catalog": str(catalog)}],
            "signal_storage": {"scaffold_root": str(scaffold)},
            "receipts": {"directory": str(scaffold / "ai/usage")},
        },
    )
    registry_bytes = settings.read_bytes()
    parsed = parse_document(authored.read_bytes())
    parsed.metadata["origin"].update(harness="claude", session_id="exact-session")
    authored.write_bytes(dump_document(parsed.metadata, parsed.body))
    request_path = tmp_path / "request.json"

    def invoke(command: str, request: object = None, run_id: str | None = None):
        args = ["--settings", str(settings), "--profile", "personal"]
        if run_id:
            args += ["--compound-run-id", run_id]
        request_path.write_text(json.dumps(request or {}))
        code = main([*args, *command.split(), "--request-file", str(request_path)])
        result = output(capsys)
        assert code == 0, result
        assert result["selection"]["profile"] == "personal"
        return result

    assert invoke("doctor", {"mode": "write"})["readiness"]["receipts"] == "ready"
    assert invoke("context")["sources"][0]["root"] == str(source)
    assert invoke("catalog", {"dimension": "topics"})["returned"] == 1
    found = invoke("search", {"text": {"any": ["fixtures"]}})
    assert found["results"][0]["local_path"] == str(source / "rule.md")
    inspected = invoke("inspect", {"document": {"source": "knowledge", "path": "rule.md"}})
    assert inspected["preview"]["local_path"] == str(source / "rule.md")
    assert invoke("validate", {"sources": ["knowledge"]})["valid"]
    recorded = invoke("signal record", {"file": authored.name})
    assert Path(recorded["local_path"]).is_relative_to(scaffold / "ai/signals")
    listed = invoke("signal list", {"session_id": "exact-session"})
    assert listed["results"][0]["origin"]["session_id"] == "exact-session"
    selected = [
        {
            "id": recorded["id"],
            "path": recorded["local_path"],
            "fingerprint": recorded["fingerprint"],
        }
    ]
    assert invoke("compound", {"action": "status"})["active"] is False
    started = invoke(
        "compound",
        {
            "action": "start",
            "workspace_id": "repo:orders",
            "harness": "claude",
            "session_id": "compound-session",
            "selected": selected,
        },
    )
    run_id = started["run_id"]
    assert invoke("validate", {"sources": ["knowledge"]}, run_id)["valid"]
    disposition = {
        "signal_id": recorded["id"],
        "decision": "keep",
        "rationale": "Existing rule covers this observation.",
        "owners": [{"source": "knowledge", "path": "rule.md"}],
    }
    drained = invoke(
        "compound",
        {
            "action": "drain",
            "run_id": run_id,
            "selected": selected,
            "dispositions": [disposition],
            "publication_verified": False,
        },
    )
    assert drained["drained"] == [recorded["id"]]
    assert not Path(recorded["local_path"]).exists()
    assert not invoke(
        "compound",
        {
            "action": "finish",
            "run_id": run_id,
            "outcome": "no-update",
            "dispositions": [disposition],
        },
    )["active"]
    now = datetime.now(UTC)
    export = tmp_path / "export"
    invoke(
        "usage export",
        {
            "since": (now - timedelta(days=1)).isoformat(),
            "until": (now + timedelta(days=1)).isoformat(),
            "destination": str(export),
        },
    )
    descriptors = list(export.rglob("descriptors/*.json"))
    assert descriptors
    for path in descriptors:
        descriptor = json.loads(path.read_text())
        assert descriptor["selection"]["profile"] == "personal"
        assert descriptor["configuration"]["values"]["sources"][0]["root"] == str(source)
    archives = list((scaffold / "ai/usage/compound" / run_id / "inputs").glob("*.md"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == authored.read_bytes()
    assert not (tmp_path / "scaffold/ai").exists()
    assert settings.read_bytes() == registry_bytes
