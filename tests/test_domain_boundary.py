"""Guard domain imports separately from the fast, in-memory semantic suite."""

import ast
from pathlib import Path

import pytest


def boundary_violations(source: str) -> set[str]:
    """Identify direct external dependencies and common external-effect calls."""
    allowed = {
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "types",
        "typing",
        "unicodedata",
    }
    violations: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in allowed:
                    violations.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1:
                continue
            module = node.module or ""
            if node.level or not (
                module.startswith("agent_knowledge.domain.") or module.split(".")[0] in allowed
            ):
                violations.add(module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "open",
                "exec",
                "eval",
                "__import__",
            }:
                violations.add(node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "now",
                "today",
                "read_text",
                "write_text",
                "read_bytes",
                "write_bytes",
                "getenv",
            }:
                violations.add(node.func.attr)
    return violations


def test_domain_has_no_direct_external_dependencies_or_io_calls() -> None:
    """Keep application, entrypoints, infrastructure and process state out of domain."""
    domain_root = Path(__file__).resolve().parents[1] / "src/agent_knowledge/domain"
    violations = {
        path.name: found
        for path in domain_root.rglob("*.py")
        if (found := boundary_violations(path.read_text()))
    }

    assert violations == {}


@pytest.mark.parametrize(
    "source",
    [
        "import os",
        "from ..infrastructure import files",
        "from ..application import retrieval",
        "from agent_knowledge.application import discovery",
        "from agent_knowledge.entrypoints.cli.main import main",
        "from agent_knowledge.infrastructure import files",
        "import yaml",
        "open('knowledge.md')",
        "datetime.now()",
        "path.read_text()",
    ],
)
def test_boundary_guard_detects_common_external_dependency_regressions(source: str) -> None:
    """Prove the guard rejects the errors it is intended to prevent."""
    assert boundary_violations(source)
