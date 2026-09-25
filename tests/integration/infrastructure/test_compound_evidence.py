"""Prove evidence boundaries with real local Git revisions and safe artifacts."""

import subprocess
from pathlib import Path

from agent_knowledge.domain.compounding import PublicationEvidence
from agent_knowledge.infrastructure.compound_evidence import capture_changes, run_root
from tests.integration.infrastructure.test_compounding import begin, workspace


def test_change_patch_uses_only_declared_revision_boundaries(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    run_id = begin(loaded, ())
    checkout = tmp_path / "repo"
    checkout.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "--initial-branch=main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    file = checkout / "guidance.md"
    file.write_text("first unrelated change\n")
    git("add", ".")
    git("commit", "-m", "Before this run")
    before = git("rev-parse", "HEAD")
    file.write_text("first unrelated change\nApollo adopted for verified reasons.\n")
    git("add", ".")
    git("commit", "-m", "This run")
    after = git("rev-parse", "HEAD")
    file.write_text("Uncommitted unrelated work\n")
    result = capture_changes(
        loaded,
        run_id,
        "a" * 32,
        PublicationEvidence(
            status="published", checkout=str(checkout), before_revision=before, after_revision=after
        ),
    )
    assert result["status"] == "captured"
    assert result["before_revision"] == before
    patch = (run_root(loaded, run_id) / result["path"]).read_text()
    assert "+Apollo adopted" in patch
    assert "Uncommitted unrelated" not in patch
    assert "+first unrelated" not in patch


def test_unavailable_revision_evidence_is_explicit(tmp_path: Path) -> None:
    loaded = workspace(tmp_path)
    run_id = begin(loaded, ())
    result = capture_changes(
        loaded,
        run_id,
        "a" * 32,
        PublicationEvidence(
            status="published",
            checkout=str(tmp_path),
            before_revision="--bad",
            after_revision="HEAD",
        ),
    )
    assert result["status"] == "unavailable"
    assert "full commit hashes" in result["reason"]
