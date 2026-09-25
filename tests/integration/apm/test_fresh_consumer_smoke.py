"""Exercise the fresh-consumer hook-registration proof without a full consumer run."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "tests" / "e2e" / "fresh_consumer_smoke.py"
_PACKAGE_SOURCE = "_local/knowledge-agent-pack"


def _smoke_module():
    e2e_root = str(SMOKE.parent)
    sys.path.insert(0, e2e_root)
    try:
        spec = importlib.util.spec_from_file_location("fresh_consumer_smoke_under_test", SMOKE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(e2e_root)


def _package_group(command: str) -> dict[str, object]:
    return {
        "hooks": [{"type": "command", "command": command}],
        "_apm_source": _PACKAGE_SOURCE,
    }


def _runtime_group(command: str) -> dict[str, object]:
    return {"hooks": [{"type": "command", "command": command}]}


def _write_consumer_hooks(
    consumer: Path, *, command: str | dict[str, str], copilot_events: tuple[str, ...]
) -> bytes:
    def selected(provider: str) -> str:
        return command[provider] if isinstance(command, dict) else command

    codex = consumer / ".codex" / "hooks.json"
    claude = consumer / ".claude" / "settings.json"
    copilot_authored = consumer / ".github" / "hooks" / "hand-authored.json"
    for path in (codex, claude, copilot_authored):
        path.parent.mkdir(parents=True, exist_ok=True)

    codex.write_text(
        json.dumps(
            {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "hand-authored-codex"}]},
                    _runtime_group(selected("codex")),
                ],
                "UserPromptSubmit": [_runtime_group(selected("codex"))],
            }
        ),
        encoding="utf-8",
    )
    claude.write_text(
        json.dumps(
            {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "hand-authored-claude"}]},
                    _runtime_group(selected("claude")),
                ],
                "UserPromptSubmit": [_runtime_group(selected("claude"))],
            }
        ),
        encoding="utf-8",
    )
    copilot_authored.write_text(
        json.dumps(
            {
                "hooks": {
                    "sessionStart": [
                        {"hooks": [{"type": "command", "command": "hand-authored-copilot"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    for provider in ("codex", "claude"):
        sidecar = consumer / f".{provider}" / "apm-hooks.json"
        sidecar.write_text(
            json.dumps(
                {
                    "SessionStart": [_package_group(selected(provider))],
                    "UserPromptSubmit": [_package_group(selected(provider))],
                }
            ),
            encoding="utf-8",
        )
    if copilot_events:
        package_copilot = (
            consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"
        )
        package_copilot.write_text(
            json.dumps(
                {
                    "hooks": {
                        event: [{"hooks": [{"type": "command", "command": selected("copilot")}]}]
                        for event in copilot_events
                    },
                    "version": 1,
                }
            ),
            encoding="utf-8",
        )
    return copilot_authored.read_bytes()


def test_recovery_proof_requires_exact_launcher_and_copilot_lifecycle(tmp_path: Path) -> None:
    module = _smoke_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    launcher = consumer / ".agent-knowledge-venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    authored = _write_consumer_hooks(
        consumer,
        command="agent-knowledge-hook",
        copilot_events=("sessionStart",),
    )
    with pytest.raises(module.SmokeFailure, match="exact expected launcher"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=True,
            hook_launcher=launcher,
        )

    exact_command = {
        provider: module._expected_hook_command(
            launcher,
            provider,
            "sessionStart" if provider == "copilot" else "SessionStart",
            None,
        )
        for provider in ("codex", "claude", "copilot")
    }
    authored = _write_consumer_hooks(
        consumer,
        command=exact_command,
        copilot_events=("sessionStart", "userPromptSubmit"),
    )
    with pytest.raises(module.SmokeFailure, match="unsupported or missing events"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=True,
            hook_launcher=launcher,
        )

    authored = _write_consumer_hooks(
        consumer,
        command=exact_command,
        copilot_events=("sessionStart",),
    )
    with pytest.raises(module.SmokeFailure, match="unsupported or missing events"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=True,
            hook_launcher=launcher,
        )

    authored = _write_consumer_hooks(
        consumer,
        command=exact_command,
        copilot_events=("sessionStart", "userPromptTransformed"),
    )
    module._hook_registration_proof(
        consumer,
        copilot_authored=authored,
        package_present=True,
        hook_launcher=launcher,
    )


def test_uninstall_proof_rejects_a_partially_removed_package_group(tmp_path: Path) -> None:
    module = _smoke_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    authored = _write_consumer_hooks(
        consumer,
        command="agent-knowledge-hook",
        copilot_events=(),
    )
    for provider in ("codex", "claude"):
        (consumer / f".{provider}" / "apm-hooks.json").unlink()
    codex = consumer / ".codex" / "hooks.json"
    document = json.loads(codex.read_text(encoding="utf-8"))
    document["UserPromptSubmit"] = []
    codex.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(module.SmokeFailure, match="Unexpected merged codex SessionStart"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=False,
        )
