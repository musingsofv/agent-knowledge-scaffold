"""Verify real installed runtimes without provisioning or mutating their files."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.factories import catalog_data
from tests.integration.apm.test_setup_runtime import ROOT, _install_setup_fixture, _setup_module


def _command(arguments: list[str]) -> None:
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def reference_package(tmp_path_factory):
    directory = tmp_path_factory.mktemp("runtime-reference")
    source = directory / "source"
    source.mkdir()
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__"))
    (source / "docs").mkdir()
    shutil.copy2(ROOT / "docs/agent-contract.md", source / "docs/agent-contract.md")
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(ROOT / filename, source / filename)
    uv = shutil.which("uv")
    assert uv is not None, "Repository tests require uv"
    _command([uv, "build", "--wheel", "--out-dir", str(directory / "dist"), str(source)])
    return source, next((directory / "dist").glob("*.whl")), uv


@pytest.fixture
def installed_runtime(tmp_path, reference_package):
    source, wheel, uv = reference_package
    venv = tmp_path / "runtime"
    _command([uv, "venv", "--python", sys.executable, "--no-python-downloads", str(venv)])
    _command([uv, "pip", "install", "--python", str(venv / "bin/python"), str(wheel)])
    return _setup_module(), source, wheel, venv


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _consumer(tmp_path: Path) -> tuple[Path, Path]:
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "knowledge").mkdir()
    (consumer / "catalog.yaml").write_text(json.dumps(catalog_data()))
    workspace = consumer / "knowledge-workspace.yaml"
    workspace.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "workspace:example",
                "applicable_scopes": ["org:example"],
                "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
            }
        )
    )
    return consumer, workspace


@pytest.mark.parametrize("reference", ["source", "wheel"])
def test_existing_runtime_verifies_actual_payload_without_changes(installed_runtime, reference):
    module, source, wheel, venv = installed_runtime
    before = _snapshot(venv)
    python, launcher, report = module._verify_existing_runtime(
        venv, source if reference == "source" else wheel, []
    )
    assert python == venv / "bin/python"
    assert launcher == venv / "bin/agent-knowledge"
    assert report["mode"] == "existing"
    assert report["status"] == "verified"
    assert len(report["payload_sha256"]) == 64
    assert _snapshot(venv) == before


def test_same_version_with_changed_contents_is_rejected(installed_runtime):
    module, _, wheel, venv = installed_runtime
    package = next(venv.glob("lib/python*/site-packages/agent_knowledge"))
    with (package / "__init__.py").open("a") as stream:
        stream.write("\n# Deliberately different runtime bytes; metadata version is unchanged.\n")
    before = _snapshot(venv)
    with pytest.raises(module.SetupFailure) as error:
        module._verify_existing_runtime(venv, wheel, [])
    assert error.value.code == "runtime-package-mismatch"
    assert _snapshot(venv) == before


def test_changed_hook_launcher_is_rejected(installed_runtime):
    module, _, wheel, venv = installed_runtime
    hook = venv / "bin/agent-knowledge-hook"
    hook.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(module.SetupFailure) as error:
        module._verify_existing_runtime(venv, wheel, [])
    assert error.value.code == "runtime-contents-unverified"


def test_relocated_runtime_rejects_launchers_bound_to_original_venv(installed_runtime, tmp_path):
    module, _, wheel, original = installed_runtime
    relocated = tmp_path / "relocated-runtime"
    shutil.copytree(original, relocated, symlinks=True)
    before = _snapshot(relocated)
    assert (original / "bin/python").exists()
    with pytest.raises(module.SetupFailure) as error:
        module._verify_existing_runtime(relocated, wheel, [])
    assert error.value.code == "runtime-contents-unverified"
    assert _snapshot(relocated) == before


def test_existing_mode_does_not_create_an_absent_venv(tmp_path):
    module = _setup_module()
    missing = tmp_path / "missing"
    with pytest.raises(module.SetupFailure):
        module._verify_existing_runtime(missing, ROOT, [])
    assert not missing.exists()


def test_existing_prepare_and_bind_need_no_uv_and_leave_runtime_unchanged(
    installed_runtime, tmp_path, monkeypatch
):
    module, _, wheel, venv = installed_runtime
    consumer, workspace = _consumer(tmp_path)
    settings = tmp_path / "profiles.yaml"
    settings.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-profiles.v1",
                "profiles": {"example": {"config": str(workspace)}},
            }
        )
    )
    monkeypatch.setenv("PATH", str(venv / "bin"))
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", str(settings))
    assert shutil.which("uv") is None
    before = _snapshot(venv)
    arguments = dict(
        workspace=workspace,
        venv=venv,
        package=wheel,
        consumer=consumer,
        target_text="codex,claude,copilot",
        settings=settings,
        profile="example",
        runtime_mode="existing",
        portable_hooks=True,
    )
    prepared = module.run_setup(**arguments, apm_mode="prepare")
    assert prepared["hooks"]["status"] == "pending"
    assert not (consumer / "apm.lock.yaml").exists()
    _install_setup_fixture(module, consumer)
    bound = module.run_setup(**arguments, apm_mode="bind")
    assert bound["hooks"]["status"] == "ready"
    assert bound["runtime"]["status"] == "verified"
    assert module.run_setup(**arguments, apm_mode="bind")["apm_lock"]["status"] == "current"
    assert _snapshot(venv) == before
    assert all(step["name"] != "runtime-install" for step in bound["steps"])


def test_existing_mode_prevents_absolute_credential_launcher_writes(installed_runtime, tmp_path):
    module, _, _, venv = installed_runtime
    environment = {
        "environment": {
            "status": "ready",
            "file": str(tmp_path / "private.env"),
            "variables": [
                {
                    "label": "example",
                    "from_env": "EXAMPLE_TOKEN",
                    "expose_as": "GH_TOKEN",
                    "description": "Fictional mapping",
                }
            ],
        },
    }
    before = _snapshot(venv)
    with pytest.raises(module.SetupFailure) as error:
        module._environment_launcher(
            environment,
            venv,
            [],
            consumer=tmp_path,
            allow_runtime_writes=False,
        )
    assert error.value.code == "existing-runtime-portable-required"
    report = module._environment_launcher(
        environment,
        venv,
        [],
        consumer=tmp_path,
        allow_runtime_writes=False,
        targets=(),
    )
    assert all(provider["status"] == "not-bound" for provider in report["providers"].values())
    assert _snapshot(venv) == before
