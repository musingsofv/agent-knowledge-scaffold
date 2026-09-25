"""Verify the setup helper's package-owned hook registration checks."""

import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent_knowledge.domain import profiles as profile_domain
from tests.factories import catalog_data

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    ROOT
    / "packages"
    / "knowledge-agent-pack"
    / ".apm"
    / "skills"
    / "knowledge-setup"
    / "scripts"
    / "setup_runtime.py"
)


def _setup_module():
    spec = importlib.util.spec_from_file_location("knowledge_setup_runtime", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _package_root(
    consumer: Path,
    source: str = "_local/knowledge-agent-pack",
    *,
    dependency: dict[str, object] | None = None,
) -> Path:
    hooks = consumer / "apm_modules" / source / ".apm" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "knowledge-discovery.json").write_text("{}\n", encoding="utf-8")
    if dependency is None:
        dependency = {"repo_url": source, "name": Path(source).name}
        if source.startswith("_local/"):
            dependency.update(source="local", local_path=f"./packages/{Path(source).name}")
        elif "/packages/" in source:
            repo, package = source.split("/packages/", 1)
            dependency.update(repo_url=repo, is_virtual=True, virtual_path=f"packages/{package}")
    lock = consumer / "apm.lock.yaml"
    document = (
        yaml.safe_load(lock.read_text())
        if lock.exists()
        else {"lockfile_version": "1", "dependencies": []}
    )
    document["dependencies"].append(dependency)
    lock.write_text(yaml.safe_dump(document, sort_keys=False))
    return hooks.parent.parent


