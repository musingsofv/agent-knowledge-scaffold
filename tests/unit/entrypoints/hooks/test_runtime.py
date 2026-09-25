"""Exercise the bounded hook entrypoint without provider processes."""

import io
import json
import os
from pathlib import Path

import pytest
import yaml

from agent_knowledge.entrypoints.hooks import runtime
from agent_knowledge.resources.hook_messages import (
    PROVIDER_PREFIX,
    REFLECTION_REMINDER_MESSAGE,
    SESSION_ID_PREFIX,
    START_DISCOVERY_MESSAGE,
)


def test_runtime_emits_json_for_an_eligible_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-1"}'
                )
            },
        )(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert runtime.main([]) == 0
    assert json.loads(output.getvalue()) == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                START_DISCOVERY_MESSAGE
                + "\n\n"
                + REFLECTION_REMINDER_MESSAGE
                + "\n\n"
                + PROVIDER_PREFIX
                + "codex\n"
                + SESSION_ID_PREFIX
                + "runtime-1"
            ),
        }
    }


def test_runtime_is_fail_open_for_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type("Input", (), {"buffer": io.BytesIO(b"not-json")})(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert runtime.main([]) == 0
    assert output.getvalue() == ""


def test_provider_launcher_executes_with_mapped_values_without_rendering_them(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "provider-launch-secret-canary"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\nUNDECLARED=ignore-me\n", encoding="utf-8")
    environment_file.chmod(0o600)
    captured: dict[str, object] = {}

    monkeypatch.setattr(runtime.shutil, "which", lambda provider, path=None: "/bin/codex")

    def capture_exec(executable, arguments, environment) -> None:
        captured.update(
            executable=executable,
            arguments=arguments,
            environment=environment,
        )
        raise OSError("do not replace the test process")

    monkeypatch.setattr(runtime.os, "execve", capture_exec)
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert (
        runtime.main(
            [
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--launch-provider",
                "codex",
                "--",
                "exec",
                "task",
            ]
        )
        == 2
    )

    assert captured["executable"] == "/bin/codex"
    assert captured["arguments"] == ["/bin/codex", "exec", "task"]
    launched = captured["environment"]
    assert isinstance(launched, dict)
    assert launched["AGENT_TOKEN"] == secret
    assert "UNDECLARED" not in launched
    assert not any(name.startswith("_AK_COPILOT_VALUE_") for name in launched)
    assert output.getvalue() == ""


def test_copilot_launcher_bridges_redacted_values_into_bash_only(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "copilot-provider-launch-secret-canary"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\n", encoding="utf-8")
    environment_file.chmod(0o600)
    captured: dict[str, object] = {}
    monkeypatch.setenv("_AK_COPILOT_VALUE_99", "stale")
    monkeypatch.setenv("AGENT_TOKEN", "provider-owned-value")
    monkeypatch.setattr(runtime.shutil, "which", lambda provider, path=None: "/bin/copilot")

    def capture_run(arguments, *, env, check):
        bash_env = Path(env["BASH_ENV"])
        captured.update(
            arguments=arguments,
            environment=env,
            bash_env=bash_env,
            bash_env_text=bash_env.read_text(encoding="utf-8"),
            bash_env_mode=bash_env.stat().st_mode & 0o777,
        )
        return runtime.subprocess.CompletedProcess(arguments, 0)

    monkeypatch.setattr(runtime.subprocess, "run", capture_run)
    monkeypatch.setattr(runtime.sys, "stdout", io.StringIO())

    assert (
        runtime.main(
            [
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--launch-provider",
                "copilot",
                "--",
                "--no-auto-update",
            ]
        )
        == 0
    )

    assert captured["arguments"] == [
        "/bin/copilot",
        "--bash-env=on",
        "--secret-env-vars=_AK_COPILOT_VALUE_0",
        "--no-auto-update",
    ]
    launched = captured["environment"]
    assert isinstance(launched, dict)
    assert launched["AGENT_TOKEN"] == "provider-owned-value"
    assert launched["_AK_COPILOT_VALUE_0"] == secret
    assert "_AK_COPILOT_VALUE_99" not in launched
    assert captured["bash_env_mode"] == 0o600
    assert secret in str(captured["bash_env_text"])
    assert "export AGENT_TOKEN" in str(captured["bash_env_text"])
    assert "unset BASH_ENV" in str(captured["bash_env_text"])
    assert not Path(captured["bash_env"]).exists()


@pytest.mark.parametrize(
    "argument",
    ["--bash-env=off", "--no-bash-env", "--secret-env-vars=OTHER_TOKEN"],
)
def test_copilot_launcher_rejects_caller_overrides_of_protection_flags(
    tmp_path: Path, monkeypatch, argument: str
) -> None:
    environment_file = tmp_path / "profile.env"
    environment_file.write_text("PROFILE_TOKEN=secret\n", encoding="utf-8")
    environment_file.chmod(0o600)
    error = io.StringIO()
    monkeypatch.setattr(runtime.shutil, "which", lambda provider, path=None: "/bin/copilot")
    monkeypatch.setattr(runtime.subprocess, "run", pytest.fail)
    monkeypatch.setattr(runtime.sys, "stderr", error)

    assert (
        runtime.main(
            [
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--launch-provider",
                "copilot",
                "--",
                argument,
            ]
        )
        == 2
    )
    assert "Profile credential activation failed" in error.getvalue()
    assert "secret" not in error.getvalue()


def test_removed_render_environment_mode_cannot_dump_a_profile_value(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "removed-render-secret-canary"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\n", encoding="utf-8")
    environment_file.chmod(0o600)
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert (
        runtime.main(
            [
                "--render-environment",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
            ]
        )
        == 0
    )
    assert output.getvalue() == ""


def test_provider_activation_failure_reports_only_value_free_remediation(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "provider-failure-secret-canary"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\n", encoding="utf-8")
    environment_file.chmod(0o600)
    error = io.StringIO()
    monkeypatch.setattr(runtime.shutil, "which", lambda provider, path=None: None)
    monkeypatch.setattr(runtime.sys, "stderr", error)

    assert (
        runtime.main(
            [
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--launch-provider",
                "codex",
            ]
        )
        == 2
    )

    assert "Profile credential activation failed" in error.getvalue()
    assert secret not in error.getvalue()


def test_claude_session_start_persists_only_declared_exports(tmp_path: Path, monkeypatch) -> None:
    secret = "hook-runtime-secret-canary"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\nUNDECLARED=ignore-me\n", encoding="utf-8")
    environment_file.chmod(0o600)
    claude_environment = tmp_path / "claude.env"
    claude_environment.write_text("", encoding="utf-8")
    claude_environment.chmod(0o600)
    state_directory = tmp_path / "session-state"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(claude_environment))
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-1"}'
                )
            },
        )(),
    )
    monkeypatch.setattr(runtime.sys, "stdout", io.StringIO())

    assert (
        runtime.main(
            [
                "--provider",
                "claude",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--environment-state-directory",
                str(state_directory),
            ]
        )
        == 0
    )

    assert claude_environment.read_text(encoding="utf-8") == (f"export AGENT_TOKEN={secret}\n")


