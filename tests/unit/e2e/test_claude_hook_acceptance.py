"""Verify local contracts for the opt-in Claude model-flow driver."""

import importlib.util
import json
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tests" / "e2e" / "claude_hook_acceptance.py"


def _driver():
    spec = importlib.util.spec_from_file_location("claude_hook_acceptance", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _consumer(tmp_path: Path, command: str | None = None) -> tuple[Path, Path, Path]:
    consumer = tmp_path / "consumer"
    hook = consumer / ".agent-knowledge-venv" / "bin" / "agent-knowledge-hook"
    launcher = hook.with_name("agent-knowledge")
    for path in (hook, launcher):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
    (consumer / "knowledge-workspace.yaml").write_text("schema_version: knowledge-workspace.v1\n")
    claude = consumer / ".claude"
    claude.mkdir()
    command = shlex.join([str(hook), "--provider", "claude"]) if command is None else command
    settings = {
        "hooks": {
            event: [{"hooks": [{"type": "command", "command": command}]}]
            for event in ("SessionStart", "UserPromptSubmit")
        }
    }
    (claude / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    registration = {
        event: [
            {
                "_apm_source": "_local/knowledge-agent-pack",
                "hooks": [{"type": "command", "command": command}],
            }
        ]
        for event in ("SessionStart", "UserPromptSubmit")
    }
    (claude / "apm-hooks.json").write_text(json.dumps(registration), encoding="utf-8")
    return consumer, hook, launcher


def test_package_registration_requires_the_exact_managed_hook_launcher(tmp_path: Path) -> None:
    module = _driver()
    consumer, hook, _ = _consumer(tmp_path)

    assert module._validate_hook_launcher(consumer, hook) == hook
    module._assert_package_registration(consumer, hook)


@pytest.mark.parametrize("command", ["agent-knowledge-hook", "/tmp/agent-knowledge-hook"])
def test_package_registration_rejects_marker_or_other_launcher(
    tmp_path: Path, command: str
) -> None:
    module = _driver()
    consumer, hook, _ = _consumer(tmp_path, command)

    with pytest.raises(
        module.ClaudeAcceptanceFailure,
        match="bare hook launcher marker|verified absolute hook launcher",
    ):
        module._assert_package_registration(consumer, hook)


def test_hook_launcher_must_be_absolute_and_consumer_local(tmp_path: Path) -> None:
    module = _driver()
    consumer, _, _ = _consumer(tmp_path)
    external = tmp_path / "outside" / "agent-knowledge-hook"
    external.parent.mkdir()
    external.write_text("#!/bin/sh\n", encoding="utf-8")
    external.chmod(0o755)

    with pytest.raises(module.ClaudeAcceptanceFailure, match="absolute path"):
        module._validate_hook_launcher(consumer, Path("agent-knowledge-hook"))
    with pytest.raises(module.ClaudeAcceptanceFailure, match="managed virtual environment"):
        module._validate_hook_launcher(consumer, external)


def test_package_registration_rejects_a_bare_marker_in_active_claude_settings(
    tmp_path: Path,
) -> None:
    module = _driver()
    consumer, hook, _ = _consumer(tmp_path)
    settings_path = consumer / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] = "agent-knowledge-hook"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    with pytest.raises(module.ClaudeAcceptanceFailure, match="active SessionStart retained"):
        module._assert_package_registration(consumer, hook)


def test_model_prompts_keep_the_session_id_out_of_the_user_prompt(tmp_path: Path) -> None:
    module = _driver()
    _, hook, launcher = _consumer(tmp_path)
    config = launcher.parent.parent.parent / "knowledge-workspace.yaml"

    record = module._record_prompt(launcher=launcher, config=config)
    dedup = module._dedup_prompt(launcher=launcher, config=config)

    assert "example-hook-session" not in record + dedup
    assert "only session ID you may use" in record
    assert "exact session ID supplied by this turn's hook context" in dedup
    assert "--request-file -" in record + dedup
    assert "index build must not run inside a transaction" in record + dedup
    assert "do not write" not in dedup.casefold()
    assert str(hook) not in record + dedup


def test_model_command_assertion_requires_installed_cli_and_explicit_config(tmp_path: Path) -> None:
    module = _driver()
    _, _, launcher = _consumer(tmp_path)
    config = launcher.parent.parent.parent / "knowledge-workspace.yaml"
    session_id = "hook-session"
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {
                            "command": (
                                "printf '%s\\n' '{\"session_id\": \"hook-session\"}' | "
                                f"{launcher} --config {config} signal list --request-file -"
                            )
                        },
                    }
                ]
            },
        }
    ]

    assert module._assert_model_used_cli(
        events,
        launcher=launcher,
        config=config,
        session_id=session_id,
        operations=("signal list",),
    )
    with pytest.raises(module.ClaudeAcceptanceFailure, match="signal record"):
        module._assert_model_used_cli(
            events,
            launcher=launcher,
            config=config,
            session_id=session_id,
            operations=("signal record",),
        )


