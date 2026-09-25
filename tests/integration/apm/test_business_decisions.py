"""Prove that current and historical questions navigate one authored owner."""

import re
from pathlib import Path

from agent_knowledge.application.retrieval import inspect_result, search_result
from agent_knowledge.application.validation import validate_result
from agent_knowledge.infrastructure.configuration import load_workspace
from agent_knowledge.infrastructure.documents import dump_document
from tests.factories import knowledge_data
from tests.integration.apm.test_business_onboarding import REFERENCE

ROOT = Path(__file__).resolve().parents[3]
DECISIONS = (
    ROOT / "packages/knowledge-agent-pack/.apm/skills/knowledge-compound"
    "/references/business-decisions.md"
)


def test_current_and_historical_questions_select_sections_of_one_valid_owner(
    tmp_path: Path,
) -> None:
    configs = re.findall(
        r"### (catalog.yaml|knowledge-workspace.yaml)\n\n```yaml\n(.*?)\n```",
        REFERENCE.read_text(),
        re.DOTALL,
    )
    for filename, body in configs:
        (tmp_path / filename).write_text(body)
    config = tmp_path / "knowledge-workspace.yaml"
    original_config = config.read_bytes()
    example = re.search(r"```markdown\n(.*?)\n```", DECISIONS.read_text(), re.DOTALL)
    assert example is not None
    source = tmp_path / "knowledge"
    (source / "guidance").mkdir(parents=True)
    (source / "runbooks").mkdir()
    guidance = source / "guidance/lead-generation.md"
    guidance.write_text(example.group(1))
    (source / "runbooks/campaign.md").write_bytes(
        dump_document(
            knowledge_data(
                kind="runbook",
                title="Run the current outreach campaign",
                scope=["org:studio"],
                topics=["lead-generation"],
            ),
            "# Run the current outreach campaign\n\n"
            "Preserve qualification evidence through the approved handoff.\n",
        )
    )
    assert (
        validate_result(load_workspace(config), {"sources": ["business-knowledge"]})["valid"]
        is True
    )

    current = search_result(
        load_workspace(config), {"kind": ["guidance"], "topics": ["lead-generation"]}
    )
    historical = search_result(
        load_workspace(config), {"topics": ["lead-generation"], "text": {"any": ["Pipedrive"]}}
    )
    assert [row["path"] for row in current["results"]] == ["guidance/lead-generation.md"]
    assert [row["path"] for row in historical["results"]] == ["guidance/lead-generation.md"]
    inspected = inspect_result(
        load_workspace(config),
        {"document": {"source": "business-knowledge", "path": "guidance/lead-generation.md"}},
    )
    headings = {row["title"]: row for row in inspected["navigation"] if row["type"] == "heading"}
    lines = guidance.read_text().splitlines()
    current_section = headings["Current approach"]
    history_section = headings["Decision history"]
    current_body = "\n".join(
        lines[current_section["start_line"] - 1 : history_section["start_line"] - 1]
    )
    historical_body = "\n".join(lines[history_section["start_line"] - 1 :])
    assert "Use Apollo" in current_body
    assert "Pipedrive" not in current_body
    assert "We previously used Pipedrive" in historical_body
    assert "experiment, not an adopted replacement" in historical_body
    assert any(
        row["type"] == "link"
        and row["document"] == {"source": "business-knowledge", "path": "runbooks/campaign.md"}
        for row in inspected["navigation"]
    )
    assert config.read_bytes() == original_config
