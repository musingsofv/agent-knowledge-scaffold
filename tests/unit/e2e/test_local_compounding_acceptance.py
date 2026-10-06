"""Test the verifier against anonymized shapes observed in Claude stream JSON.

These synthetic parser cases are not live-provider evidence. Unknown provider
formats must fail closed until actual native traces establish their correlation.
"""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tests/e2e/local_compounding_acceptance.py"
SKILL = Path("/work/consumer/apm_modules/pack/.apm/skills/knowledge-compound/SKILL.md")
PREFIX = [
    "/work/consumer/.agent-knowledge-venv/bin/agent-knowledge",
    "--settings",
    "/work/consumer/local-profiles.yaml",
    "--profile",
    "example",
]
SESSION = "fixture-parent-session"
WORKER = "a123456789abcdef"
RUN = "compound-fixture"
SPAWN = "toolu_fixture_spawn"


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("local_compounding_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def call(identifier, name, arguments, *, parent=SPAWN):
    return {
        "type": "assistant",
        "session_id": SESSION,
        "parent_tool_use_id": parent,
        "message": {
            "content": [{"type": "tool_use", "id": identifier, "name": name, "input": arguments}]
        },
    }


def result(identifier, content, *, parent=SPAWN, native=None, is_error=False):
    event = {
        "type": "user",
        "session_id": SESSION,
        "parent_tool_use_id": parent,
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": identifier,
                    "content": content,
                    "is_error": is_error,
                }
            ]
        },
    }
    if native is not None:
        event["tool_use_result"] = native
    return event


def trace(*, late_worker=False):
    selection = {"mode": "profile", "profile": "example", "settings_path": PREFIX[2]}
    start = {
        "event": "start",
        "run_id": RUN,
        "automatic": True,
        "harness": "claude",
        "parent_session_id": SESSION,
    }
    if not late_worker:
        start["worker_id"] = WORKER
    finish = {**start, "event": "end", "completion": "completed"}
    activity = {"active": False, "events": [start, finish]}
    if late_worker:
        activity["events"].append(
            {"event": "worker", "run_id": RUN, "worker_id": WORKER, "harness": "claude"}
        )
    events = [
        call(
            SPAWN,
            "Agent",
            {
                "prompt": f"[agent-knowledge-compound-worker] Load {SKILL}; "
                f"run {' '.join(PREFIX)}. Parent: {SESSION}."
            },
            parent=None,
        ),
        result(SPAWN, "Native result", parent=None, native={"agentId": WORKER}),
        call("read", "Read", {"file_path": str(SKILL)}),
        result("read", "# Installed compound skill\nFollow the delegated worker procedure."),
    ]
    for action in ("start", "finish"):
        returned = {
            "status": "ok",
            "action": action,
            "run_id": RUN,
            "selection": selection,
            "started": True,
            "completion": "completed",
        }
        events.extend(
            [
                call(
                    action,
                    "Bash",
                    {
                        "command": f"{' '.join(PREFIX)} compound --request-file - <<'YAML'\n"
                        f"action: {action}\nYAML"
                    },
                ),
                result(action, json.dumps(returned)),
            ]
        )
    return events, activity


def verify(driver, events, activity, provider="claude"):
    return driver._delegation_evidence(
        provider, events, activity, skill=SKILL, prefix=PREFIX, session_id=SESSION
    )


@pytest.mark.parametrize("late_worker", [False, True])
def test_claude_native_handle_correlates_to_actual_child_lifecycle(driver, late_worker):
    events, activity = trace(late_worker=late_worker)
    evidence = verify(driver, events, activity)
    assert evidence["status"] == "passed"
    assert evidence["worker_id"] == WORKER
    assert evidence["run_id"] == RUN
    assert evidence["spawn_tool_use_id"] == SPAWN
    assert evidence["lifecycle_tool_use_ids"] == {"start": "start", "finish": "finish"}
    assert evidence["skill_read_tool_use_ids"] == ["read"]


@pytest.mark.parametrize("provider", ["codex", "copilot"])
def test_unobserved_native_child_format_cannot_pass_from_generic_spawn(driver, provider):
    events, activity = trace()
    evidence = verify(driver, events, activity, provider)
    assert evidence["status"] == "failed"
    assert "identity" in evidence["reason"].lower() or "provider" in evidence["reason"].lower()


