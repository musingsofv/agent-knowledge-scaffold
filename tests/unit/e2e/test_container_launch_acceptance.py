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
    assert result["prompt"] == result["lifecycle"] == "pending"


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


@pytest.mark.parametrize("provider", ["claude", "copilot"])
def test_explicit_native_login_strips_tokens_and_known_provider_overrides(driver, provider):
    clean = {"HOME": "/fixture/home", "PATH": "/fixture/bin", "TERM": "xterm"}
    overrides = {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_PROFILE",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CONFIG_DIR",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "CODEX_API_KEY",
        "CODEX_HOME",
        "COPILOT_GITHUB_TOKEN",
        "COPILOT_PROVIDER_API_KEY",
        "COPILOT_PROVIDER_API_KEY_COMMAND",
        "COPILOT_PROVIDER_BASE_URL",
        "COPILOT_HOME",
        "COPILOT_ALLOW_ALL",
        "GH_TOKEN",
        "GH_HOST",
        "GH_CONFIG_DIR",
        "GITHUB_TOKEN",
        "GITHUB_API_URL",
    }
    original = {**clean, **dict.fromkeys(overrides, "synthetic-unrelated")}
    assert driver.native_environment(provider, "native-login", original) == clean
    assert original["COPILOT_GITHUB_TOKEN"] == "synthetic-unrelated"


@pytest.mark.parametrize("source", [None, "", "auto", "saved-login", "ANTHROPIC_API_KEY"])
def test_available_saved_login_does_not_make_auth_selection_implicit(driver, tmp_path, source):
    saved = tmp_path / ".claude/.credentials.json"
    saved.parent.mkdir()
    saved.write_text('{"fictional": "saved-login"}')
    with pytest.raises(ValueError, match="route is unavailable"):
        driver.native_environment("claude", source, {"HOME": str(tmp_path)})


@pytest.mark.parametrize("provider", ["codex", "unknown"])
def test_native_login_cannot_expand_supported_provider_routes(driver, provider):
    with pytest.raises(ValueError, match="route is unavailable"):
        driver.native_environment(provider, "native-login", {})
    with pytest.raises(ValueError):
        driver.auth_routes(["claude:native-login"], {})


def test_copilot_defaults_preserve_existing_settings_and_login_without_reading(
    driver, tmp_path, monkeypatch
):
    settings = tmp_path / "settings.json"
    login = tmp_path / "config.json"
    settings.write_text('{"fixtureNativeSettings": true}\n')
    login.write_text('{"fixtureNativeLogin": true}\n')
    before = {p: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in (settings, login)}
    original_open = Path.open

    def no_native_reads(path, mode="r", *args, **kwargs):
        if path in (settings, login) and mode != "x":
            pytest.fail("The driver attempted to read or overwrite provider-owned state")
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", no_native_reads)
        driver.prepare_copilot_settings(tmp_path)
    assert before == {p: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in before}


def test_copilot_defaults_only_trust_fixture_when_no_settings_exist(driver, tmp_path):
    home = tmp_path / "native"
    driver.prepare_copilot_settings(home)
    value = json.loads((home / "settings.json").read_text())
    assert value == {
        "trustedFolders": [str(driver.CONSUMER)],
        "autoUpdate": False,
        "disableAllHooks": False,
        "memory": False,
    }
    assert not (home / "config.json").exists()


@pytest.mark.parametrize("provider", ["claude", "copilot"])
def test_native_login_cli_is_an_explicit_inside_only_choice(driver, monkeypatch, capsys, provider):
    calls = []

    def native(selected, phase, timeout, source):
        calls.append((selected, phase, timeout, source))
        return {"status": "pending", "authentication_source": source}

    monkeypatch.setattr(driver, "native", native)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--inside",
            "native",
            "--provider",
            provider,
            "--phase",
            "fresh",
            "--auth-source",
            "native-login",
        ],
    )
    assert driver.main() == 0
    assert calls == [(provider, "fresh", 300, "native-login")]
    assert json.loads(capsys.readouterr().out)["authentication_source"] == "native-login"


