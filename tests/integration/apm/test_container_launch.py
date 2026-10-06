"""Keep actual container launches pinned to checked setup routes without shell eval."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.apm.test_setup_runtime import _setup_module

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT / "packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/launch_container.py"
)


def _module():
    spec = importlib.util.spec_from_file_location("container_launcher", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def launch_fixture(tmp_path, monkeypatch):
    setup = _setup_module()
    context = {
        "workspace_id": "workspace:example",
        "environment": None,
        "selection": {"profile": "example", "settings_path": str(tmp_path / "registry.yaml")},
    }
    environment = {
        "providers": {"codex": {"status": "cli-launch", "command": "'/runtime path/loader' codex"}}
    }
    recipe = setup._launch_report(
        context,
        environment,
        launcher=tmp_path / "venv/bin/agent-knowledge",
        selector=["--profile", "example"],
        venv=tmp_path / "venv",
        consumer=tmp_path,
        targets=("codex",),
        hooks_ready=True,
    )
    report = {"schema": "knowledge-setup-runtime.v1", "status": "ok", "launch": recipe}
    result = {
        "schema_version": "knowledge-preflight.v1",
        "status": "ok",
        "selection": recipe["selection"],
        "environment_declaration": None,
    }
    calls = []
    module = _module()

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(result), "")

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setenv("PATH", "/consumer/bin")
    return module, report, result, calls


def test_launch_checks_inherited_route_and_preserves_provider_arguments(launch_fixture):
    module, report, _, calls = launch_fixture
    args = ["--config", "value with spaces", "$(never run)", "--"]
    command, environment, cwd = module.prepare_launch(report, "codex", args)
    assert command == ["/runtime path/loader", "codex", *args]
    assert environment["PATH"].endswith(":/consumer/bin")
    assert environment["AGENT_KNOWLEDGE_SETTINGS"] == report["launch"]["settings"]
    assert cwd == report["launch"]["cwd"]
    assert len(calls) == 1
    _, options = calls[0]
    assert options["env"] == environment
    assert json.loads(options["input"])["expected_execution"] == "container"
    assert json.loads(options["input"])["mode"] == "read"
    assert "shell" not in options


def test_pending_provider_cannot_launch_or_run_preflight(launch_fixture):
    module, report, _, calls = launch_fixture
    with pytest.raises(module.LaunchFailure, match="pending"):
        module.prepare_launch(report, "claude", [])
    assert not calls


@pytest.mark.parametrize("changed", ["selection", "environment_declaration"])
def test_stale_recipe_requires_setup_before_activation(launch_fixture, changed):
    module, report, result, _ = launch_fixture
    result[changed] = {"changed": True}
    with pytest.raises(module.LaunchFailure, match="changed"):
        module.prepare_launch(report, "codex", [])


def test_preflight_failure_does_not_echo_uncontrolled_output(launch_fixture, monkeypatch, capsys):
    module, report, _, _ = launch_fixture
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 2, "FIXTURE_SECRET", "OTHER_SECRET"
        ),
    )
    with pytest.raises(module.LaunchFailure, match="no valid report") as error:
        module.prepare_launch(report, "codex", [])
    assert "SECRET" not in str(error.value)
    assert "SECRET" not in capsys.readouterr().err


def test_managed_install_refuses_omitted_existing_target_before_mutation(tmp_path):
    setup = _setup_module()
    path = tmp_path / ".claude/settings.json"
    path.parent.mkdir()
    path.write_text('{"hooks":{"user-owned":"preserve"}}')
    before = path.read_bytes()
    with pytest.raises(setup.SetupFailure, match="claude"):
        setup._guard_managed_targets(tmp_path, ("codex",))
    assert path.read_bytes() == before
    setup._guard_managed_targets(tmp_path, ("codex", "claude"))


def test_setup_launch_recipe_keeps_blank_credentials_pending(tmp_path):
    setup = _setup_module()
    report = setup._launch_report(
        {"environment": None, "selection": {}, "workspace_id": "workspace:example"},
        {"providers": {"codex": {"status": "pending"}}},
        launcher=tmp_path / "bin/agent-knowledge",
        selector=["--config", str(tmp_path / "workspace.yaml")],
        venv=tmp_path,
        consumer=tmp_path,
        targets=("codex",),
        hooks_ready=True,
    )
    assert report["providers"]["codex"] == {"status": "pending", "argv": None}


@pytest.mark.parametrize("path", [None, ""])
def test_absent_path_never_adds_consumer_directory(launch_fixture, monkeypatch, path):
    module, report, _, _ = launch_fixture
    if path is None:
        monkeypatch.delenv("PATH", raising=False)
    else:
        monkeypatch.setenv("PATH", path)
    _, environment, _ = module.prepare_launch(report, "codex", [])
    assert environment["PATH"] == report["launch"]["path_prepend"]


@pytest.mark.parametrize("evidence", ["skills", "lock", "deployed-files", "unknown-lock"])
def test_managed_install_preserves_skills_only_target(tmp_path, evidence):
    setup = _setup_module()
    if evidence == "skills":
        (tmp_path / ".claude/skills/local").mkdir(parents=True)
    else:
        content = {
            "lock": (
                "deployments:\n- kind: project-relative\n  target: claude\n"
                "  value: .claude/skills/local/SKILL.md\n"
            ),
            "deployed-files": (
                "dependencies:\n- deployed_files:\n"
                "    .claude/skills/local/SKILL.md: sha256:fixture\n"
            ),
            "unknown-lock": "deployments: [{target: claude}]\n",
        }[evidence]
        (tmp_path / "apm.lock.yaml").write_text(content)
    with pytest.raises(setup.SetupFailure):
        setup._guard_managed_targets(tmp_path, ("codex",))
    if evidence != "unknown-lock":
        setup._guard_managed_targets(tmp_path, ("codex", "claude"))
