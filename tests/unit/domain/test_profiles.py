"""Prove profile selection and overlays without filesystem access."""

import json

import pytest

from agent_knowledge.domain.configuration import parse_workspace
from agent_knowledge.domain.profiles import (
    EnvironmentVariable,
    environment_session_pin_size,
    merge_overrides,
    parse_profiles,
    select_profile,
)
from agent_knowledge.domain.validation import ValidationError
from tests.unit.domain.test_configuration import workspace_data


def registry_data(**overrides: object) -> dict[str, object]:
    return {
        "schema_version": "knowledge-profiles.v1",
        "default_profile": "personal",
        "profiles": {"personal": {"config": "./personal.yaml"}},
        **overrides,
    }


def test_default_and_exact_selection_do_not_change_registry() -> None:
    registry = parse_profiles(registry_data())
    assert select_profile(registry, None).name == "personal"
    assert select_profile(registry, "personal").config == "./personal.yaml"
    with pytest.raises(ValidationError, match="Unknown profile"):
        select_profile(registry, "Personal")
    assert registry.default_profile == "personal"


def test_profile_environment_retains_only_declared_names_and_description() -> None:
    registry = parse_profiles(
        registry_data(
            profiles={
                "personal": {
                    "config": "./personal.yaml",
                    "environment": {
                        "file": "./private/personal.env",
                        "variables": {
                            "github": {
                                "from_env": "GITHUB_V_TOKEN",
                                "expose_as": "GH_TOKEN",
                                "description": "Personal GitHub repository access",
                            }
                        },
                    },
                }
            }
        )
    )

    environment = registry.profiles[0].environment
    assert environment is not None
    assert environment.file == "./private/personal.env"
    assert environment.variables[0].label == "github"
    assert environment.variables[0].from_env == "GITHUB_V_TOKEN"
    assert environment.variables[0].expose_as == "GH_TOKEN"


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"file": "./personal.env", "variables": {}},
        {
            "file": "./personal.env",
            "variables": {
                "GitHub": {
                    "from_env": "GITHUB_V_TOKEN",
                    "expose_as": "GH_TOKEN",
                    "description": "GitHub",
                }
            },
        },
        {
            "file": "./personal.env",
            "variables": {
                "github": {
                    "from_env": "not-valid",
                    "expose_as": "GH_TOKEN",
                    "description": "GitHub",
                }
            },
        },
        {
            "file": "./personal.env",
            "variables": {
                "github": {
                    "from_env": "GITHUB_V_TOKEN",
                    "expose_as": "GH_TOKEN",
                    "description": "GitHub",
                    "value": "forbidden",
                }
            },
        },
    ],
)
def test_profile_environment_is_closed_and_exact(environment: object) -> None:
    with pytest.raises(ValidationError):
        parse_profiles(
            registry_data(
                profiles={"personal": {"config": "./personal.yaml", "environment": environment}}
            )
        )


@pytest.mark.parametrize("field", ["from_env", "expose_as"])
def test_profile_environment_names_are_unique(field: str) -> None:
    first = {
        "from_env": "SOURCE_ONE",
        "expose_as": "TARGET_ONE",
        "description": "First",
    }
    second = {
        "from_env": "SOURCE_TWO",
        "expose_as": "TARGET_TWO",
        "description": "Second",
    }
    second[field] = first[field]

    with pytest.raises(ValidationError, match="must be unique"):
        parse_profiles(
            registry_data(
                profiles={
                    "personal": {
                        "config": "./personal.yaml",
                        "environment": {
                            "file": "./personal.env",
                            "variables": {"one": first, "two": second},
                        },
                    }
                }
            )
        )


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
def test_profile_environment_rejects_process_control_and_loader_internal_targets(
    target: str,
) -> None:
    with pytest.raises(ValidationError) as error:
        parse_profiles(
            registry_data(
                profiles={
                    "personal": {
                        "config": "./personal.yaml",
                        "environment": {
                            "file": "./personal.env",
                            "variables": {
                                "credential": {
                                    "from_env": "SOURCE_TOKEN",
                                    "expose_as": target,
                                    "description": "Credential",
                                }
                            },
                        },
                    }
                }
            )
        )

    assert error.value.code == "reserved-environment-name"


