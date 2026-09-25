"""Use the real CLI boundary with explicit and default profile selections."""

import json
from pathlib import Path

import pytest

from agent_knowledge.entrypoints.cli.main import main
from tests.integration.application.test_discovery import workspace_file
from tests.integration.entrypoints.cli.test_main import output
from tests.integration.infrastructure.test_profiles import write_registry


def test_profile_listing_default_context_and_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    settings = write_registry(tmp_path, config, {"receipts": {"retention_days": 60}})
    assert main(["--settings", str(settings), "profiles", "list"]) == 0
    assert len(output(capsys)["profiles"]) == 2
    assert main(["--settings", str(settings), "context"]) == 0
    result = output(capsys)
    assert result["selection"]["profile"] == "personal"
    assert result["selection"]["mode"] == "default"
    assert result["receipts"]["retention_days"] == 60
    assert result["configuration"]["field_origins"]["receipts.retention_days"] == str(settings)


def test_search_receipt_uses_effective_override_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    settings = write_registry(tmp_path, config, {"receipts": {"directory": "./usage"}})
    (settings.parent / "usage").mkdir()
    assert main(["--settings", str(settings), "--profile", "personal", "search"]) == 0
    result = output(capsys)
    assert result["receipt"]["status"] == "written"
    receipt = json.loads(Path(result["receipt"]["path"]).read_text().splitlines()[-1])
    assert receipt["selection"]["profile"] == "personal"
    descriptor = json.loads((settings.parent / "usage" / receipt["descriptor"]).read_text())
    assert descriptor["configuration"]["values"]["receipts"]["directory"] == str(
        settings.parent / "usage"
    )
    assert not (config.parent / "ai/usage").exists()


def test_profile_environment_is_visible_only_on_safe_cli_surfaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    secret = "cli-profile-secret-canary"
    env_file = tmp_path / "private.env"
    env_file.write_text(f"GITHUB_V_TOKEN={secret}\n", encoding="utf-8")
    env_file.chmod(0o600)
    environment = {
        "file": str(env_file),
        "variables": {
            "github": {
                "from_env": "GITHUB_V_TOKEN",
                "expose_as": "GH_TOKEN",
                "description": "Personal GitHub repositories",
            }
        },
    }
    settings = write_registry(
        tmp_path,
        config,
        {"receipts": {"directory": "./usage"}},
        environment,
    )
    (settings.parent / "usage").mkdir()

    assert main(["--settings", str(settings), "profiles", "list"]) == 0
    listed = output(capsys)
    personal = next(item for item in listed["profiles"] if item["name"] == "personal")
    assert personal["environment"]["variables"][0]["from_env"] == "GITHUB_V_TOKEN"
    assert "available" not in personal["environment"]["variables"][0]
    assert main(["--settings", str(settings), "--profile", "personal", "context"]) == 0
    context = output(capsys)
    assert context["environment"]["status"] == "ready"
    assert context["environment"]["variables"][0]["available"] is True
    assert main(["--settings", str(settings), "--profile", "personal", "doctor"]) == 0
    checked = output(capsys)
    assert checked["readiness"]["environment"] == "ready"
    assert main(["--settings", str(settings), "--profile", "personal", "search"]) == 0
    searched = output(capsys)
    receipt = json.loads(Path(searched["receipt"]["path"]).read_text().splitlines()[-1])
    descriptor = json.loads((settings.parent / "usage" / receipt["descriptor"]).read_text())

    rendered = json.dumps([listed, context, checked, searched, receipt, descriptor])
    assert secret not in rendered
    assert str(env_file) not in json.dumps([receipt, descriptor])
    assert "GITHUB_V_TOKEN" not in json.dumps([receipt, descriptor])


def test_direct_config_context_has_no_profile_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)

    assert main(["--config", str(config), "context"]) == 0

    assert output(capsys)["environment"] is None


@pytest.mark.parametrize(
    "args",
    [
        ["--config", "base.yaml", "--profile", "personal", "search"],
        ["--config", "base.yaml", "--settings", "settings.yaml", "search"],
        ["--profile", "personal", "describe"],
        ["--profile", "personal", "profiles", "list"],
    ],
)
def test_conflicting_selectors_fail_without_reading_any_workspace(
    args: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(args) == 2
    assert output(capsys)["diagnostics"][0]["code"] == "invalid-arguments"


def test_catalog_continuation_pins_default_profile_but_rejects_changed_effective_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    settings = write_registry(tmp_path, config)
    request = tmp_path / "request.json"
    query = {"dimension": "scopes", "limit": 1}
    request.write_text(json.dumps(query))
    assert main(["--settings", str(settings), "catalog", "--request-file", str(request)]) == 0
    first = output(capsys)
    assert first["continuation"]
    query["continuation"] = first["continuation"]
    request.write_text(json.dumps(query))
    data = json.loads(settings.read_text())
    data["default_profile"] = "offline"
    settings.write_text(json.dumps(data))
    args = [
        "--settings",
        str(settings),
        "--profile",
        "personal",
        "catalog",
        "--request-file",
        str(request),
    ]
    assert main(args) == 0
    second = output(capsys)
    assert second["results"] != first["results"]
    data["profiles"]["personal"]["overrides"] = {"applicable_scopes": []}
    settings.write_text(json.dumps(data))
    assert main(args) == 2
    assert output(capsys)["diagnostics"][0]["code"] == "stale-snapshot"


def test_failed_profile_selection_does_not_choose_default_receipt_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = workspace_file(tmp_path)
    settings = write_registry(tmp_path, config)
    assert main(["--settings", str(settings), "--profile", "missing", "search"]) == 2
    result = output(capsys)
    assert result["selection"]["profile"] == "missing"
    assert result["receipt"]["status"] == "unavailable"
    assert not (config.parent / "ai/usage").exists()


def test_receipt_does_not_fall_back_when_selected_profile_disappears_mid_invocation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    entrypoint = importlib.import_module("agent_knowledge.entrypoints.cli.main")
    config = workspace_file(tmp_path)
    settings = write_registry(tmp_path, config, {"receipts": {"directory": "./usage"}})
    original = entrypoint.search_result

    def changing(workspace, request):
        result = original(workspace, request)
        settings.write_text('{"schema_version":"knowledge-profiles.v1","profiles":{}}')
        return result

    monkeypatch.setattr(entrypoint, "search_result", changing)
    assert main(["--settings", str(settings), "--profile", "personal", "search"]) == 0
    result = output(capsys)
    assert result["status"] == "ok"
    assert result["receipt"]["status"] == "failed"
    assert not (config.parent / "ai/usage").exists()
    assert not (settings.parent / "usage").exists()
