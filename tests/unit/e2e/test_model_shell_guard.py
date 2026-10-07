"""Model worker detection examines commands rather than documentation prose."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "e2e/model_shell_guard.py"
spec = importlib.util.spec_from_file_location("model_shell_guard_under_test", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "command",
    [
        "codex exec 'work'",
        "/opt/bin/claude -p 'work'",
        "copilot -p 'work'",
        "env -u GH_TOKEN NAME=value codex exec work",
        "cat file; codex exec work",
        "cat file\nclaude -p work",
        "sh -lc 'copilot -p work'",
        "exec codex resume session",
    ],
)
def test_rejects_model_executable_launch(command):
    with pytest.raises(ValueError, match="native subagent"):
        module.reject_model_shell_launch(command)


@pytest.mark.parametrize(
    "command",
    [
        "cat docs/claude.md",
        "printf '%s' 'codex exec example'",
        "rg 'claude -p' docs",
        "cat <<'DOC'\ncodex exec example\nDOC",
        "codex --version",
        "copilot --help",
        "agent-knowledge describe",
        'sh -lc "cat docs/guide.md"',
    ],
)
def test_prose_and_readonly_version_checks_are_not_workers(command):
    module.reject_model_shell_launch(command)