SESSION = "1a8f31a8-4254-42ae-9da4-0482d1b04836"


def copilot_hooks(driver):
    context = "Run agent-knowledge describe. Provider session ID: " + SESSION
    transformed = "Fixture request. " + driver.REFLECTION
    return [
        {"type": "session.start", "id": "session", "data": {"sessionId": SESSION}},
        {
            "type": "hook.start",
            "id": "start",
            "data": {
                "hookInvocationId": "startup-invocation",
                "hookType": "sessionStart",
                "input": {"sessionId": SESSION, "initialPrompt": "never-copy-input"},
            },
        },
        {
            "type": "hook.end",
            "id": "end",
            "parentId": "start",
            "data": {
                "hookInvocationId": "startup-invocation",
                "hookType": "sessionStart",
                "success": True,
                "output": {"additionalContext": context, "opaque": "never-copy-output"},
            },
        },
        {
            "type": "hook.start",
            "id": "transform-start",
            "data": {
                "hookInvocationId": "transform-invocation",
                "hookType": "userPromptTransformed",
                "input": {"sessionId": SESSION},
            },
        },
        {
            "type": "hook.end",
            "id": "transform-end",
            "parentId": "transform-start",
            "data": {
                "hookInvocationId": "transform-invocation",
                "hookType": "userPromptTransformed",
                "success": True,
                "output": {"modifiedTransformedPrompt": transformed},
            },
        },
        {
            "type": "user.message",
            "id": "user",
            "parentId": "transform-end",
            "data": {"transformedContent": transformed, "content": "never-copy-raw-user"},
        },
        {"type": "assistant.message", "data": {"reasoning": "never-copy-reasoning"}},
    ]


def write_copilot_transcript(driver, home):
    path = home / "session-state" / SESSION / "events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("\n".join(json.dumps(event) for event in copilot_hooks(driver)) + "\n")
    return path


def test_copilot_native_transcript_correlates_success_and_exports_only_selected_fields(
    driver, tmp_path
):
    home = tmp_path / "copilot"
    write_copilot_transcript(driver, home)
    destination = tmp_path / "fresh-hooks.jsonl"
    result = driver.save_copilot_hook_evidence(home, SESSION, destination, ["Fixture request."])
    assert result["lifecycle"] == result["prompt"] == "passed"
    assert result["evidence_path"] == str(destination)
    text = destination.read_text()
    assert "never-copy" not in text and "Fixture request." not in text
    assert "[redacted]" in text and SESSION in text and "additionalContext" in text
    assert {json.loads(line)["type"] for line in text.splitlines()} == {
        "session.start",
        "hook.start",
        "hook.end",
        "user.message",
    }


@pytest.mark.parametrize(
    "fault",
    ["session", "invocation", "parent", "failed", "foreign-input", "no-start", "no-id", "string"],
)
def test_copilot_startup_needs_exact_successful_native_invocation(driver, fault):
    trace = copilot_hooks(driver)
    if fault == "session":
        trace[0]["data"]["sessionId"] = "another-session"
    elif fault == "invocation":
        trace[2]["data"]["hookInvocationId"] = "another-invocation"
    elif fault == "parent":
        trace[2]["parentId"] = "another-parent"
    elif fault == "failed":
        trace[2]["data"]["success"] = False
    elif fault == "foreign-input":
        trace[1]["data"]["input"]["sessionId"] = "another-session"
    elif fault == "no-start":
        trace.pop(1)
    elif fault == "no-id":
        trace[1].pop("id")
        trace[2].pop("parentId")
    else:
        trace[2]["data"]["output"] = "agent-knowledge describe " + SESSION
    assert driver.native_hooks("copilot", trace, session=SESSION)["lifecycle"] == "pending"