def test_claude_session_start_creates_the_provider_environment_file(
    tmp_path: Path, monkeypatch
) -> None:
    environment_file = tmp_path / "profile.env"
    environment_file.write_text("PROFILE_TOKEN=created-file-secret\n", encoding="utf-8")
    environment_file.chmod(0o600)
    claude_environment = tmp_path / "claude.env"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(claude_environment))
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-create"}'
                )
            },
        )(),
    )
    monkeypatch.setattr(runtime.sys, "stdout", io.StringIO())

    assert (
        runtime.main(
            [
                "--provider",
                "claude",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--environment-state-directory",
                str(tmp_path / "session-state"),
            ]
        )
        == 0
    )

    assert claude_environment.read_text(encoding="utf-8") == (
        "export AGENT_TOKEN=created-file-secret\n"
    )
    assert claude_environment.stat().st_mode & 0o777 == 0o600


def test_claude_session_start_reports_missing_native_environment_channel(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "missing-claude-channel-secret"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\n", encoding="utf-8")
    environment_file.chmod(0o600)
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-missing-channel"}'
                )
            },
        )(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert (
        runtime.main(
            [
                "--provider",
                "claude",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--environment-state-directory",
                str(tmp_path / "session-state"),
            ]
        )
        == 0
    )

    context = json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]
    assert "Profile credential activation failed" in context
    assert secret not in output.getvalue()


