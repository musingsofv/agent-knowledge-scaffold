"""Prove complete local corpus discovery without following links or hiding failures."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_knowledge.domain.models import DocumentReference
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure import corpus
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.corpus import inventory, load_document
from agent_knowledge.infrastructure.errors import AdapterError
from tests.factories import catalog_data, knowledge_data
from tests.unit.domain.test_configuration import workspace_data


def make_workspace(tmp_path: Path, sources: tuple[str, ...] = ("knowledge",)) -> Workspace:
    """Create distinct explicit source roots and their shared fictional vocabulary."""
    (tmp_path / "catalog.yaml").write_text(json.dumps(catalog_data()))
    for source in sources:
        (tmp_path / source).mkdir()
    path = tmp_path / "workspace.yaml"
    path.write_text(
        json.dumps(
            workspace_data(
                sources=[{"id": name, "root": name, "catalog": "catalog.yaml"} for name in sources]
            )
        )
    )
    return load_workspace(path)


def write_knowledge(path: Path, body: str = "# Testing\n\nPreserve observable behavior.\n") -> Path:
    """Write one small valid Markdown envelope at a chosen corpus location."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + json.dumps(knowledge_data()) + "\n---\n" + body)
    return path


def test_inventory_is_sorted_and_includes_hidden_markdown_only(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, ("z-source", "a-source"))
    for source, relative in (
        ("z-source", "b.md"),
        ("a-source", "z.md"),
        ("a-source", ".hidden/a.md"),
        ("a-source", ".guide.md"),
    ):
        write_knowledge(tmp_path / source / relative)
    (tmp_path / "a-source/old.yaml").write_text("not knowledge")
    (tmp_path / "a-source/.git").mkdir()
    (tmp_path / "a-source/.git/ignored.md").write_text("not knowledge")
    assert inventory(workspace).files == (
        DocumentReference("a-source", ".guide.md"),
        DocumentReference("a-source", ".hidden/a.md"),
        DocumentReference("a-source", "z.md"),
        DocumentReference("z-source", "b.md"),
    )


