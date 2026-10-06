"""Parser regressions use anonymized Copilot event shapes, not live proof."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tests/e2e/copilot_compounding_evidence.py"
SKILL = Path("/work/consumer/apm_modules/pack/.apm/skills/knowledge-compound/SKILL.md")
PREFIX = [
    "/work/consumer/.agent-knowledge-venv/bin/agent-knowledge",
    "--settings",
    "/work/consumer/profiles.yaml",
    "--profile",
    "example",
]
SESSION = "d4ee9f6c-a51e-4ec3-9273-15eacb728bc9"
WORKER = "04078d23-aca7-44d2-ba0c-957521cd9404"
SPAWN = "call_spawn"
RUN = "compound-fixture"


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("copilot_compound_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def call(identifier, tool, arguments):
    return {
        "type": "tool.execution_start",
        "agentId": WORKER,
        "id": identifier + "-event",
        "data": {
            "toolCallId": identifier,
            "toolName": tool,
            "arguments": arguments,
            "parentToolCallId": SPAWN,
        },
    }


def result(identifier, content, *, shell=False):
    data = {
        "toolCallId": identifier,
        "parentToolCallId": SPAWN,
        "success": True,
        "result": {"content": content, "detailedContent": content},
    }
    if shell:
        data["shellExecution"] = {"exitCode": 0}
    return {"type": "tool.execution_complete", "agentId": WORKER, "data": data}


def trace():
    identity = {
        "run_id": RUN,
        "worker_id": WORKER,
        "parent_session_id": SESSION,
        "harness": "copilot",
    }
    events = [
        {
            "type": "tool.execution_start",
            "id": "dispatch-event",
            "data": {
                "toolCallId": SPAWN,
                "toolName": "task",
                "arguments": {
                    "prompt": f"[agent-knowledge-compound-worker] Load {SKILL}. "
                    f"Use {' '.join(PREFIX)}. Parent {SESSION}."
                },
            },
        },
        {
            "type": "subagent.started",
            "agentId": WORKER,
            "id": "native-started",
            "parentId": "dispatch-event",
            "data": {"toolCallId": SPAWN, "executionMode": "background"},
        },
        call("read", "view", {"path": str(SKILL), "view_range": [1, 180]}),
        result("read", "1. ---\n2. name: knowledge-compound\n3. Follow the worker procedure."),
    ]
    for action in ("start", "finish"):
        response = {
            "status": "ok",
            "action": action,
            "run_id": RUN,
            "started": True,
            "completion": "completed",
            "selection": {"mode": "profile", "profile": "example", "settings_path": PREFIX[2]},
        }
        events.extend(
            [
                call(
                    action,
                    "bash",
                    {
                        "command": f"{' '.join(PREFIX)} compound --request-file - <<'YAML'\n"
                        f"action: {action}\nYAML"
                    },
                ),
                result(
                    action,
                    json.dumps(response) + "\n<shellId: 1 completed with exit code 0>",
                    shell=True,
                ),
            ]
        )
    handed = events[0]["data"]["arguments"]["prompt"]
    events.append(
        {
            "type": "user.message",
            "id": "native-child-prompt",
            "agentId": WORKER,
            "data": {
                "content": handed,
                "transformedContent": handed + "\nReflect and record useful observations\n"
                "Provider harness (copy exactly into origin.harness "
                "for a harness-origin signal): copilot\n"
                "Provider session ID (copy exactly into origin.session_id "
                "for a harness-origin signal): " + WORKER,
            },
        }
    )
    return events, identity


def verify(driver, events, identity):
    return driver.copilot_worker_evidence(
        events, identity, skill=SKILL, prefix=PREFIX, session_id=SESSION
    )


def test_native_copilot_dispatch_correlates_actual_direct_child_lifecycle(driver):
    events, identity = trace()
    original = deepcopy((events, identity))
    result = verify(driver, events, identity)
    assert result["status"] == "passed"
    assert result["worker_id"] == WORKER
    assert result["native_subagent_event_id"] == "native-started"
    assert result["spawn_tool_call_id"] == SPAWN
    assert result["skill_read_tool_call_ids"] == ["read"]
    assert result["lifecycle_tool_call_ids"] == {"start": "start", "finish": "finish"}
    assert (events, identity) == original


@pytest.mark.parametrize(
    "change", ["missing-worker", "wrong-parent", "wrong-provider", "grandchild"]
)
def test_identity_cannot_be_inferred_or_borrowed_from_ancestor(driver, change):
    events, identity = trace()
    if change == "missing-worker":
        identity.pop("worker_id")
    elif change == "wrong-parent":
        identity["parent_session_id"] = WORKER
    elif change == "wrong-provider":
        identity["harness"] = "claude"
    else:
        events[1]["data"]["parentId"] = "other-native-worker"
    with pytest.raises(ValueError):
        verify(driver, events, identity)


@pytest.mark.parametrize("field", ["agentId", "parentToolCallId"])
def test_other_child_or_parent_execution_cannot_complete_worker_proof(driver, field):
    events, identity = trace()
    for event in events[2:]:
        if field == "agentId":
            event["agentId"] = "another-worker"
        else:
            event["data"]["parentToolCallId"] = "another-spawn"
    with pytest.raises(ValueError, match="skill body read"):
        verify(driver, events, identity)


def test_inherited_reminder_cannot_authorize_recursive_compounding(driver):
    events, identity = trace()
    events.insert(2, call("nested-task", "task", {"prompt": f"Perform compounding; load {SKILL}."}))
    with pytest.raises(ValueError, match="recursively delegated"):
        verify(driver, events, identity)


@pytest.mark.parametrize(
    "change", ["no-native-start", "wrong-call", "wrong-event", "child-dispatch"]
)
def test_native_id_must_link_to_real_main_task_dispatch(driver, change):
    events, identity = trace()
    if change == "no-native-start":
        events.pop(1)
    elif change == "wrong-call":
        events[1]["data"]["toolCallId"] = "unrelated-call"
    elif change == "wrong-event":
        events[1]["parentId"] = "unrelated-event"
    else:
        events[0]["agentId"] = "ancestor-worker"
    with pytest.raises(ValueError):
        verify(driver, events, identity)


@pytest.mark.parametrize("change", ["skill", "selector", "parent", "profile-prefix"])
def test_exact_handoff_must_reach_native_worker(driver, change):
    events, identity = trace()
    args = events[0]["data"]["arguments"]
    if change == "skill":
        args["prompt"] = args["prompt"].replace(str(SKILL), "/work/different/SKILL.md")
    elif change == "selector":
        args["prompt"] = args["prompt"].replace(PREFIX[2], "/work/different/profiles.yaml")
    elif change == "parent":
        args["prompt"] = args["prompt"].replace(SESSION, "different-session")
    else:
        args["prompt"] = args["prompt"].replace("--profile example", "--profile example-other")
    with pytest.raises(ValueError, match="exact skill, selector and parent"):
        verify(driver, events, identity)


@pytest.mark.parametrize("change", ["refused", "error", "wrong-path", "late-read"])
def test_view_metadata_success_is_not_always_a_skill_body_read(driver, change):
    events, identity = trace()
    if change == "refused":
        events[3]["data"]["result"]["content"] = "File too large to read at once."
        events[3]["data"]["toolTelemetry"] = {"properties": {"largeOutputAvoided": "true"}}
    elif change == "error":
        events[3]["data"]["success"] = False
    elif change == "wrong-path":
        events[2]["data"]["arguments"]["path"] = "/work/unrelated/SKILL.md"
    else:
        read = events[2:4]
        del events[2:4]
        events.extend(read)
    with pytest.raises(ValueError):
        verify(driver, events, identity)


@pytest.mark.parametrize("action", ["start", "finish"])
@pytest.mark.parametrize("change", ["command", "run", "profile", "exit", "completion-event"])
def test_both_actual_child_cli_operations_are_required(driver, action, change):
    events, identity = trace()
    called = next(
        e
        for e in events
        if e.get("type") == "tool.execution_start" and e["data"].get("toolCallId") == action
    )
    returned = next(
        e
        for e in events
        if e.get("type") == "tool.execution_complete" and e["data"].get("toolCallId") == action
    )
    if change == "command":
        called["data"]["arguments"]["command"] = "echo claimed-compounding"
    elif change == "exit":
        returned["data"]["shellExecution"]["exitCode"] = 2
    elif change == "completion-event":
        events.remove(returned)
    else:
        value = json.loads(returned["data"]["result"]["content"].splitlines()[0])
        if change == "run":
            value["run_id"] = "compound-other"
        else:
            value["selection"]["profile"] = "other"
        returned["data"]["result"]["content"] = json.dumps(value)
    with pytest.raises(ValueError, match="selected successful start/finish"):
        verify(driver, events, identity)


@pytest.mark.parametrize(
    "change",
    ["marker", "prompt-missing", "wrong-child", "reflection", "session", "delegation", "due"],
)
def test_native_child_hook_preserves_reflection_without_redelegation(driver, change):
    events, identity = trace()
    message = next(event for event in events if event.get("type") == "user.message")
    if change == "marker":
        args = events[0]["data"]["arguments"]
        args["prompt"] = args["prompt"].replace("[agent-knowledge-compound-worker]", "")
    elif change == "prompt-missing":
        events.remove(message)
    elif change == "wrong-child":
        message["agentId"] = "another-child"
    elif change == "reflection":
        message["data"]["transformedContent"] = message["data"]["content"]
    elif change == "session":
        message["data"]["transformedContent"] = message["data"]["transformedContent"].replace(
            WORKER, SESSION
        )
    else:
        message["data"]["transformedContent"] += (
            "\nLocal knowledge compounding is due."
            if change == "due"
            else "\nMain agent: delegate one subagent."
        )
    with pytest.raises(ValueError):
        verify(driver, events, identity)


def bound_context():
    return (
        "\nBound compounding worker context (Copilot):\n"
        "You are already the native compounding worker. Load "
        + json.dumps(str(SKILL))
        + ". Your native worker_id is "
        + json.dumps(WORKER)
        + ", exposed by this child prompt hook. "
        "Use this exact prefix for every configured call: "
        + " ".join(PREFIX)
        + ". For describe only, use "
        + PREFIX[0]
        + " describe without selectors. Preserve the parent's consumer instructions."
    )


def set_handoff(events, handoff):
    original = events[0]["data"]["arguments"]["prompt"]
    events[0]["data"]["arguments"]["prompt"] = handoff
    message = next(event for event in events if event.get("type") == "user.message")
    message["data"]["content"] = handoff
    message["data"]["transformedContent"] = message["data"]["transformedContent"].replace(
        original, handoff
    )
    return message


@pytest.mark.parametrize("omit", ["none", "skill", "prefix", "both"])
def test_actual_child_binding_can_deliver_missing_parent_routes(driver, omit):
    events, identity = trace()
    handoff = events[0]["data"]["arguments"]["prompt"]
    if omit in {"skill", "both"}:
        handoff = handoff.replace(f"Load {SKILL}.", "Perform compounding.")
    if omit in {"prefix", "both"}:
        handoff = handoff.replace(f"Use {' '.join(PREFIX)}.", "Use the bound route.")
    message = set_handoff(events, handoff)
    message["data"]["transformedContent"] += bound_context()
    result = verify(driver, events, identity)
    assert result["bound_worker_id_verified"] is True
    assert result["skill_selector_transport"] == (
        "native-parent-handoff-and-child-binding" if omit == "none" else "native-child-binding"
    )


@pytest.mark.parametrize("change", ["worker", "skill", "launcher", "settings", "profile", "absent"])
def test_child_binding_must_supply_exact_identity_and_route(driver, change):
    events, identity = trace()
    message = set_handoff(events, f"[agent-knowledge-compound-worker] Parent {SESSION}.")
    bound = bound_context()
    substitutions = {
        "worker": (WORKER, SESSION),
        "skill": (str(SKILL), "/wrong/SKILL.md"),
        "launcher": (PREFIX[0], "/wrong/bin/agent-knowledge"),
        "settings": (PREFIX[2], "/wrong/registry.yaml"),
        "profile": ("--profile example", "--profile other"),
    }
    if change != "absent":
        bound = bound.replace(*substitutions[change])
        message["data"]["transformedContent"] += bound
    with pytest.raises(ValueError):
        verify(driver, events, identity)


@pytest.mark.parametrize("change", ["skill", "launcher", "settings", "profile", "parent", "marker"])
def test_valid_child_binding_cannot_override_conflicting_parent_handoff(driver, change):
    events, identity = trace()
    handoff = events[0]["data"]["arguments"]["prompt"]
    substitutions = {
        "skill": (str(SKILL), "/wrong/SKILL.md"),
        "launcher": (PREFIX[0], "/wrong/bin/agent-knowledge"),
        "settings": (PREFIX[2], "/wrong/registry.yaml"),
        "profile": ("--profile example", "--profile other"),
        "parent": (SESSION, "another-parent"),
        "marker": ("[agent-knowledge-compound-worker]", ""),
    }
    message = set_handoff(events, handoff.replace(*substitutions[change]))
    message["data"]["transformedContent"] += bound_context()
    with pytest.raises(ValueError):
        verify(driver, events, identity)
