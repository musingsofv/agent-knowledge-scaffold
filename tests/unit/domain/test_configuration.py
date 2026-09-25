"""Validate author-provided workspace definitions without file or process state."""

from copy import deepcopy

import pytest

from agent_knowledge.domain.configuration import parse_workspace
from agent_knowledge.domain.validation import ValidationError


def workspace_data(**overrides: object) -> dict[str, object]:
    return {
        "schema_version": "knowledge-workspace.v1",
        "workspace_id": "repo:orders",
        "applicable_scopes": ["org:example", "repo:orders"],
        "sources": [{"id": "knowledge", "root": "../knowledge", "catalog": "../catalog.yaml"}],
    } | overrides


def test_workspace_retains_explicit_scopes_and_unresolved_paths() -> None:
    workspace = parse_workspace(workspace_data())
    assert workspace.workspace_id == "repo:orders"
    assert workspace.applicable_scopes == ("org:example", "repo:orders")
    assert workspace.sources[0].root == "../knowledge"
    assert workspace.sources[0].catalog == "../catalog.yaml"
    assert workspace.signal_storage is None
    assert workspace.sources[0].publication is None


def test_empty_scope_list_and_no_catalog_membership_inference() -> None:
    assert parse_workspace(workspace_data(applicable_scopes=[])).applicable_scopes == ()
    assert parse_workspace(workspace_data(workspace_id="unregistered:workspace"))


def test_optional_signal_and_publication_definitions() -> None:
    data = workspace_data(
        sources=[
            {
                "id": "knowledge",
                "root": "/srv/knowledge",
                "catalog": "/srv/catalog.yaml",
                "publication": {
                    "repository": "example/knowledge",
                    "base_branch": "main",
                    "branch_prefix": "knowledge/",
                },
            }
        ],
        signal_storage={"scaffold_root": "../scaffold", "code_root": ".."},
    )
    workspace = parse_workspace(data)
    assert workspace.signal_storage.scaffold_root == "../scaffold"
    assert workspace.sources[0].publication.repository == "example/knowledge"
    assert workspace.sources[0].publication.branch_prefix == "knowledge/"


def test_optional_setup_preferences_are_retained_without_provider_state() -> None:
    workspace = parse_workspace(
        workspace_data(
            setup={
                "venv": ".venv",
                "harnesses": ["codex", "claude", "copilot"],
                "automation": {
                    "name": "knowledge-compound",
                    "cadence": "daily",
                    "timezone": "Europe/London",
                },
            }
        )
    )

    assert workspace.setup is not None
    assert workspace.setup.venv == ".venv"
    assert workspace.setup.harnesses == ("codex", "claude", "copilot")
    assert workspace.setup.automation is not None
    assert workspace.setup.automation.name == "knowledge-compound"


@pytest.mark.parametrize(
    "setup",
    [
        {"harnesses": ["codex", "codex"]},
        {"automation": {"name": "bad\nname", "cadence": "daily", "timezone": "UTC"}},
        {"automation": {"name": "compound", "cadence": "daily\n", "timezone": "UTC"}},
        {"automation": {"name": "compound", "cadence": "daily", "timezone": "UTC\x00"}},
        {"unknown": True},
    ],
)
def test_setup_rejects_duplicate_or_unsafe_provider_preferences(setup: object) -> None:
    with pytest.raises(ValidationError):
        parse_workspace(workspace_data(setup=setup))


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"schema_version": "old.v1"}, "unsupported-schema"),
        ({"workspace_id": "Invalid Name"}, "invalid-identifier"),
        ({"applicable_scopes": ["any"]}, "reserved-identifier"),
        ({"applicable_scopes": ["repo:orders", "repo:orders"]}, "duplicate-value"),
        ({"sources": []}, "invalid-value"),
        ({"sources": {}}, "invalid-type"),
        (
            {"sources": [{"id": "a", "root": ".", "catalog": "catalog.yaml"}] * 2},
            "duplicate-source",
        ),
        ({"scope": ["repo:orders"]}, "unknown-field"),
        ({"signal_storage": None}, "invalid-type"),
        ({"signal_storage": {"scaffold_root": "../scaffold"}}, "missing-field"),
    ],
)
def test_rejects_invalid_workspace_shapes(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(ValidationError) as error:
        parse_workspace(workspace_data(**overrides))
    assert error.value.code == code


@pytest.mark.parametrize(
    "path",
    ["", " ", "~/.config", "$ROOT/knowledge", "https://example.com", "a\x00b", "a\\b", "a\nb"],
)
def test_rejects_ambiguous_config_path_syntax(path: str) -> None:
    with pytest.raises(ValidationError):
        parse_workspace(
            workspace_data(sources=[{"id": "knowledge", "root": path, "catalog": "catalog.yaml"}])
        )


@pytest.mark.parametrize(
    "publication",
    [
        {
            "repository": "https://github.com/example/repo",
            "base_branch": "main",
            "branch_prefix": "knowledge/",
        },
        {"repository": "example/repo", "base_branch": "-main", "branch_prefix": "knowledge/"},
        {
            "repository": "example/repo",
            "base_branch": "heads/../main",
            "branch_prefix": "knowledge/",
        },
        {"repository": "example/repo", "base_branch": "main", "branch_prefix": "knowledge//"},
        {"repository": "example/repo", "base_branch": "main", "branch_prefix": ""},
        {
            "repository": "example/repo",
            "base_branch": "main",
            "branch_prefix": "knowledge/",
            "token": "secret",
        },
    ],
)
def test_rejects_invalid_publication_data(publication: object) -> None:
    with pytest.raises(ValidationError):
        parse_workspace(
            workspace_data(
                sources=[
                    {
                        "id": "knowledge",
                        "root": ".",
                        "catalog": "catalog.yaml",
                        "publication": publication,
                    }
                ]
            )
        )


def test_definition_is_independent_of_later_input_mutation() -> None:
    data = workspace_data()
    original = deepcopy(data)
    workspace = parse_workspace(data)
    data["sources"] = []
    assert workspace == parse_workspace(original)


def test_receipts_default_to_enabled_thirty_day_local_usage() -> None:
    receipts = parse_workspace(workspace_data()).receipts
    assert receipts.enabled is True
    assert receipts.directory == "./ai/usage"
    assert receipts.retention_days == 30
    assert parse_workspace(workspace_data(receipts={})).receipts == receipts


def test_disabled_diagnostics_retain_archive_location_and_retention() -> None:
    receipts = parse_workspace(
        workspace_data(
            receipts={"enabled": False, "directory": "../scaffold/ai/usage", "retention_days": 7}
        )
    ).receipts
    assert receipts.enabled is False
    assert receipts.directory == "../scaffold/ai/usage"
    assert receipts.retention_days == 7


@pytest.mark.parametrize(
    "receipts",
    [
        None,
        [],
        {"enabled": "false"},
        {"enabled": 0},
        {"retention_days": True},
        {"retention_days": 0},
        {"retention_days": -1},
        {"retention_days": 1.5},
        {"retention_days": "30"},
        {"directory": "~/usage"},
        {"directory": "$HOME/usage"},
        {"directory": "https://example.com/usage"},
        {"unknown": "value"},
    ],
)
def test_receipt_policy_rejects_ambiguous_or_invalid_fields(receipts: object) -> None:
    with pytest.raises(ValidationError):
        parse_workspace(workspace_data(receipts=receipts))
