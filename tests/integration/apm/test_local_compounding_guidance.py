"""Guard the shared setup and worker safety contract across provider references."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKILLS = ROOT / "packages/knowledge-agent-pack/.apm/skills"
SETUP = SKILLS / "knowledge-setup"


def test_each_provider_routes_to_one_local_trigger_owner() -> None:
    for provider in ("codex", "claude", "copilot"):
        text = (SETUP / "references" / f"{provider}-scheduled.md").read_text()
        assert "local-compounding.md" in text
        assert "agent-knowledge-compound:<workspace_id>" in text
        assert "prompt" in text
        assert "durable" in text
        assert "cloud automation" not in text
        assert "GitHub Actions" not in text
        assert "provider-native cloud environment" not in text


def test_prompt_scheduling_fallback_uses_native_subagents_only() -> None:
    shared = " ".join((SETUP / "references/local-compounding.md").read_text().split())
    worker = " ".join((SKILLS / "knowledge-compound/SKILL.md").read_text().split())
    for text in (shared, worker):
        assert "native subagents are the execution interface" in text
        assert "scheduling fallback" in text
        assert "[agent-knowledge-compound-worker]" in text
        assert "native subagent tools are unavailable" in text
        for executable in ("codex exec", "claude -p", "copilot -p"):
            assert f"`{executable}`" in text
    assert "role context, not authorization, a lock" in worker
    assert "worker's own hook session is not a replacement parent identity" in worker
    for provider in ("codex", "claude", "copilot"):
        text = " ".join((SETUP / "references" / f"{provider}-scheduled.md").read_text().split())
        assert "native subagent tools" in text.lower()
        assert "[agent-knowledge-compound-worker]" in text
        assert "another model CLI as the worker" in text
        assert "compounding pending" in text


def test_setup_preserves_separate_runtime_and_apm_lifecycles() -> None:
    text = (SETUP / "SKILL.md").read_text()
    assert "references/containers.md" in text
    assert "references/local-compounding.md" in text
    assert "--runtime-mode existing" in text
    assert "prepare -> repository-owned install/compile -> bind -> repository checks" in text
    assert "Installed fixtures do not" in text
    assert "prove live delegation" in text
    assert "never implicitly runs `configure-trigger`" in text
    assert "only after final consumer checks pass" in text
    assert "valid discovery/reflection bindings still proceed" in text


def test_worker_guards_are_documented_with_existing_compound_safety() -> None:
    text = (SKILLS / "knowledge-compound/SKILL.md").read_text()
    for term in (
        "automatic: true",
        "started: false",
        "parent_session_id",
        "worker_id",
        "recovery_of",
        "action: record-worker",
        "Prompt fallback has no scheduler-provided automation handle",
        "Do\nnot wait indefinitely before starting",
        "Do not delegate another opportunistic compound",
        "completion: completed",
        "remote commit and PR head",
        "Changed, new, missing",
    ):
        assert term in text
    for completion in ("completed", "deferred", "failed", "empty"):
        assert f"`{completion}`:" in text
    setup = (SETUP / "references/local-compounding.md").read_text()
    assert "compound-activity.jsonl" in setup
    assert "configure-trigger" in setup
    assert "expected_trigger" in setup
    assert "replace_trigger" not in setup
    assert "Active runs\nnever expire by age" in setup