@pytest.mark.parametrize("what", ["native-handle", "recorded-handle", "late-conflict"])
def test_missing_or_conflicting_worker_identity_fails(driver, what):
    events, activity = trace()
    if what == "native-handle":
        events[1].pop("tool_use_result")
    elif what == "recorded-handle":
        for record in activity["events"]:
            record.pop("worker_id")
    else:
        activity["events"].append(
            {"event": "worker", "run_id": RUN, "worker_id": "different-native-worker"}
        )
    assert verify(driver, events, activity)["status"] == "failed"


@pytest.mark.parametrize("scope", ["parent", "different-child"])
def test_unrelated_spawn_cannot_claim_parent_or_other_child_compounding(driver, scope):
    events, activity = trace()
    for event in events[2:]:
        event["parent_tool_use_id"] = None if scope == "parent" else "toolu_other_spawn"
    evidence = verify(driver, events, activity)
    assert evidence["status"] == "failed"
    assert "successful read" in evidence["reason"]


@pytest.mark.parametrize("change", ["skill", "selector", "parent", "profile-prefix"])
def test_matching_child_needs_exact_handoff(driver, change):
    events, activity = trace()
    handed = events[0]["message"]["content"][0]["input"]
    if change == "skill":
        handed["prompt"] = handed["prompt"].replace(str(SKILL), "/work/other/SKILL.md")
    elif change == "selector":
        handed["prompt"] = handed["prompt"].replace(PREFIX[2], "/work/other/registry.yaml")
    elif change == "profile-prefix":
        handed["prompt"] = handed["prompt"].replace("--profile example", "--profile example-two")
    else:
        handed["prompt"] = handed["prompt"].replace(SESSION, "different-parent")
    assert verify(driver, events, activity)["status"] == "failed"


@pytest.mark.parametrize("change", ["absent", "error", "wrong-file", "after-start"])
def test_handoff_text_alone_does_not_prove_child_loaded_skill(driver, change):
    events, activity = trace()
    if change == "absent":
        del events[2:4]
    elif change == "error":
        events[3]["message"]["content"][0]["is_error"] = True
    elif change == "wrong-file":
        events[2]["message"]["content"][0]["input"]["file_path"] = "/work/other/SKILL.md"
    else:
        read = events[2:4]
        del events[2:4]
        events.extend(read)
    assert verify(driver, events, activity)["status"] == "failed"


@pytest.mark.parametrize("action", ["start", "finish"])
@pytest.mark.parametrize("change", ["missing", "failed", "different-run", "wrong-selection"])
def test_child_must_execute_both_successful_actions_for_exact_run(driver, action, change):
    events, activity = trace()
    target = next(
        event
        for event in events
        if event["type"] == "user" and event["message"]["content"][0]["tool_use_id"] == action
    )
    if change == "missing":
        events.remove(target)
    else:
        content = target["message"]["content"][0]
        returned = json.loads(content["content"])
        if change == "failed":
            returned["status"] = "error"
        elif change == "different-run":
            returned["run_id"] = "compound-unrelated"
        else:
            returned["selection"]["profile"] = "other"
        content["content"] = json.dumps(returned)
    assert verify(driver, events, activity)["status"] == "failed"


def test_prompt_trigger_owner_cannot_be_fabricated_automation_identity(driver):
    events, activity = trace()
    for record in activity["events"]:
        record["automation_id"] = "agent-knowledge-compound:workspace:example"
    evidence = verify(driver, events, activity)
    assert evidence["status"] == "failed"
    assert "fabricated" in evidence["reason"]


def test_unrelated_worker_event_does_not_supply_missing_run_identity(driver):
    events, activity = trace(late_worker=True)
    activity["events"][-1]["run_id"] = "compound-other"
    assert verify(driver, events, activity)["status"] == "failed"


def test_input_trace_is_not_rewritten_to_manufacture_evidence(driver):
    events, activity = trace(late_worker=True)
    original = deepcopy((events, activity))
    assert verify(driver, events, activity)["status"] == "passed"
    assert (events, activity) == original


def test_fixture_evidence_exists_and_boundary_allows_only_owning_source_reads(tmp_path, driver):
    evidence = driver._write_observation_evidence(tmp_path, "claude")
    assert evidence == tmp_path / "docs/r8-claude-observation.md"
    assert evidence.is_file()
    for first in (True, False):
        prompt = driver._fixture_prompt(first=first)
        assert "Write only inside this disposable checkout" in prompt
        assert "verified owning sources" in prompt
        assert "do not write outside it" in prompt
        assert "Do not publish, access network services or modify canonical knowledge" in prompt


