"""Keep conditional delegation isolated from mandatory reminder transport."""

import io
import json
import subprocess
from pathlib import Path

import pytest

from agent_knowledge.entrypoints.hooks import compounding, runtime


def _invoke(monkeypatch, provider, extra=None, *, prompt_text=None):
    payload = (
        {"sessionId": "parent-1", "transformedPrompt": "Ordinary user task."}
        if provider == "copilot"
        else {"session_id": "parent-1", "hook_event_name": "UserPromptSubmit"}
    )
    payload["cwd"] = "/work/consumer"
    if prompt_text is not None:
        payload["prompt"] = prompt_text
        if provider == "copilot":
            payload["transformedPrompt"] = prompt_text
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type("Input", (), {"buffer": io.BytesIO(json.dumps(payload).encode())})(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)
    assert runtime.main(["--provider", provider, *(extra or [])]) == 0
    return json.loads(output.getvalue())


@pytest.mark.parametrize("provider", ["codex", "claude", "copilot"])
def test_due_delegation_uses_one_channel_and_preserves_prompt(monkeypatch, provider):
    received = {}

    def check(**kwargs):
        received.update(kwargs)
        return "Delegate installed knowledge-compound."

    monkeypatch.setattr(compounding, "bounded_compound_context", check)
    result = _invoke(
        monkeypatch,
        provider,
        ["--profile", "example", "--compound-skill", "apm_modules/pack/SKILL.md"],
    )
    assert len(result) == 1
    context = (
        result["modifiedTransformedPrompt"]
        if provider == "copilot"
        else result["hookSpecificOutput"]["additionalContext"]
    )
    if provider == "copilot":
        assert context.startswith("Ordinary user task.\n\n")
    assert "Reflect and record useful observations" in context
    assert context.endswith("Delegate installed knowledge-compound.")
    assert received["provider"] == provider
    assert received["session_id"] == "parent-1"
    assert received["cwd"] == "/work/consumer"
    assert received["profile"] == "example"


@pytest.mark.parametrize("provider", ["codex", "claude", "copilot"])
def test_no_binding_never_launches_due_check(monkeypatch, provider):
    def forbidden(**kwargs):
        pytest.fail("Unconfigured hook must not inspect coordination state.")

    monkeypatch.setattr(compounding, "bounded_compound_context", forbidden)
    result = _invoke(monkeypatch, provider)
    assert "Reflect and record useful observations" in json.dumps(result)


@pytest.mark.parametrize("provider", ["codex", "claude", "copilot"])
def test_native_worker_marker_suppresses_inherited_delegation_only(monkeypatch, provider):
    def worker_binding(**kwargs):
        assert provider == "copilot"
        assert kwargs["worker"] is True
        assert kwargs["session_id"] == "parent-1"
        return "Bound compounding worker context (Copilot): exact bound selection."

    monkeypatch.setattr(compounding, "bounded_compound_context", worker_binding)
    assignment = compounding.WORKER_MARKER + " Process the parent's selected workspace."
    result = _invoke(
        monkeypatch,
        provider,
        ["--profile", "example", "--compound-skill", "/installed/SKILL.md"],
        prompt_text=assignment,
    )
    assert "Reflect and record useful observations" in json.dumps(result)
    assert "Local knowledge compounding is due" not in json.dumps(result)
    if provider == "copilot":
        assert result["modifiedTransformedPrompt"].startswith(assignment + "\n\n")
        assert "Bound compounding worker context (Copilot)" in json.dumps(result)


def test_marked_copilot_worker_cannot_silently_lose_its_binding(monkeypatch):
    monkeypatch.setattr(compounding, "bounded_compound_context", lambda **kwargs: None)
    result = _invoke(
        monkeypatch,
        "copilot",
        ["--profile", "example", "--compound-skill", "/installed/SKILL.md"],
        prompt_text=compounding.WORKER_MARKER,
    )
    context = result["modifiedTransformedPrompt"]
    assert "Bound compounding worker context unavailable" in context
    assert "Do not infer a selection" in context
    assert "Reflect and record useful observations" in context
    assert "Local knowledge compounding is due" not in context


def test_worker_marker_is_an_explicit_hint_not_a_semantic_role_guess():
    assert not compounding.is_worker_prompt({"prompt": "Discuss knowledge compounding."})
    assert not compounding.is_worker_prompt({"prompt": {"marker": compounding.WORKER_MARKER}})
    assert compounding.is_worker_prompt(
        {"transformedPrompt": "Provider prefix\n" + compounding.WORKER_MARKER + " Assignment"}
    )


@pytest.mark.parametrize("provider", ["codex", "claude", "copilot"])
@pytest.mark.parametrize("failure", ["timeout", "error", "invalid"])
def test_due_check_failure_does_not_suppress_reflection(monkeypatch, provider, failure):
    def run(*args, **kwargs):
        assert kwargs["timeout"] == 1.0
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args[0], 1.0)
        return subprocess.CompletedProcess(args[0], 2 if failure == "error" else 0, "invalid", "")

    monkeypatch.setattr(compounding.subprocess, "run", run)
    result = _invoke(
        monkeypatch,
        provider,
        ["--config", "/state/workspace.yaml", "--compound-skill", "/skill.md"],
    )
    assert "Reflect and record useful observations" in json.dumps(result)
    assert "Local knowledge compounding is due" not in json.dumps(result)


def test_portable_skill_uses_bounded_provider_cwd_ancestry(tmp_path: Path):
    skill = tmp_path / "consumer/apm_modules/pack/.apm/skills/knowledge-compound/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Skill body is not read by the probe.")
    nested = tmp_path / "consumer/src/nested"
    nested.mkdir(parents=True)
    relative = str(skill.relative_to(tmp_path / "consumer"))
    assert compounding._installed_skill(relative, str(nested)) == skill
    with pytest.raises(ValueError):
        compounding._installed_skill(relative, None)
    with pytest.raises(ValueError):
        compounding._installed_skill("../SKILL.md", str(nested))
    with pytest.raises(ValueError):
        compounding._installed_skill(relative, "relative/cwd")


def test_quiet_due_result_has_no_prompt_context(monkeypatch):
    monkeypatch.setattr(
        compounding.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "null\n", ""),
    )
    assert (
        compounding.bounded_compound_context(
            config=Path("/state/workspace.yaml"),
            settings=None,
            profile=None,
            skill=Path("/skill.md"),
            provider="codex",
            session_id="parent-1",
            cwd="/work/consumer",
        )
        is None
    )
