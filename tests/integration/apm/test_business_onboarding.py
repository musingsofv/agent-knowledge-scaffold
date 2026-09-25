"""Verify that the installed skill's paired examples use the real catalog contract."""

import re
from pathlib import Path

from agent_knowledge.application.discovery import catalog_result, context_result
from agent_knowledge.application.retrieval import search_result
from agent_knowledge.application.validation import validate_result
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from tests.factories import knowledge_data

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = (
    ROOT
    / "packages/knowledge-agent-pack/.apm/skills/knowledge-setup/references/business-onboarding.md"
)


def test_onboarding_examples_bootstrap_a_solo_workspace_and_business_workflow(
    tmp_path: Path,
) -> None:
    examples = dict(
        re.findall(
            r"### (catalog.yaml|knowledge-workspace.yaml)\n\n```yaml\n(.*?)\n```",
            REFERENCE.read_text(),
            re.DOTALL,
        )
    )
    assert set(examples) == {"catalog.yaml", "knowledge-workspace.yaml"}
    for filename, text in examples.items():
        (tmp_path / filename).write_text(text)
    source = tmp_path / "knowledge"
    source.mkdir()
    config = tmp_path / "knowledge-workspace.yaml"
    context = context_result(load_workspace(config), {})
    assert context["applicable_scopes"] == ["org:studio"]
    assert len(context["sources"]) == 1
    assert context["receipts"] == {
        "enabled": True,
        "directory": str(tmp_path / "ai/usage"),
        "retention_days": 30,
    }
    assert (
        validate_result(load_workspace(config), {"sources": ["business-knowledge"]})["checked"] == 0
    )
    topics = catalog_result(
        load_workspace(config), {"dimension": "topics", "text": {"any": ["prospecting"]}}
    )
    assert [row["id"] for row in topics["results"]] == ["lead-generation"]

    # A separate authoring operation can now use the confirmed vocabulary.
    (source / "qualification.md").write_bytes(
        dump_document(
            knowledge_data(
                kind="workflow",
                title="Qualify an agency before outreach",
                scope=["org:studio"],
                topics=["lead-generation"],
                entities=["product:client-intake"],
            ),
            "# Qualify an agency\n\nCheck its intake needs before selecting it for outreach.\n",
        )
    )
    assert (
        validate_result(load_workspace(config), {"sources": ["business-knowledge"]})["valid"]
        is True
    )
    selected = search_result(
        load_workspace(config), {"kind": ["workflow"], "topics": ["lead-generation"]}
    )
    assert [row["path"] for row in selected["results"]] == ["qualification.md"]
    assert search_result(load_workspace(config), {"topics": ["testing"]})["results"] == []