def test_codex_trust_override_is_one_top_level_toml_table(driver):
    import tomllib

    consumer = Path("/tmp/isolated.checkout with space/consumer")
    args = driver._codex_hook_overrides(consumer)
    parsed = tomllib.loads(args[1])
    assert parsed == {"projects": {str(consumer): {"trust_level": "trusted"}}}
    assert args[2:] == ["-c", "features.hooks=true"]


def test_codex_wait_is_not_a_spawn_event(driver):
    assert (
        driver._spawn_evidence(
            [
                {
                    "type": "item.completed",
                    "item": {
                        "type": "collab_tool_call",
                        "tool": "wait",
                        "status": "completed",
                    },
                }
            ]
        )
        == []
    )


def test_claude_native_handoff_requires_exact_worker_marker(driver):
    events, activity = trace()
    handed = events[0]["message"]["content"][0]["input"]
    handed["prompt"] = handed["prompt"].replace("[agent-knowledge-compound-worker]", "")
    evidence = verify(driver, events, activity)
    assert evidence["status"] == "failed"
    assert "exact worker marker" in evidence["reason"]


@pytest.mark.parametrize(
    "arguments,diagnostic",
    [
        (["context"], "default-profile-required"),
        (["--profile", "unrelated", "context"], "unknown-profile"),
    ],
)
def test_probe_environment_cannot_fall_back_to_unrelated_user_profiles(
    driver, monkeypatch, tmp_path, capsys, arguments, diagnostic
):
    from agent_knowledge.entrypoints.cli.main import main

    ambient = tmp_path / "user"
    ambient_registry = ambient / ".config/agent-knowledge/config.yaml"
    ambient_registry.parent.mkdir(parents=True)
    ambient_registry.write_text(
        "schema_version: knowledge-profiles.v1\n"
        "default_profile: unrelated\n"
        "profiles:\n  unrelated:\n    config: unrelated-workspace.yaml\n"
    )
    original_ambient = ambient_registry.read_bytes()
    registry = tmp_path / "consumer/local-profiles.yaml"
    registry.parent.mkdir()
    registry.write_text(
        "schema_version: knowledge-profiles.v1\n"
        "profiles:\n  example:\n    config: knowledge-workspace.yaml\n"
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: ambient))
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", str(ambient_registry))
    launcher = registry.parent / ".agent-knowledge-venv/bin/agent-knowledge"
    environment = driver._fixture_environment(launcher, registry)
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", environment["AGENT_KNOWLEDGE_SETTINGS"])
    assert main(["profiles", "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["settings_path"] == str(registry)
    assert [profile["name"] for profile in listing["profiles"]] == ["example"]
    assert listing["default_profile"] is None
    assert main(arguments) == 2
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["diagnostics"][0]["code"] == diagnostic
    assert rejected["selection"]["settings_path"] == str(registry)
    assert ambient_registry.read_bytes() == original_ambient


def test_fixture_environment_keeps_provider_auth_and_launcher_path(driver, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", "/unrelated/registry.yaml")
    monkeypatch.setenv("AGENT_KNOWLEDGE_OTHER", "ambient-workspace")
    monkeypatch.setenv("KNOWLEDGE_CONFIG", "/unrelated/workspace.yaml")
    monkeypatch.setenv("PYTHONPATH", "/unrelated/module")
    monkeypatch.setenv("PATH", "/provider/bin")
    monkeypatch.setenv("PROVIDER_AUTH_TEST_SELECTOR", "provider-owned")
    launcher = tmp_path / "venv/bin/agent-knowledge"
    registry = tmp_path / "registry.yaml"
    environment = driver._fixture_environment(launcher, registry)
    assert environment["AGENT_KNOWLEDGE_SETTINGS"] == str(registry)
    assert environment["PATH"].split(":") == [str(launcher.parent), "/provider/bin"]
    assert environment["PROVIDER_AUTH_TEST_SELECTOR"] == "provider-owned"
    assert not {"AGENT_KNOWLEDGE_OTHER", "KNOWLEDGE_CONFIG", "PYTHONPATH"} & environment.keys()