@pytest.mark.parametrize("fault", ["failed", "parent", "content", "missing-user", "wrong-session"])
def test_copilot_prompt_needs_success_and_actual_transformed_message(driver, fault):
    trace = copilot_hooks(driver)
    if fault == "failed":
        trace[4]["data"]["success"] = False
    elif fault == "parent":
        trace[5]["parentId"] = "another-end"
    elif fault == "content":
        trace[5]["data"]["transformedContent"] += "different"
    elif fault == "missing-user":
        trace.pop(5)
    else:
        trace[3]["data"]["input"]["sessionId"] = "another-session"
    assert driver.native_hooks("copilot", trace, session=SESSION)["prompt"] == "pending"


@pytest.mark.parametrize("session", [None, "", "../config", "/credentials", SESSION.upper()])
def test_copilot_transcript_rejects_noncanonical_ids_before_reading(driver, tmp_path, session):
    with pytest.raises(ValueError):
        driver.copilot_hook_events(tmp_path, session)


@pytest.mark.parametrize("fault", ["wrong-session", "oversize", "symlink", "missing", "malformed"])
def test_copilot_unavailable_or_unbounded_transcript_never_promotes_hook_proof(
    driver, tmp_path, monkeypatch, fault
):
    home = tmp_path / "copilot"
    path = write_copilot_transcript(driver, home)
    if fault == "wrong-session":
        path.write_text(path.read_text().replace(SESSION, "another-session"))
    elif fault == "oversize":
        monkeypatch.setattr(driver, "COPILOT_TRANSCRIPT_LIMIT", 20)
    elif fault == "symlink":
        external = tmp_path / "private-native-file"
        path.rename(external)
        path.symlink_to(external)
    elif fault == "missing":
        path.unlink()
    else:
        path.write_text("invalid-json\n")
    destination = tmp_path / "hooks.jsonl"
    result = driver.save_copilot_hook_evidence(home, SESSION, destination, [])
    assert result["lifecycle"] == result["prompt"] == "pending"
    assert not destination.exists()


@pytest.mark.parametrize("suffix", [" 2>&1", "\t2>&1  "])
def test_exact_probe_allows_bare_trailing_stderr_merge(driver, suffix):
    command = (
        f"{driver.RUNTIME}/bin/python {driver.TOOL_PROBE} "
        "--provider claude --phase reused --session-id native"
    )
    assert driver._probe_command(command + suffix, "claude", "reused", "native")
    assert driver._probe_command(
        "/bin/bash -c '" + command + suffix + "'", "claude", "reused", "native"
    )


@pytest.mark.parametrize(
    "suffix",
    [' "2>&1"', " '2>&1'", r" \2\>\&1", " 2>/tmp/log", " 2>&1; true", " 2>&1 2>&1"],
)
def test_probe_never_confuses_positional_text_or_shell_suffix_with_stderr_merge(driver, suffix):
    command = (
        f"{driver.RUNTIME}/bin/python {driver.TOOL_PROBE} "
        "--provider claude --phase reused --session-id native"
    )
    assert not driver._probe_command(command + suffix, "claude", "reused", "native")


def test_copilot_permissions_use_exact_executable_names_and_fixture_read_directories(driver):
    arguments = driver.provider_arguments("copilot", "fixture")
    allowed = [
        arguments[i + 1] for i, value in enumerate(arguments[:-1]) if value == "--allow-tool"
    ]
    assert "shell(command)" in allowed and "shell(agent-knowledge)" in allowed
    assert "shell(command -v agent-knowledge)" not in allowed
    directories = [
        arguments[i + 1] for i, value in enumerate(arguments[:-1]) if value == "--add-dir"
    ]
    # The container venv interpreter resolves to /usr/bin/python3.13; native
    # Copilot checks the real executable path as well as the venv path.
    assert directories == [
        str(driver.STATE),
        "/opt/proof",
        str(driver.RUNTIME),
        "/opt/fixture",
        "/usr/bin",
    ]
    assert "--deny-url=*" in arguments and "--disable-builtin-mcps" in arguments
