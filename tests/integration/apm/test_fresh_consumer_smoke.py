"""Exercise the fresh-consumer hook-registration proof without a full consumer run."""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from tests.e2e.skill_catalog_probe import verify_catalog_links, verify_markdown_parity

ROOT = Path(__file__).resolve().parents[3]
SMOKE = ROOT / "tests" / "e2e" / "fresh_consumer_smoke.py"
_PACKAGE_SOURCE = "_local/knowledge-agent-pack"


def _smoke_module():
    e2e_root = str(SMOKE.parent)
    sys.path.insert(0, e2e_root)
    try:
        spec = importlib.util.spec_from_file_location("fresh_consumer_smoke_under_test", SMOKE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(e2e_root)


def _package_group(command: str) -> dict[str, object]:
    return {
        "hooks": [{"type": "command", "command": command}],
        "_apm_source": _PACKAGE_SOURCE,
    }


def _runtime_group(command: str) -> dict[str, object]:
    return {"hooks": [{"type": "command", "command": command}]}


def _write_consumer_hooks(
    consumer: Path, *, command: str | dict[str, str], copilot_events: tuple[str, ...]
) -> bytes:
    def selected(provider: str) -> str:
        return command[provider] if isinstance(command, dict) else command

    codex = consumer / ".codex" / "hooks.json"
    claude = consumer / ".claude" / "settings.json"
    copilot_authored = consumer / ".github" / "hooks" / "hand-authored.json"
    for path in (codex, claude, copilot_authored):
        path.parent.mkdir(parents=True, exist_ok=True)

    codex.write_text(
        json.dumps(
            {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "hand-authored-codex"}]},
                    _runtime_group(selected("codex")),
                ],
                "UserPromptSubmit": [_runtime_group(selected("codex"))],
            }
        ),
        encoding="utf-8",
    )
    claude.write_text(
        json.dumps(
            {
                "SessionStart": [
                    {"hooks": [{"type": "command", "command": "hand-authored-claude"}]},
                    _runtime_group(selected("claude")),
                ],
                "UserPromptSubmit": [_runtime_group(selected("claude"))],
            }
        ),
        encoding="utf-8",
    )
    copilot_authored.write_text(
        json.dumps(
            {
                "hooks": {
                    "sessionStart": [
                        {"hooks": [{"type": "command", "command": "hand-authored-copilot"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    for provider in ("codex", "claude"):
        sidecar = consumer / f".{provider}" / "apm-hooks.json"
        sidecar.write_text(
            json.dumps(
                {
                    "SessionStart": [_package_group(selected(provider))],
                    "UserPromptSubmit": [_package_group(selected(provider))],
                }
            ),
            encoding="utf-8",
        )
    if copilot_events:
        package_copilot = (
            consumer / ".github" / "hooks" / "knowledge-agent-pack-knowledge-discovery.json"
        )
        package_copilot.write_text(
            json.dumps(
                {
                    "hooks": {
                        event: [{"hooks": [{"type": "command", "command": selected("copilot")}]}]
                        for event in copilot_events
                    },
                    "version": 1,
                }
            ),
            encoding="utf-8",
        )
    return copilot_authored.read_bytes()


def test_recovery_proof_requires_exact_launcher_and_copilot_lifecycle(tmp_path: Path) -> None:
    module = _smoke_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    launcher = consumer / ".agent-knowledge-venv" / "bin" / "agent-knowledge-hook"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")

    authored = _write_consumer_hooks(
        consumer,
        command="agent-knowledge-hook",
        copilot_events=("sessionStart",),
    )
    with pytest.raises(module.SmokeFailure, match="exact expected launcher"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=True,
            hook_launcher=launcher,
        )

    exact_command = {
        provider: module._expected_hook_command(
            launcher,
            provider,
            "sessionStart" if provider == "copilot" else "SessionStart",
            None,
        )
        for provider in ("codex", "claude", "copilot")
    }
    authored = _write_consumer_hooks(
        consumer,
        command=exact_command,
        copilot_events=("sessionStart", "userPromptSubmit"),
    )
    with pytest.raises(module.SmokeFailure, match="unsupported or missing events"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=True,
            hook_launcher=launcher,
        )

    authored = _write_consumer_hooks(
        consumer,
        command=exact_command,
        copilot_events=("sessionStart",),
    )
    with pytest.raises(module.SmokeFailure, match="unsupported or missing events"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=True,
            hook_launcher=launcher,
        )

    authored = _write_consumer_hooks(
        consumer,
        command=exact_command,
        copilot_events=("sessionStart", "userPromptTransformed"),
    )
    module._hook_registration_proof(
        consumer,
        copilot_authored=authored,
        package_present=True,
        hook_launcher=launcher,
    )


def test_uninstall_proof_rejects_a_partially_removed_package_group(tmp_path: Path) -> None:
    module = _smoke_module()
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    authored = _write_consumer_hooks(
        consumer,
        command="agent-knowledge-hook",
        copilot_events=(),
    )
    for provider in ("codex", "claude"):
        (consumer / f".{provider}" / "apm-hooks.json").unlink()
    codex = consumer / ".codex" / "hooks.json"
    document = json.loads(codex.read_text(encoding="utf-8"))
    document["UserPromptSubmit"] = []
    codex.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(module.SmokeFailure, match="Unexpected merged codex SessionStart"):
        module._hook_registration_proof(
            consumer,
            copilot_authored=authored,
            package_present=False,
        )


def test_skill_resource_proof_rejects_missing_scripts_and_stale_references(tmp_path: Path) -> None:
    module = _smoke_module()
    source = tmp_path / "source"
    consumer = tmp_path / "consumer"
    installed = consumer / "apm_modules/_local/knowledge-agent-pack"
    for skill in ("knowledge-setup", "knowledge-compound", "knowledge-upgrade"):
        root = source / ".apm/skills" / skill
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(f"# {skill}\n")
    script = source / ".apm/skills/knowledge-setup/scripts/setup_runtime.py"
    script.parent.mkdir()
    script.write_text("print('fixture')\n")
    catalogs = (installed / ".apm/skills", consumer / ".agents/skills", consumer / ".claude/skills")
    for catalog in catalogs:
        shutil.copytree(source / ".apm/skills", catalog)
    assert module._skill_resource_proof(source, installed, consumer) == catalogs

    missing = catalogs[1] / "knowledge-setup/scripts/setup_runtime.py"
    missing.unlink()
    with pytest.raises(module.SmokeFailure, match="missing or stale"):
        module._skill_resource_proof(source, installed, consumer)
    missing.write_bytes(script.read_bytes())
    stale = catalogs[2] / "knowledge-setup/references/scaffold-upgrades.md"
    stale.parent.mkdir()
    stale.write_text("# Old owner\n")
    with pytest.raises(module.SmokeFailure, match="missing or stale"):
        module._skill_resource_proof(source, installed, consumer)
    stale.unlink()
    missing.write_text("print('changed deployment')\n")
    with pytest.raises(module.SmokeFailure, match="differs from its source"):
        module._skill_resource_proof(source, installed, consumer)


def test_catalog_links_resolve_sibling_resources_and_ignore_fenced_examples(tmp_path: Path) -> None:
    setup = tmp_path / "knowledge-setup/references"
    setup.mkdir(parents=True)
    (setup / "existing-repository.md").write_text("# Integration\n\n## Preserve local skills\n")
    upgrade = tmp_path / "knowledge-upgrade"
    upgrade.mkdir()
    (upgrade / "SKILL.md").write_text(
        "[APM](../knowledge-setup/references/existing-repository.md#preserve-local-skills)\n\n"
        "```markdown\n[Example](missing-example.md)\n```\n"
        "[External](https://example.invalid/docs)\n"
    )
    report = verify_catalog_links(tmp_path)
    assert report["local_links"] == [
        {
            "source": "knowledge-upgrade/SKILL.md",
            "target": "knowledge-setup/references/existing-repository.md",
            "fragment": "preserve-local-skills",
        }
    ]


@pytest.mark.parametrize(
    "target,error",
    [
        ("../knowledge-setup/references/missing.md", "target is missing"),
        ("../knowledge-setup/references/existing-repository.md#missing", "anchor is missing"),
        ("../../outside.md", "escapes deployed catalog"),
    ],
)
def test_catalog_links_reject_incomplete_or_external_resource_paths(
    tmp_path: Path, target: str, error: str
) -> None:
    setup = tmp_path / "catalog/knowledge-setup/references"
    setup.mkdir(parents=True)
    (setup / "existing-repository.md").write_text("# Integration\n")
    upgrade = tmp_path / "catalog/knowledge-upgrade"
    upgrade.mkdir()
    (upgrade / "SKILL.md").write_text(f"[Integration]({target})\n")
    (tmp_path / "outside.md").write_text("# Outside\n")
    with pytest.raises(ValueError, match=error):
        verify_catalog_links(tmp_path / "catalog")


@pytest.fixture
def relocated_skill_catalog(tmp_path: Path):
    source = tmp_path / "source"
    for skill in ("knowledge-setup", "knowledge-compound", "knowledge-upgrade"):
        root = source / skill
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text("# Safe\n\n## Other\n")
    references = source / "knowledge-setup/references"
    references.mkdir()
    for name in ("current.md", "other.md"):
        (references / name).write_text("# Safe\n\n## Other\n")
    original = "../knowledge-setup/references/current.md#safe"
    (source / "knowledge-upgrade/SKILL.md").write_text(
        f"# Upgrade\n\nPreserve local work. [Setup]({original})\n\n"
        "```markdown\n[Example](missing.md)\n```\n"
    )
    consumer = tmp_path / "consumer"
    installed = consumer / "apm_modules/_local/knowledge-agent-pack/.apm/skills"
    native = consumer / ".agents/skills"
    shutil.copytree(source, installed)
    shutil.copytree(source, native)
    document = native / "knowledge-upgrade/SKILL.md"
    relocated = os.path.relpath(
        installed / "knowledge-setup/references/current.md", document.parent
    )
    document.write_text(document.read_text().replace(original, relocated + "#safe"))
    return source, installed, native, document


def test_markdown_parity_accepts_apm_links_to_the_exact_installed_package(
    relocated_skill_catalog,
) -> None:
    source, installed, native, _ = relocated_skill_catalog
    verify_markdown_parity(source, native, installed)
    report = verify_catalog_links(native, installed_catalog=installed)
    assert report["local_links"][0]["target"] == "knowledge-setup/references/current.md"


@pytest.mark.parametrize(
    "fault", ["owner", "file", "anchor", "prose", "fenced-example", "line-endings", "other-package"]
)
def test_markdown_parity_rejects_redirects_and_every_non_destination_change(
    relocated_skill_catalog, fault: str
) -> None:
    source, installed, native, document = relocated_skill_catalog
    body = document.read_text()
    if fault == "owner":
        body = body.replace("knowledge-setup/references/current.md", "knowledge-compound/SKILL.md")
    elif fault == "file":
        body = body.replace("current.md", "other.md")
    elif fault == "anchor":
        body = body.replace("#safe", "#other")
    elif fault == "prose":
        body = body.replace("Preserve local work.", "Discard local work.")
    elif fault == "fenced-example":
        body = body.replace("missing.md", "changed.md")
    elif fault == "line-endings":
        body = body.replace("\n", "\r\n")
    else:
        alternate = installed.parents[2] / "unrelated/.apm/skills"
        shutil.copytree(source, alternate)
        body = body.replace("_local/knowledge-agent-pack", "_local/unrelated")
    document.write_bytes(body.encode("utf-8"))
    with pytest.raises(ValueError, match="differs from its source|escapes deployed catalog"):
        verify_markdown_parity(source, native, installed)
