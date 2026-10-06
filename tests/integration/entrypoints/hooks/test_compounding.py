"""Exercise real selected state through all three installed prompt adapters."""

from __future__ import annotations

import builtins
import hashlib
import io
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_knowledge.domain.compounding import (
    CompoundDecision,
    OwnerReference,
    SignalDisposition,
    SignalSnapshot,
)
from agent_knowledge.entrypoints.hooks.compounding import compound_context
from agent_knowledge.infrastructure import compounding as compound_store
from agent_knowledge.infrastructure import environment
from agent_knowledge.infrastructure.compounding import (
    activity_path,
    configure_trigger,
    finish_run,
    start_run,
)
from agent_knowledge.infrastructure.configuration import Workspace, resolve_workspace
from agent_knowledge.infrastructure.documents import dump_document
from tests.factories import catalog_data, signal_data

PROVIDERS = ("codex", "claude", "copilot")


@dataclass(frozen=True)
class Consumer:
    config: Path
    registry: Path
    skill: Path
    signal: Path
    corpus: Path
    credentials: Path

    def workspace(self, profile: str | None = None) -> Workspace:
        return (
            resolve_workspace(config=self.config)
            if profile is None
            else resolve_workspace(settings=self.registry, profile=profile)
        )

    def request(self, provider: str = "codex", profile: str | None = None) -> dict[str, object]:
        return {
            "config": str(self.config) if profile is None else None,
            "settings": str(self.registry) if profile is not None else None,
            "profile": profile,
            "skill": str(self.skill),
            "provider": provider,
            "session_id": "exact-parent-session",
            "cwd": str(self.skill.parent),
        }


def consumer(tmp_path: Path, *, mode: str = "prompt") -> Consumer:
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    corpus = knowledge / "canonical.md"
    corpus.write_text("The prompt check must not read this body.\n")
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(json.dumps(catalog_data()))
    scaffold = tmp_path / "state"
    inbox = scaffold / "ai/signals/shared"
    inbox.mkdir(parents=True)
    config = tmp_path / "workspace.yaml"
    config.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
                "signal_storage": {"scaffold_root": "state", "code_root": "."},
                "setup": {
                    "compounding": {
                        "mode": mode,
                        "owner": "shared-local-trigger",
                        "interval_seconds": 86400,
                        "retry_seconds": 3600,
                    }
                },
            }
        )
    )
    credentials = tmp_path / "private.env"
    registry = tmp_path / "profiles.yaml"
    registry.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-profiles.v1",
                "default_profile": "alias",
                "profiles": {
                    name: {
                        "config": str(config),
                        "environment": {
                            "file": str(credentials),
                            "variables": {
                                "repository": {
                                    "from_env": "LOCAL_REPOSITORY_TOKEN",
                                    "expose_as": "GH_TOKEN",
                                    "description": "Selected repository access",
                                }
                            },
                        },
                    }
                    for name in ("primary", "alias")
                },
            }
        )
    )
    skill = tmp_path / "consumer/.agents/skills/knowledge-compound/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("The installed skill body is reserved for the worker.\n")
    signal = inbox / "candidate.md"
    signal.write_bytes(
        dump_document(
            signal_data(
                id="candidate",
                origin={
                    "workspace_id": "repo:orders",
                    "project_path": None,
                    "applicable_scopes": ["org:example", "repo:orders"],
                    "source_ids": ["knowledge"],
                },
            ),
            "# Candidate\n\nA pending observation for worker evaluation.\n",
        )
    )
    result = Consumer(config, registry, skill, signal, corpus, credentials)
    configure_trigger(result.workspace())
    return result


