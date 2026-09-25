"""Exercise readiness against real neutral configurations and temporary directories."""

import json
import os
import stat
import sys
from dataclasses import asdict
from importlib import metadata
from pathlib import Path

import pytest

from agent_knowledge.application import doctor
from tests.factories import catalog_data


def workspace_config(
    root: Path, *, storage: bool = True, inbox: bool = True
) -> tuple[Path, Path, Path]:
    """Create an empty, healthy source with an independently optional signal inbox."""
    source = root / "knowledge"
    source.mkdir()
    signal_root = root / "scaffold" / "ai" / "signals"
    if inbox:
        signal_root.mkdir(parents=True)
    catalog = root / "catalog.yaml"
    catalog.write_text(json.dumps(catalog_data()))
    config: dict[str, object] = {
        "schema_version": "knowledge-workspace.v1",
        "workspace_id": "repo:orders",
        "applicable_scopes": ["org:example", "repo:orders"],
        "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
    }
    if storage:
        config["signal_storage"] = {"scaffold_root": "scaffold", "code_root": "."}
    path = root / "knowledge-workspace.yaml"
    path.write_text(json.dumps(config))
    return path, source, signal_root


def profile_settings(config: Path, env_file: Path) -> Path:
    path = config.parent / "profiles.yaml"
    path.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-profiles.v1",
                "default_profile": "personal",
                "profiles": {
                    "personal": {
                        "config": str(config),
                        "environment": {
                            "file": str(env_file),
                            "variables": {
                                "github": {
                                    "from_env": "GITHUB_V_TOKEN",
                                    "expose_as": "GH_TOKEN",
                                    "description": "Personal GitHub repositories",
                                }
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_read_checks_real_runtime_config_catalog_and_empty_source(tmp_path: Path) -> None:
    config, _, inbox = workspace_config(tmp_path)

    result = doctor.run_doctor(config, {})

    assert result.exit_code == 0
    assert result.runtime.package_version == metadata.version("agent-knowledge-scaffold")
    assert result.runtime.interpreter == sys.executable
    assert Path(result.runtime.module_path).is_file()
    assert result.workspace_id == "repo:orders"
    assert result.config_path == str(config.resolve())
    assert result.readiness == doctor.Readiness("ready", "unverified")
    assert {check.name for check in result.checks} >= {
        "runtime",
        "configuration",
        "catalog",
        "source:knowledge",
        "signal-storage",
        "write-probe",
    }
    assert list(inbox.iterdir()) == []
    assert result.diagnostics == ()


def test_doctor_reports_profile_environment_readiness_without_values(tmp_path: Path) -> None:
    config, _, _ = workspace_config(tmp_path)
    secret = "doctor-secret-canary"
    env_file = tmp_path / "personal.env"
    env_file.write_text(f"GITHUB_V_TOKEN={secret}\n", encoding="utf-8")
    env_file.chmod(0o600)
    settings = profile_settings(config, env_file)

    result = doctor.run_doctor(None, {}, settings=settings, profile="personal")

    assert result.exit_code == 0
    assert result.readiness.environment == "ready"
    assert {check.name for check in result.checks} >= {
        "environment-file",
        "environment:github",
    }
    assert secret not in repr(asdict(result))


def test_doctor_keeps_knowledge_readiness_when_environment_key_is_missing(
    tmp_path: Path,
) -> None:
    config, _, _ = workspace_config(tmp_path)
    env_file = tmp_path / "personal.env"
    env_file.write_text("SOMETHING_ELSE=secret\n", encoding="utf-8")
    env_file.chmod(0o600)
    settings = profile_settings(config, env_file)

    result = doctor.run_doctor(None, {}, settings=settings, profile="personal")

    assert result.exit_code == 2
    assert result.readiness.read == "ready"
    assert result.readiness.environment == "not-ready"
    assert any(item.code == "environment-variable-missing" for item in result.diagnostics)


def test_read_does_not_scan_bodies_or_create_missing_inbox(tmp_path: Path) -> None:
    config, source, inbox = workspace_config(tmp_path, inbox=False)
    (source / "unparseable.md").write_bytes(b"\xff--- not a document")

    result = doctor.run_doctor(config, {})

    assert result.exit_code == 0
    assert result.readiness == doctor.Readiness("ready", "unverified")
    assert not inbox.exists()
    assert not inbox.parent.exists()


def test_read_without_signal_storage_is_healthy(tmp_path: Path) -> None:
    config, _, _ = workspace_config(tmp_path, storage=False)

    result = doctor.run_doctor(config, {})

    assert result.exit_code == 0
    assert result.readiness == doctor.Readiness("ready", "not-configured")


def test_write_without_storage_is_configuration_error(tmp_path: Path) -> None:
    config, _, _ = workspace_config(tmp_path, storage=False)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 2
    assert result.readiness == doctor.Readiness("ready", "not-configured")
    assert result.diagnostics[0].code == "signal-storage-required"


def test_write_probe_is_removed_and_existing_inputs_are_untouched(tmp_path: Path) -> None:
    config, source, inbox = workspace_config(tmp_path)
    existing = inbox / "existing.md"
    existing.write_text("An authored observation")
    canonical = source / "document.md"
    canonical.write_text("Untouched canonical bytes")

    result = doctor.run_doctor(config, {"mode": "write", "expected_workspace_id": "repo:orders"})

    assert result.exit_code == 0
    assert result.readiness == doctor.Readiness("ready", "ready")
    assert list(inbox.iterdir()) == [existing]
    assert existing.read_text() == "An authored observation"
    assert canonical.read_text() == "Untouched canonical bytes"
    assert {check.name for check in result.checks if check.status == "passed"} >= {
        "write-probe",
        "probe-cleanup",
    }


def test_missing_storage_directory_is_reported_without_creating_it(tmp_path: Path) -> None:
    config, _, inbox = workspace_config(tmp_path, inbox=False)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 2
    assert result.readiness == doctor.Readiness("ready", "not-ready")
    assert result.diagnostics
    assert result.diagnostics[0].remediation
    assert not inbox.exists()


def test_missing_config_keeps_actual_runtime_and_setup_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    result = doctor.run_doctor(None, {})

    assert result.exit_code == 2
    assert result.runtime.package_version == metadata.version("agent-knowledge-scaffold")
    assert result.workspace_id is None
    assert result.readiness.read == "not-ready"
    assert result.diagnostics[0].code == "profile-settings-unavailable"
    assert "--config" in (result.diagnostics[0].remediation or "")


def test_wrong_workspace_stops_before_requested_write(tmp_path: Path) -> None:
    config, _, inbox = workspace_config(tmp_path)

    result = doctor.run_doctor(
        config, {"mode": "write", "expected_workspace_id": "repo:unregistered-workspace"}
    )

    assert result.exit_code == 2
    assert result.workspace_id == "repo:orders"
    assert result.diagnostics[0].code == "workspace-mismatch"
    assert "repo:unregistered-workspace" in result.diagnostics[0].message
    assert list(inbox.iterdir()) == []
    assert not any(check.name == "write-probe" for check in result.checks)


@pytest.mark.parametrize(
    "query_data",
    [
        None,
        [],
        {"mode": "repair"},
        {"mode": True},
        {"mode": []},
        {"write": True},
        {"expected_workspace_id": ""},
    ],
)
def test_invalid_request_is_rejected_before_configuration_access(
    tmp_path: Path, query_data: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_load(**kwargs: object) -> None:
        pytest.fail("Invalid requests must not load configuration.")

    monkeypatch.setattr(doctor, "resolve_workspace", forbidden_load)

    result = doctor.run_doctor(tmp_path / "missing.yaml", query_data)

    assert result.exit_code == 2
    assert result.diagnostics
    assert result.readiness.read == "not-ready"


def test_invalid_catalog_is_not_a_healthy_empty_source(tmp_path: Path) -> None:
    config, _, _ = workspace_config(tmp_path)
    (tmp_path / "catalog.yaml").write_text("schema_version: invalid\n")

    result = doctor.run_doctor(config, {})

    assert result.exit_code == 2
    assert result.readiness.read == "not-ready"
    assert not any(check.name == "catalog" and check.status == "passed" for check in result.checks)


def test_missing_named_configuration_is_invalid_setup(tmp_path: Path) -> None:
    result = doctor.run_doctor(tmp_path / "missing.yaml", {})

    assert result.exit_code == 2
    assert result.readiness.read == "not-ready"
    assert result.runtime.package_version is not None


def test_source_failure_keeps_read_not_ready(tmp_path: Path) -> None:
    config, source, _ = workspace_config(tmp_path)
    source.rmdir()

    result = doctor.run_doctor(config, {})

    assert result.exit_code == 2
    assert result.readiness.read == "not-ready"
    assert any(
        check.name == "source:knowledge" and check.status == "failed" for check in result.checks
    )


def test_bad_storage_containment_preserves_honest_read_result(tmp_path: Path) -> None:
    config, _, inbox = workspace_config(tmp_path)
    data = json.loads(config.read_text())
    data["sources"][0]["root"] = "scaffold/ai/signals"
    config.write_text(json.dumps(data))

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 2
    assert result.readiness == doctor.Readiness("ready", "not-ready")
    assert list(inbox.iterdir()) == []
    assert any(
        check.name == "signal-storage" and check.status == "failed" for check in result.checks
    )


def test_symlink_storage_cannot_redirect_probe_into_canonical_source(tmp_path: Path) -> None:
    config, source, inbox = workspace_config(tmp_path)
    inbox.rmdir()
    inbox.symlink_to(source, target_is_directory=True)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 2
    assert result.readiness.write == "not-ready"
    assert list(source.iterdir()) == []


def test_probe_creation_failure_is_io_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, inbox = workspace_config(tmp_path)
    real_open = os.open

    def fail_probe(path: str, flags: int, mode: int = 0o777, *, dir_fd: int | None = None) -> int:
        if flags & os.O_CREAT:
            raise PermissionError("No write access")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(doctor.os, "open", fail_probe)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 3
    assert result.readiness == doctor.Readiness("ready", "not-ready")
    assert result.diagnostics[0].code == "write-probe-failed"
    assert list(inbox.iterdir()) == []


def test_failed_probe_write_still_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, inbox = workspace_config(tmp_path)

    def fail_write(descriptor: int, payload: bytes) -> int:
        raise OSError("No storage capacity")

    monkeypatch.setattr(doctor.os, "write", fail_write)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 3
    assert result.readiness.write == "not-ready"
    assert list(inbox.iterdir()) == []
    assert any(
        check.name == "probe-cleanup" and check.status == "passed" for check in result.checks
    )


def test_cleanup_failure_reports_retained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, inbox = workspace_config(tmp_path)

    def fail_unlink(path: str, *, dir_fd: int | None = None) -> None:
        raise PermissionError("Cannot remove")

    monkeypatch.setattr(doctor.os, "unlink", fail_unlink)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 3
    assert result.readiness.write == "not-ready"
    diagnostic = next(item for item in result.diagnostics if item.code == "probe-cleanup-failed")
    assert Path(diagnostic.path).is_file()
    assert list(inbox.iterdir()) == [Path(diagnostic.path)]


def test_replaced_probe_is_preserved_and_not_reported_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, inbox = workspace_config(tmp_path)
    real_write = os.write

    def replace_during_write(descriptor: int, payload: bytes) -> int:
        probe = next(inbox.iterdir())
        probe.unlink()
        probe.write_text("Replacement belongs to someone else")
        return real_write(descriptor, payload)

    monkeypatch.setattr(doctor.os, "write", replace_during_write)

    result = doctor.run_doctor(config, {"mode": "write"})

    assert result.exit_code == 3
    assert result.readiness.write == "not-ready"
    assert next(inbox.iterdir()).read_text() == "Replacement belongs to someone else"
    assert result.diagnostics[0].code == "probe-cleanup-failed"


def test_runtime_does_not_dump_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config, _, _ = workspace_config(tmp_path)
    monkeypatch.setenv("PRIVATE_API_TOKEN", "DO-NOT-INCLUDE-THIS")

    result = doctor.run_doctor(config, {})

    assert result.exit_code == 0
    assert "DO-NOT-INCLUDE-THIS" not in json.dumps(asdict(result))
    assert "PRIVATE_API_TOKEN" not in json.dumps(asdict(result))


def test_probe_identity_failure_retains_unverifiable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, inbox = workspace_config(tmp_path)
    real_fstat = os.fstat

    def fail_probe_identity(descriptor: int) -> os.stat_result:
        result = real_fstat(descriptor)
        if stat.S_ISREG(result.st_mode):
            raise OSError("Identity unavailable")
        return result

    monkeypatch.setattr(doctor.os, "fstat", fail_probe_identity)

    _, diagnostics = doctor._probe(inbox.resolve())

    assert {item.code for item in diagnostics} == {"write-probe-failed", "probe-cleanup-failed"}
    assert len(list(inbox.iterdir())) == 1


def test_probe_close_failure_still_attempts_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, inbox = workspace_config(tmp_path)
    real_close = os.close

    def fail_probe_close(descriptor: int) -> None:
        is_probe = stat.S_ISREG(os.fstat(descriptor).st_mode)
        real_close(descriptor)
        if is_probe:
            raise OSError("Probe handle close failed")

    monkeypatch.setattr(doctor.os, "close", fail_probe_close)

    checks, diagnostics = doctor._probe(inbox.resolve())

    assert [item.code for item in diagnostics] == ["probe-close-failed"]
    assert any(check.name == "probe-cleanup" and check.status == "passed" for check in checks)
    assert list(inbox.iterdir()) == []


def test_doctor_reports_missing_usage_without_creating_or_claiming_writability(
    tmp_path: Path,
) -> None:
    config, _, _ = workspace_config(tmp_path)
    result = doctor.run_doctor(config, {})
    assert result.readiness.read == "ready"
    assert result.readiness.receipts == "unverified"
    assert not (tmp_path / "ai/usage").exists()
    assert any(
        check.name == "receipt-storage" and check.status == "unverified" for check in result.checks
    )


@pytest.mark.parametrize("enabled", [True, False])
def test_doctor_probes_usage_even_with_diagnostic_collection_disabled(
    tmp_path: Path, enabled: bool
) -> None:
    config, _, _ = workspace_config(tmp_path)
    data = json.loads(config.read_text())
    data["receipts"] = {"enabled": enabled, "retention_days": 8}
    config.write_text(json.dumps(data))
    usage = tmp_path / "ai/usage"
    usage.mkdir(parents=True)
    sentinel = usage / "unrelated.txt"
    sentinel.write_text("preserve")
    result = doctor.run_doctor(config, {"mode": "write"})
    assert result.exit_code == 0
    assert result.readiness.receipts == "ready"
    assert list(usage.iterdir()) == [sentinel]
    check = next(check for check in result.checks if check.name == "receipt-collection")
    assert ("enabled" if enabled else "disabled") in check.message
    assert "8 days" in check.message
    assert "remain required" in check.message


def test_receipt_storage_failure_preserves_independent_read_readiness(tmp_path: Path) -> None:
    config, _, _ = workspace_config(tmp_path)
    usage = tmp_path / "ai/usage"
    usage.parent.mkdir()
    usage.write_text("a file is not a usage directory")
    result = doctor.run_doctor(config, {})
    assert result.exit_code != 0
    assert result.readiness.read == "ready"
    assert result.readiness.receipts == "not-ready"
    assert any(
        check.name == "receipt-storage" and check.status == "failed" for check in result.checks
    )
