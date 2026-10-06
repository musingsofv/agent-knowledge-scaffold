"""Guard explicit private container projections without weakening runtime activation."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import container_profiles as projection
from agent_knowledge.infrastructure.environment import mapped_environment_values
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.profiles import resolve_profile_environment
from agent_knowledge.infrastructure.usage import usage_lock
from tests.factories import catalog_data


@pytest.fixture
def prepared(tmp_path):
    knowledge = tmp_path / "knowledge-instance"
    knowledge.mkdir()
    (knowledge / "knowledge").mkdir()
    (knowledge / "catalog.yaml").write_text(json.dumps(catalog_data()))
    (knowledge / "workspace.yaml").write_text(
        json.dumps(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "workspace:example",
                "applicable_scopes": ["org:example"],
                "sources": [{"id": "example", "root": "knowledge", "catalog": "catalog.yaml"}],
            }
        )
    )
    settings = tmp_path / "registry.yaml"
    source = tmp_path / "mounted.env"
    source.write_text("EXAMPLE_TOKEN=fictional-original-value\n")
    source.chmod(0o644)  # A deliberately unsuitable host-mount permission fixture.
    private = tmp_path / "private"
    data = {
        "schema_version": "knowledge-profiles.v1",
        "profiles": {
            "example": {
                "config": "knowledge-instance/workspace.yaml",
                "environment": {
                    "file": "private/example.env",
                    "variables": {
                        "example": {
                            "from_env": "EXAMPLE_TOKEN",
                            "expose_as": "GH_TOKEN",
                            "description": "Example tool",
                        }
                    },
                },
            }
        },
    }
    return dict(
        operation="prepare",
        settings=settings,
        profile="example",
        candidate=yaml.safe_dump(data).encode(),
        expected_sha256=None,
        private_directory=private,
        source_env_file=source,
    )


def apply(args, **changes):
    args = {**args, **changes}
    if args["settings"].exists() and "expected_sha256" not in changes:
        args["expected_sha256"] = hashlib.sha256(args["settings"].read_bytes()).hexdigest()
    return projection.prepare_container_profile(**args)


def target(args):
    return args["private_directory"] / "example.env"


def test_projection_and_rotation_preserve_source_and_values_out_of_report(prepared):
    result = apply(prepared)
    assert result["status"] == "ok" and result["source_security"] == "unverified"
    assert prepared["private_directory"].stat().st_mode & 0o777 == 0o700
    assert target(prepared).stat().st_mode & 0o777 == 0o600
    assert target(prepared).read_bytes() == prepared["source_env_file"].read_bytes()
    assert prepared["source_env_file"].stat().st_mode & 0o777 == 0o644
    environment = resolve_profile_environment(prepared["settings"], "example")
    assert environment is not None
    assert mapped_environment_values(environment) == (("GH_TOKEN", "fictional-original-value"),)
    prepared["source_env_file"].write_text("EXAMPLE_TOKEN=fictional-rotated-value\n")
    result = apply(prepared, operation="refresh")
    assert mapped_environment_values(environment) == (("GH_TOKEN", "fictional-rotated-value"),)
    manifest = prepared["private_directory"] / ".example.projection.json"
    assert "fictional-" not in json.dumps(result) + manifest.read_text()
    assert "sha256" not in manifest.read_text()


def test_repeat_prepare_keeps_one_projection_and_registry_bytes(prepared):
    apply(prepared)
    registry = prepared["settings"].read_bytes()
    result = apply(prepared)
    assert result["registry"] == "unchanged"
    assert prepared["settings"].read_bytes() == registry
    assert sorted(p.name for p in prepared["private_directory"].iterdir()) == [
        ".example.projection.json",
        ".example.projection.lock",
        "example.env",
    ]


@pytest.mark.parametrize(
    "body,missing", [("EXAMPLE_TOKEN=\n", ["EXAMPLE_TOKEN"]), ("EXAMPLE_TOKEN=valid\nOTHER=\n", [])]
)
def test_blanks_publish_pending_but_remain_invalid_for_activation(prepared, body, missing):
    prepared["source_env_file"].write_text(body)
    result = apply(prepared)
    assert result["status"] == "pending" and result["environment"]["missing"] == missing
    assert prepared["settings"].exists() and target(prepared).read_text() == body
    environment = resolve_profile_environment(prepared["settings"], "example")
    assert environment is not None
    with pytest.raises(ValidationError):
        mapped_environment_values(environment)


@pytest.mark.parametrize(
    "body", ["EXAMPLE_TOKEN=\nEXAMPLE_TOKEN=again\n", 'EXAMPLE_TOKEN="quoted"\n']
)
def test_pending_parser_still_rejects_duplicate_and_quoted_values(prepared, body):
    prepared["source_env_file"].write_text(body)
    with pytest.raises(ValidationError):
        apply(prepared)
    assert not prepared["settings"].exists() and not target(prepared).exists()


def test_reuse_local_pending_file_does_not_copy_or_chmod(prepared):
    prepared["source_env_file"].write_text("EXAMPLE_TOKEN=\n")
    prepared["source_env_file"].chmod(0o600)
    candidate = yaml.safe_load(prepared["candidate"])
    candidate["profiles"]["example"]["environment"]["file"] = "mounted.env"
    result = apply(
        prepared,
        candidate=yaml.safe_dump(candidate).encode(),
        private_directory=None,
        source_env_file=None,
    )
    assert result["status"] == "pending" and result["projection"] == "reused-local"
    assert not prepared["private_directory"].exists()
    assert prepared["source_env_file"].read_text() == "EXAMPLE_TOKEN=\n"


def test_no_environment_profile_is_ready_without_any_credential_source(prepared):
    data = yaml.safe_load(prepared["candidate"])
    del data["profiles"]["example"]["environment"]
    result = apply(
        prepared,
        candidate=yaml.safe_dump(data).encode(),
        private_directory=None,
        source_env_file=None,
    )
    assert result["status"] == "ok" and result["environment"]["status"] == "not-configured"


@pytest.mark.parametrize("failure", ["missing", "symlink", "malformed"])
def test_failed_refresh_never_leaves_stale_credentials_activatable(prepared, failure):
    apply(prepared)
    source = prepared["source_env_file"]
    if failure == "missing":
        source.unlink()
    elif failure == "symlink":
        other = source.with_name("other.env")
        source.rename(other)
        source.symlink_to(other)
    else:
        source.write_text('EXAMPLE_TOKEN="fictional-bad-value"\n')
    with pytest.raises((AdapterError, ValidationError)):
        apply(prepared, operation="refresh")
    assert not target(prepared).exists()
    environment = resolve_profile_environment(prepared["settings"], "example")
    assert environment is not None
    with pytest.raises(AdapterError):
        mapped_environment_values(environment)
    assert not list(prepared["private_directory"].glob("*.tmp"))


def test_candidate_preserves_defaults_unrelated_profiles_comments_and_allows_addition(prepared):
    original = (
        b"# Keep owner note\nschema_version: knowledge-profiles.v1\ndefault_profile: other\n"
        b"profiles:\n  other: {config: ./other.yaml} # Keep inline\n"
    )
    prepared["settings"].write_bytes(original)
    candidate = yaml.safe_load(prepared["candidate"])
    candidate["default_profile"] = "other"
    candidate["profiles"]["other"] = {"config": "./other.yaml"}
    candidate["profiles"]["extra"] = {"config": "./extra.yaml"}
    data = b"# Keep owner note\n# Keep inline\n" + yaml.safe_dump(candidate).encode()
    apply(prepared, candidate=data)
    assert prepared["settings"].read_bytes() == data


@pytest.mark.parametrize("change", ["default", "other", "comment"])
def test_registry_guard_rejects_unrelated_edits_before_projection(prepared, change):
    original = (
        b"# Preserve this\nschema_version: knowledge-profiles.v1\n"
        b"profiles:\n  other: {config: ./other.yaml}\n"
    )
    prepared["settings"].write_bytes(original)
    value = yaml.safe_load(prepared["candidate"])
    value["profiles"]["other"] = {"config": "./other.yaml"}
    if change == "default":
        value["default_profile"] = "example"
    elif change == "other":
        value["profiles"]["other"]["config"] = "changed.yaml"
    data = (b"" if change == "comment" else b"# Preserve this\n") + yaml.safe_dump(value).encode()
    with pytest.raises(AdapterError):
        apply(prepared, candidate=data)
    assert prepared["settings"].read_bytes() == original
    assert not prepared["private_directory"].exists()


def test_stale_registry_precondition_does_not_mutate_projection(prepared):
    apply(prepared)
    before = target(prepared).read_bytes()
    with pytest.raises(AdapterError, match="Reinspect"):
        apply(prepared, operation="refresh", expected_sha256="0" * 64)
    assert target(prepared).read_bytes() == before


def test_candidate_relative_bases_follow_final_registry_not_candidate_location(prepared, tmp_path):
    apply(prepared)
    environment = resolve_profile_environment(prepared["settings"], "example")
    assert environment is not None and environment.file == target(prepared)
    assert not list(tmp_path.glob(".container-profile-candidate-*"))


@pytest.mark.parametrize(
    "failure", ["directory-mode", "target-unowned", "source-target", "source-directory-link"]
)
def test_unsafe_projection_paths_are_rejected(prepared, tmp_path, failure):
    private = prepared["private_directory"]
    if failure in {"directory-mode", "target-unowned", "source-target"}:
        private.mkdir(mode=0o700)
    if failure == "directory-mode":
        private.chmod(0o755)
    elif failure == "target-unowned":
        target(prepared).write_text("unrelated")
        target(prepared).chmod(0o600)
    elif failure == "source-target":
        prepared["source_env_file"] = target(prepared)
    else:
        directory = tmp_path / "source-real"
        directory.mkdir()
        original = prepared["source_env_file"]
        original.rename(directory / "mounted.env")
        alias = tmp_path / "source-link"
        alias.symlink_to(directory, target_is_directory=True)
        prepared["source_env_file"] = alias / "mounted.env"
    with pytest.raises(AdapterError):
        apply(prepared)
    assert not prepared["settings"].exists()
    if failure == "target-unowned":
        assert target(prepared).read_text() == "unrelated"


def test_registry_publish_failure_removes_prepared_secret(prepared, monkeypatch):
    def fail(*args, **kwargs):
        raise AdapterError("registry-write-failed", "", "Interrupted fixture")

    monkeypatch.setattr(projection, "replace_registry", fail)
    with pytest.raises(AdapterError):
        apply(prepared)
    assert not target(prepared).exists() and not prepared["settings"].exists()
    assert prepared["source_env_file"].exists()


def test_interrupted_secret_write_is_cleaned_and_retry_succeeds(prepared, monkeypatch):
    original = projection._write_all

    def interrupted(descriptor, data):
        if b"fictional-original-value" in data:
            os.write(descriptor, data[:12])
            raise KeyboardInterrupt()
        return original(descriptor, data)

    monkeypatch.setattr(projection, "_write_all", interrupted)
    with pytest.raises(KeyboardInterrupt):
        apply(prepared)
    assert not target(prepared).exists()
    assert not list(prepared["private_directory"].glob("*.tmp"))
    monkeypatch.setattr(projection, "_write_all", original)
    assert apply(prepared)["status"] == "ok"


def test_concurrent_attempt_fails_without_changing_active_projection(prepared):
    apply(prepared)
    before = target(prepared).read_bytes()
    with (
        usage_lock(prepared["private_directory"] / ".example.projection.lock"),
        pytest.raises(AdapterError) as error,
    ):
        apply(prepared, operation="refresh")
    assert error.value.code == "usage-lock-busy"
    assert target(prepared).read_bytes() == before


def test_remove_detaches_registry_then_deletes_only_owned_files(prepared):
    apply(prepared)
    unrelated = prepared["private_directory"] / "unrelated.txt"
    unrelated.write_text("keep")
    value = yaml.safe_load(prepared["candidate"])
    del value["profiles"]["example"]["environment"]
    candidate = yaml.safe_dump(value).encode()
    result = apply(prepared, operation="remove", candidate=candidate, source_env_file=None)
    assert result["projection"] == "removed"
    assert not target(prepared).exists()
    assert not (prepared["private_directory"] / ".example.projection.json").exists()
    assert unrelated.read_text() == "keep" and prepared["source_env_file"].exists()
    assert (
        apply(prepared, operation="remove", candidate=candidate, source_env_file=None)["status"]
        == "ok"
    )


def test_remove_rejects_registry_still_referencing_private_target(prepared):
    apply(prepared)
    with pytest.raises(AdapterError) as error:
        apply(prepared, operation="remove", source_env_file=None)
    assert error.value.code == "projection-still-referenced"
    assert target(prepared).exists()


def test_script_reports_pending_without_secret_output(prepared, tmp_path):
    prepared["source_env_file"].write_text("EXAMPLE_TOKEN=\nOTHER=fictional-never-print\n")
    candidate = tmp_path / "reviewed.yaml"
    candidate.write_bytes(prepared["candidate"])
    root = Path(__file__).resolve().parents[3]
    script = (
        root
        / "packages/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts"
        / "prepare_container_profile.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--operation",
            "prepare",
            "--settings",
            str(prepared["settings"]),
            "--profile",
            "example",
            "--candidate",
            str(candidate),
            "--expected-sha256",
            "missing",
            "--private-directory",
            str(prepared["private_directory"]),
            "--source-env-file",
            str(prepared["source_env_file"]),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 3 and result.stderr == ""
    report = json.loads(result.stdout)
    assert report["status"] == "pending" and report["launch_allowed"] is False
    assert "fictional-never-print" not in result.stdout


def test_source_rotation_during_copy_is_rejected(prepared, monkeypatch):
    apply(prepared)
    original = projection.read_bytes

    def changing(path, **kwargs):
        data = original(path, **kwargs)
        if path == prepared["source_env_file"]:
            path.write_text("EXAMPLE_TOKEN=concurrent-rotation\n")
        return data

    monkeypatch.setattr(projection, "read_bytes", changing)
    with pytest.raises(AdapterError) as error:
        apply(prepared, operation="refresh")
    assert error.value.code == "projection-source-changed"
    assert not target(prepared).exists()


def test_abrupt_process_exit_recovers_journaled_temporary_secret(prepared, tmp_path):
    candidate = tmp_path / "reviewed.yaml"
    candidate.write_bytes(prepared["candidate"])
    program = """