def prompt(case: Consumer, provider: str, *, profile: str | None = None) -> str:
    payload = (
        {"sessionId": "exact-parent-session", "transformedPrompt": "Keep my ordinary task."}
        if provider == "copilot"
        else {"session_id": "exact-parent-session", "hook_event_name": "UserPromptSubmit"}
    )
    payload["cwd"] = str(case.skill.parent)
    selection = (
        ["--config", str(case.config)]
        if profile is None
        else ["--settings", str(case.registry), "--profile", profile]
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_knowledge.entrypoints.hooks.runtime",
            "--provider",
            provider,
            *selection,
            "--compound-skill",
            str(case.skill),
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    context = (
        rendered["modifiedTransformedPrompt"]
        if provider == "copilot"
        else rendered["hookSpecificOutput"]["additionalContext"]
    )
    if provider == "copilot":
        assert context.startswith("Keep my ordinary task.\n\n")
    assert "Reflect and record useful observations" in context
    return context


@pytest.mark.parametrize("provider", PROVIDERS)
def test_prompt_due_then_active_and_completed_are_quiet(tmp_path: Path, provider: str) -> None:
    case = consumer(tmp_path)
    before = activity_path(case.workspace()).read_bytes()
    first = prompt(case, provider)
    assert "Local knowledge compounding is due" in first
    assert str(case.skill) in first
    assert f'"harness": "{provider}"' in first
    assert '"parent_session_id": "exact-parent-session"' in first
    assert "Main agent: use your harness's native subagent tool" in first
    assert "[agent-knowledge-compound-worker]" in first
    assert "Never launch a worker through shell/terminal model CLI processes" in first
    assert "Skip the main-agent paragraph below" in first
    assert "keep the original parent's handoff" in first
    assert "do not delegate another compound worker" in first
    assert "action:record-worker" in first
    assert "Prompt fallback has no automation_id; omit it" in first
    assert "automatic:true" in first and "started:false" in first
    # A reminder is not a reservation or completion record.
    assert activity_path(case.workspace()).read_bytes() == before
    assert prompt(case, provider) == first

    snapshot = SignalSnapshot(
        "candidate",
        str(case.signal),
        "sha256:" + hashlib.sha256(case.signal.read_bytes()).hexdigest(),
    )
    started = start_run(
        case.workspace(),
        workspace_id="repo:orders",
        selected=(snapshot,),
        harness=provider,
        session_id="exact-worker-session",
        automation_id=None,
        automatic=True,
        parent_session_id="exact-parent-session",
        worker_id="exact-worker-handle",
    )
    assert "Local knowledge compounding is due" not in prompt(case, provider)
    finish_run(
        case.workspace(),
        run_id=started.run_id,
        outcome="reviewed and retained",
        completion="deferred",
        dispositions=(
            SignalDisposition(
                "candidate",
                CompoundDecision.DEFER,
                "Publication prerequisite remains unavailable.",
                (OwnerReference("canonical.md", source="knowledge"),),
            ),
        ),
    )
    # Retaining the input after full evaluation does not launch on every prompt.
    assert case.signal.exists()
    assert "Local knowledge compounding is due" not in prompt(case, provider)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("mode", ["disabled", "manual", "local-schedule"])
def test_non_prompt_owners_leave_only_reflection(tmp_path: Path, provider: str, mode: str) -> None:
    case = consumer(tmp_path, mode=mode)
    assert "Local knowledge compounding is due" not in prompt(case, provider)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_empty_inbox_does_not_delay_a_later_signal(tmp_path: Path, provider: str) -> None:
    case = consumer(tmp_path)
    contents = case.signal.read_bytes()
    case.signal.unlink()
    assert "Local knowledge compounding is due" not in prompt(case, provider)
    case.signal.write_bytes(contents)
    assert "Local knowledge compounding is due" in prompt(case, provider)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("credential_state", ["missing", "blank"])
def test_unfinished_credentials_do_not_block_prompt_metadata(
    tmp_path: Path, provider: str, credential_state: str
) -> None:
    case = consumer(tmp_path)
    if credential_state == "blank":
        case.credentials.write_text("LOCAL_REPOSITORY_TOKEN=\n")
        case.credentials.chmod(0o600)
    context = prompt(case, provider, profile="primary")
    assert "Local knowledge compounding is due" in context
    assert "--profile primary" in context
    assert str(case.registry) in context
    assert str(case.credentials) not in context
    assert "LOCAL_REPOSITORY_TOKEN" not in context


@pytest.mark.parametrize("provider", PROVIDERS)
def test_malformed_coordination_leaves_request_and_reflection_usable(
    tmp_path: Path, provider: str
) -> None:
    case = consumer(tmp_path)
    log = activity_path(case.workspace())
    with log.open("ab") as stream:
        stream.write(b'{"incomplete":')
    before = log.read_bytes()
    assert "Local knowledge compounding is due" not in prompt(case, provider)
    assert log.read_bytes() == before


def test_equivalent_profile_aliases_share_trigger_but_keep_explicit_handoff(tmp_path: Path) -> None:
    case = consumer(tmp_path)
    before = activity_path(case.workspace()).read_bytes()
    for name in ("primary", "alias"):
        configure_trigger(case.workspace(name))
        context = compound_context(case.request(profile=name))
        assert context is not None and f"--profile {name}" in context
        assert str(case.registry) in context
    assert activity_path(case.workspace()).read_bytes() == before

    registry = json.loads(case.registry.read_text())
    registry["profiles"]["alias"]["overrides"] = {
        "setup": {
            "compounding": {"mode": "prompt", "owner": "competing-owner"},
        }
    }
    case.registry.write_text(json.dumps(registry))
    assert compound_context(case.request(profile="alias")) is None
    assert compound_context(case.request(profile="primary")) is not None
    assert activity_path(case.workspace()).read_bytes() == before


def test_marked_copilot_worker_restores_bound_selection_without_checking_due(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = consumer(tmp_path)
    before = activity_path(case.workspace()).read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("An assigned worker must not consult advisory due state again.")

    monkeypatch.setattr(compound_store, "compound_due", forbidden)
    request = {**case.request("copilot", "primary"), "worker": True, "session_id": "native-child"}
    context = compound_context(request)
    prefix = shlex.join(
        [
            str(Path(sys.executable).parent / "agent-knowledge"),
            "--settings",
            str(case.registry),
            "--profile",
            "primary",
        ]
    )
    assert context is not None
    assert prefix in context
    assert str(case.skill) in context
    assert 'worker_id is "native-child"' in context
    assert "parent_session_id from the original parent assignment" in context
    assert "Local knowledge compounding is due" not in context
    assert "automatic:true" in context and "started:false" in context
    assert activity_path(case.workspace()).read_bytes() == before
    for provider in ("codex", "claude"):
        with pytest.raises(ValueError, match="Unsupported provider worker identity"):
            compound_context({**request, "provider": provider})


@pytest.mark.parametrize("worker", [False, True])
def test_due_probe_reads_no_corpus_signal_skill_or_credential_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker: bool
) -> None:
    case = consumer(tmp_path)
    # Malformed bodies still count as potential files; semantic evaluation is the worker's job.
    case.signal.write_text("Malformed metadata: worker must evaluate and retain this input.\n")
    case.credentials.write_text("LOCAL_REPOSITORY_TOKEN=\n")
    prohibited = {p.name for p in (case.signal, case.corpus, case.skill, case.credentials)}
    original_open = os.open
    original_file_open = builtins.open
    original_io_open = io.open

    def guarded_open(path, flags, *args, **kwargs):
        if not flags & os.O_DIRECTORY and Path(path).name in prohibited:
            pytest.fail("Prompt-time due check attempted a body or credential read.")
        return original_open(path, flags, *args, **kwargs)

    def guarded_file_open(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path).name in prohibited:
            pytest.fail("Prompt-time due check attempted a Python body or credential read.")
        return original_file_open(path, *args, **kwargs)

    def guarded_io_open(path, *args, **kwargs):
        if not isinstance(path, int) and Path(path).name in prohibited:
            pytest.fail("Prompt-time due check attempted a pathlib body or credential read.")
        return original_io_open(path, *args, **kwargs)

    def no_environment_read(*args, **kwargs):
        pytest.fail("Prompt-time due check must not activate or inspect credential values.")

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(builtins, "open", guarded_file_open)
    monkeypatch.setattr(io, "open", guarded_io_open)
    monkeypatch.setattr(environment, "_read_private_file", no_environment_read)
    assert compound_context({**case.request("copilot", "primary"), "worker": worker}) is not None


@pytest.mark.parametrize("provider", PROVIDERS)
def test_missing_skill_keeps_discovery_contract_and_does_not_claim_work(
    tmp_path: Path, provider: str
) -> None:
    case = consumer(tmp_path)
    before = activity_path(case.workspace()).read_bytes()
    case.skill.unlink()
    assert "Local knowledge compounding is due" not in prompt(case, provider)
    assert activity_path(case.workspace()).read_bytes() == before
