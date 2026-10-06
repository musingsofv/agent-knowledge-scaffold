"""Safety and evidence regressions; synthetic events are never native proof."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "tests/e2e/container_launch_acceptance.py"


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("container_launch_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_clean_parent_removes_profiles_mapping_and_conflicting_service_credentials(driver):
    parent = {
        "HOME": "/fixture/home",
        "PATH": "/fixture/bin",
        "OPENAI_API_KEY": "synthetic",
        "AGENT_KNOWLEDGE_SETTINGS": "/other/registry",
        "KNOWLEDGE_ROOT": "/other/root",
        "GH_TOKEN": "unrelated",
        "GITHUB_TOKEN": "unrelated",
        "PYTHONPATH": "/other",
        driver.TARGET_VARIABLE: "ambient",
        driver.SOURCE_VARIABLE: "ambient",
    }
    clean = driver.clean_parent_environment(parent)
    assert clean == {"HOME": "/fixture/home", "PATH": "/fixture/bin", "OPENAI_API_KEY": "synthetic"}
    assert parent[driver.TARGET_VARIABLE] == "ambient"


@pytest.mark.parametrize(
    "route",
    [
        "copilot:GH_TOKEN",
        "copilot:GITHUB_TOKEN",
        "codex:GH_TOKEN",
        "claude:OPENAI_API_KEY",
        "codex:OPENAI_API_KEY=value",
        "bogus:X",
    ],
)
def test_provider_auth_never_borrows_unrelated_route(driver, route):
    with pytest.raises(ValueError):
        driver.auth_routes([route], {"OPENAI_API_KEY": "synthetic", "GH_TOKEN": "unrelated"})


def test_provider_auth_is_explicit_name_only_and_rejects_missing_or_duplicate(driver):
    assert driver.auth_routes([], {"OPENAI_API_KEY": "synthetic"}) == {}
    assert driver.auth_routes(["codex:OPENAI_API_KEY"], {"OPENAI_API_KEY": "synthetic"}) == {
        "codex": "OPENAI_API_KEY"
    }
    for values, environment in [
        (["codex:OPENAI_API_KEY"], {}),
        (["codex:OPENAI_API_KEY"] * 2, {"OPENAI_API_KEY": "synthetic"}),
    ]:
        with pytest.raises(ValueError):
            driver.auth_routes(values, environment)


@pytest.mark.parametrize("provider", ["codex", "claude", "copilot"])
def test_launch_flags_do_not_disable_sandbox_or_grant_unbounded_trust(driver, provider):
    arguments = driver.provider_arguments(provider, "fixture prompt with spaces; $(not-code)")
    assert "fixture prompt with spaces; $(not-code)" in arguments
    for denied in (
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "bypassPermissions",
        "--allow-all",
        "--allow-all-paths",
        "--allow-all-tools",
    ):
        assert denied not in arguments


def events(driver, provider):
    command = (
        f"/opt/runtime/bin/python {driver.TOOL_PROBE} --provider {provider} "
        "--phase fresh --session-id native-session"
    )
    output = json.dumps(
        {
            "status": "passed",
            "session_id": "native-session",
            "tool_proof": f"/state/evidence/{provider}/fresh-tool.json",
        }
    )
    if provider == "codex":
        return [
            {
                "type": "item.completed",
                "item": {
                    "type": "command_execution",
                    "command": command,
                    "exit_code": 0,
                    "aggregated_output": output,
                },
            }
        ]
    if provider == "copilot":
        return [
            {
                "type": "tool.execution_start",
                "data": {
                    "toolName": "bash",
                    "toolCallId": "tool-1",
                    "arguments": {"command": command},
                },
            },
            {
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "tool-1",
                    "success": True,
                    "shellExecution": {"exitCode": 0},
                    "result": {"content": output},
                },
            },
        ]
    return [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "tool-1", "content": output}]
            },
        },
    ]


@pytest.mark.parametrize("provider", ["codex", "claude", "copilot"])
def test_native_probe_needs_successful_correlated_execution(driver, provider):
    trace = events(driver, provider)
    assert driver.native_probe_executed(provider, trace, "fresh", "native-session")
    assert not driver.native_probe_executed(provider, trace, "reused", "native-session")
    assert not driver.native_probe_executed(provider, trace, "fresh", "other-session")
    assert not driver.native_probe_executed(
        provider, [{"type": "assistant", "content": str(trace)}], "fresh", "native-session"
    )
    if provider == "codex":
        trace[0]["item"]["exit_code"] = 1
    elif provider == "copilot":
        trace[-1]["data"]["shellExecution"]["exitCode"] = 1
    else:
        trace[-1]["message"]["content"][0]["is_error"] = True
    assert not driver.native_probe_executed(provider, trace, "fresh", "native-session")


def test_quoted_narrative_echo_does_not_establish_probe_execution(driver):
    command = (
        f"/opt/runtime/bin/python {driver.TOOL_PROBE} --provider codex "
        "--phase fresh --session-id native"
    )
    assert driver._probe_command(command, "codex", "fresh", "native")
    assert driver._probe_command("/bin/bash -lc '" + command + "'", "codex", "fresh", "native")
    assert not driver._probe_command("echo '" + command + "'", "codex", "fresh", "native")
    assert not driver._probe_command(command + "; true", "codex", "fresh", "native")


def proof(driver):
    return {
        "provider": "codex",
        "phase": "fresh",
        "session_id": "native-session",
        "container_marker": True,
        "uid": 1000,
        "registry": str(driver.REGISTRY),
        "profile": driver.PROFILE,
        "retrieval": {"receipt_operations": ["catalog", "search", "inspect"]},
        "credentials": {"target_matches_fixture": True, "source_not_exposed": True},
        "scope": {"canonical_fixture_write_denied": True},
        "doctor": {"status": "ok", "workspace_id": "workspace:container-fixture"},
        "signal": {
            "finish": "ok",
            "id": "container-codex-fresh",
            "absent_after": True,
            "cleanup": {"drained": ["container-codex-fresh"], "retained": []},
        },
    }


@pytest.mark.parametrize(
    "missing",
    [
        "session",
        "tool",
        "container",
        "profile",
        "receipt",
        "credentials",
        "canonical",
        "doctor",
        "signal",
    ],
)
def test_report_cannot_promote_partial_fixture_to_native_acceptance(driver, missing):
    value = proof(driver)
    evidence = {"status": "passed", "session_id": "native-session", "probe_execution": True}
    if missing == "session":
        evidence["session_id"] = "another"
    elif missing == "tool":
        evidence["probe_execution"] = False
    elif missing == "container":
        value["container_marker"] = False
    elif missing == "profile":
        value["profile"] = "other"
    elif missing == "receipt":
        value["retrieval"]["receipt_operations"] = ["search"]
    elif missing == "credentials":
        value["credentials"]["target_matches_fixture"] = False
    elif missing == "canonical":
        value["scope"]["canonical_fixture_write_denied"] = False
    elif missing == "doctor":
        value["doctor"]["workspace_id"] = "other"
    else:
        value["signal"]["finish"] = "failed"
    with pytest.raises(ValueError):
        driver.verify_tool_proof(value, evidence, provider="codex", phase="fresh")


def test_native_hook_proof_rejects_assistant_echo_and_keeps_registration_separate(driver):
    echoed = [{"type": "assistant", "content": "agent-knowledge describe " + driver.REFLECTION}]
    for provider in ("codex", "claude", "copilot"):
        result = driver.native_hooks(provider, echoed)
        assert result["lifecycle"] == result["prompt"] == "pending"
    native = [{"type": "user.message", "data": {"transformedContent": "task " + driver.REFLECTION}}]
    result = driver.native_hooks("copilot", native)
    assert result["prompt"] == "passed" and result["lifecycle"] == "pending"


def test_persistent_snapshot_detects_bytes_and_lock_identity_without_following_links(
    driver, tmp_path
):
    state = tmp_path / "signals"
    state.mkdir()
    activity = state / "compound-activity.jsonl"
    activity.write_text("{}\n")
    lock = state / ".compound.lock"
    lock.touch()
    (state / "external").symlink_to(tmp_path / "credentials")
    first = driver.persistent_snapshot(state)
    assert set(first) == {"compound-activity.jsonl", ".compound.lock"}
    assert driver.persistent_snapshot(state) == first
    activity.write_text("{}\n{}\n")
    assert driver.persistent_snapshot(state) != first
    original = deepcopy(driver.persistent_snapshot(state))
    held = lock.open()
    lock.unlink()
    lock.touch()
    assert driver.persistent_snapshot(state) != original
    held.close()


@pytest.mark.parametrize("remaining", ["retained", "present", "wrong-id"])
def test_successful_finish_does_not_hide_undrained_fixture(driver, remaining):
    value = proof(driver)
    if remaining == "retained":
        value["signal"]["cleanup"] = {"drained": [], "retained": ["container-codex-fresh"]}
    elif remaining == "present":
        value["signal"]["absent_after"] = False
    else:
        value["signal"]["cleanup"]["drained"] = ["different-signal"]
    with pytest.raises(ValueError, match="exact fixture signal"):
        driver.verify_tool_proof(
            value,
            {"status": "passed", "session_id": "native-session", "probe_execution": True},
            provider="codex",
            phase="fresh",
        )


def test_failed_child_keeps_structured_failure_report(driver, monkeypatch):
    import subprocess

    monkeypatch.setattr(
        driver.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 1, '{"status":"failed","reason":"native tool failed"}', ""
        ),
    )
    assert driver.command_json(["native"], allow_failure=True) == {
        "status": "failed",
        "reason": "native tool failed",
    }


def test_failure_export_tries_all_evidence_without_replacing_original_failure(
    driver, monkeypatch, tmp_path
):
    import subprocess

    calls = []

    def failing(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "")

    monkeypatch.setattr(driver.subprocess, "run", failing)
    reports = driver.export_evidence("fixture", tmp_path)
    assert len(calls) == 2
    assert all(row["status"] == "unavailable" for row in reports)


def bound_audit():
    names = [
        "lockfile-exists",
        "ref-consistency",
        "deployment-ledger-owners",
        "deployed-files-present",
        "no-orphaned-packages",
        "skill-subset-consistency",
        "config-consistency",
        "content-integrity",
        "includes-consent",
        "drift",
    ]
    paths = [
        ".claude/apm-hooks.json",
        ".claude/settings.json",
        ".codex/apm-hooks.json",
        ".codex/hooks.json",
        ".github/hooks/knowledge-agent-pack-knowledge-discovery.json",
    ]
    return {
        "passed": False,
        "checks": [{"name": n, "passed": n != "drift"} for n in names],
        "drift": {"drift": [{"path": p, "kind": "modified"} for p in paths]},
    }


def test_bound_audit_retains_raw_marker_drift_and_requires_other_checks(driver):
    result = driver.verify_bound_audit(bound_audit())
    assert result["apm_replay_passed"] is False
    assert result["other_audit_checks"] == "passed"
    assert len(result["expected_bound_hook_differences"]) == 5


@pytest.mark.parametrize("error", ["missing-check", "failed-check", "extra-file", "removed-file"])
def test_bound_audit_rejects_any_unexpected_change_or_check_failure(driver, error):
    report = bound_audit()
    if error == "missing-check":
        report["checks"].pop(0)
    elif error == "failed-check":
        report["checks"][0]["passed"] = False
    elif error == "extra-file":
        report["drift"]["drift"].append(
            {"path": ".agents/skills/local/SKILL.md", "kind": "modified"}
        )
    else:
        report["drift"]["drift"][0]["kind"] = "removed"
    with pytest.raises(ValueError):
        driver.verify_bound_audit(report)


def test_codex_auth_uses_only_explicit_child_route_without_persisting_or_fallback(driver):
    original = {
        "OPENAI_API_KEY": "selected-fixture",
        "CODEX_API_KEY": "conflicting-fixture",
        "ANTHROPIC_API_KEY": "unrelated-fixture",
        "COPILOT_GITHUB_TOKEN": "other-fixture",
    }
    result = driver.native_environment("codex", "OPENAI_API_KEY", original)
    assert result == {"CODEX_API_KEY": "selected-fixture"}
    assert original["CODEX_API_KEY"] == "conflicting-fixture"
    with pytest.raises(ValueError):
        driver.native_environment("codex", "OPENAI_API_KEY", {"CODEX_API_KEY": "ambient"})


def test_native_auth_does_not_forward_other_provider_credentials(driver):
    result = driver.native_environment(
        "claude",
        "ANTHROPIC_API_KEY",
        {
            "ANTHROPIC_API_KEY": "selected-fixture",
            "CLAUDE_CODE_OAUTH_TOKEN": "conflicting-fixture",
            "OPENAI_API_KEY": "unrelated-fixture",
            "CODEX_API_KEY": "other-fixture",
        },
    )
    assert result == {"ANTHROPIC_API_KEY": "selected-fixture"}