@pytest.fixture
def setup_consumer(tmp_path: Path, monkeypatch):
    """Use real CLI readiness, replacing only runtime provisioning and APM execution."""
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "knowledge").mkdir()
    (consumer / "catalog.yaml").write_text(json.dumps(catalog_data()))
    workspace = consumer / "workspace.yaml"
    workspace.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
            }
        )
    )
    env_file = tmp_path / "profile.env"
    env_file.write_text("SOURCE_TOKEN=\n")
    env_file.chmod(0o600)
    settings = tmp_path / "profiles.yaml"
    settings.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-profiles.v1",
                "profiles": {
                    "example": {
                        "config": str(workspace),
                        "environment": {
                            "file": str(env_file),
                            "variables": {
                                "github": {
                                    "from_env": "SOURCE_TOKEN",
                                    "expose_as": "GH_TOKEN",
                                    "description": "Fixture credential",
                                }
                            },
                        },
                    }
                },
            }
        )
    )
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    launcher = venv / "bin" / "agent-knowledge"
    launcher.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} "
        '-m agent_knowledge.entrypoints.cli.main "$@"\n'
    )
    launcher.chmod(0o700)
    hook = venv / "bin" / "agent-knowledge-hook"
    hook.write_text("#!/bin/sh\n")
    commands = []
    run = module._run

    def execute(command, **kwargs):
        commands.append(command)
        if command[0] == "/fixture/uv":
            return subprocess.CompletedProcess(command, 0, "", "")
        assert command[0] != "/fixture/apm", "Staged setup must not run APM"
        return run(command, **kwargs)

    monkeypatch.setattr(module, "_run", execute)
    monkeypatch.setattr(module, "_prepare_venv", lambda *_: (Path(sys.executable), launcher))
    monkeypatch.setattr(module, "_venv_executables", lambda *_: (Path(sys.executable), launcher))
    monkeypatch.setattr(
        module.shutil, "which", lambda name: "/fixture/uv" if name == "uv" else None
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    args = dict(
        workspace=workspace,
        venv=venv,
        package=ROOT,
        consumer=consumer,
        target_text="codex,claude,copilot",
        settings=settings,
        profile="example",
    )
    return module, args, env_file, commands


def _install_setup_fixture(
    module, consumer: Path, source: str = "_local/knowledge-agent-pack"
) -> None:
    package = _package_root(consumer, source)
    descriptor = ROOT / "packages/knowledge-agent-pack/.apm/hooks/knowledge-discovery.json"
    (package / ".apm/hooks/knowledge-discovery.json").write_bytes(descriptor.read_bytes())
    _write_registration_files(consumer, module._DESCRIPTOR_HOOK_COMMAND, source=source)
    lock = consumer / "apm.lock.yaml"
    document = yaml.safe_load(lock.read_text())
    path = ".github/hooks/knowledge-agent-pack-knowledge-discovery.json"
    document["dependencies"][0]["deployed_file_hashes"] = {path: "sha256:stale"}
    document["deployments"] = [
        {
            "kind": "project-relative",
            "target": "copilot",
            "value": path,
            "content_hash": "sha256:stale",
        }
    ]
    lock.write_text(yaml.safe_dump(document, sort_keys=False))


def test_prepare_keeps_targets_and_consumer_unchanged_with_blank_credentials(setup_consumer):
    module, args, _, commands = setup_consumer
    before = {
        p.relative_to(args["consumer"]): p.read_bytes()
        for p in args["consumer"].rglob("*")
        if p.is_file()
    }
    report = module.run_setup(**args, apm_mode="prepare")
    after = {
        p.relative_to(args["consumer"]): p.read_bytes()
        for p in args["consumer"].rglob("*")
        if p.is_file()
    }
    assert before == after
    assert report["status"] == "ok"
    assert report["targets"] == ["codex", "claude", "copilot"]
    assert report["hooks"]["status"] == "pending"
    assert report["apm"]["mode"] == "prepare"
    assert report["environment"]["status"] == "not-ready"
    assert report["environment"]["launcher"] is None
    assert all(
        value["status"] == "not-bound" for value in report["environment"]["providers"].values()
    )
    assert not any("apm" in command[0] for command in commands)


@pytest.mark.parametrize("condition", ["blank", "missing-variable", "missing-file", "permissions"])
def test_bind_with_pending_credentials_then_activate_without_recompilation(
    setup_consumer, condition
):
    module, args, env_file, commands = setup_consumer
    consumer = args["consumer"]
    _install_setup_fixture(module, consumer)
    protected = {
        "apm.yml": b"# consumer-owned manifest\n",
        "AGENTS.md": b"# generated routing\n",
        ".apm/skills/local/SKILL.md": b"# local skill\n",
    }
    for name, data in protected.items():
        path = consumer / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    match condition:
        case "missing-variable":
            env_file.write_text("UNRELATED=fixture\n")
        case "missing-file":
            env_file.unlink()
        case "permissions":
            env_file.chmod(0o644)
    pending = module.run_setup(**args, apm_mode="bind")
    assert pending["hooks"]["status"] == "ready"
    assert pending["doctor"]["readiness"]["read"] == "ready"
    assert pending["doctor"]["readiness"]["environment"] == "not-ready"
    assert pending["environment"]["status"] == "not-ready"
    assert pending["environment"]["launcher"] is None
    assert all(
        value["status"] == "pending" for value in pending["environment"]["providers"].values()
    )
    assert "--environment-" not in json.dumps(pending["hooks"])
    assert pending["doctor"]["diagnostics"]
    env_file.write_text("SOURCE_TOKEN=setup-integration-secret-canary\n")
    env_file.chmod(0o600)
    ready = module.run_setup(**args, apm_mode="bind")
    repeated = module.run_setup(**args, apm_mode="bind")
    assert ready["hooks"] == repeated["hooks"]
    assert ready["environment"]["status"] == "ready"
    assert ready["environment"]["providers"]["claude"]["status"] == "native-session-start"
    assert (
        "--environment-file"
        in ready["hooks"]["registrations"]["claude"]["commands"]["SessionStart"]
    )
    assert "setup-integration-secret-canary" not in json.dumps(ready)
    for name, data in protected.items():
        assert (consumer / name).read_bytes() == data
    assert not any("apm" in command[0] for command in commands)


def test_prepare_ready_environment_does_not_claim_provider_binding(setup_consumer):
    module, args, env_file, _ = setup_consumer
    env_file.write_text("SOURCE_TOKEN=fixture\n")
    report = module.run_setup(**args, apm_mode="prepare")
    assert report["doctor"]["readiness"]["environment"] == "ready"
    assert all(
        value["status"] == "not-bound" for value in report["environment"]["providers"].values()
    )


def test_staged_setup_rejects_non_environment_failure(setup_consumer):
    module, args, _, _ = setup_consumer
    _install_setup_fixture(module, args["consumer"])
    before = (args["consumer"] / ".claude/apm-hooks.json").read_bytes()
    (args["consumer"] / "knowledge").rmdir()
    with pytest.raises(module.SetupFailure):
        module.run_setup(**args, apm_mode="bind")
    assert (args["consumer"] / ".claude/apm-hooks.json").read_bytes() == before


def test_pending_environment_does_not_hide_broken_receipt_storage(setup_consumer):
    module, args, _, _ = setup_consumer
    _install_setup_fixture(module, args["consumer"])
    before = (args["consumer"] / ".claude/apm-hooks.json").read_bytes()
    receipt_path = args["consumer"] / "usage"
    receipt_path.write_text("not a directory\n")
    config = json.loads(args["workspace"].read_text())
    config["receipts"] = {"directory": str(receipt_path)}
    args["workspace"].write_text(json.dumps(config))
    with pytest.raises(module.SetupFailure) as error:
        module.run_setup(**args, apm_mode="bind")
    assert error.value.steps[-1].name == "doctor"
    assert (args["consumer"] / ".claude/apm-hooks.json").read_bytes() == before


def test_bind_requires_installed_package_lockfile(setup_consumer):
    module, args, _, _ = setup_consumer
    with pytest.raises(module.SetupFailure) as error:
        module.run_setup(**args, apm_mode="bind")
    assert error.value.code == "lockfile-missing"


@pytest.mark.parametrize(
    "mode,code", [("managed", "apm-unavailable"), ("unknown", "unsupported-apm-mode")]
)
def test_setup_mode_validation_before_provisioning(setup_consumer, mode, code):
    module, args, _, commands = setup_consumer
    with pytest.raises(module.SetupFailure) as error:
        module.run_setup(**args, apm_mode=mode)
    assert error.value.code == code
    assert commands == []


def test_setup_environment_target_guard_matches_the_domain_contract() -> None:
    module = _setup_module()

    assert module._RESERVED_ENVIRONMENT_TARGETS == profile_domain._RESERVED_ENVIRONMENT_TARGETS
    assert module._is_safe_environment_target("GH_TOKEN")
    assert profile_domain.is_safe_environment_target("GH_TOKEN")


def _portable_setup(setup_consumer, monkeypatch):
    """Expose this environment's installed launchers and private registry."""
    module, args, env_file, commands = setup_consumer
    bin_path = args["venv"] / "bin"
    monkeypatch.setenv("PATH", str(bin_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", str(args["settings"]))
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: "/fixture/uv" if name == "uv" else str(bin_path / name),
    )
    _install_setup_fixture(module, args["consumer"])
    return module, args, env_file, commands


def test_portable_bind_keeps_hook_bytes_stable_when_credentials_become_ready(
    setup_consumer, monkeypatch
):
    module, args, env_file, _ = _portable_setup(setup_consumer, monkeypatch)
    pending = module.run_setup(**args, apm_mode="bind", portable_hooks=True)
    paths = [
        args["consumer"] / ".codex/apm-hooks.json",
        args["consumer"] / ".claude/apm-hooks.json",
        args["consumer"] / ".github/hooks/knowledge-agent-pack-knowledge-discovery.json",
        args["consumer"] / "apm.lock.yaml",
    ]
    before = {path: path.read_bytes() for path in paths}
    env_file.write_text("SOURCE_TOKEN=portable-secret-canary\n")
    ready = module.run_setup(**args, apm_mode="bind", portable_hooks=True)
    assert pending["hooks"]["mode"] == ready["hooks"]["mode"] == "portable"
    assert ready["environment"]["providers"]["codex"]["command"] == (
        "agent-knowledge-hook --profile example --launch-provider codex --"
    )
    for target, registration in ready["hooks"]["registrations"].items():
        for command in registration["commands"].values():
            assert command == f"agent-knowledge-hook --provider {target} --profile example"
    assert before == {path: path.read_bytes() for path in paths}
    assert all(b"portable-secret-canary" not in data for data in before.values())
    assert ready["doctor"]["readiness"]["environment"] == "ready"


def test_portable_bind_converts_existing_absolute_binding(setup_consumer, monkeypatch):
    module, args, _, _ = _portable_setup(setup_consumer, monkeypatch)
    module.run_setup(**args, apm_mode="bind")
    report = module.run_setup(**args, apm_mode="bind", portable_hooks=True)
    repeated = module.run_setup(**args, apm_mode="bind", portable_hooks=True)
    assert report["hooks"] == repeated["hooks"]
    assert str(args["venv"]) not in json.dumps(report["hooks"]["registrations"])
    descriptor = (
        args["consumer"]
        / "apm_modules/_local/knowledge-agent-pack/.apm/hooks/knowledge-discovery.json"
    ).read_text()
    assert str(args["venv"]) not in descriptor


@pytest.mark.parametrize("failure", ["no-profile", "wrong-path", "wrong-registry"])
def test_portable_bind_rejects_unresolvable_runtime_before_hook_writes(
    setup_consumer, monkeypatch, failure
):
    module, args, _, _ = _portable_setup(setup_consumer, monkeypatch)
    path = args["consumer"] / ".claude/apm-hooks.json"
    before = path.read_bytes()
    if failure == "no-profile":
        args = args | {"profile": None, "settings": None}
    elif failure == "wrong-path":
        monkeypatch.setattr(
            module.shutil, "which", lambda name: "/fixture/uv" if name == "uv" else None
        )
    else:
        monkeypatch.delenv("AGENT_KNOWLEDGE_SETTINGS")
    with pytest.raises(module.SetupFailure) as error:
        module.run_setup(**args, apm_mode="bind", portable_hooks=True)
    assert (
        error.value.code
        == {
            "no-profile": "portable-profile-required",
            "wrong-path": "portable-launcher-unavailable",
            "wrong-registry": "portable-registry-mismatch",
        }[failure]
    )
    assert path.read_bytes() == before


def test_setup_without_profile_environment_reports_each_target_without_crashing(
    tmp_path: Path,
) -> None:
    module = _setup_module()

    report = module._environment_launcher(
        {"selection": {"profile": None}},
        tmp_path / "venv",
        [],
        consumer=tmp_path,
        targets=("codex", "copilot"),
    )

    assert report["status"] == "not-configured"
    assert report["providers"] == {
        "codex": {"status": "not-configured"},
        "claude": {"status": "not-configured"},
        "copilot": {"status": "not-configured"},
    }


@pytest.mark.parametrize("mismatch", ["workspace", "venv", None])
def test_installed_profile_must_match_bootstrap_before_hooks(
    tmp_path: Path, mismatch: str | None
) -> None:
    module = _setup_module()
    workspace = tmp_path / "workspace.yaml"
    venv = tmp_path / "runtime"
    context = {
        "selection": {
            "config_path": str(tmp_path / "other" if mismatch == "workspace" else workspace)
        },
        "configuration": {
            "values": {"setup": {"venv": str(tmp_path / "other" if mismatch == "venv" else venv)}}
        },
    }
    if mismatch:
        with pytest.raises(module.SetupFailure) as error:
            module._verify_selection(context, workspace, venv, [])
        assert error.value.code == f"profile-{mismatch}-mismatch"
    else:
        module._verify_selection(context, workspace, venv, [])


@pytest.mark.parametrize(
    "target",
    [
        "PS4",
        "BASH_XTRACEFD",
        "HOME",
        "CLAUDE_ENV_FILE",
        "LD_PRELOAD",
        "EUID",
        "RANDOM",
        "_ak_status",
        "_AK_COPILOT_VALUE_0",
        "_Ak_Internal",
    ],
)
def test_setup_rejects_process_control_and_loader_internal_targets(
    tmp_path: Path, target: str
) -> None:
    module = _setup_module()
    context = {
        "selection": {"settings_path": str(tmp_path / "profiles.yaml")},
        "environment": {
            "status": "ready",
            "file": str(tmp_path / "profile.env"),
            "variables": [
                {
                    "label": "credential",
                    "from_env": "SOURCE_TOKEN",
                    "expose_as": target,
                    "description": "Credential",
                    "available": True,
                }
            ],
        },
    }

    with pytest.raises(module.SetupFailure) as error:
        module._environment_launcher(context, tmp_path / "venv", [], consumer=tmp_path)

    assert error.value.code == "environment-contract-invalid"


def test_setup_rejects_environment_too_large_for_claude_session_state(
    tmp_path: Path,
) -> None:
    module = _setup_module()
    context = {
        "selection": {"settings_path": str(tmp_path / "profiles.yaml")},
        "environment": {
            "status": "ready",
            "file": str(tmp_path / "profile.env"),
            "variables": [
                {
                    "label": f"credential-{index}",
                    "from_env": f"SOURCE_{index:04d}_{'X' * 40}",
                    "expose_as": f"TARGET_{index:04d}_{'Y' * 40}",
                    "description": "Credential",
                    "available": True,
                }
                for index in range(300)
            ],
        },
    }

    with pytest.raises(module.SetupFailure) as error:
        module._environment_launcher(context, tmp_path / "venv", [], consumer=tmp_path)

    assert error.value.code == "environment-contract-invalid"


def _write_registration_files(
    consumer: Path, command: str, *, source: str = "_local/knowledge-agent-pack"
) -> dict[str, bytes]:
    codex = consumer / ".codex" / "apm-hooks.json"
    claude = consumer / ".claude" / "apm-hooks.json"
    copilot = consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"
    for path in (codex, claude, copilot):
        path.parent.mkdir(parents=True, exist_ok=True)
    codex.write_text(
        json.dumps(
            {
                "SessionStart": [
                    {
                        "hooks": [{"type": "command", "command": command}],
                        "_apm_source": source,
                    }
                ],
                "UserPromptSubmit": [
                    {
                        "hooks": [{"type": "command", "command": command}],
                        "_apm_source": source,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    claude.write_text(
        json.dumps(
            {
                "SessionStart": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": command}],
                        "_apm_source": source,
                    }
                ],
                "UserPromptSubmit": [
                    {
                        "matcher": "*",
                        "hooks": [{"type": "command", "command": command}],
                        "_apm_source": source,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    copilot.write_text(
        json.dumps(
            {
                "hooks": {"sessionStart": [{"hooks": [{"type": "command", "command": command}]}]},
                "version": 1,
            }
        ),
        encoding="utf-8",
    )
    return {
        "codex": codex.read_bytes(),
        "claude": claude.read_bytes(),
        "copilot": copilot.read_bytes(),
    }


def test_verifier_reports_one_owned_registration_per_requested_target(tmp_path: Path) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    package = _package_root(consumer)
    launcher = consumer / "venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    _write_registration_files(consumer, module._DESCRIPTOR_HOOK_COMMAND)

    report = module._configure_hook_registrations(
        consumer, ("codex", "claude", "copilot"), launcher
    )

    assert report["status"] == "ready"
    assert report["targets"] == ["codex", "claude", "copilot"]
    assert set(report["registrations"]) == {"codex", "claude", "copilot"}
    assert report["registrations"]["codex"]["source"] == "_local/knowledge-agent-pack"
    assert report["registrations"]["codex"]["commands"]["SessionStart"].endswith("--provider codex")
    assert report["registrations"]["copilot"]["path"].endswith(
        "knowledge-agent-pack-knowledge-discovery.json"
    )
    assert package.is_dir()


def test_verifier_is_disabled_when_no_targets_are_requested(tmp_path: Path) -> None:
    module = _setup_module()

    assert module._verify_hook_registrations(tmp_path, (), launcher=tmp_path / "hook") == {
        "status": "disabled",
        "targets": [],
    }


def test_verifier_rejects_duplicate_codex_owned_groups(tmp_path: Path) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _package_root(consumer)
    launcher = consumer / "venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    _write_registration_files(consumer, module._launcher_command(launcher))
    path = consumer / ".codex" / "apm-hooks.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["SessionStart"].append(document["SessionStart"][0])
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(module.SetupFailure, match="one package-owned codex") as error:
        module._verify_hook_registrations(consumer, ("codex",), launcher=launcher)

    assert error.value.code == "hook-registration-ambiguous"


def test_configure_replaces_descriptor_marker_with_installed_launcher(tmp_path: Path) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _package_root(consumer)
    launcher = consumer / "venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    _write_registration_files(consumer, module._DESCRIPTOR_HOOK_COMMAND)
    copilot = consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"
    copilot_document = json.loads(copilot.read_text(encoding="utf-8"))
    copilot_document["hooks"]["userPromptSubmit"] = [
        {"hooks": [{"type": "command", "command": module._DESCRIPTOR_HOOK_COMMAND}]}
    ]
    copilot.write_text(json.dumps(copilot_document), encoding="utf-8")

    report = module._configure_hook_registrations(
        consumer, ("codex", "claude", "copilot"), launcher
    )

    expected = module._launcher_command(launcher)
    assert report["status"] == "ready"
    for path in (
        consumer / ".codex" / "apm-hooks.json",
        consumer / ".claude" / "apm-hooks.json",
        consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json",
    ):
        assert expected in path.read_text(encoding="utf-8")
        assert '"command": "agent-knowledge-hook"' not in path.read_text(encoding="utf-8")


def test_profile_environment_launcher_is_value_free_and_exposes_only_declared_targets(
    tmp_path: Path,
) -> None:
    module = _setup_module()
    secret = "setup-loader-secret-canary"
    env_file = tmp_path / "personal.env"
    env_file.write_text(f"GITHUB_V_TOKEN={secret}\nUNDECLARED=must-not-export\n", encoding="utf-8")
    env_file.chmod(0o600)
    venv = tmp_path / "venv"
    hook_launcher = venv / "bin" / "agent-knowledge-hook"
    hook_launcher.parent.mkdir(parents=True)
    hook_launcher.write_text(
        "#!/bin/sh\n"
        f"exec {module.shlex.quote(sys.executable)} -m "
        'agent_knowledge.entrypoints.hooks.runtime "$@"\n',
        encoding="utf-8",
    )
    hook_launcher.chmod(0o700)
    context = {
        "selection": {"profile": "personal", "settings_path": str(tmp_path / "profiles.yaml")},
        "environment": {
            "status": "ready",
            "file": str(env_file),
            "session_policy": "one-profile-per-session",
            "variables": [
                {
                    "label": "github",
                    "from_env": "GITHUB_V_TOKEN",
                    "expose_as": "GH_TOKEN",
                    "description": "Personal GitHub repositories",
                    "available": True,
                }
            ],
        },
    }
    steps: list[object] = []

    report = module._environment_launcher(context, venv, steps, consumer=tmp_path)

    loader = Path(report["launcher"])
    loader_text = loader.read_text(encoding="utf-8")
    assert secret not in loader_text
    assert secret not in json.dumps(report)
    assert "GITHUB_V_TOKEN" in loader_text
    assert "GH_TOKEN" in loader_text
    provider_bin = tmp_path / "provider-bin"
    provider_bin.mkdir()
    codex = provider_bin / "codex"
    codex.write_text(
        "#!/bin/sh\n"
        f'test "$GH_TOKEN" = {module.shlex.quote(secret)}\n'
        'test -z "${UNDECLARED-}"\n'
        "printf ENVIRONMENT_PRESENT\n",
        encoding="utf-8",
    )
    codex.chmod(0o700)
    copilot = provider_bin / "copilot"
    copilot.write_text(
        "#!/bin/sh\n"
        'test "$1" = --bash-env=on\n'
        'test "$2" = --secret-env-vars=_AK_COPILOT_VALUE_0\n'
        f'test "$_AK_COPILOT_VALUE_0" = {module.shlex.quote(secret)}\n'
        'test -z "${GH_TOKEN-}"\n'
        "unset _AK_COPILOT_VALUE_0\n"
        "exec /bin/bash -c "
        + module.shlex.quote(
            f'test "$GH_TOKEN" = {module.shlex.quote(secret)}; '
            'test -z "${_AK_COPILOT_VALUE_0-}"; '
            'test -z "${BASH_ENV-}"; '
            "printf ENVIRONMENT_PRESENT"
        )
        + "\n",
        encoding="utf-8",
    )
    copilot.chmod(0o700)
    probe = subprocess.run(
        [str(loader), "codex"],
        env={"PATH": str(provider_bin)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout == "ENVIRONMENT_PRESENT"
    assert secret not in probe.stdout
    assert secret not in probe.stderr
    copilot_probe = subprocess.run(
        module.shlex.split(str(report["providers"]["copilot"]["command"])),
        env={"PATH": str(provider_bin)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert copilot_probe.stdout == "ENVIRONMENT_PRESENT"
    assert secret not in copilot_probe.stdout
    assert secret not in copilot_probe.stderr
    env_file.chmod(0o644)
    rejected = subprocess.run(
        [str(loader), "codex"],
        env={"PATH": str(provider_bin)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert rejected.stdout == ""
    assert "Profile credential activation failed" in rejected.stderr
    assert secret not in rejected.stderr
    assert report["providers"]["claude"]["status"] == "native-session-start"
    assert report["providers"]["codex"]["command"].endswith(" codex")
    assert report["providers"]["copilot"]["command"].endswith(" copilot")
    assert "_AK_COPILOT_VALUE_" not in loader_text

    unbound = module._environment_launcher(
        context,
        venv,
        [],
        consumer=tmp_path,
        targets=(),
    )
    assert {value["status"] for value in unbound["providers"].values()} == {"not-bound"}


def test_json_result_preserves_nonzero_doctor_diagnostic(tmp_path: Path) -> None:
    module = _setup_module()
    command = tmp_path / "doctor.py"
    command.write_text(
        "import json\n"
        "print(json.dumps({'status': 'error', 'diagnostics': [{"
        "'code': 'environment-variable-missing', "
        "'message': 'Declared source variable is absent.', "
        "'remediation': 'Add the declared name to the private env file.'}]}))\n"
        "raise SystemExit(2)\n",
        encoding="utf-8",
    )
    steps: list[object] = []

    with pytest.raises(module.SetupFailure) as error:
        module._json_result(
            [sys.executable, str(command)],
            cwd=tmp_path,
            name="doctor",
            steps=steps,
            allow_error=True,
        )

    assert error.value.code == "environment-variable-missing"
    assert str(error.value) == "Declared source variable is absent."
    assert error.value.remediation == "Add the declared name to the private env file."
    assert steps == [module.Step("doctor", "not-ready")]


def test_setup_output_preserves_doctor_remediation(monkeypatch, capsys) -> None:
    module = _setup_module()

    def fail_setup(**_kwargs):
        raise module.SetupFailure(
            "environment-variable-missing",
            "Declared source variable is absent.",
            [module.Step("doctor", "not-ready")],
            "Add the declared name to the private env file.",
        )

    monkeypatch.setattr(module, "run_setup", fail_setup)

    assert (
        module.main(
            [
                "--workspace",
                "/tmp/workspace.yaml",
                "--package",
                "/tmp/package.whl",
                "--consumer",
                "/tmp/consumer",
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().err)
    assert payload["diagnostic"] == {
        "code": "environment-variable-missing",
        "message": "Declared source variable is absent.",
        "remediation": "Add the declared name to the private env file.",
    }
    assert payload["steps"] == [{"name": "doctor", "status": "not-ready"}]


def test_claude_session_state_is_scoped_to_consumer_instead_of_registry(
    tmp_path: Path,
) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    other_consumer = tmp_path / "other-consumer"
    consumer.mkdir()
    other_consumer.mkdir()
    venv = tmp_path / "venv"
    hook_launcher = venv / "bin" / "agent-knowledge-hook"
    hook_launcher.parent.mkdir(parents=True)
    hook_launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    def context(settings: Path, environment_file: Path) -> dict[str, object]:
        return {
            "selection": {"profile": "selected", "settings_path": str(settings)},
            "environment": {
                "status": "ready",
                "file": str(environment_file),
                "variables": [
                    {
                        "label": "credential",
                        "from_env": "SOURCE_TOKEN",
                        "expose_as": "TARGET_TOKEN",
                        "description": "Credential",
                        "available": True,
                    }
                ],
            },
        }

    first = module._environment_launcher(
        context(tmp_path / "personal-profiles.yaml", tmp_path / "personal.env"),
        venv,
        [],
        consumer=consumer,
    )
    switched_registry = module._environment_launcher(
        context(tmp_path / "work-profiles.yaml", tmp_path / "work.env"),
        venv,
        [],
        consumer=consumer,
    )
    other = module._environment_launcher(
        context(tmp_path / "personal-profiles.yaml", tmp_path / "personal.env"),
        venv,
        [],
        consumer=other_consumer,
    )

    assert first["session_state_directory"] == switched_registry["session_state_directory"]
    assert first["session_state_directory"] != other["session_state_directory"]


def test_claude_session_hook_pins_environment_metadata_while_other_events_remain_value_free(
    tmp_path: Path,
) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _package_root(consumer)
    launcher = consumer / "venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    loader = consumer / "venv" / "agent-knowledge-environments" / "profile-1.sh"
    loader.parent.mkdir()
    loader.write_text("# no values\n", encoding="utf-8")
    env_file = consumer / "personal.env"
    env_file.write_text("PROFILE_TOKEN=secret\n", encoding="utf-8")
    env_file.chmod(0o600)
    environment = {
        "status": "ready",
        "environment_file": str(env_file),
        "session_state_directory": str(consumer / "claude-session-state"),
        "launcher": str(loader),
        "variables": [
            {
                "label": "proof",
                "from_env": "PROFILE_TOKEN",
                "expose_as": "AGENT_TOKEN",
                "description": "Provider proof",
            }
        ],
    }
    _write_registration_files(consumer, module._DESCRIPTOR_HOOK_COMMAND)

    report = module._configure_hook_registrations(
        consumer,
        ("codex", "claude", "copilot"),
        launcher,
        environment=environment,
    )

    registrations = report["registrations"]
    claude = registrations["claude"]["commands"]
    assert "--environment-file" in claude["SessionStart"]
    assert str(env_file) in claude["SessionStart"]
    assert "--environment-map PROFILE_TOKEN=AGENT_TOKEN" in claude["SessionStart"]
    assert "--environment-file" not in claude["UserPromptSubmit"]
    assert "--environment-file" not in registrations["codex"]["commands"]["SessionStart"]
    assert "--environment-file" not in registrations["copilot"]["commands"]["sessionStart"]


def test_configure_replaces_stale_copilot_prompt_event(tmp_path: Path) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _package_root(consumer)
    launcher = consumer / "venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    _write_registration_files(consumer, module._DESCRIPTOR_HOOK_COMMAND)

    module._configure_hook_registrations(consumer, ("copilot",), launcher)

    document = json.loads(
        (
            consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"
        ).read_text(encoding="utf-8")
    )
    assert document["hooks"].keys() == {"sessionStart", "userPromptTransformed"}
    prompt_entry = document["hooks"]["userPromptTransformed"][0]
    assert prompt_entry["command"].endswith("--provider copilot")
    assert prompt_entry["timeoutSec"] == 3
    assert module._launcher_command(launcher) in json.dumps(document)


def test_setup_updates_copilot_deployment_hash_after_binding_launcher(tmp_path: Path) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    hook = consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"
    hook.parent.mkdir(parents=True)
    hook.write_text(
        '{"hooks":{"sessionStart":[{"hooks":[{"type":"command","command":"/venv/bin/agent-knowledge-hook"}]}],"userPromptSubmit":[{"hooks":[{"type":"command","command":"/venv/bin/agent-knowledge-hook"}]}]},"version":1}\n',
        encoding="utf-8",
    )
    lock = consumer / "apm.lock.yaml"
    lock.write_text(
        "\n".join(
            [
                "lockfile_version: '1'",
                "dependencies:",
                "- repo_url: _local/knowledge-agent-pack",
                "  deployed_file_hashes:",
                "    .github/hooks/knowledge-agent-pack-knowledge-discovery.json: sha256:stale",
                "deployments:",
                "- kind: project-relative",
                "  target: copilot",
                "  value: .github/hooks/knowledge-agent-pack-knowledge-discovery.json",
                "  runtime: null",
                "  scope: project",
                "  content_hash: sha256:stale",
                "- kind: project-relative",
                "  target: claude",
                "  value: .claude/rules/example.md",
                "  content_hash: sha256:untouched",
                "",
            ]
        ),
        encoding="utf-8",
    )

    steps: list[object] = []
    report = module._update_copilot_lock_hash(consumer, hook, steps)

    expected = "sha256:" + module.hashlib.sha256(hook.read_bytes()).hexdigest()
    assert report == {
        "status": "updated",
        "path": str(lock.resolve()),
        "content_hash": expected,
    }
    lock_text = lock.read_text(encoding="utf-8")
    assert (
        f"    .github/hooks/knowledge-agent-pack-knowledge-discovery.json: {expected}" in lock_text
    )
    assert f"  content_hash: {expected}" in lock_text
    assert "  content_hash: sha256:untouched" in lock_text
    assert steps[0].name == "apm-lock"
    assert steps[0].status == "updated"


@pytest.mark.parametrize("version", ["3.9.6", "3.10.14"])
def test_existing_venv_rejects_python_below_minimum(tmp_path: Path, version: str) -> None:
    module = _setup_module()
    python = tmp_path / "python"
    python.write_text(f"#!/bin/sh\nprintf 'Python {version}\\n'\n", encoding="utf-8")
    python.chmod(0o755)

    with pytest.raises(module.SetupFailure, match="Python 3.11 or newer is required") as error:
        module._require_supported_python(python, [], source="The existing virtual environment")

    assert error.value.code == "python-version-mismatch"


@pytest.mark.parametrize("version", ["3.11.0", "3.12.12", "3.13.12", "3.14.6", "3.20.0"])
def test_existing_supported_venv_is_reused_without_provisioning(
    tmp_path: Path, version: str
) -> None:
    module = _setup_module()
    venv = tmp_path / "venv"
    python = venv / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(f"#!/bin/sh\nprintf 'Python {version}\\n'\n", encoding="utf-8")
    python.chmod(0o755)
    (venv / "pyvenv.cfg").write_text("home = /fixture/python\n")
    steps = []

    selected, launcher = module._prepare_venv(venv, "/missing/uv", steps)

    assert selected == python
    assert launcher == venv / "bin" / "agent-knowledge"
    assert [(step.name, step.status) for step in steps] == [
        ("python", version),
        ("venv", "reused"),
    ]


def test_missing_supported_python_reports_install_remediation(tmp_path: Path) -> None:
    module = _setup_module()
    uv = tmp_path / "uv"
    uv.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    uv.chmod(0o755)

    with pytest.raises(module.SetupFailure, match="Python 3.11 or newer") as error:
        module._find_supported_python(str(uv), [])

    assert error.value.code == "python-version-unavailable"
    assert "uv python install 3.11" in str(error.value)


@pytest.mark.parametrize(
    "source",
    [
        "_local/knowledge-agent-pack",
        "example/knowledge-agent-pack",
        "example/agent-knowledge-scaffold/packages/knowledge-agent-pack",
    ],
)
def test_bind_supports_local_and_remote_installed_packages(setup_consumer, source: str) -> None:
    module, args, _, commands = setup_consumer
    consumer = args["consumer"]
    _install_setup_fixture(module, consumer, source)
    manifest = consumer / "apm.yml"
    manifest.write_text(f"dependencies:\n  apm:\n    - {source}#main\n")
    before = manifest.read_bytes()

    first = module.run_setup(**args, apm_mode="bind")
    assert first["hooks"]["status"] == "ready"
    assert {item["source"] for item in first["hooks"]["registrations"].values()} == {source}
    assert first["apm_lock"]["status"] == "updated"
    repeated = module.run_setup(**args, apm_mode="bind")
    assert repeated["hooks"] == first["hooks"]
    assert repeated["apm_lock"]["status"] == "current"
    assert manifest.read_bytes() == before
    assert not any("apm" in command[0] for command in commands)


def test_discovery_ignores_uninstalled_source_copies(tmp_path: Path) -> None:
    module = _setup_module()
    installed = _package_root(tmp_path)
    source = tmp_path / "apm_modules/example/scaffold/packages/knowledge-agent-pack/.apm/hooks"
    source.mkdir(parents=True)
    (source / "knowledge-discovery.json").write_text("{}\n")

    assert module._hook_package(tmp_path) == ("_local/knowledge-agent-pack", installed)


def test_remote_materialization_case_preserves_canonical_ownership(tmp_path: Path) -> None:
    module = _setup_module()
    canonical = "example/scaffold/packages/knowledge-agent-pack"
    installed = _package_root(
        tmp_path,
        "Example/Scaffold/packages/knowledge-agent-pack",
        dependency={
            "repo_url": "example/scaffold",
            "materialization_repo_url": "Example/Scaffold",
            "is_virtual": True,
            "virtual_path": "packages/knowledge-agent-pack",
        },
    )
    _write_registration_files(tmp_path, module._DESCRIPTOR_HOOK_COMMAND, source=canonical)
    report = module._configure_hook_registrations(tmp_path, ("codex",), tmp_path / "hook")

    assert module._hook_package(tmp_path) == (canonical, installed)
    assert report["registrations"]["codex"]["source"] == canonical


def test_discovery_finds_registered_transitive_local_package(tmp_path: Path) -> None:
    module = _setup_module()
    anchor = "example/scaffold/packages/knowledge-agent-pack"
    source = (
        f"_local/{module.hashlib.sha256(anchor.encode()).hexdigest()[:12]}/knowledge-agent-pack"
    )
    installed = _package_root(
        tmp_path,
        source,
        dependency={
            "repo_url": "_local/knowledge-agent-pack",
            "source": "local",
            "local_path": "./packages/knowledge-agent-pack",
            "declaring_parent": "example/scaffold",
            "anchored_local_path": anchor,
        },
    )

    assert module._hook_package(tmp_path) == (source, installed)


@pytest.mark.parametrize("transitive", [False, True])
def test_discovery_handles_wrapped_yaml_paths_without_loading_consumer_modules(
    tmp_path: Path, transitive: bool
) -> None:
    module = _setup_module()
    local = (
        "/Users/example/Documents/Engineering Projects/Business Operations/Shared Development/"
        "agent-knowledge-scaffold/packages/knowledge-agent-pack"
    )
    dependency = {
        "repo_url": "_local/knowledge-agent-pack",
        "source": "local",
        "local_path": local,
    }
    source = "_local/knowledge-agent-pack"
    if transitive:
        dependency.update(declaring_parent="example/scaffold", anchored_local_path=local)
        digest = module.hashlib.sha256(local.encode()).hexdigest()[:12]
        source = f"_local/{digest}/knowledge-agent-pack"
    installed = _package_root(tmp_path, source, dependency=dependency)
    assert local not in (tmp_path / "apm.lock.yaml").read_text()
    (tmp_path / "yaml.py").write_text("raise RuntimeError('Do not import consumer code')\n")

    assert module._hook_package(tmp_path) == (source, installed)


def test_discovery_rejects_malformed_lock_yaml(tmp_path: Path) -> None:
    module = _setup_module()
    (tmp_path / "apm.lock.yaml").write_text("dependencies: [\n")
    with pytest.raises(module.SetupFailure) as error:
        module._hook_package(tmp_path)
    assert error.value.code == "lockfile-invalid"


def test_discovery_rejects_lock_paths_outside_modules(tmp_path: Path) -> None:
    module = _setup_module()
    _package_root(tmp_path, dependency={"repo_url": "../../outside"})
    with pytest.raises(module.SetupFailure) as error:
        module._hook_package(tmp_path)
    assert error.value.code == "hook-package-invalid"


@pytest.mark.parametrize("source", ["_local/another-pack", "example/knowledge-agent-pack"])
def test_package_discovery_rejects_ambiguous_hook_bundles(tmp_path: Path, source: str) -> None:
    module = _setup_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    _package_root(consumer)
    _package_root(consumer, source)

    with pytest.raises(module.SetupFailure, match="no unique package-owned") as error:
        module._hook_package(consumer)

    assert error.value.code == "hook-package-missing"