import os, sys
from pathlib import Path
from agent_knowledge.infrastructure import container_profiles as module
original = module._write_all
def interrupted(fd, data):
    if data.startswith(b"EXAMPLE_TOKEN="):
        os.write(fd, data)
        os._exit(23)
    return original(fd, data)
module._write_all = interrupted
module.prepare_container_profile(operation="prepare", settings=Path(sys.argv[1]),
    profile="example", candidate=Path(sys.argv[2]).read_bytes(), expected_sha256=None,
    private_directory=Path(sys.argv[3]), source_env_file=Path(sys.argv[4]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            program,
            str(prepared["settings"]),
            str(candidate),
            str(prepared["private_directory"]),
            str(prepared["source_env_file"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 23 and result.stdout == result.stderr == ""
    assert not prepared["settings"].exists() and not target(prepared).exists()
    assert list(prepared["private_directory"].glob("*.tmp"))
    assert apply(prepared)["status"] == "ok"
    assert not list(prepared["private_directory"].glob("*.tmp"))


def test_remove_preserves_replaced_target_and_registry(prepared):
    apply(prepared)
    value = yaml.safe_load(prepared["candidate"])
    del value["profiles"]["example"]["environment"]
    original_registry = prepared["settings"].read_bytes()
    target(prepared).unlink()
    target(prepared).write_text("user-owned-replacement")
    target(prepared).chmod(0o600)
    with pytest.raises(AdapterError):
        apply(
            prepared,
            operation="remove",
            candidate=yaml.safe_dump(value).encode(),
            source_env_file=None,
        )
    assert target(prepared).read_text() == "user-owned-replacement"
    assert prepared["settings"].read_bytes() == original_registry


def test_selected_overrides_keep_the_registry_relative_base(prepared, tmp_path):
    from agent_knowledge.infrastructure.configuration import resolve_workspace

    (tmp_path / "local-source").mkdir()
    (tmp_path / "local-catalog.yaml").write_text(json.dumps(catalog_data()))
    value = yaml.safe_load(prepared["candidate"])
    value["profiles"]["example"]["overrides"] = {
        "sources": [{"id": "local", "root": "local-source", "catalog": "local-catalog.yaml"}],
        "receipts": {"directory": "local-usage"},
        "setup": {"venv": "local-venv"},
    }
    apply(prepared, candidate=yaml.safe_dump(value).encode())
    workspace = resolve_workspace(settings=prepared["settings"], profile="example")
    assert workspace.sources[0].root == tmp_path / "local-source"
    assert workspace.receipts.directory == tmp_path / "local-usage"
    assert workspace.definition.setup.venv == str(tmp_path / "local-venv")


def test_new_source_requires_prepare_instead_of_refresh(prepared, tmp_path):
    apply(prepared)
    source = tmp_path / "replacement-source.env"
    source.write_text("EXAMPLE_TOKEN=replacement\n")
    with pytest.raises(AdapterError) as error:
        apply(prepared, operation="refresh", source_env_file=source)
    assert error.value.code == "projection-owner-conflict"
    assert apply(prepared, operation="prepare", source_env_file=source)["status"] == "ok"
    assert target(prepared).read_bytes() == source.read_bytes()
