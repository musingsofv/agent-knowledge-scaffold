"""Check evidence preservation when continuing bounded live onboarding acceptance."""

import importlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(ROOT / "tests/e2e"))
    return importlib.import_module("setup_onboarding_acceptance")


def test_resume_preparation_preserves_source_and_failed_provider_result(
    tmp_path: Path, driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    consumer = tmp_path / "studio"
    consumer.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    events = [
        {"type": "system", "subtype": "init", "model": "claude-opus-5", "session_id": "session-a"},
        {
            "type": "result",
            "is_error": True,
            "terminal_reason": "budget_exhausted",
            "total_cost_usd": 2.1,
        },
    ]
    previous_log = logs / "marketing.log"
    previous_log.write_text("\n".join(json.dumps(event) for event in events))
    report = {
        "schema": "setup-onboarding-acceptance.v1",
        "status": "failed",
        "consumer": str(consumer),
        "diagnostic": "Previous provider budget cap.",
        "turns": [
            {"phase": phase, "session_id": "session-a"}
            for phase in ("proposal", "configure", "repeat")
        ],
    }
    source = tmp_path / "failed.json"
    source.write_text(json.dumps(report))
    original = source.read_bytes()
    log_bytes = previous_log.read_bytes()

    def forbidden(*args, **kwargs):
        pytest.fail("Preparation must not invoke a provider or repeat setup.")

    monkeypatch.setattr(driver, "_run", forbidden)
    continued = driver.resume(source, tmp_path / "runtime.whl", live=False, timeout=10, budget=4)

    assert continued["status"] == "prepared"
    assert continued["turns"][:3] == report["turns"]
    failed = continued["turns"][-1]
    assert failed["phase"] == "marketing"
    assert failed["status"] == "failed"
    assert failed["provider_terminal_reason"] == "budget_exhausted"
    preserved = Path(continued["resume_history"][-1]["preserved_report"])
    assert preserved.read_bytes() == source.read_bytes() == original
    assert previous_log.read_bytes() == log_bytes


def test_provider_timeout_keeps_partial_output_and_explicit_failure(
    tmp_path: Path, driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "attempt.log"
    partial = json.dumps(
        {"type": "system", "subtype": "init", "model": "claude-opus-5", "session_id": "session-a"}
    )

    def timed_out(*args, **kwargs):
        log.write_text("TIMEOUT\n")
        raise driver.HarnessSmokeFailure("Timed out", log=log) from subprocess.TimeoutExpired(
            "claude", 10, output=partial.encode()
        )

    monkeypatch.setattr(driver, "_run", timed_out)
    report = {"turns": []}
    with pytest.raises(driver.HarnessSmokeFailure, match="timeout"):
        driver._provider_turn(
            "claude",
            "claude",
            consumer=tmp_path,
            env={},
            log=log,
            session="session-a",
            label="marketing-resume",
            prompt="Continue",
            timeout=10,
            budget=4,
            copilot_credits=30,
            report=report,
        )
    assert report["turns"][0]["status"] == "failed"
    assert report["turns"][0]["provider_terminal_reason"] == "timeout"
    assert partial in log.read_text()


def test_codex_commands_start_a_persisted_thread_then_resume_it(tmp_path: Path, driver) -> None:
    first = driver._provider_command(
        "codex",
        "codex",
        consumer=tmp_path,
        session=None,
        prompt="propose",
        first=True,
        budget=4,
        copilot_credits=30,
    )
    resumed = driver._provider_command(
        "codex",
        "codex",
        consumer=tmp_path,
        session="thread-a",
        prompt="configure",
        first=False,
        budget=4,
        copilot_credits=30,
    )

    assert first[:3] == ["codex", "exec", "--json"]
    assert "--ephemeral" not in first
    assert first[-1] == "propose"
    assert resumed[:4] == ["codex", "exec", "resume", "--json"]
    assert resumed[-2:] == ["thread-a", "configure"]


def test_claude_command_keeps_the_existing_model_and_session_contract(
    tmp_path: Path, driver
) -> None:
    command = driver._provider_command(
        "claude",
        "claude",
        consumer=tmp_path,
        session="session-a",
        prompt="configure",
        first=False,
        budget=4,
        copilot_credits=30,
    )

    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--setting-sources") + 1] == "project,local"
    assert command[command.index("--max-budget-usd") + 1] == "4"
    assert command[-4:] == ["--resume", "session-a", "-p", "configure"]


def test_copilot_commands_pin_one_bounded_session_and_disable_remote_surfaces(
    tmp_path: Path, driver
) -> None:
    first = driver._provider_command(
        "copilot",
        "copilot",
        consumer=tmp_path,
        session="00000000-0000-4000-8000-000000000001",
        prompt="propose",
        first=True,
        budget=4,
        copilot_credits=30,
    )
    resumed = driver._provider_command(
        "copilot",
        "copilot",
        consumer=tmp_path,
        session="00000000-0000-4000-8000-000000000001",
        prompt="configure",
        first=False,
        budget=4,
        copilot_credits=30,
    )

    assert "--session-id=00000000-0000-4000-8000-000000000001" in first
    assert "--resume=00000000-0000-4000-8000-000000000001" in resumed
    for command in (first, resumed):
        assert command[0] == "copilot"
        assert command[command.index("--model") + 1] == "auto"
        assert command[command.index("--auto-tier") + 1] == "efficiency"
        assert command[command.index("--max-ai-credits") + 1] == "30"
        assert "--output-format" in command
        assert "--no-auto-update" in command
        assert "--no-remote" in command
        assert "--no-remote-export" in command
        assert "--disable-builtin-mcps" in command
        assert "--allow-all" not in command
        assert "--allow-all-tools" in command
        assert "--allow-all-paths" not in command
        assert "--disallow-temp-dir" in command
        assert "--deny-url=*" in command
        assert command[command.index("--add-dir") + 1] == "."


def test_copilot_timeout_retains_the_preselected_session(
    tmp_path: Path, driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "attempt.log"
    session = "00000000-0000-4000-8000-000000000001"

    def timed_out(*args, **kwargs):
        log.write_text("TIMEOUT\n")
        raise driver.HarnessSmokeFailure("Timed out", log=log) from subprocess.TimeoutExpired(
            "copilot", 10
        )

    monkeypatch.setattr(driver, "_run", timed_out)
    report = {"turns": []}
    with pytest.raises(driver.HarnessSmokeFailure, match="timeout"):
        driver._provider_turn(
            "copilot",
            "copilot",
            consumer=tmp_path,
            env={},
            log=log,
            session=session,
            label="marketing-resume",
            prompt="Continue",
            timeout=10,
            budget=4,
            copilot_credits=30,
            report=report,
        )

    assert report["turns"][0]["status"] == "failed"
    assert report["turns"][0]["provider_terminal_reason"] == "timeout"
    assert report["turns"][0]["session_id"] == session


def test_provider_evidence_parses_codex_and_copilot_jsonl(tmp_path: Path, driver) -> None:
    codex = driver._provider_evidence(
        "codex",
        "proposal",
        [
            {"type": "thread.started", "thread_id": "thread-a"},
            {
                "type": "item.completed",
                "item": {"type": "command_execution", "command": "agent-knowledge context"},
            },
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Ready"},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 10}},
        ],
        tmp_path / "codex.log",
    )
    copilot = driver._provider_evidence(
        "copilot",
        "proposal",
        [
            {
                "type": "session.auto_mode_resolved",
                "data": {"chosenModel": "gpt-test"},
            },
            {
                "type": "tool.execution_start",
                "data": {
                    "toolName": "bash",
                    "arguments": {"command": "agent-knowledge context"},
                },
            },
            {
                "type": "assistant.message",
                "data": {"phase": "final_answer", "content": "Ready", "model": "gpt-test"},
            },
            {
                "type": "result",
                "sessionId": "session-a",
                "exitCode": 0,
                "usage": {"premiumRequests": 1},
            },
        ],
        tmp_path / "copilot.log",
    )

    assert codex["phase"] == "proposal"
    assert codex["session_id"] == "thread-a"
    assert codex["status"] == "passed"
    assert codex["response"] == "Ready"
    assert codex["commands"] == ["agent-knowledge context"]
    assert copilot["phase"] == "proposal"
    assert copilot["session_id"] == "session-a"
    assert copilot["model"] == "gpt-test"
    assert copilot["status"] == "passed"
    assert copilot["response"] == "Ready"
    assert copilot["commands"] == ["agent-knowledge context"]
    assert copilot["credits_used"] == 1


def test_fresh_signal_storage_requires_checkout_below_code_root(tmp_path: Path, driver) -> None:
    consumer = tmp_path / "studio"
    consumer.mkdir()
    config = consumer / "knowledge-workspace.yaml"
    config.write_text(
        "signal_storage:\n  scaffold_root: .\n  code_root: ..\n",
        encoding="utf-8",
    )

    driver._assert_fresh_signal_storage(config, consumer)

    config.write_text(
        "signal_storage:\n  scaffold_root: .\n  code_root: .\n",
        encoding="utf-8",
    )
    with pytest.raises(driver.HarnessSmokeFailure, match="strictly below"):
        driver._assert_fresh_signal_storage(config, consumer)


@pytest.mark.parametrize(
    ("provider", "session", "events"),
    [
        (
            "codex",
            None,
            [
                {"type": "thread.started", "thread_id": "thread-a"},
                {"type": "turn.completed"},
            ],
        ),
        (
            "copilot",
            "00000000-0000-4000-8000-000000000001",
            [
                {
                    "type": "session.auto_mode_resolved",
                    "data": {"chosenModel": "gpt-test"},
                },
                {
                    "type": "result",
                    "sessionId": "00000000-0000-4000-8000-000000000001",
                    "exitCode": 0,
                },
            ],
        ),
    ],
)
def test_provider_turn_returns_the_exact_native_session(
    tmp_path: Path,
    driver,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    session: str | None,
    events: list[dict[str, object]],
) -> None:
    stdout = "\n".join(json.dumps(event) for event in events)

    def completed(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(driver, "_run", completed)
    report = {"turns": []}

    _, actual = driver._provider_turn(
        provider,
        provider,
        consumer=tmp_path,
        env={},
        log=tmp_path / f"{provider}.log",
        session=session,
        label="proposal",
        prompt="Propose",
        timeout=10,
        budget=4,
        copilot_credits=30,
        report=report,
        first=True,
    )

    assert actual == ("thread-a" if provider == "codex" else session)
    assert report["turns"][0]["status"] == "passed"


def test_provider_turn_rejects_a_different_resumed_session(
    tmp_path: Path, driver, monkeypatch: pytest.MonkeyPatch
) -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "thread-b"}),
            json.dumps({"type": "turn.completed"}),
        ]
    )

    def completed(*args, **kwargs):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(driver, "_run", completed)

    with pytest.raises(driver.HarnessSmokeFailure, match="preserve the provider session ID"):
        driver._provider_turn(
            "codex",
            "codex",
            consumer=tmp_path,
            env={},
            log=tmp_path / "codex.log",
            session="thread-a",
            label="configure",
            prompt="Configure",
            timeout=10,
            budget=4,
            copilot_credits=30,
            report={"turns": []},
        )


@pytest.mark.parametrize(
    ("provider", "relative"),
    [
        ("codex", ".agents/skills/knowledge-setup/SKILL.md"),
        ("claude", ".claude/skills/knowledge-setup/SKILL.md"),
        ("copilot", ".agents/skills/knowledge-setup/SKILL.md"),
    ],
)
def test_provider_uses_its_installed_setup_skill(
    tmp_path: Path, driver, provider: str, relative: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("# setup\n")

    assert driver._skill_path(tmp_path, provider) == path
