"""Discover explicit Markdown sources and read individual canonical documents.

Inventory stores paths and stat fingerprints, never document bodies. Hidden
directories and files are included; only real ``.git`` directories are skipped.
Ignore files have no effect. Internal symlinks are diagnosed without following
them, including dangling links and links whose target type cannot be known safely.
Callers compare inventories before and after streamed document processing before
returning a successful scan. This detects concurrent changes without a database or
retaining all bodies; it does not lock writers or promise an atomic filesystem.
"""

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from agent_knowledge.domain.models import DocumentReference, KnowledgeMetadata
from agent_knowledge.domain.schema import parse_knowledge
from agent_knowledge.domain.validation import ValidationError, read_relative_path

from .configuration import Source, Workspace
from .documents import DEFAULT_DOCUMENT_BYTES, ParsedDocument, parse_document
from .errors import AdapterError
from .filesystem import _identity, _io_error, open_directory, read_bytes, resolve_document_path


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """Bind validated metadata and navigation facts to one explicitly selected file."""

    source_id: str
    path: str
    local_path: Path
    parsed: ParsedDocument
    metadata: KnowledgeMetadata


@dataclass(frozen=True, slots=True)
class Inventory:
    """Retain a deterministic file list and source/directory/file stat fingerprint."""

    files: tuple[DocumentReference, ...]
    fingerprint: str


def inventory(workspace: Workspace, source_ids: tuple[str, ...] | None = None) -> Inventory:
    """Enumerate only selected sources, failing if completeness cannot be established.

    File bytes and frontmatter are validated later by ``load_document`` as the
    caller processes this inventory. A successful inventory alone certifies no
    knowledge claims and does not establish that the documents are valid.
    """
    requested = workspace.catalog.source_ids if source_ids is None else source_ids
    sources = tuple(_source(workspace, identifier) for identifier in sorted(set(requested)))
    files: list[DocumentReference] = []
    parts: list[str] = []
    for source in sources:
        source_files, source_parts = _inventory_source(source)
        files.extend(DocumentReference(source.id, relative) for relative in source_files)
        parts.extend((source.id, str(source.root), *source_parts))
    digest = hashlib.sha256()
    for value in parts:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return Inventory(
        tuple(sorted(files, key=lambda ref: (ref.source, ref.path))),
        "sha256:" + digest.hexdigest(),
    )


def load_document(workspace: Workspace, ref: DocumentReference) -> LoadedDocument:
    """Read just one bounded Markdown document; never fall back to standalone YAML."""
    source = _source(workspace, ref.source)
    local_path = document_path(workspace, ref)
    with open_directory(source.root) as root, open_directory(local_path.parent) as parent:
        root_identity = _identity(os.fstat(root))[:2]
        parent_identity = _identity(os.fstat(parent))[:2]
        data = read_bytes(local_path, max_bytes=DEFAULT_DOCUMENT_BYTES)
        with open_directory(source.root) as current_root:
            if root_identity != _identity(os.fstat(current_root))[:2]:
                raise _changed(source.root)
        with open_directory(local_path.parent) as current_parent:
            if parent_identity != _identity(os.fstat(current_parent))[:2]:
                raise _changed(local_path.parent)
    parsed = parse_document(data, path=str(local_path))
    try:
        metadata = parse_knowledge(parsed.metadata, workspace.catalog)
    except ValidationError as error:
        raise ValidationError(error.code, f"{local_path}:{error.path}", error.message) from error
    return LoadedDocument(source.id, ref.path, local_path, parsed, metadata)


def document_path(workspace: Workspace, ref: DocumentReference) -> Path:
    """Validate a source-qualified Markdown location, including a now-missing target."""
    source = _source(workspace, ref.source)
    relative = read_relative_path(ref.path, "document.path")
    if not relative.endswith(".md"):
        raise ValidationError(
            "invalid-document-extension", "document.path", "Knowledge documents must end in .md."
        )
    if ".git" in relative.split("/")[:-1]:
        raise ValidationError(
            "invalid-document-path",
            "document.path",
            "Git metadata is outside the knowledge corpus.",
        )
    return resolve_document_path(source.root, relative)


def _source(workspace: Workspace, identifier: str) -> Source:
    """Resolve an exact configured source without inferring a root."""
    for source in workspace.sources:
        if source.id == identifier:
            return source
    raise ValidationError("unknown-source", "sources", f"Unknown configured source {identifier!r}.")


def _inventory_source(source: Source) -> tuple[list[str], list[str]]:
    """Traverse through pinned directory descriptors without recursion or body reads."""
    files: list[str] = []
    fingerprints: list[str] = []
    try:
        with open_directory(source.root) as root:
            initial = _identity(os.fstat(root))
            pending: list[tuple[tuple[str, ...], tuple[int, int, int, int, int]]] = [((), initial)]
            while pending:
                relative, expected = pending.pop()
                local_path = source.root.joinpath(*relative)
                with _open_relative_directory(root, relative, local_path) as directory:
                    before = _identity(os.fstat(directory))
                    if before != expected:
                        raise _changed(local_path)
                    if not os.access(".", os.R_OK | os.X_OK, dir_fd=directory):
                        raise AdapterError(
                            "directory-unreadable",
                            str(local_path),
                            "Cannot enumerate the directory.",
                        )
                    names = sorted(os.listdir(directory))
                    fingerprints.extend(("directory", "/".join(relative), repr(before)))
                    for name in names:
                        child_relative = (*relative, name)
                        child_path = source.root.joinpath(*child_relative)
                        child = os.stat(name, dir_fd=directory, follow_symlinks=False)
                        if stat.S_ISLNK(child.st_mode):
                            raise AdapterError(
                                "unsafe-path",
                                str(child_path),
                                "Knowledge sources cannot contain internal symlinks.",
                                exit_code=2,
                            )
                        if stat.S_ISDIR(child.st_mode):
                            if name != ".git":
                                pending.append((child_relative, _identity(child)))
                            continue
                        if not name.endswith(".md"):
                            continue
                        if not stat.S_ISREG(child.st_mode):
                            raise AdapterError(
                                "not-regular-file",
                                str(child_path),
                                "Expected a regular Markdown file.",
                                exit_code=2,
                            )
                        document_path = read_relative_path(
                            "/".join(child_relative), str(child_path)
                        )
                        files.append(document_path)
                        fingerprints.extend(("file", document_path, repr(_identity(child))))
                    if before != _identity(os.fstat(directory)):
                        raise _changed(local_path)
                # Re-open from the pinned source root to detect directory replacement.
                with _open_relative_directory(root, relative, local_path) as current:
                    if before != _identity(os.fstat(current)):
                        raise _changed(local_path)
            if initial != _identity(os.fstat(root)):
                raise _changed(source.root)
            # Re-opening the configured root detects root replacement/renaming as well.
            with open_directory(source.root) as current_root:
                if initial != _identity(os.fstat(current_root)):
                    raise _changed(source.root)
    except OSError as error:
        raise _io_error(error, source.root, directory=True) from error
    return files, fingerprints


@contextmanager
def _open_relative_directory(root: int, parts: tuple[str, ...], path: Path) -> Iterator[int]:
    """Open a descendant from a pinned root with no-follow checks at every step."""
    descriptor = os.dup(root)
    try:
        for part in parts:
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            try:
                opened = os.fstat(child)
                current = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                if _identity(opened) != _identity(current):
                    raise _changed(path)
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _changed(path: Path) -> AdapterError:
    """Report a scan race as retryable external-state failure, never an empty match."""
    return AdapterError(
        "corpus-changed", str(path), "Knowledge source changed during discovery; retry the request."
    )