def test_profile_environment_rejects_a_declaration_too_large_for_session_pinning() -> None:
    variables = {
        f"credential-{index}": {
            "from_env": f"SOURCE_{index:04d}_{'X' * 40}",
            "expose_as": f"TARGET_{index:04d}_{'Y' * 40}",
            "description": "Credential",
        }
        for index in range(300)
    }

    with pytest.raises(ValidationError) as error:
        parse_profiles(
            registry_data(
                profiles={
                    "personal": {
                        "config": "./personal.yaml",
                        "environment": {"file": "./personal.env", "variables": variables},
                    }
                }
            )
        )

    assert error.value.code == "environment-session-state-too-large"


def test_session_pin_size_matches_the_infrastructure_json_contract() -> None:
    file = '/tmp/quoted-"-\U0001f680.env'
    variables = (EnvironmentVariable("credential", "SOURCE_TOKEN", "TARGET_TOKEN", "Credential"),)
    encoded = json.dumps(
        {
            "schema": "profile-environment-session.v1",
            "file": file,
            "variables": [{"from_env": "SOURCE_TOKEN", "expose_as": "TARGET_TOKEN"}],
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert environment_session_pin_size(file, variables) == len(encoded)


def test_overlay_replaces_lists_but_retains_unspecified_settings() -> None:
    base = parse_workspace(workspace_data(receipts={"enabled": False, "retention_days": 30}))
    registry = parse_profiles(
        registry_data(
            profiles={
                "personal": {
                    "config": "./personal.yaml",
                    "overrides": {"applicable_scopes": [], "receipts": {"retention_days": 60}},
                }
            }
        )
    )
    effective = merge_overrides(base, registry.profiles[0])
    assert effective.applicable_scopes == ()
    assert effective.receipts.retention_days == 60
    assert effective.receipts.enabled is False
    assert base.receipts.retention_days == 30
    assert effective.sources == base.sources


@pytest.mark.parametrize(
    "override",
    [
        {"workspace_id": "another"},
        {"schema_version": "wrong"},
        {"receipts": {"directory": None}},
        {"receipts": {"retention_days": True}},
        {"sources": []},
        {"setup": {"harnesses": ["codex", "codex"]}},
        {"receipts": {"retention_days": 0}},
        {"unknown": True},
    ],
)
def test_invalid_overrides_are_rejected_before_opening_workspaces(override: object) -> None:
    with pytest.raises(ValidationError):
        parse_profiles(
            registry_data(
                profiles={
                    "personal": {
                        "config": "./personal.yaml",
                        "overrides": override,
                    }
                }
            )
        )


def test_empty_registry_has_no_implicit_first_profile() -> None:
    registry = parse_profiles({"schema_version": "knowledge-profiles.v1", "profiles": {}})
    with pytest.raises(ValidationError, match="default"):
        select_profile(registry, None)


def test_partial_storage_override_requires_a_complete_effective_mapping() -> None:
    registry = parse_profiles(
        registry_data(
            profiles={
                "personal": {
                    "config": "./personal.yaml",
                    "overrides": {"signal_storage": {"code_root": ".."}},
                }
            }
        )
    )
    with pytest.raises(ValidationError):
        merge_overrides(parse_workspace(workspace_data()), registry.profiles[0])


@pytest.mark.parametrize("name", ["Work", "two words", "_private", "x" * 65, 17, "", "../work"])
def test_registry_names_are_exact_bounded_slugs(name: object) -> None:
    with pytest.raises(ValidationError):
        parse_profiles(
            registry_data(profiles={name: {"config": "base.yaml"}}, default_profile=name)
        )


@pytest.mark.parametrize(
    "value",
    [None, {"profiles": {}}, {"config": "~/base.yaml"}, {"config": "base.yaml", "overrides": None}],
)
def test_invalid_profile_records_are_rejected(value: object) -> None:
    with pytest.raises(ValidationError):
        parse_profiles(registry_data(profiles={"personal": value}))
