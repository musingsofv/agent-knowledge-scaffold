"""Resolve profiles against explicit authoring directories and effective catalogs."""

import json
from pathlib import Path

import pytest

from agent_knowledge.infrastructure.configuration import resolve_workspace, workspace_is_current
from agent_knowledge.infrastructure.profiles import list_profiles
from tests.integration.infrastructure.test_configuration import write_workspace


def write_registry(
    tmp_path: Path, config: Path, overrides: object = None, environment: object = None
) -> Path:
    path = tmp_path / "settings" / "config.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "knowledge-profiles.v1",
                "default_profile": "personal",
                "profiles": {
                    "personal": {
                        "config": str(config),
                        "overrides": overrides or {},
                        **({"environment": environment} if environment is not None else {}),
                    },
                    "offline": {"config": "/does-not-exist/workspace.yaml"},
                },
            }
        )
    )
    return path


def test_inherited_and_overridden_paths_keep_their_authoring_bases(tmp_path: Path) -> None:
    config = write_workspace(
        tmp_path, signal_storage={"scaffold_root": "../scaffold", "code_root": ".."}
    )
    settings = write_registry(
        tmp_path,
        config,
        {
            "signal_storage": {"code_root": "./code"},
            "receipts": {"retention_days": 60},
            "setup": {"venv": "./runtime"},
        },
    )
    workspace = resolve_workspace(settings=settings, profile="personal")
    assert workspace.signal_storage.scaffold_root == tmp_path / "scaffold"
    assert workspace.signal_storage.code_root == settings.parent / "code"
    assert workspace.receipts.directory == config.parent / "ai/usage"
    assert workspace.definition.setup.venv == str(settings.parent / "runtime")
    assert workspace.receipts.retention_days == 60
    assert len(list_profiles(settings)["profiles"]) == 2


def test_default_is_pinned_and_unrelated_profile_changes_do_not_invalidate(tmp_path: Path) -> None:
    config = write_workspace(tmp_path)
    settings = write_registry(tmp_path, config)
    workspace = resolve_workspace(settings=settings)
    data = json.loads(settings.read_text())
    data["default_profile"] = "offline"
    data["profiles"]["offline"]["config"] = "/different-missing.yaml"
    settings.write_text(json.dumps(data))
    assert workspace_is_current(workspace)
    assert (
        resolve_workspace(settings=settings, profile="personal").fingerprint
        == workspace.fingerprint
    )
    data["profiles"]["personal"]["overrides"]["receipts"] = {"retention_days": 90}
    settings.write_text(json.dumps(data))
    assert not workspace_is_current(workspace)


def test_direct_path_bypasses_bad_user_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = write_workspace(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = tmp_path / ".config/agent-knowledge/config.yaml"
    settings.parent.mkdir(parents=True)
    settings.write_text("broken: [")
    assert resolve_workspace(config=config).selection.mode == "config"


def test_profile_environment_path_is_registry_relative_and_not_fingerprinted(
    tmp_path: Path,
) -> None:
    config = write_workspace(tmp_path)
    settings = write_registry(
        tmp_path,
        config,
        environment={
            "file": "./secrets/personal.env",
            "variables": {
                "github": {
                    "from_env": "GITHUB_V_TOKEN",
                    "expose_as": "GH_TOKEN",
                    "description": "Personal GitHub repositories",
                }
            },
        },
    )
    workspace = resolve_workspace(settings=settings, profile="personal")

    assert workspace.environment is not None
    assert workspace.environment.file == settings.parent / "secrets/personal.env"
    assert workspace.selection.summary(workspace.fingerprint).get("environment") is None
    assert workspace_is_current(workspace)
    data = json.loads(settings.read_text())
    data["profiles"]["personal"]["environment"]["file"] = "./secrets/rotated.env"
    data["profiles"]["personal"]["environment"]["variables"]["github"]["description"] = (
        "Rotated personal GitHub repositories"
    )
    settings.write_text(json.dumps(data))
    assert workspace_is_current(workspace)


def test_profile_listing_does_not_open_environment_file(tmp_path: Path) -> None:
    config = write_workspace(tmp_path)
    settings = write_registry(
        tmp_path,
        config,
        environment={
            "file": "./missing.env",
            "variables": {
                "github": {
                    "from_env": "GITHUB_V_TOKEN",
                    "expose_as": "GH_TOKEN",
                    "description": "Personal GitHub repositories",
                }
            },
        },
    )

    result = list_profiles(settings)

    environment = next(
        item["environment"] for item in result["profiles"] if item["name"] == "personal"
    )
    assert environment["file"] == str(settings.parent / "missing.env")
    assert "available" not in environment["variables"][0]


def test_replaced_offline_sources_are_not_opened_but_invalid_base_is_rejected(
    tmp_path: Path,
) -> None:
    import yaml

    from agent_knowledge.domain.validation import ValidationError

    config = write_workspace(tmp_path)
    original = yaml.safe_load(config.read_text())
    source = original["sources"][0].copy()
    source["root"] = str((config.parent / source["root"]).resolve())
    source["catalog"] = str((config.parent / source["catalog"]).resolve())
    original["sources"][0]["root"] = "/offline/knowledge"
    original["sources"][0]["catalog"] = "/offline/catalog.yaml"
    config.write_text(yaml.safe_dump(original))
    settings = write_registry(tmp_path, config, {"sources": [source]})
    assert resolve_workspace(settings=settings, profile="personal").sources[0].root == Path(
        source["root"]
    )
    del original["sources"][0]["id"]
    config.write_text(yaml.safe_dump(original))
    with pytest.raises(ValidationError):
        resolve_workspace(settings=settings, profile="personal")


@pytest.mark.parametrize(
    "data", [b"\xff", b"profiles: {}\nprofiles: {}\n", b"x: &x [*x]\n", b"x: " + b"a" * 1048576]
)
def test_registry_uses_the_shared_strict_bounded_yaml_reader(tmp_path: Path, data: bytes) -> None:
    from agent_knowledge.domain.validation import ValidationError
    from agent_knowledge.infrastructure.errors import AdapterError

    path = tmp_path / "config.yaml"
    path.write_bytes(data)
    with pytest.raises((ValidationError, AdapterError)):
        list_profiles(path)