def test_empty_inventory_is_valid_and_stable(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    first = inventory(workspace)
    assert first.files == ()
    assert first.fingerprint == inventory(workspace).fingerprint


def test_selected_sources_only_are_enumerated(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path, ("first", "second"))
    write_knowledge(tmp_path / "first/rule.md")
    (tmp_path / "second").rmdir()
    assert inventory(workspace, ("first",)).files == (DocumentReference("first", "rule.md"),)
    with pytest.raises(AdapterError):
        inventory(workspace)


def test_unknown_source_is_a_query_error(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    with pytest.raises(ValidationError) as error:
        inventory(workspace, ("unknown",))
    assert error.value.code == "unknown-source"


@pytest.mark.parametrize("kind", ["markdown", "directory", "dangling", "git-link"])
def test_internal_symlinks_are_errors_without_following_targets(tmp_path: Path, kind: str) -> None:
    workspace = make_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    write_knowledge(outside / "private.md")
    match kind:
        case "markdown":
            (tmp_path / "knowledge/link.md").symlink_to(outside / "private.md")
        case "directory":
            (tmp_path / "knowledge/link").symlink_to(outside, target_is_directory=True)
        case "dangling":
            (tmp_path / "knowledge/link.md").symlink_to(outside / "missing.md")
        case "git-link":
            (tmp_path / "knowledge/.git").symlink_to(outside, target_is_directory=True)
    with pytest.raises(AdapterError) as error:
        inventory(workspace)
    assert error.value.code == "unsafe-path"


def test_nonregular_markdown_is_diagnosed_without_opening_fifo(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    os.mkfifo(tmp_path / "knowledge/pipe.md")
    with pytest.raises(AdapterError) as error:
        inventory(workspace)
    assert error.value.code == "not-regular-file"


@pytest.mark.parametrize("change", ["edit", "replace", "add", "remove", "rename-directory"])
def test_inventory_fingerprint_detects_corpus_changes(tmp_path: Path, change: str) -> None:
    workspace = make_workspace(tmp_path)
    path = write_knowledge(tmp_path / "knowledge/runbooks/test.md")
    before = inventory(workspace)
    match change:
        case "edit":
            path.write_text(path.read_text() + "A new warning.\n")
        case "replace":
            replacement = tmp_path / "replacement.md"
            replacement.write_bytes(path.read_bytes())
            replacement.replace(path)
        case "add":
            write_knowledge(tmp_path / "knowledge/added.md")
        case "remove":
            path.unlink()
        case "rename-directory":
            path.parent.rename(tmp_path / "knowledge/procedures")
    assert inventory(workspace).fingerprint != before.fingerprint


def test_direct_load_preserves_metadata_and_locations_without_scanning_others(
    tmp_path: Path,
) -> None:
    workspace = make_workspace(tmp_path)
    path = write_knowledge(tmp_path / "knowledge/runbooks/test.md", "# Details\n\nExact body.\n")
    (tmp_path / "knowledge/malformed.md").write_text("bad document")
    document = load_document(workspace, DocumentReference("knowledge", "runbooks/test.md"))
    assert document.source_id == "knowledge"
    assert document.path == "runbooks/test.md"
    assert document.local_path == path
    assert document.parsed.body == "# Details\n\nExact body.\n"
    assert document.metadata.title == "Test observable behavior"
    assert document.parsed.byte_count == len(path.read_bytes())
    assert document.parsed.body_range == (4, 6)


@pytest.mark.parametrize(
    "relative,code",
    [("../outside.md", "invalid-path"), ("rule.yaml", "invalid-document-extension")],
)
def test_direct_load_rejects_escaping_paths_and_yaml_fallbacks(
    tmp_path: Path, relative: str, code: str
) -> None:
    workspace = make_workspace(tmp_path)
    with pytest.raises(ValidationError) as error:
        load_document(workspace, DocumentReference("knowledge", relative))
    assert error.value.code == code


def test_direct_load_validates_metadata_instead_of_forgiving_malformed_files(
    tmp_path: Path,
) -> None:
    workspace = make_workspace(tmp_path)
    (tmp_path / "knowledge/bad.md").write_text("---\nkind: rule\n---\nBody\n")
    with pytest.raises(ValidationError) as error:
        load_document(workspace, DocumentReference("knowledge", "bad.md"))
    assert "bad.md" in error.value.path


def test_missing_target_does_not_become_empty_document(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    with pytest.raises(AdapterError) as error:
        load_document(workspace, DocumentReference("knowledge", "absent.md"))
    assert error.value.code == "file-missing"


def test_enumeration_permission_failure_is_not_an_empty_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)

    def denied(descriptor: int) -> list[str]:
        raise PermissionError(13, "simulated denial")

    monkeypatch.setattr(corpus.os, "listdir", denied)
    with pytest.raises(AdapterError) as error:
        inventory(workspace)
    assert error.value.code == "directory-unreadable"


def test_addition_while_enumerating_requires_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.listdir

    def changing(descriptor: int) -> list[str]:
        names = original(descriptor)
        write_knowledge(tmp_path / "knowledge/late.md")
        return names

    monkeypatch.setattr(corpus.os, "listdir", changing)
    with pytest.raises(AdapterError) as error:
        inventory(workspace)
    assert error.value.code == "corpus-changed"


def test_root_replacement_during_enumeration_requires_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    original = os.listdir

    def changing(descriptor: int) -> list[str]:
        names = original(descriptor)
        (tmp_path / "knowledge").rename(tmp_path / "old-root")
        (tmp_path / "knowledge").mkdir()
        return names

    monkeypatch.setattr(corpus.os, "listdir", changing)
    with pytest.raises(AdapterError) as error:
        inventory(workspace)
    assert error.value.code == "corpus-changed"


def test_directory_symlink_swap_during_enumeration_never_enters_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    write_knowledge(tmp_path / "knowledge/nested/rule.md")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside/private.md").write_text("private")
    original = corpus._open_relative_directory

    @contextmanager
    def changing(root: int, parts: tuple[str, ...], path: Path) -> Iterator[int]:
        if parts == ("nested",):
            (tmp_path / "knowledge/nested").rename(tmp_path / "old-nested")
            (tmp_path / "knowledge/nested").symlink_to(
                tmp_path / "outside", target_is_directory=True
            )
        with original(root, parts, path) as directory:
            yield directory

    monkeypatch.setattr(corpus, "_open_relative_directory", changing)
    with pytest.raises(AdapterError) as error:
        inventory(workspace)
    assert error.value.code == "unsafe-path"


def test_direct_read_is_bounded_before_parsing(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    path = tmp_path / "knowledge/huge.md"
    with path.open("wb") as output:
        output.truncate(8_388_609)
    with pytest.raises(AdapterError) as error:
        load_document(workspace, DocumentReference("knowledge", "huge.md"))
    assert error.value.code == "file-too-large"


def test_direct_read_rejects_parent_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = make_workspace(tmp_path)
    write_knowledge(tmp_path / "knowledge/nested/rule.md")
    original = corpus.read_bytes

    def changing(path: Path, *, max_bytes: int) -> bytes:
        result = original(path, max_bytes=max_bytes)
        path.parent.rename(tmp_path / "moved")
        write_knowledge(tmp_path / "knowledge/nested/rule.md")
        return result

    monkeypatch.setattr(corpus, "read_bytes", changing)
    with pytest.raises(AdapterError) as error:
        load_document(workspace, DocumentReference("knowledge", "nested/rule.md"))
    assert error.value.code == "corpus-changed"


def test_direct_read_cannot_open_excluded_git_metadata(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path)
    write_knowledge(tmp_path / "knowledge/.git/rule.md")
    with pytest.raises(ValidationError) as error:
        load_document(workspace, DocumentReference("knowledge", ".git/rule.md"))
    assert error.value.code == "invalid-document-path"
