"""Keep run routing stable without blocking ordinary catalog maintenance."""

import json
from pathlib import Path

import pytest
import yaml

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.compounding import resolve_run
from agent_knowledge.infrastructure.configuration import resolve_workspace
from agent_knowledge.infrastructure.errors import AdapterError
from tests.integration.infrastructure.test_compounding import begin, workspace
from tests.integration.infrastructure.test_profiles import write_registry


def test_aliases_coordinate_one_store_and_allow_catalog_content_updates(tmp_path: Path) -> None:
    original = workspace(tmp_path)
    settings = write_registry(tmp_path, original.path)
    data = json.loads(settings.read_text())
    data["profiles"]["alias"] = data["profiles"]["personal"]
    settings.write_text(json.dumps(data))
    loaded = resolve_workspace(settings=settings, profile="personal")
    run_id = begin(loaded, ())
    catalog = yaml.safe_load(loaded.sources[0].catalog_path.read_text())
    catalog["topics"]["planning"] = {"label": "Planning"}
    loaded.sources[0].catalog_path.write_text(yaml.safe_dump(catalog))
    data["profiles"]["alias"]["overrides"] = {"receipts": {"retention_days": 90}}
    settings.write_text(json.dumps(data))
    alias = resolve_workspace(settings=settings, profile="alias")
    assert resolve_run(alias, run_id).run_id == run_id
    with pytest.raises(AdapterError) as error:
        begin(alias, ())
    assert error.value.code == "compound-active"


@pytest.mark.parametrize(
    "override",
    [
        {"applicable_scopes": ["org:example"]},
        {"signal_storage": {"code_root": "./another-code"}},
        {
            "sources": [
                {
                    "id": "knowledge",
                    "root": "../knowledge",
                    "catalog": "../catalog.yaml",
                    "publication": {
                        "repository": "example/knowledge",
                        "base_branch": "main",
                        "branch_prefix": "knowledge/",
                    },
                }
            ]
        },
    ],
)
def test_changed_route_rejects_run_before_further_mutation(
    tmp_path: Path, override: object
) -> None:
    original = workspace(tmp_path)
    settings = write_registry(tmp_path, original.path)
    loaded = resolve_workspace(settings=settings, profile="personal")
    run_id = begin(loaded, ())
    before = {p: p.read_bytes() for p in loaded.receipts.directory.rglob("*") if p.is_file()}
    data = json.loads(settings.read_text())
    data["profiles"]["personal"]["overrides"] = override
    settings.write_text(json.dumps(data))
    with pytest.raises(ValidationError) as error:
        resolve_run(resolve_workspace(settings=settings, profile="personal"), run_id)
    assert error.value.code == "configuration-route-mismatch"
    assert {p: p.read_bytes() for p in before} == before
