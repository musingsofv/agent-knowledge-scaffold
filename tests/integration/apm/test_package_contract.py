"""Keep the neutral APM package's source-owned contract explicit."""

import ast
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "packages" / "knowledge-agent-pack"
INSTRUCTION = PACKAGE / ".apm" / "instructions" / "agent-knowledge-discovery.instructions.md"
SETUP = PACKAGE / ".apm" / "skills" / "knowledge-setup"
COMPOUND = PACKAGE / ".apm" / "skills" / "knowledge-compound"
HOOK = PACKAGE / ".apm" / "hooks" / "knowledge-discovery.json"


def test_package_manifest_and_instruction_are_neutral() -> None:
    manifest = (PACKAGE / "apm.yml").read_text(encoding="utf-8")
    instruction = INSTRUCTION.read_text(encoding="utf-8")

    assert "name: knowledge-agent-pack" in manifest
    assert "agent-knowledge" in manifest
    assert "command -v agent-knowledge" in instruction
    assert "agent-knowledge describe" in instruction
    assert "repository-relative" in instruction


def test_scaffold_distributes_only_the_core_knowledge_package_and_skills() -> None:
    manifest = yaml.safe_load((ROOT / "apm.yml").read_text(encoding="utf-8"))
    assert manifest["dependencies"]["apm"] == ["./packages/knowledge-agent-pack"]
    assert {path.parent.name for path in (ROOT / "packages").glob("*/apm.yml")} == {
        "knowledge-agent-pack"
    }
    assert {path.parent.name for path in ROOT.glob("packages/*/.apm/skills/*/SKILL.md")} == {
        "knowledge-setup",
        "knowledge-compound",
    }
    assert not list(ROOT.glob(".apm/skills/*/SKILL.md"))
    assert {path.name for path in (ROOT / ".apm/instructions").glob("*.instructions.md")} == {
        "scaffold-local.instructions.md"
    }


def test_package_declares_provider_neutral_lifecycle_and_prompt_hooks() -> None:
    descriptor = json.loads(HOOK.read_text(encoding="utf-8"))
    assert set(descriptor["hooks"]) == {"SessionStart", "UserPromptSubmit"}
    for event_name in ("SessionStart", "UserPromptSubmit"):
        groups = descriptor["hooks"][event_name]
        assert len(groups) == 1
        entries = groups[0]["hooks"]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["type"] == "command"
        assert entry["command"] == "agent-knowledge-hook"
        assert entry["timeout"] == 3
        assert "matcher" not in groups[0]
    assert not (PACKAGE / ".apm" / "hooks" / "scripts").exists()


def test_setup_and_compound_skills_are_concise_and_provider_neutral() -> None:
    for name, path in (
        ("knowledge-setup", SETUP / "SKILL.md"),
        ("knowledge-compound", COMPOUND / "SKILL.md"),
    ):
        body = path.read_text(encoding="utf-8")
        _, _, frontmatter = body.partition("---\n")
        frontmatter, _, _ = frontmatter.partition("\n---")
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"] == name
        assert len(str(metadata["description"]).split()) <= 40
        assert "Use" in str(metadata["description"])
        assert "Do not use" in str(metadata["description"])
        assert "Success means" in str(metadata["description"])

    setup_text = (SETUP / "SKILL.md").read_text(encoding="utf-8")
    assert "references/business-onboarding.md" in setup_text
    assert (SETUP / "references/business-onboarding.md").is_file()
    assert "registered" in setup_text
    assert "<scaffold>/ai/signals" in setup_text
    assert "<scaffold>/.agent-knowledge-venv" in setup_text
    assert "Python 3.11" in setup_text
    assert "agent-knowledge-hook" in setup_text
    assert "codex`, `claude` and `copilot`" in setup_text
    assert "UserPromptSubmit" in setup_text
    assert "userPromptTransformed" in setup_text
    assert "session_id" in setup_text
    assert "Publication" in setup_text
    assert "daily" in setup_text

    all_package_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.suffix in {".md", ".py", ".yml", ".yaml"}
    )
    assert "knowledge-setup" in all_package_text
    assert "knowledge-compound" in all_package_text
    assert "agent-knowledge-compound:<workspace_id>" in all_package_text
    assert "knowledge_discovery.py" not in all_package_text
    assert (SETUP / "references" / "codex-scheduled.md").is_file()
    assert (SETUP / "references" / "claude-scheduled.md").is_file()
    assert (SETUP / "references" / "copilot-scheduled.md").is_file()


def test_setup_helper_is_standard_library_python_and_script_is_valid() -> None:
    script = SETUP / "scripts" / "setup_runtime.py"
    ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imports <= {
        "__future__",
        "argparse",
        "hashlib",
        "dataclasses",
        "json",
        "os",
        "pathlib",
        "re",
        "shlex",
        "shutil",
        "subprocess",
        "sys",
        "tempfile",
        "typing",
    }


def test_package_readme_documents_both_skills_and_setup_flow() -> None:
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "knowledge-setup" in readme
    assert "knowledge-compound" in readme
    assert "setup_runtime.py" in readme
    assert "pause/remove" in readme
    assert "agent-knowledge-compound:<workspace_id>" in readme
    assert "UserPromptSubmit" in readme
    assert "session ID" in readme


def test_runner_help_is_available_without_installing_a_consumer() -> None:
    result = subprocess.run(
        [str(ROOT / "tests" / "e2e" / "fresh-consumer-smoke"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "isolated agent-knowledge APM consumer" in result.stdout
    assert "--live-cli" in result.stdout

    hook_runner = subprocess.run(
        [str(ROOT / "tests" / "e2e" / "provider_hook_smoke.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert hook_runner.returncode == 0
    assert "installed provider discovery hooks" in hook_runner.stdout

    claude_runner = subprocess.run(
        [str(ROOT / "tests" / "e2e" / "claude_hook_acceptance.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert claude_runner.returncode == 0
    assert "Opus 5 hook acceptance" in claude_runner.stdout


def test_r8_evidence_runners_expose_safe_opt_in_controls() -> None:
    harness = subprocess.run(
        [str(ROOT / "tests" / "e2e" / "harness_agent_smoke.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    measurement = subprocess.run(
        [str(ROOT / "tests" / "e2e" / "retrieval_measurement.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert harness.returncode == 0
    assert "--live-agent" in harness.stdout
    assert "--require-passed" in harness.stdout
    assert "--providers" in harness.stdout
    assert measurement.returncode == 0
    assert "preview/body consumption" in measurement.stdout

    onboarding = subprocess.run(
        [sys.executable, str(ROOT / "tests/e2e/setup_onboarding_acceptance.py"), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert onboarding.returncode == 0
    assert "--live-agent" in onboarding.stdout
    assert "--provider" in onboarding.stdout
    assert "--wheel" in onboarding.stdout
