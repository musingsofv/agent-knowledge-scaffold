"""Exercise configured discovery and snapshot paging over a neutral temporary source."""

import base64
from pathlib import Path

import pytest
import yaml

from agent_knowledge.application.discovery import catalog_result, context_result
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import load_workspace, resolve_workspace
from tests.factories import catalog_data


def workspace_file(tmp_path: Path) -> Path:
    """Create one configured empty source with a small catalog."""
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "catalog.yaml").write_text(yaml.safe_dump(catalog_data()))
    path = tmp_path / "workspace.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": "repo:orders",
                "applicable_scopes": ["org:example", "repo:orders"],
                "sources": [{"id": "knowledge", "root": "knowledge", "catalog": "catalog.yaml"}],
            }
        )
    )
    return path


def test_context_reports_explicit_scopes_paths_and_catalog_handles(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    result = context_result(load_workspace(config), {})

    assert result["workspace_id"] == "repo:orders"
    assert result["applicable_scopes"] == ["org:example", "repo:orders"]
    assert result["sources"][0]["root"] == str((tmp_path / "knowledge").resolve())
    assert result["sources"][0]["catalog"] == str((tmp_path / "catalog.yaml").resolve())
    assert result["signal_storage"] is None
    assert result["environment"] is None


def test_context_reports_profile_environment_metadata_without_values(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    secret = "context-secret-canary"
    env_file = tmp_path / "personal.env"
    env_file.write_text(f"GITHUB_V_TOKEN={secret}\n", encoding="utf-8")
    env_file.chmod(0o600)
    settings = tmp_path / "profiles.yaml"
    settings.write_text(
        yaml.safe_dump(
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

    result = context_result(resolve_workspace(settings=settings, profile="personal"), {})

    assert result["environment"] == {
        "file": str(env_file),
        "status": "ready",
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
    }
    assert secret not in repr(result)


def test_catalog_pages_all_matches_once_without_changing_predicates(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    first = catalog_result(load_workspace(config), {"dimension": "scopes", "limit": 1})
    second = catalog_result(
        load_workspace(config),
        {
            "dimension": "scopes",
            "limit": 1,
            "continuation": first["continuation"],
        },
    )

    assert first["total_matches"] == 2
    assert first["returned"] == 1
    assert first["truncated"] is True
    assert [item["id"] for item in first["results"] + second["results"]] == [
        "org:example",
        "repo:orders",
    ]
    assert second["continuation"] is None
    assert second["truncated"] is False


def test_catalog_alias_discovers_entity_and_returns_provenance(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    result = catalog_result(
        load_workspace(config), {"dimension": "technologies", "text": {"any": ["Postgres"]}}
    )

    assert result["results"][0]["id"] == "postgresql"
    assert result["results"][0]["source_ids"] == ["knowledge"]
    assert result["results"][0]["technology_families"] == ["relational-database"]


def test_empty_catalog_match_is_a_truthful_empty_page(tmp_path: Path) -> None:
    result = catalog_result(
        load_workspace(workspace_file(tmp_path)),
        {
            "dimension": "entities",
            "text": {"any": ["not present"]},
        },
    )

    assert result["results"] == []
    assert result["total_matches"] == result["returned"] == 0
    assert result["continuation"] is None


def test_changed_catalog_rejects_old_cursor(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    first = catalog_result(load_workspace(config), {"dimension": "scopes", "limit": 1})
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(catalog.read_text() + "\n# revised\n")

    with pytest.raises(ValidationError, match="snapshot") as caught:
        catalog_result(
            load_workspace(config),
            {"dimension": "scopes", "limit": 1, "continuation": first["continuation"]},
        )
    assert caught.value.code == "stale-snapshot"


def test_cursor_cannot_be_reused_with_different_query(tmp_path: Path) -> None:
    config = workspace_file(tmp_path)
    first = catalog_result(load_workspace(config), {"dimension": "scopes", "limit": 1})

    with pytest.raises(ValidationError) as caught:
        catalog_result(
            load_workspace(config),
            {"dimension": "entities", "limit": 1, "continuation": first["continuation"]},
        )
    assert caught.value.code == "invalid-continuation"


@pytest.mark.parametrize("cursor", ["not base64", "e30=", "W10=", "x" * 4097])
def test_invalid_cursor_is_not_an_empty_page(tmp_path: Path, cursor: str) -> None:
    with pytest.raises(ValidationError) as caught:
        catalog_result(
            load_workspace(workspace_file(tmp_path)),
            {"dimension": "scopes", "continuation": cursor},
        )
    assert caught.value.code == "invalid-continuation"


def test_deep_cursor_json_is_a_structured_input_error(tmp_path: Path) -> None:
    cursor = base64.b64encode(("[" * 1500 + "0" + "]" * 1500).encode()).decode()
    assert len(cursor) < 4096
    with pytest.raises(ValidationError) as caught:
        catalog_result(
            load_workspace(workspace_file(tmp_path)),
            {"dimension": "scopes", "continuation": cursor},
        )
    assert caught.value.code == "invalid-continuation"


def test_context_does_not_accept_implicit_request_filters(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as caught:
        context_result(load_workspace(workspace_file(tmp_path)), {"scope": ["org:example"]})
    assert caught.value.code == "unknown-field"
