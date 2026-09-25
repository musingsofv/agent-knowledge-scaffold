"""Check explicit registry selection without resolving a complete workspace."""

from pathlib import Path

import pytest

from agent_knowledge.domain.profiles import parse_profiles
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import profiles
from tests.unit.domain.test_configuration import workspace_data


def test_settings_path_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AGENT_KNOWLEDGE_SETTINGS", raising=False)
    assert profiles.settings_path(None) == tmp_path / "home/.config/agent-knowledge/config.yaml"
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", str(tmp_path / "custom.yaml"))
    assert profiles.settings_path(None) == tmp_path / "custom.yaml"
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", "invalid-relative.yaml")
    assert profiles.settings_path(tmp_path / "explicit.yaml") == tmp_path / "explicit.yaml"


@pytest.mark.parametrize("override", ["", " ", "relative.yaml", "~/config.yaml"])
def test_settings_environment_override_requires_an_absolute_path(
    override: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", override)
    with pytest.raises(ValidationError) as error:
        profiles.settings_path(None)
    assert error.value.code == "invalid-settings-path"


def test_direct_workspace_does_not_read_registry_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_KNOWLEDGE_SETTINGS", "")
    monkeypatch.setattr(profiles, "read_bytes", lambda *args, **kwargs: b"workspace")
    monkeypatch.setattr(profiles, "load_mapping", lambda *args, **kwargs: workspace_data())
    prepared = profiles.prepare_workspace(config=tmp_path / "workspace.yaml")
    assert prepared.selection.mode == "config"
    assert prepared.environment is None


def test_environment_resolution_needs_only_registry_and_exact_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = parse_profiles(
        {
            "schema_version": "knowledge-profiles.v1",
            "default_profile": "reminders",
            "profiles": {
                "reminders": {"config": "missing-workspace.yaml"},
                "personal": {
                    "config": "another-missing-workspace.yaml",
                    "environment": {
                        "file": "secrets.env",
                        "variables": {
                            "token": {
                                "from_env": "LOCAL_TOKEN",
                                "expose_as": "TOOL_TOKEN",
                                "description": "Local tool credential",
                            }
                        },
                    },
                },
            },
        }
    )
    monkeypatch.setattr(profiles, "read_profiles", lambda path: registry)
    monkeypatch.setattr(profiles, "read_bytes", pytest.fail)
    settings = tmp_path / "config.yaml"
    assert profiles.resolve_profile_environment(settings, None) is None
    selected = profiles.resolve_profile_environment(settings, "personal")
    assert selected is not None
    assert selected.file == tmp_path / "secrets.env"
    assert selected.variables[0].expose_as == "TOOL_TOKEN"
    with pytest.raises(ValidationError):
        profiles.resolve_profile_environment(settings, "unknown")