def test_environment_binding_is_ignored_for_prompts_and_other_providers(
    tmp_path: Path, monkeypatch
) -> None:
    environment_file = tmp_path / "profile.env"
    environment_file.write_text("PROFILE_TOKEN=secret\n", encoding="utf-8")
    environment_file.chmod(0o600)
    destination = tmp_path / "claude.env"
    destination.write_text("", encoding="utf-8")
    destination.chmod(0o600)
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    for provider, payload in (
        (
            "claude",
            b'{"hook_event_name":"UserPromptSubmit","session_id":"prompt-1"}',
        ),
        (
            "codex",
            b'{"hook_event_name":"SessionStart","source":"startup","session_id":"codex-1"}',
        ),
    ):
        monkeypatch.setattr(
            runtime.sys,
            "stdin",
            type("Input", (), {"buffer": io.BytesIO(payload)})(),
        )
        assert (
            runtime.main(
                [
                    "--provider",
                    provider,
                    "--environment-file",
                    str(environment_file),
                    "--environment-map",
                    "PROFILE_TOKEN=AGENT_TOKEN",
                    "--environment-state-directory",
                    str(tmp_path / "session-state"),
                ]
            )
            == 0
        )

    assert destination.read_text(encoding="utf-8") == ""


def test_claude_resume_uses_the_environment_pinned_by_session(tmp_path: Path, monkeypatch) -> None:
    personal = tmp_path / "personal.env"
    work = tmp_path / "work.env"
    personal.write_text("PROFILE_TOKEN=personal-token\n", encoding="utf-8")
    work.write_text("PROFILE_TOKEN=work-token\n", encoding="utf-8")
    personal.chmod(0o600)
    work.chmod(0o600)
    state = tmp_path / "session-state"

    def invoke(*, source: str, session_id: str, selected: Path) -> str:
        destination = tmp_path / f"claude-{source}-{session_id}.env"
        destination.write_text("", encoding="utf-8")
        destination.chmod(0o600)
        monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
        monkeypatch.setattr(
            runtime.sys,
            "stdin",
            type(
                "Input",
                (),
                {
                    "buffer": io.BytesIO(
                        json.dumps(
                            {
                                "hook_event_name": "SessionStart",
                                "source": source,
                                "session_id": session_id,
                            }
                        ).encode()
                    )
                },
            )(),
        )
        monkeypatch.setattr(runtime.sys, "stdout", io.StringIO())
        assert (
            runtime.main(
                [
                    "--provider",
                    "claude",
                    "--environment-file",
                    str(selected),
                    "--environment-map",
                    "PROFILE_TOKEN=AGENT_TOKEN",
                    "--environment-state-directory",
                    str(state),
                ]
            )
            == 0
        )
        return destination.read_text(encoding="utf-8")

    assert invoke(source="startup", session_id="same-session", selected=personal) == (
        "export AGENT_TOKEN=personal-token\n"
    )
    assert invoke(source="resume", session_id="same-session", selected=work) == (
        "export AGENT_TOKEN=personal-token\n"
    )
    assert invoke(source="startup", session_id="new-session", selected=work) == (
        "export AGENT_TOKEN=work-token\n"
    )


def test_environment_failure_does_not_suppress_discovery_reminder(
    tmp_path: Path, monkeypatch
) -> None:
    environment_file = tmp_path / "unsafe.env"
    environment_file.write_text("PROFILE_TOKEN=secret\n", encoding="utf-8")
    environment_file.chmod(0o644)
    destination = tmp_path / "claude.env"
    destination.write_text("", encoding="utf-8")
    destination.chmod(0o600)
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-unsafe"}'
                )
            },
        )(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert (
        runtime.main(
            [
                "--provider",
                "claude",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--environment-state-directory",
                str(tmp_path / "session-state"),
            ]
        )
        == 0
    )

    assert "agent-knowledge describe" in output.getvalue()
    assert "Profile credential activation failed" in output.getvalue()
    assert destination.read_text(encoding="utf-8") == ""


def test_shell_control_target_is_rejected_without_exposing_or_persisting_value(
    tmp_path: Path, monkeypatch
) -> None:
    secret = "shell-control-secret-canary"
    environment_file = tmp_path / "profile.env"
    environment_file.write_text(f"PROFILE_TOKEN={secret}\n", encoding="utf-8")
    environment_file.chmod(0o600)
    destination = tmp_path / "claude.env"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-shell-control"}'
                )
            },
        )(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert (
        runtime.main(
            [
                "--provider",
                "claude",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=PS4",
                "--environment-state-directory",
                str(tmp_path / "session-state"),
            ]
        )
        == 0
    )

    assert "agent-knowledge describe" in output.getvalue()
    assert secret not in output.getvalue()
    assert not destination.exists()
    assert not list((tmp_path / "session-state").glob("*.json"))


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_claude_destination_fifo_fails_open_without_blocking(tmp_path: Path, monkeypatch) -> None:
    environment_file = tmp_path / "profile.env"
    environment_file.write_text("PROFILE_TOKEN=secret\n", encoding="utf-8")
    environment_file.chmod(0o600)
    destination = tmp_path / "claude.fifo"
    os.mkfifo(destination, mode=0o600)
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    b'{"hook_event_name":"SessionStart","source":"startup",'
                    b'"session_id":"runtime-fifo"}'
                )
            },
        )(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)

    assert (
        runtime.main(
            [
                "--provider",
                "claude",
                "--environment-file",
                str(environment_file),
                "--environment-map",
                "PROFILE_TOKEN=AGENT_TOKEN",
                "--environment-state-directory",
                str(tmp_path / "session-state"),
            ]
        )
        == 0
    )

    assert "agent-knowledge describe" in output.getvalue()
    assert destination.is_fifo()