def test_model_list_requires_session_id_as_an_inline_request_key(tmp_path: Path) -> None:
    module = _driver()
    _, _, launcher = _consumer(tmp_path)
    config = launcher.parent.parent.parent / "knowledge-workspace.yaml"
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {
                            "command": (
                                "printf '%s\\n' '{\"note\": \"hook-session\"}' | "
                                f"{launcher} --config {config} signal list --request-file -"
                            )
                        },
                    }
                ]
            },
        }
    ]

    with pytest.raises(module.ClaudeAcceptanceFailure, match="required inline request"):
        module._assert_model_used_cli(
            events,
            launcher=launcher,
            config=config,
            session_id="hook-session",
            operations=("signal list",),
        )


def test_model_inspection_accepts_native_read_of_the_listed_signal(tmp_path: Path) -> None:
    module = _driver()
    signal = tmp_path / "model-hook-origin.md"
    signal.write_text("# fixture\n", encoding="utf-8")
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": str(signal)},
                    }
                ]
            },
        }
    ]

    module._assert_model_inspected(events, signal)


def test_model_inspection_rejects_echoing_the_listed_signal_path(tmp_path: Path) -> None:
    module = _driver()
    signal = tmp_path / "model-hook-origin.md"
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": f"echo {signal}"},
                    }
                ]
            },
        }
    ]

    with pytest.raises(module.ClaudeAcceptanceFailure, match="did not inspect"):
        module._assert_model_inspected(events, signal)


def test_session_signal_requires_one_exact_harness_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _driver()
    consumer, _, launcher = _consumer(tmp_path)
    config = consumer / "knowledge-workspace.yaml"
    stored = consumer / "ai" / "signals" / "projects" / "consumer" / "model.md"
    stored.parent.mkdir(parents=True)
    stored.write_text("---\n---\n", encoding="utf-8")
    preview = {
        "id": "model-hook-origin",
        "origin": {"harness": "claude", "session_id": "hook-session"},
        "local_path": str(stored),
        "body_range": [4, 4],
    }
    monkeypatch.setattr(
        module,
        "_run_agent_knowledge",
        lambda *args, **kwargs: {"status": "ok", "results": [preview]},
    )

    assert (
        module._session_signal(
            launcher,
            consumer=consumer,
            config=config,
            session_id="hook-session",
            timeout=1,
            environment={},
        )
        == preview
    )


def test_main_preserves_partial_transport_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _driver()
    partial = {
        "status": "failed",
        "provider": "claude",
        "transport": {"status": "passed", "startup": {"session_id": "hook-session"}},
        "model_flow": {"status": "failed", "stage": "record"},
        "diagnostic": "record did not complete",
    }

    def fail(**_: object) -> dict[str, object]:
        raise module.ClaudeAcceptanceFailure("record did not complete", report=partial)

    monkeypatch.setattr(module, "run_acceptance", fail)
    hook_launcher = tmp_path / "consumer" / ".agent-knowledge-venv" / "bin" / "agent-knowledge-hook"

    assert (
        module.main(
            [
                "--consumer",
                str(tmp_path / "consumer"),
                "--hook-launcher",
                str(hook_launcher),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().err) == partial


def test_installed_launcher_accepts_consumer_relative_path_but_not_global(tmp_path: Path) -> None:
    module = _driver()
    launcher = tmp_path / ".agent-knowledge-venv/bin/agent-knowledge"
    assert module._invokes_installed_launcher(
        "./.agent-knowledge-venv/bin/agent-knowledge signal list --request-file -",
        launcher,
        tmp_path,
    )
    assert not module._invokes_installed_launcher(
        "agent-knowledge signal list --request-file -",
        launcher,
        tmp_path,
    )
    assert not module._invokes_installed_launcher(
        "cat ./.agent-knowledge-venv/bin/agent-knowledge",
        launcher,
        tmp_path,
    )


def test_explicit_configuration_accepts_equivalent_relative_path(tmp_path: Path) -> None:
    module = _driver()
    config = tmp_path / "knowledge-workspace.yaml"
    assert module._uses_explicit_config("cli --config ./knowledge-workspace.yaml search", config)
    assert not module._uses_explicit_config("cli --config other.yaml search", config)
    assert not module._uses_explicit_config("cli search", config)
