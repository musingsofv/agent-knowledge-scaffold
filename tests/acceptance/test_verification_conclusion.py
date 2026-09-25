"""Exercise a supplied compounding decision without treating validation as a judge."""

from pathlib import Path

from agent_knowledge.application.compounding import compound_result
from agent_knowledge.application.retrieval import inspect_result, search_result
from agent_knowledge.application.signals import list_signal_result, record_signal_result
from agent_knowledge.application.validation import validate_result
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document, parse_document
from tests.factories import knowledge_data, signal_data
from tests.integration.application.test_signals import signal_workspace


def test_compounding_can_keep_verification_evidence_outside_canonical_knowledge(
    tmp_path: Path,
) -> None:
    """The fixture supplies the agent's conclusion; tools check its storage contract."""
    config, authored = signal_workspace(tmp_path, project=False)
    scaffold = tmp_path / "scaffold"
    report = config.parent / "index-check-2026-09-14.md"
    report_bytes = (
        b"# Index check, 2026-09-14\n\nPostgreSQL 16 staging, runner v2.\n"
        b"CREATE INDEX CONCURRENTLY failed inside the runner's transaction.\n"
    )
    report.write_bytes(report_bytes)
    evidence_url = "https://example.invalid/reports/index-check-2026-09-14"
    authored.write_bytes(
        dump_document(
            signal_data(
                kind_hint="limitation",
                origin={
                    "workspace_id": "repo:orders",
                    "project_path": None,
                    "applicable_scopes": ["org:example", "repo:orders"],
                    "source_ids": ["knowledge"],
                },
                evidence=[{"type": "file", "reference": str(report)}],
            ),
            "# Observation\n\nThe transaction wrapper prevents concurrent index creation.\n",
        )
    )
    captured = record_signal_result(load_workspace(config), {"file": str(authored)})
    selected = list_signal_result(load_workspace(config), {"include_shared": True})["results"][0]
    started = compound_result(
        load_workspace(config),
        {
            "action": "start",
            "workspace_id": "repo:orders",
            "selected": [
                {
                    "id": selected["id"],
                    "path": selected["local_path"],
                    "fingerprint": selected["fingerprint"],
                }
            ],
        },
    )
    existing = search_result(
        load_workspace(config),
        {"kind": ["limitation", "runbook"], "text": {"any": ["transaction wrapper"]}},
    )
    assert existing["results"] == []

    # This is a scripted authoring outcome, not automated inference from a report.
    conclusion = scaffold / "knowledge/index-runner.md"
    conclusion.write_bytes(
        dump_document(
            knowledge_data(
                kind="limitation",
                title="The index runner wraps statements in a transaction",
                scope=["repo:orders"],
                technologies=["postgresql"],
            ),
            "# Index runner transaction constraint\n\n"
            "On PostgreSQL 16 staging with runner v2, concurrent index creation fails "
            "inside its transaction wrapper. Use a reviewed nontransactional migration "
            "path for this operation. This result does not establish behavior "
            "for other runners.\n\n"
            f"## Evidence\n\n[Verification on 2026-09-14]({evidence_url}).\n"
            f"Local report: `{report}`.\n",
        )
    )
    validated = validate_result(load_workspace(config), {"sources": ["knowledge"]})
    assert validated["valid"] is True
    assert [item["kind"] for item in validated["results"]] == ["limitation"]
    inspected = inspect_result(
        load_workspace(config), {"document": {"source": "knowledge", "path": "index-runner.md"}}
    )
    assert any(item.get("target") == evidence_url for item in inspected["navigation"])
    assert "PostgreSQL 16 staging with runner v2" in parse_document(conclusion.read_bytes()).body

    finished = compound_result(
        load_workspace(config),
        {
            "action": "finish",
            "run_id": started["run_id"],
            "outcome": "prepared-unpublished",
            "dispositions": [
                {
                    "signal_id": selected["id"],
                    "decision": "create",
                    "rationale": "Prepared a scoped limitation citing the dated verification.",
                    "owners": [{"source": "knowledge", "path": "index-runner.md"}],
                }
            ],
        },
    )
    assert finished["active"] is False
    assert report.read_bytes() == report_bytes
    assert Path(captured["local_path"]).is_file()  # No publication is claimed by this fixture.
