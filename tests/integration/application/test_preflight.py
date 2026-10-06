"""Check explicit launch routes and no-write defaults with real fictional profiles."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from agent_knowledge.application import doctor, preflight
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.preflight import ExecutionObservation
from tests.integration.application.test_doctor import workspace_config


@pytest.fixture
def configured(tmp_path, monkeypatch):
    config, source, inbox = workspace_config(tmp_path)
    usage = tmp_path / "ai/usage"
    usage.mkdir(parents=True)
    monkeypatch.setattr(
        preflight,
        "observe_execution",
        lambda: ExecutionObservation(
            "unknown", "Linux", 1000, "/home/developer", str(tmp_path), 100, 99, ()
        ),
    )
    monkeypatch.setattr(
        preflight, "executable_path", lambda name: str(Path(sys.prefix) / "bin" / name)
    )
    monkeypatch.setattr(preflight, "available_executable", lambda path: True)
    return config, source, inbox, usage


def test_default_preflight_reports_independent_readiness_without_writes(configured, monkeypatch):
    config, source, inbox, usage = configured
    monkeypatch.setattr(doctor, "_probe", lambda directory: pytest.fail("Default preflight wrote"))
    source.joinpath("invalid-document.md").write_text("not a valid knowledge document")
    result = preflight.run_preflight(config, {})
    assert result.exit_code == 0 and result.status == "ok"
    assert result.schema_version == "knowledge-preflight.v1"
    assert result.readiness["read"] == "ready"
    assert result.readiness["write"] == result.readiness["receipts"] == "unverified"
    assert result.readiness["execution"] == "unverified"
    assert result.execution.harness_location == "unverified"
    assert result.readiness["harness_sandbox"] == "unverified"
    assert list(inbox.iterdir()) == list(usage.iterdir()) == []
    assert result.routes["signal_root"] == str(inbox)
    assert result.routes["receipt_root"] == str(usage)


def test_write_preflight_reuses_disposable_probes_and_preserves_existing_files(configured):
    config, _, inbox, usage = configured
    sentinel = inbox / "keep.txt"
    sentinel.write_text("preserve")
    result = preflight.run_preflight(config, {"mode": "write"})
    assert result.exit_code == 0
    assert result.readiness["write"] == result.readiness["receipts"] == "ready"
    assert result.readiness["harness_sandbox"] == "unverified"
    assert "this preflight process" in result.write_scope
    assert sentinel.read_text() == "preserve"
    assert list(inbox.iterdir()) == [sentinel]
    assert list(usage.iterdir()) == []


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"expected_execution": "container"}, "execution-unverified"),
        ({"expected_venv": "/other/runtime"}, "runtime-venv-mismatch"),
        ({"expected_workspace_id": "repo:another"}, "workspace-mismatch"),
    ],
)
def test_unestablished_route_does_not_write_even_when_explicitly_requested(
    configured, monkeypatch, payload, code
):
    config, _, _, _ = configured
    monkeypatch.setattr(doctor, "_probe", lambda directory: pytest.fail("Wrong route wrote"))
    result = preflight.run_preflight(config, {"mode": "write", **payload})
    assert result.exit_code == 2
    assert code in {item.code for item in result.diagnostics}


def test_path_mismatch_is_separate_from_read_readiness(configured, monkeypatch):
    config, _, _, _ = configured
    monkeypatch.setattr(preflight, "executable_path", lambda name: "/stale/bin/" + name)
    result = preflight.run_preflight(config, {})
    assert result.exit_code == 2
    assert result.readiness["path_launchers"] == "not-ready"
    assert result.readiness["read"] == "ready"
    assert any(item.remediation for item in result.diagnostics)


def test_missing_provider_is_not_repaired_or_treated_as_live_hook_proof(configured, monkeypatch):
    config, _, _, _ = configured
    original = preflight.executable_path
    monkeypatch.setattr(
        preflight, "executable_path", lambda name: None if name == "codex" else original(name)
    )
    result = preflight.run_preflight(config, {"provider": "codex"})
    assert result.exit_code == 2
    assert result.readiness["provider_launcher"] == "not-ready"
    assert result.runtime["provider_executed"] is False
    assert result.hooks["native_trust"] == result.hooks["firing"] == "unverified"


@pytest.mark.parametrize("value,ready", [("", False), ("fictional-canary", True)])
def test_private_credential_readiness_has_no_values_or_ambient_fallback(
    configured, monkeypatch, value, ready
):
    config, _, _, _ = configured
    env = config.parent / "private.env"
    env.write_text("SOURCE_TOKEN=" + value + "\n")
    env.chmod(0o600)
    settings = config.parent / "profiles.yaml"
    settings.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-profiles.v1",
                "profiles": {
                    "example": {
                        "config": str(config),
                        "environment": {
                            "file": "private.env",
                            "variables": {
                                "service": {
                                    "from_env": "SOURCE_TOKEN",
                                    "expose_as": "TOOL_TOKEN",
                                    "description": "Fixture API",
                                }
                            },
                        },
                    }
                },
            }
        )
    )
    monkeypatch.setenv("TOOL_TOKEN", "ambient-must-not-satisfy")
    result = preflight.run_preflight(None, {}, settings=settings, profile="example")
    assert result.exit_code == (0 if ready else 2)
    assert result.readiness["environment"] == ("ready" if ready else "not-ready")
    assert result.readiness["read"] == "ready"
    assert result.environment_declaration == {
        "file": str(env),
        "variables": [{"from_env": "SOURCE_TOKEN", "expose_as": "TOOL_TOKEN"}],
    }
    rendered = json.dumps(asdict(result))
    assert "fictional-canary" not in rendered and "ambient-must-not-satisfy" not in rendered
    assert result.readiness["credential_activation"] == "unverified"


def test_probe_permission_failure_remains_exit_three(configured, monkeypatch):
    config, _, _, _ = configured

    def denied(directory):
        from agent_knowledge.infrastructure.errors import AdapterError

        raise AdapterError("write-probe-failed", str(directory), "Permission denied.")

    monkeypatch.setattr(doctor, "_probe", denied)
    result = preflight.run_preflight(config, {"mode": "write"})
    assert result.exit_code == 3
    assert result.readiness["read"] == "ready"
    assert result.readiness["write"] == "not-ready"


def test_missing_configuration_retains_tool_observation_and_runtime(configured):
    config, _, _, _ = configured
    result = preflight.run_preflight(config.parent / "missing.yaml", {})
    assert result.exit_code != 0
    assert result.execution.system == "Linux"
    assert result.runtime["interpreter"]
    assert result.readiness["read"] == "not-ready"
    assert result.routes == {}


def test_native_request_paths_cannot_be_relative(configured):
    config, _, _, _ = configured
    with pytest.raises(ValidationError, match="absolute path"):
        preflight.run_preflight(config, {"expected_venv": "../runtime"})


def test_consumer_registration_availability_does_not_certify_contents(configured):
    config, _, _, _ = configured
    consumer = config.parent / "consumer"
    registration = consumer / ".codex/hooks.json"
    registration.parent.mkdir(parents=True)
    registration.write_text("{}")
    result = preflight.run_preflight(config, {"provider": "codex", "consumer": str(consumer)})
    assert result.exit_code == 0
    assert result.hooks["file_available"] is True
    assert result.hooks["registration"] == "unverified"
    assert result.readiness["native_trust"] == result.readiness["hook_firing"] == "unverified"


def test_environment_declaration_rotation_invalidates_report_even_when_fingerprint_is_same(
    configured, monkeypatch
):
    config, _, _, _ = configured
    env = config.parent / "private.env"
    env.write_text("SOURCE_TOKEN=fixture-only\n")
    env.chmod(0o600)
    settings = config.parent / "profiles.yaml"
    data = {
        "schema_version": "knowledge-profiles.v1",
        "profiles": {
            "example": {
                "config": str(config),
                "environment": {
                    "file": str(env),
                    "variables": {
                        "service": {
                            "from_env": "SOURCE_TOKEN",
                            "expose_as": "TOOL_TOKEN",
                            "description": "Fixture",
                        }
                    },
                },
            }
        },
    }
    settings.write_text(json.dumps(data))
    original = preflight.run_doctor

    def rotate(*args, **kwargs):
        result = original(*args, **kwargs)
        data["profiles"]["example"]["environment"]["variables"]["service"]["expose_as"] = (
            "OTHER_TOKEN"
        )
        settings.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(preflight, "run_doctor", rotate)
    result = preflight.run_preflight(None, {}, settings=settings, profile="example")
    assert result.exit_code == 2
    assert any(item.code == "context-changed" for item in result.diagnostics)


def test_missing_registration_is_visible_and_never_created(configured):
    config, _, _, _ = configured
    consumer = config.parent / "consumer"
    consumer.mkdir()
    result = preflight.run_preflight(config, {"provider": "codex", "consumer": str(consumer)})
    assert result.exit_code == 2
    assert result.hooks["file_available"] is False
    assert list(consumer.iterdir()) == []


@pytest.mark.parametrize("route", ["venv", "launcher"])
def test_path_resolution_failure_reports_diagnostic_without_writes(configured, monkeypatch, route):
    config, _, _, _ = configured
    loop = config.parent / "loop"
    loop.symlink_to(loop)
    monkeypatch.setattr(doctor, "_probe", lambda _: pytest.fail("Invalid runtime route wrote"))
    request = {"mode": "write"}
    if route == "venv":
        request["expected_venv"] = str(loop)
    else:
        monkeypatch.setattr(preflight, "executable_path", lambda _: str(loop))
    result = preflight.run_preflight(config, request)
    assert result.exit_code == 2
    assert any(item.code == "runtime-path-unavailable" for item in result.diagnostics)
