"""Synthetic regressions for shapes observed in the native Codex proof."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "e2e/codex_compounding_evidence.py"
PARENT = "parent-native"
CHILD = "child-native"
WORKER = "/root/compound"
RUN = "compound-native"
TIME = "2026-10-06T10:00:00Z"


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("codex_evidence_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


def event(ordinal, payload, kind="response_item"):
    return {"ordinal": ordinal, "timestamp": TIME, "type": kind, "payload": payload}


def trace(tmp_path):
    skill = tmp_path / "pack/.apm/skills/knowledge-compound/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Installed compound skill\nFollow the delegated worker procedure.\n")
    prefix = [
        str(tmp_path / "venv/bin/agent-knowledge"),
        "--settings",
        str(tmp_path / "registry.yaml"),
        "--profile",
        "example",
    ]
    parent_meta = {"id": PARENT, "cwd": str(tmp_path), "timestamp": TIME}
    child_meta = {
        "id": CHILD,
        "cwd": str(tmp_path),
        "timestamp": TIME,
        "parent_thread_id": PARENT,
        "forked_from_id": PARENT,
        "agent_path": WORKER,
        "subagent_history_start_ordinal": 10,
        "source": {
            "subagent": {"thread_spawn": {"parent_thread_id": PARENT, "agent_path": WORKER}}
        },
    }
    parent = [
        event(0, parent_meta, "session_meta"),
        event(
            1,
            {
                "type": "function_call",
                "namespace": "collaboration",
                "name": "spawn_agent",
                "call_id": "spawn",
                "arguments": "provider-encrypted",
            },
        ),
        event(
            2,
            {
                "type": "function_call_output",
                "call_id": "spawn",
                "output": json.dumps({"task_name": WORKER}),
            },
        ),
    ]
    child = [event(0, child_meta, "session_meta"), event(1, parent_meta, "session_meta")]
    commands = [("read", "cat " + str(skill), skill.read_text())]
    for action in ("start", "finish"):
        returned = {
            "status": "ok",
            "action": action,
            "run_id": RUN,
            "started": True,
            "completion": "completed",
            "selection": {"mode": "profile", "profile": "example", "settings_path": prefix[2]},
        }
        commands.append(
            (action, " ".join(prefix) + " compound --request-file -", json.dumps(returned))
        )
    for index, (identifier, command, output) in enumerate(commands):
        child.extend(
            [
                event(
                    10 + index * 2,
                    {
                        "type": "custom_tool_call",
                        "name": "exec",
                        "call_id": identifier,
                        "input": "text(await tools.exec_command({cmd:"
                        + json.dumps(command)
                        + "}));",
                    },
                ),
                event(
                    11 + index * 2,
                    {
                        "type": "custom_tool_call_output",
                        "call_id": identifier,
                        "output": [
                            {
                                "type": "input_text",
                                "text": json.dumps({"exit_code": 0, "output": output}),
                            }
                        ],
                    },
                ),
            ]
        )
    identity = {"worker_id": WORKER, "run_id": RUN}
    return parent, child, identity, skill, prefix


def verify(module, values):
    parent, child, identity, skill, prefix = values
    return module.codex_worker_evidence(
        parent, child, identity, skill=skill, prefix=prefix, session_id=PARENT
    )


def test_correlates_native_identity_and_child_execution(module, tmp_path):
    values = trace(tmp_path)
    before = deepcopy(values[:3])
    result = verify(module, values)
    assert result["status"] == "passed"
    assert result["child_thread_id"] == CHILD
    assert result["worker_id"] == WORKER
    assert result["lifecycle_call_ids"] == {"start": "start", "finish": "finish"}
    assert "encrypted" in result["handoff_text"]
    assert values[:3] == before


@pytest.mark.parametrize("field", ["agent_path", "parent_thread_id", "forked_from_id", "cwd"])
def test_wrong_child_metadata_cannot_substitute(module, tmp_path, field):
    values = trace(tmp_path)
    values[1][0]["payload"][field] = "unrelated"
    with pytest.raises(Exception, match="not linked"):
        verify(module, values)


def test_unrelated_spawn_result_cannot_substitute(module, tmp_path):
    values = trace(tmp_path)
    values[0][2]["payload"]["output"] = json.dumps({"task_name": "/root/other"})
    with pytest.raises(Exception, match="spawn result"):
        verify(module, values)


def test_inherited_parent_tools_do_not_count_as_child_execution(module, tmp_path):
    values = trace(tmp_path)
    values[1][0]["payload"]["subagent_history_start_ordinal"] = 100
    with pytest.raises(Exception, match="own successful"):
        verify(module, values)


@pytest.mark.parametrize(
    "change",
    [
        "missing-read",
        "failed-read",
        "wrong-body",
        "wrong-selection",
        "wrong-run",
        "parent-only",
        "wrong-executable",
    ],
)
def test_requires_actual_child_read_and_matching_successful_lifecycle(module, tmp_path, change):
    values = trace(tmp_path)
    child = values[1]
    if change == "missing-read":
        del child[2:4]
    elif change == "failed-read":
        child[3]["payload"]["output"][0]["text"] = json.dumps(
            {"exit_code": 1, "output": values[3].read_text()}
        )
    elif change == "wrong-body":
        child[3]["payload"]["output"][0]["text"] = json.dumps(
            {"exit_code": 0, "output": "Skill mentioned but not read."}
        )
    elif change == "parent-only":
        values[0].extend(child[2:])
        del child[2:]
    elif change == "wrong-executable":
        child[4]["payload"]["input"] = child[4]["payload"]["input"].replace(values[4][0], "echo")
    else:
        wrapper = json.loads(child[5]["payload"]["output"][0]["text"])
        result = json.loads(wrapper["output"])
        if change == "wrong-selection":
            result["selection"]["profile"] = "another"
        else:
            result["run_id"] = "compound-another"
        wrapper["output"] = json.dumps(result)
        child[5]["payload"]["output"][0]["text"] = json.dumps(wrapper)
    with pytest.raises(Exception, match="own successful"):
        verify(module, values)


@pytest.mark.parametrize("placement", ["parent", "child"])
def test_shell_model_worker_is_rejected_even_with_native_trace(module, tmp_path, placement):
    values = trace(tmp_path)
    target = values[0] if placement == "parent" else values[1]
    target.append(
        event(
            30,
            {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "shell-worker",
                "input": 'text(await tools.exec_command({cmd:"codex exec do-work"}));',
            },
        )
    )
    with pytest.raises(ValueError, match="native subagent"):
        verify(module, values)


def test_repeat_prompt_counts_only_new_native_spawns(module, tmp_path):
    parent = trace(tmp_path)[0]
    assert len(module.codex_spawn_calls(parent)) == 1
    assert not module.codex_spawn_calls(parent, after_ordinal=2)
    parent.append(
        event(
            20,
            {
                "type": "function_call",
                "namespace": "collaboration",
                "name": "spawn_agent",
                "call_id": "extra",
            },
        )
    )
    assert len(module.codex_spawn_calls(parent, after_ordinal=2)) == 1


@pytest.mark.parametrize(
    "settings", ["$PWD/registry.yaml", "${PWD}/registry.yaml", "registry.yaml"]
)
def test_relative_launcher_and_pwd_registry_resolve_from_native_cwd(module, tmp_path, settings):
    values = trace(tmp_path)
    for index in (4, 6):
        command = (
            f'venv/bin/agent-knowledge --settings "{settings}" '
            "--profile example compound --request-file -"
        )
        values[1][index]["payload"]["input"] = (
            "text(await tools.exec_command({cmd:" + json.dumps(command) + "}));"
        )
    assert verify(module, values)["status"] == "passed"


@pytest.mark.parametrize("change", ["settings", "launcher", "variable", "workdir"])
def test_relative_commands_cannot_borrow_another_launcher_or_registry(module, tmp_path, change):
    values = trace(tmp_path)
    command = (
        'venv/bin/agent-knowledge --settings "$PWD/registry.yaml" '
        "--profile example compound --request-file -"
    )
    suffix = ""
    if change == "settings":
        command = command.replace("registry.yaml", "other.yaml")
    elif change == "launcher":
        command = command.replace("venv/bin/", "other/bin/")
    elif change == "variable":
        command = command.replace("$PWD", "$SOMEWHERE")
    else:
        suffix = ',workdir:"/unrelated"'
    values[1][4]["payload"]["input"] = (
        "text(await tools.exec_command({cmd:" + json.dumps(command) + suffix + "}));"
    )
    with pytest.raises(Exception, match="own successful"):
        verify(module, values)