def _profile_registry(home: Path, *, environment: bool = True) -> Path:
    registry = home / ".config/agent-knowledge/config.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)
    profile: dict[str, object] = {"config": "missing-workspace.yaml"}
    if environment:
        profile["environment"] = {
            "file": "profile.env",
            "variables": {
                "token": {
                    "from_env": "PROFILE_TOKEN",
                    "expose_as": "AGENT_TOKEN",
                    "description": "Tool token",
                }
            },
        }
        path = registry.parent / "profile.env"
        path.write_text(f"PROFILE_TOKEN={home.name}-secret\n", encoding="utf-8")
        path.chmod(0o600)
    registry.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-profiles.v1",
                "default_profile": "other",
                "profiles": {"personal": profile, "other": {"config": "other-missing.yaml"}},
            }
        ),
        encoding="utf-8",
    )
    return registry


def _invoke_profile_hook(monkeypatch, *arguments: str, session_id: str = "portable") -> str:
    monkeypatch.setattr(
        runtime.sys,
        "stdin",
        type(
            "Input",
            (),
            {
                "buffer": io.BytesIO(
                    json.dumps(
                        {
                            "hook_event_name": "SessionStart",
                            "source": "resume",
                            "session_id": session_id,
                        }
                    ).encode()
                )
            },
        )(),
    )
    output = io.StringIO()
    monkeypatch.setattr(runtime.sys, "stdout", output)
    assert runtime.main(["--provider", "claude", "--profile", "personal", *arguments]) == 0
    assert "agent-knowledge describe" in output.getvalue()
    return output.getvalue()


