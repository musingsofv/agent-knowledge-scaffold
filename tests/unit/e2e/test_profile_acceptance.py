"""Verify the provider-neutral contracts of the named-profile live driver."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tests" / "e2e" / "profile_acceptance.py"


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("profile_acceptance_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_provider_commands_preserve_sessions_and_disable_remote_surfaces(
    tmp_path: Path, driver
) -> None:
    claude = driver._provider_command(
        "claude",
        "claude",
        consumer=tmp_path,
        session="claude-session",
        prompt="continue",
        first=False,
        budget=2,
        copilot_credits=30,
        log_dir=tmp_path / "logs",
    )
    codex_first = driver._provider_command(
        "codex",
        "codex",
        consumer=tmp_path,
        session=None,
        prompt="discover",
        first=True,
        budget=2,
        copilot_credits=30,
        log_dir=tmp_path / "logs",
    )
    codex_resume = driver._provider_command(
        "codex",
        "codex",
        consumer=tmp_path,
        session="codex-thread",
        prompt="continue",
        first=False,
        budget=2,
        copilot_credits=30,
        log_dir=tmp_path / "logs",
    )
    copilot_first = driver._provider_command(
        "copilot",
        "copilot",
        consumer=tmp_path,
        session="00000000-0000-4000-8000-000000000001",
        prompt="discover",
        first=True,
        budget=2,
        copilot_credits=30,
        log_dir=tmp_path / "logs",
    )
    copilot_resume = driver._provider_command(
        "copilot",
        "copilot",
        consumer=tmp_path,
        session="00000000-0000-4000-8000-000000000001",
        prompt="continue",
        first=False,
        budget=2,
        copilot_credits=30,
        log_dir=tmp_path / "logs",
    )

    assert claude[-4:] == ["--resume", "claude-session", "-p", "continue"]
    assert claude[claude.index("--model") + 1] == "opus"
    assert codex_first[:3] == ["codex", "exec", "--json"]
    assert "--ephemeral" not in codex_first
    assert codex_resume[:4] == ["codex", "exec", "resume", "--json"]
    assert codex_resume[-2:] == ["codex-thread", "continue"]
    assert "--session-id=00000000-0000-4000-8000-000000000001" in copilot_first
    assert "--resume=00000000-0000-4000-8000-000000000001" in copilot_resume
    for command in (copilot_first, copilot_resume):
        assert "--no-auto-update" in command
        assert "--no-remote" in command
        assert "--no-remote-export" in command
        assert "--disable-builtin-mcps" in command
        assert "--disallow-temp-dir" in command
        assert "--deny-url=*" in command
        assert command[command.index("--add-dir") + 1] == "."
        assert command[command.index("--log-dir") + 1] == str(tmp_path / "logs")


def test_copilot_environment_trusts_only_the_disposable_consumer(tmp_path: Path, driver) -> None:
    source = tmp_path / "source-home"
    source.mkdir()
    (source / "config.json").write_text(
        '// managed\n{"lastLoggedInUser":{"login":"tester"},'
        '"loggedInUsers":[{"login":"tester"}],"token":"never-copy"}\n'
    )
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    state = tmp_path / "isolated"

    env = driver._isolated_copilot_environment(
        consumer,
        base_env={
            "HOME": str(tmp_path),
            "COPILOT_HOME": str(source),
            "GITHUB_TOKEN": "classic-token",
        },
        state_directory=state,
    )

    settings = json.loads((state / "settings.json").read_text())
    config_text = (state / "config.json").read_text()
    assert settings["trustedFolders"] == [str(consumer.resolve())]
    assert settings["disableAllHooks"] is False
    assert "never-copy" not in config_text
    assert "tester" in config_text
    assert env["COPILOT_HOME"] == str(state.resolve())
    assert "GITHUB_TOKEN" not in env


@pytest.mark.parametrize(
    ("provider", "events", "session", "response", "command"),
    [
        (
            "claude",
            [
                {
                    "type": "system",
                    "subtype": "init",
                    "session_id": "claude-session",
                    "model": "claude-opus-5",
                },
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": "agent-knowledge context"},
                            }
                        ]
                    },
                },
                {"type": "result", "is_error": False, "result": "blue-window-17"},
            ],
            "claude-session",
            "blue-window-17",
            "agent-knowledge context",
        ),
        (
            "codex",
            [
                {"type": "thread.started", "thread_id": "codex-thread"},
                {
                    "type": "item.completed",
                    "item": {"type": "command_execution", "command": "agent-knowledge context"},
                },
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "blue-window-17"},
                },
                {"type": "turn.completed"},
            ],
            "codex-thread",
            "blue-window-17",
            "agent-knowledge context",
        ),
        (
            "copilot",
            [
                {
                    "type": "tool.execution_start",
                    "data": {
                        "toolName": "bash",
                        "arguments": {"command": "agent-knowledge context"},
                    },
                },
                {
                    "type": "assistant.message",
                    "data": {
                        "phase": "final_answer",
                        "content": "blue-window-17",
                        "model": "gpt-test",
                    },
                },
                {"type": "result", "sessionId": "copilot-session", "exitCode": 0},
            ],
            "copilot-session",
            "blue-window-17",
            "agent-knowledge context",
        ),
    ],
)
def test_provider_evidence_normalizes_native_jsonl(
    tmp_path: Path,
    driver,
    provider: str,
    events: list[dict[str, object]],
    session: str,
    response: str,
    command: str,
) -> None:
    evidence = driver._provider_evidence(provider, events, tmp_path / f"{provider}.log")

    assert evidence["status"] == "passed"
    assert evidence["session_id"] == session
    assert evidence["response"] == response
    assert evidence["commands"] == [command]


def test_model_activity_requires_context_and_an_ordinary_body_read(tmp_path: Path, driver) -> None:
    launcher = tmp_path / ".agent-knowledge-venv/bin/agent-knowledge"
    settings = tmp_path / "profile-proof/config.yaml"
    body = tmp_path / "profile-proof/personal/knowledge/release.md"
    prefix = (
        f"{launcher} --settings {settings} --profile personal --harness codex "
        "--session-id exact-session"
    )
    commands = [
        prefix + " context --request-file -",
        f"sed -n '1,120p' {body}",
    ]

    driver._assert_model_activity(
        commands,
        launcher=launcher,
        settings=settings,
        profile="personal",
        provider="codex",
        session="exact-session",
        body=body,
    )
    with pytest.raises(driver.HarnessSmokeFailure, match="ordinary file read"):
        driver._assert_model_activity(
            commands[:1],
            launcher=launcher,
            settings=settings,
            profile="personal",
            provider="codex",
            session="exact-session",
            body=body,
        )


def test_copilot_model_activity_accepts_relative_paths_and_native_session_variable(
    tmp_path: Path, driver
) -> None:
    launcher = tmp_path / ".agent-knowledge-venv/bin/agent-knowledge"
    settings = tmp_path / "profile-proof/config.yaml"
    body = tmp_path / "profile-proof/personal/knowledge/release.md"
    commands = [
        'sid="$COPILOT_AGENT_SESSION_ID"; '
        "cli=./.agent-knowledge-venv/bin/agent-knowledge; "
        "settings=profile-proof/config.yaml; "
        '"$cli" --settings "$settings" --profile personal --harness copilot '
        '--session-id "$sid" context',
        f"cat {body}",
    ]

    driver._assert_model_activity(
        commands,
        launcher=launcher,
        settings=settings,
        profile="personal",
        provider="copilot",
        session="00000000-0000-4000-8000-000000000001",
        body=body,
    )


def test_model_activity_accepts_installed_launcher_name_from_bounded_path(
    tmp_path: Path, driver
) -> None:
    launcher = tmp_path / ".agent-knowledge-venv/bin/agent-knowledge"
    settings = tmp_path / "profile-proof/config.yaml"
    body = tmp_path / "profile-proof/personal/knowledge/release.md"

    driver._assert_model_activity(
        [
            "agent-knowledge --settings profile-proof/config.yaml --profile personal "
            "--harness copilot --session-id exact-session context",
            f"cat {body}",
        ],
        launcher=launcher,
        settings=settings,
        profile="personal",
        provider="copilot",
        session="exact-session",
        body=body,
    )


def test_retrieval_proof_requires_all_operations_and_exact_selection(
    tmp_path: Path, driver
) -> None:
    body = tmp_path / "profile-proof/personal/knowledge/release.md"

    def event(operation: str, profile: str = "personal") -> dict[str, object]:
        response: dict[str, object] = {"status": "ok"}
        if operation == "search":
            response["results"] = [{"local_path": str(body)}]
        elif operation == "inspect":
            response["preview"] = {"local_path": str(body)}
        return {
            "schema_version": "knowledge-retrieval-receipt.v1",
            "operation": operation,
            "context": {
                "harness": "copilot",
                "session_id": "exact-session",
                "workspace_id": "workspace:personal",
            },
            "selection": {"profile": profile},
            "response": response,
        }

    events = [event(operation) for operation in ("catalog", "search", "inspect")]

    proof = driver._retrieval_proof(
        events,
        profile="personal",
        provider="copilot",
        session="exact-session",
        body=body,
    )
    assert proof["operations"] == ["catalog", "inspect", "search"]
    assert proof["receipt_count"] == 3
    assert proof["recovered_attempts"] == 0

    failed_catalog = event("catalog")
    failed_catalog["response"] = {"status": "error"}
    recovered = driver._retrieval_proof(
        [failed_catalog, *events],
        profile="personal",
        provider="copilot",
        session="exact-session",
        body=body,
    )
    assert recovered["recovered_attempts"] == 1

    with pytest.raises(driver.HarnessSmokeFailure, match="did not recover"):
        driver._retrieval_proof(
            [*events, failed_catalog],
            profile="personal",
            provider="copilot",
            session="exact-session",
            body=body,
        )

    with pytest.raises(driver.HarnessSmokeFailure, match="selected profile"):
        driver._retrieval_proof(
            [events[0], events[1], event("inspect", "work")],
            profile="personal",
            provider="copilot",
            session="exact-session",
            body=body,
        )
    with pytest.raises(driver.HarnessSmokeFailure, match="Missing retrieval receipts"):
        driver._retrieval_proof(
            events[:2],
            profile="personal",
            provider="copilot",
            session="exact-session",
            body=body,
        )


def test_signal_duplicate_check_requires_inline_exact_session_filter(
    tmp_path: Path, driver
) -> None:
    launcher = tmp_path / ".agent-knowledge-venv/bin/agent-knowledge"
    settings = tmp_path / "profile-proof/config.yaml"
    prefix = (
        f"{launcher} --settings {settings} --profile personal --harness claude "
        "--session-id exact-session signal list --request-file -"
    )
    command = f"printf '%s\\n' 'session_id: exact-session' | {prefix}"

    driver._assert_signal_list_activity(
        [command],
        launcher=launcher,
        settings=settings,
        profile="personal",
        provider="claude",
        session="exact-session",
    )
    with pytest.raises(driver.HarnessSmokeFailure, match="inline session filter"):
        driver._assert_signal_list_activity(
            [prefix],
            launcher=launcher,
            settings=settings,
            profile="personal",
            provider="claude",
            session="exact-session",
        )


def test_signal_duplicate_check_accepts_escaped_json_and_copilot_session_variable(
    tmp_path: Path, driver
) -> None:
    launcher = tmp_path / ".agent-knowledge-venv/bin/agent-knowledge"
    settings = tmp_path / "profile-proof/config.yaml"
    command = (
        f'/bin/zsh -lc "sid=\\"$COPILOT_AGENT_SESSION_ID\\"; {launcher} '
        f"--settings {settings} --profile personal "
        "--harness copilot --session-id $sid signal list "
        "--request-file - <<'JSON'\n"
        '{\\"session_id\\":\\"$sid\\"}\nJSON"'
    )

    driver._assert_signal_list_activity(
        [command],
        launcher=launcher,
        settings=settings,
        profile="personal",
        provider="copilot",
        session="00000000-0000-4000-8000-000000000001",
    )


def test_profile_isolation_rejects_alternate_cli_and_file_access(tmp_path: Path, driver) -> None:
    other = tmp_path / "profile-proof/work"
    driver._assert_profile_isolation(
        ["agent-knowledge --profile personal context"],
        other_profile="work",
        other_root=other,
        consumer=tmp_path,
    )
    with pytest.raises(driver.HarnessSmokeFailure, match="alternate profile"):
        driver._assert_profile_isolation(
            ["agent-knowledge --profile work context"],
            other_profile="work",
            other_root=other,
            consumer=tmp_path,
        )
    with pytest.raises(driver.HarnessSmokeFailure, match="directly read"):
        driver._assert_profile_isolation(
            [f"cat {other}/knowledge/release.md"],
            other_profile="work",
            other_root=other,
            consumer=tmp_path,
        )
    with pytest.raises(driver.HarnessSmokeFailure, match="directly read"):
        driver._assert_profile_isolation(
            [],
            other_profile="work",
            other_root=other,
            consumer=tmp_path,
            events=[
                {
                    "type": "tool.execution_start",
                    "data": {"toolName": "view", "arguments": {"path": str(other)}},
                }
            ],
        )


def test_profile_isolation_rejects_relative_paths_without_matching_similar_names(
    tmp_path: Path, driver
) -> None:
    other = tmp_path / "profile-proof/work"
    with pytest.raises(driver.HarnessSmokeFailure, match="directly read"):
        driver._assert_profile_isolation(
            ["cat ./profile-proof/work/knowledge/release.md"],
            other_profile="work",
            other_root=other,
            consumer=tmp_path,
        )
    with pytest.raises(driver.HarnessSmokeFailure, match="directly read"):
        driver._assert_profile_isolation(
            [],
            other_profile="work",
            other_root=other,
            consumer=tmp_path,
            events=[
                {
                    "type": "tool.execution_start",
                    "data": {
                        "toolName": "view",
                        "arguments": {"path": "profile-proof/work/knowledge/release.md"},
                    },
                }
            ],
        )

    driver._assert_profile_isolation(
        ["cat profile-proof/workbench/knowledge/release.md"],
        other_profile="work",
        other_root=other,
        consumer=tmp_path,
        events=[
            {
                "type": "tool.execution_start",
                "data": {
                    "toolName": "view",
                    "arguments": {"path": "profile-proof/work-notes.md"},
                },
            }
        ],
    )


def test_no_remote_effect_check_rejects_network_tools(driver) -> None:
    driver._assert_no_remote_effects([], ["cat local.md"])

    with pytest.raises(driver.HarnessSmokeFailure, match="remote-capable"):
        driver._assert_no_remote_effects([], ["curl https://example.test"])
    with pytest.raises(driver.HarnessSmokeFailure, match="remote provider tool"):
        driver._assert_no_remote_effects(
            [{"type": "tool.execution_start", "data": {"toolName": "web_fetch"}}],
            [],
        )


def test_usage_events_read_only_json_objects(tmp_path: Path, driver) -> None:
    usage = tmp_path / "ai/usage/retrieval/2026-09-21.jsonl"
    usage.parent.mkdir(parents=True)
    usage.write_text(
        "not-json\n"
        + json.dumps({"schema_version": "knowledge-retrieval-receipt.v1"})
        + "\n"
        + json.dumps(["not", "an", "object"])
        + "\n",
        encoding="utf-8",
    )

    assert driver._usage_events(tmp_path / "ai/usage") == [
        {"schema_version": "knowledge-retrieval-receipt.v1"}
    ]
