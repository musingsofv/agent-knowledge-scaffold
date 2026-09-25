"""Resolve one document's references without reading linked knowledge bodies."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from agent_knowledge.domain.navigation import MarkdownLink, scan_markdown
from agent_knowledge.domain.schema import parse_knowledge
from agent_knowledge.infrastructure.configuration import Workspace, load_workspace
from agent_knowledge.infrastructure.corpus import LoadedDocument
from agent_knowledge.infrastructure.documents import dump_document, parse_document
from agent_knowledge.infrastructure.links import ResolvedLink, resolve_links
from tests.factories import knowledge_data
from tests.integration.infrastructure.test_configuration import write_workspace


@pytest.fixture
def context(tmp_path: Path) -> tuple[Workspace, LoadedDocument]:
    config = write_workspace(
        tmp_path,
        sources=[
            {"id": "first", "root": "../first", "catalog": "../catalog.yaml"},
            {"id": "second", "root": "../second", "catalog": "../catalog.yaml"},
        ],
    )
    workspace = load_workspace(config)
    for source in workspace.sources:
        source.root.mkdir()
    path = workspace.sources[0].root / "runbooks/current.md"
    path.parent.mkdir()
    raw = dump_document(knowledge_data(), "# Current\n\n## Useful procedure\n\nSteps.\n")
    path.write_bytes(raw)
    parsed = parse_document(raw, path=str(path))
    current = LoadedDocument(
        "first",
        "runbooks/current.md",
        path,
        parsed,
        parse_knowledge(parsed.metadata, workspace.catalog),
    )
    return workspace, current


def references(
    context: tuple[Workspace, LoadedDocument], *targets: str | None
) -> tuple[ResolvedLink, ...]:
    workspace, current = context
    navigation = scan_markdown(current.parsed.body, start_line=current.parsed.body_range[0])
    navigation = replace(
        navigation,
        links=tuple(
            MarkdownLink(f"Reference {index}", target, index + 30, index + 30)
            for index, target in enumerate(targets)
        ),
    )
    return resolve_links(workspace, current, navigation)


def test_same_file_anchors_are_checked_against_current_navigation(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    found, missing, empty, explicit = references(
        context, "#useful-procedure", "#absent", "#", "current.md#useful-procedure"
    )
    assert (found.status, found.anchor_status, found.anchor) == (
        "resolved",
        "resolved",
        "useful-procedure",
    )
    assert found.document.source == "first"
    assert found.document.path == "runbooks/current.md"
    assert (missing.status, missing.anchor_status) == ("resolved", "missing")
    assert empty.anchor_status == "not-present"
    assert explicit.anchor_status == "resolved"


def test_relative_existing_target_preserves_original_and_location(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    workspace, current = context
    target = current.local_path.parent / "other.md"
    target.write_text("A linked file, deliberately not valid canonical metadata.")
    link = references(context, "other.md#later")[0]
    assert link.status == "resolved"
    assert link.anchor_status == "unverified"
    assert link.target == "other.md#later"
    assert link.local_path == str(target)
    assert link.document.source == workspace.sources[0].id
    assert link.document.path == "runbooks/other.md"
    assert link.start_line == link.end_line == 30


def test_cross_source_relative_and_absolute_paths(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    workspace, _ = context
    target = workspace.sources[1].root / "principle.md"
    target.write_text("# Related principle")
    relative, absolute = references(context, "../../second/principle.md", str(target))
    assert relative.document == absolute.document
    assert relative.document.source == "second"
    assert relative.document.path == "principle.md"
    assert relative.status == absolute.status == "resolved"


def test_missing_targets_and_unresolved_references_stay_visible(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    missing, reference = references(context, "gone.md#section", None)
    assert (missing.status, missing.anchor_status) == ("missing", "unverified")
    assert missing.document.path == "runbooks/gone.md"
    assert reference.status == "unresolved"
    assert reference.target is None
    assert reference.reason


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/doc#part",
        "http://example.com",
        "mailto:team@example.com",
        "../code.py",
        "../../outside/README.txt",
    ],
)
def test_external_evidence_is_classified_without_stat(
    context: tuple[Workspace, LoadedDocument], monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("External evidence must not be accessed")

    with monkeypatch.context() as patch:
        patch.setattr(os, "stat", forbidden)
        patch.setattr(os, "open", forbidden)
        link = references(context, target)[0]
    assert link.status == "external"
    assert link.document is None


def test_unconfigured_markdown_path_is_not_accessed(
    context: tuple[Workspace, LoadedDocument], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Unconfigured Markdown target must not be accessed")

    with monkeypatch.context() as patch:
        patch.setattr(os, "stat", forbidden)
        patch.setattr(os, "open", forbidden)
        link = references(context, "../../outside/private.md")[0]
    assert link.status == "unresolved"
    assert "configured" in link.reason
    assert link.local_path is None


@pytest.mark.parametrize(
    "target",
    [
        "ftp://example.com/file.md",
        "javascript:alert(1)",
        "other.md?view=plain",
        "other%ZZ.md",
        "other%FF.md",
        "other.md#%ZZ",
        "other.md#%FF",
        "other%00.md",
        "bad\\path.md",
    ],
)
def test_unsupported_and_malformed_destinations_remain_visible(
    context: tuple[Workspace, LoadedDocument], target: str
) -> None:
    link = references(context, target)[0]
    assert link.status == "unresolved"
    assert link.reason
    assert link.target == target


def test_percent_encoded_filename_and_anchor(context: tuple[Workspace, LoadedDocument]) -> None:
    _, current = context
    target = current.local_path.parent / "index guide.md"
    target.write_text("Unopened content")
    encoded, anchor = references(
        context, "index%20guide.md#future%20section", "#useful%2Dprocedure"
    )
    assert encoded.status == "resolved"
    assert encoded.document.path == "runbooks/index guide.md"
    assert encoded.anchor == "future section"
    assert encoded.anchor_status == "unverified"
    assert anchor.anchor_status == "resolved"


def test_links_never_read_target_bodies_or_recurse(
    context: tuple[Workspace, LoadedDocument], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, current = context
    target = current.local_path.parent / "cycle.md"
    target.write_text("[Back](current.md)\n[Self](cycle.md)\n")
    original_open = os.open

    def directories_only(path: object, flags: int, *args: object, **kwargs: object) -> int:
        assert flags & os.O_DIRECTORY, "Only directory descriptors may be opened"
        return original_open(path, flags, *args, **kwargs)

    def no_body_read(*args: object, **kwargs: object) -> None:
        pytest.fail("Linked bodies must not be opened through Python file helpers")

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", directories_only)
        patch.setattr("builtins.open", no_body_read)
        patch.setattr(Path, "open", no_body_read)
        links = references(context, "cycle.md", "current.md")
    assert len(links) == 2
    assert all(link.status == "resolved" for link in links)


@pytest.mark.parametrize("outside", [False, True])
def test_internal_file_symlinks_are_unsafe_even_when_target_is_configured(
    context: tuple[Workspace, LoadedDocument], outside: bool
) -> None:
    workspace, current = context
    target = (workspace.path.parent if outside else workspace.sources[1].root) / "target.md"
    target.write_text("Do not follow")
    (current.local_path.parent / "alias.md").symlink_to(target)
    link = references(context, "alias.md")[0]
    assert link.status == "unsafe"
    assert link.reason


def test_symlink_component_cannot_be_hidden_by_parent_normalization(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    workspace, current = context
    (current.local_path.parent / "alias").symlink_to(
        workspace.sources[1].root, target_is_directory=True
    )
    link = references(context, "alias/../current.md")[0]
    assert link.status == "unsafe"


def test_missing_parent_directory_is_missing_not_resolved(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    link = references(context, "absent/target.md")[0]
    assert link.status == "missing"


def test_directory_with_markdown_suffix_is_unresolved(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    _, current = context
    (current.local_path.parent / "directory.md").mkdir()
    link = references(context, "directory.md")[0]
    assert link.status == "unresolved"
    assert "regular file" in link.reason


def test_percent_encoded_control_anchor_is_malformed(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    link = references(context, "#%00")[0]
    assert link.status == "unresolved"
    assert link.anchor is None


def test_dangling_symlink_stays_unsafe_instead_of_missing(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    _, current = context
    (current.local_path.parent / "dangling.md").symlink_to("absent.md")
    assert references(context, "dangling.md")[0].status == "unsafe"


def test_intermediate_symlink_is_unsafe(context: tuple[Workspace, LoadedDocument]) -> None:
    workspace, current = context
    (workspace.sources[1].root / "target.md").write_text("Do not open")
    (current.local_path.parent / "alias").symlink_to(
        workspace.sources[1].root, target_is_directory=True
    )
    assert references(context, "alias/target.md")[0].status == "unsafe"


def test_replacement_after_location_check_is_not_followed(
    context: tuple[Workspace, LoadedDocument], monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_knowledge.infrastructure import links

    workspace, current = context
    target = current.local_path.parent / "target.md"
    target.write_text("Original")
    outside = workspace.path.parent / "outside.md"
    outside.write_text("Do not follow replacement")
    original_resolve = links.resolve_document_path

    def replace_target(root: Path, relative: str) -> Path:
        resolved = original_resolve(root, relative)
        target.unlink()
        target.symlink_to(outside)
        return resolved

    monkeypatch.setattr(links, "resolve_document_path", replace_target)
    assert references(context, "target.md")[0].status == "unsafe"


def test_unreadable_reference_is_unresolved_not_missing(
    context: tuple[Workspace, LoadedDocument], monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno

    def denied(*args: object, **kwargs: object) -> int:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(os, "open", denied)
    link = references(context, "other.md")[0]
    assert link.status == "unresolved"
    assert "safely" in link.reason


@pytest.mark.parametrize("target", ["UPPER.MD", ".git/rule.md", "nested/.git/rule.md"])
def test_non_corpus_paths_are_external_without_access(
    context: tuple[Workspace, LoadedDocument], monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    _, current = context
    path = current.local_path.parent / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Not an eligible canonical document")

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Excluded corpus paths must not be accessed")

    with monkeypatch.context() as patch:
        patch.setattr(os, "stat", forbidden)
        patch.setattr(os, "open", forbidden)
        link = references(context, target)[0]
    assert link.status == "external"
    assert link.document is None
    assert link.local_path is None
    assert link.reason


def test_git_named_markdown_file_is_still_canonical(
    context: tuple[Workspace, LoadedDocument],
) -> None:
    _, current = context
    (current.local_path.parent / ".git.md").write_text("Eligible hidden Markdown file")
    link = references(context, ".git.md")[0]
    assert link.status == "resolved"
    assert link.document.path == "runbooks/.git.md"