def test_profile_hook_resolves_runtime_home_and_pins_only_declarations(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("AGENT_KNOWLEDGE_SETTINGS", raising=False)
    for home in (tmp_path / "first", tmp_path / "second"):
        _profile_registry(home)
        monkeypatch.setenv("HOME", str(home))
        destination = home / "claude.env"
        monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
        output = _invoke_profile_hook(monkeypatch)
        assert "Profile credential activation failed" not in output
        assert destination.read_text() == f"export AGENT_TOKEN={home.name}-secret\n"
        state = home / ".local/state/agent-knowledge/claude-environment"
        assert state.stat().st_mode & 0o777 == 0o700
        pin = next(state.glob("*.json"))
        assert pin.stat().st_mode & 0o777 == 0o600
        assert f"{home.name}-secret" not in pin.read_text() + output


def test_profile_resume_retains_first_declaration_after_registry_changes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_KNOWLEDGE_SETTINGS", raising=False)
    registry = _profile_registry(tmp_path)
    destination = tmp_path / "claude.env"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    _invoke_profile_hook(monkeypatch)
    registry.write_text("malformed: [")
    output = _invoke_profile_hook(monkeypatch)
    assert "Profile credential activation failed" not in output
    assert destination.read_text().splitlines() == [
        f"export AGENT_TOKEN={tmp_path.name}-secret",
        f"export AGENT_TOKEN={tmp_path.name}-secret",
    ]
    output = _invoke_profile_hook(monkeypatch, session_id="new-session")
    assert "Profile credential activation failed" in output


@pytest.mark.parametrize(
    "failure",
    ["missing-registry", "malformed-registry", "missing-env", "unsafe-env", "malformed-env"],
)
def test_profile_hook_activation_failures_keep_reminders(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    registry = _profile_registry(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_KNOWLEDGE_SETTINGS", raising=False)
    destination = tmp_path / "claude.env"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    if failure == "missing-registry":
        registry.unlink()
    elif failure == "malformed-registry":
        registry.write_text("broken: [")
    elif failure == "missing-env":
        (registry.parent / "profile.env").unlink()
    elif failure == "malformed-env":
        (registry.parent / "profile.env").write_text("PROFILE_TOKEN=\n")
    else:
        (registry.parent / "profile.env").chmod(0o644)
    assert "Profile credential activation failed" in _invoke_profile_hook(monkeypatch)
    assert not destination.exists()


def test_profile_without_environment_requires_no_native_channel(
    tmp_path: Path, monkeypatch
) -> None:
    _profile_registry(tmp_path, environment=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AGENT_KNOWLEDGE_SETTINGS", raising=False)
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
    output = _invoke_profile_hook(monkeypatch)
    assert "Profile credential activation failed" not in output
    assert not (tmp_path / ".local/state/agent-knowledge/claude-environment").exists()


def test_hook_explicit_settings_wins_over_invalid_registry_override(tmp_path: Path, monkeypatch):
    registry = _profile_registry(tmp_path)
    destination = tmp_path / "claude.env"
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", "invalid-relative.yaml")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    state = tmp_path / "session-state"
    output = _invoke_profile_hook(
        monkeypatch, "--settings", str(registry), "--environment-state-directory", str(state)
    )
    assert "Profile credential activation failed" not in output
    assert destination.read_text() == f"export AGENT_TOKEN={tmp_path.name}-secret\n"


def test_profile_resume_ignores_new_profile_declaration_and_default(tmp_path: Path, monkeypatch):
    registry = _profile_registry(tmp_path)
    destination = tmp_path / "claude.env"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", str(registry))
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    _invoke_profile_hook(monkeypatch)
    data = yaml.safe_load(registry.read_text())
    data["default_profile"] = "personal"
    data["profiles"]["personal"]["environment"]["variables"]["token"]["expose_as"] = "NEW_TOKEN"
    registry.write_text(yaml.safe_dump(data))
    _invoke_profile_hook(monkeypatch)
    _invoke_profile_hook(monkeypatch, "--profile", "other")
    _invoke_profile_hook(monkeypatch, session_id="fresh")
    assert destination.read_text().splitlines() == [
        f"export AGENT_TOKEN={tmp_path.name}-secret",
        f"export AGENT_TOKEN={tmp_path.name}-secret",
        f"export AGENT_TOKEN={tmp_path.name}-secret",
        f"export NEW_TOKEN={tmp_path.name}-secret",
    ]


@pytest.mark.parametrize(
    "legacy", [["--environment-file", "/unused.env"], ["--environment-map", "A=B"]]
)
def test_profile_hook_rejects_legacy_override_flags(tmp_path: Path, monkeypatch, legacy) -> None:
    registry = _profile_registry(tmp_path)
    destination = tmp_path / "claude.env"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(destination))
    output = _invoke_profile_hook(monkeypatch, "--settings", str(registry), *legacy)
    assert "Profile credential activation failed" in output
    assert not destination.exists()


@pytest.mark.parametrize("provider", ["codex", "copilot"])
def test_provider_launcher_resolves_profile_from_custom_registry(
    tmp_path: Path, monkeypatch, provider: str
) -> None:
    registry = _profile_registry(tmp_path)
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", str(registry))
    monkeypatch.setattr(runtime.shutil, "which", lambda provider, path=None: f"/bin/{provider}")
    captured = {}

    def capture_exec(executable, arguments, environment):
        captured.update(environment)
        raise OSError("avoid executing provider")

    def capture_copilot(executable, arguments, environment, values):
        captured.update(values)
        return 0

    monkeypatch.setattr(runtime.os, "execve", capture_exec)
    monkeypatch.setattr(runtime, "_run_copilot", capture_copilot)
    assert runtime.main(["--profile", "personal", "--launch-provider", provider]) == (
        2 if provider == "codex" else 0
    )
    assert captured["AGENT_TOKEN"] == f"{tmp_path.name}-secret"
