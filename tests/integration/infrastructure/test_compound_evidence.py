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
            status="published",
            repository="example/knowledge",
            publication_verified=True,
            checkout=str(checkout),
            before_revision=before,
            after_revision=after,
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
            repository="example/knowledge",
            publication_verified=True,
            checkout=str(tmp_path),
            before_revision="--bad",
            after_revision="HEAD",
        ),
    )
    assert result["status"] == "unavailable"
    assert "full commit hashes" in result["reason"]


def test_repository_patches_are_distinct_bounded_and_exportable_in_one_attempt(
    tmp_path: Path,
) -> None:
    import hashlib
    import json
    from datetime import UTC, datetime, timedelta

    from agent_knowledge.application.usage import export_usage
    from agent_knowledge.domain.compounding import (
        CompoundDecision,
        OwnerReference,
        SignalDisposition,
    )
    from agent_knowledge.infrastructure.compound_evidence import evidence_records
    from agent_knowledge.infrastructure.compounding import drain_signals
    from tests.integration.infrastructure.test_compounding import snapshot, stored_signal

    loaded = workspace(tmp_path)
    signal = stored_signal(loaded.signal_storage.signal_root / "shared/one.md", "one")
    selected = (snapshot(signal),)
    run_id = begin(loaded, selected)
    publications = []
    for slug in ("knowledge", "consumer"):
        checkout = tmp_path / slug / "repo"
        checkout.mkdir(parents=True)

        def git(*args: str, checkout: Path = checkout) -> str:
            return subprocess.run(
                ["git", "-C", str(checkout), *args], check=True, capture_output=True, text=True
            ).stdout.strip()

        git("init", "--initial-branch=main")
        git("config", "user.email", "test@example.com")
        git("config", "user.name", "Test")
        file = checkout / "guidance.md"
        file.write_text(f"Earlier {slug} work\n")
        git("add", ".")
        git("commit", "-m", "Before compounding")
        before = git("rev-parse", "HEAD")
        file.write_text(f"Earlier {slug} work\nDurable {slug} correction.\n")
        git("add", ".")
        git("commit", "-m", "This compounding change")
        after = git("rev-parse", "HEAD")
        file.write_text("Unrelated uncommitted work\n")
        publications.append(
            PublicationEvidence(
                "published",
                f"example/{slug}",
                True,
                commit=after,
                checkout=str(checkout),
                before_revision=before,
                after_revision=after,
            )
        )
    decision = SignalDisposition(
        "one",
        CompoundDecision.UPDATE,
        "Both authoring routes published.",
        (
            OwnerReference("guidance/example.md", source="knowledge"),
            OwnerReference("guidance.md", repository="example/consumer"),
        ),
    )
    drained = drain_signals(
        loaded, selected, (decision,), run_id=run_id, publications=tuple(publications)
    )
    assert drained.drained == ("one",)
    event = evidence_records(loaded, run_id)[-1]
    artifacts = event["artifacts"]["changes"]
    assert len(artifacts) == 2
    assert len({item["path"] for item in artifacts}) == 2
    assert {item["repository"] for item in artifacts} == {"example/knowledge", "example/consumer"}
    for artifact in artifacts:
        patch = (run_root(loaded, run_id) / artifact["path"]).read_bytes()
        slug = artifact["repository"].split("/")[-1]
        assert f"+Durable {slug} correction.".encode() in patch
        assert b"Unrelated uncommitted" not in patch
        assert b"+Earlier" not in patch
        assert artifact["fingerprint"] == "sha256:" + hashlib.sha256(patch).hexdigest()
        assert artifact["status"] == "captured"
    now = datetime.now(UTC)
    destination = tmp_path / "export"
    export_usage(
        loaded,
        {
            "since": (now - timedelta(days=1)).isoformat(),
            "until": (now + timedelta(days=1)).isoformat(),
            "destination": str(destination),
        },
    )
    exported = [
        json.loads(line) for line in (destination / "events.jsonl").read_text().splitlines()
    ]
    exported_drain = next(item for item in exported if item["operation"] == "compound.drain")
    assert exported_drain["artifacts"]["changes"] == artifacts
    assert exported_drain["agent_report"]["publications"] == event["agent_report"]["publications"]
    for artifact in artifacts:
        relative = f"compound/{run_id}/{artifact['path']}"
        assert (destination / relative).read_bytes() == (
            run_root(loaded, run_id) / artifact["path"]
        ).read_bytes()
