"""Resolve visible Markdown references without loading or following linked bodies."""

import os
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlsplit

from agent_knowledge.domain.models import DocumentReference
from agent_knowledge.domain.navigation import MarkdownLink, MarkdownNavigation
from agent_knowledge.domain.validation import ValidationError

from .configuration import Source, Workspace
from .corpus import LoadedDocument
from .errors import AdapterError
from .filesystem import open_directory, resolve_document_path

LinkStatus = Literal["resolved", "missing", "unresolved", "external", "unsafe"]
AnchorStatus = Literal["not-present", "resolved", "missing", "unverified"]


@dataclass(frozen=True, slots=True)
class ResolvedLink:
    """Retain a reference and distinguish path presence from anchor verification."""

    label: str
    target: str | None
    anchor: str | None
    start_line: int
    end_line: int
    status: LinkStatus
    anchor_status: AnchorStatus
    document: DocumentReference | None
    local_path: str | None
    reason: str | None = None


def resolve_links(
    workspace: Workspace, current: LoadedDocument, navigation: MarkdownNavigation
) -> tuple[ResolvedLink, ...]:
    """Resolve only this document's links; other-file anchors remain unverified.

    Local paths are normalized lexically before selecting a configured source.
    Targets outside those roots are never statted. Symlinks within a configured
    path are rejected even when a later ``..`` would hide them lexically. Regular
    target-file presence is checked with a no-follow stat, never a body read.
    """
    return tuple(_resolve_link(workspace, current, navigation, link) for link in navigation.links)


def _resolve_link(
    workspace: Workspace,
    current: LoadedDocument,
    navigation: MarkdownNavigation,
    link: MarkdownLink,
) -> ResolvedLink:
    result = ResolvedLink(
        link.label,
        link.target,
        None,
        link.start_line,
        link.end_line,
        "unresolved",
        "not-present",
        None,
        None,
    )
    if link.target is None:
        return replace(result, reason="The Markdown reference has no known destination.")
    if any(ord(character) < 32 or ord(character) == 127 for character in link.target):
        return replace(result, reason="The destination contains unsupported control characters.")
    try:
        parsed = urlsplit(link.target)
        anchor = _decode(parsed.fragment) or None
    except (ValueError, UnicodeError):
        return replace(result, reason="The destination or its percent encoding is malformed.")
    result = replace(result, anchor=anchor, anchor_status="unverified" if anchor else "not-present")
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        if (parsed.scheme.lower() == "mailto" and not parsed.path) or (
            parsed.scheme.lower() in {"http", "https"} and not parsed.netloc
        ):
            return replace(result, reason="The external destination is malformed.")
        return replace(result, status="external", reason="External evidence is not fetched.")
    if parsed.scheme:
        return replace(result, reason="This destination scheme is unsupported.")
    if parsed.netloc:
        return replace(result, status="external", reason="Network evidence is not fetched.")
    if "?" in link.target.split("#", 1)[0]:
        return replace(result, reason="Query parameters on local knowledge links are unsupported.")
    try:
        target_path = _decode(parsed.path)
    except (ValueError, UnicodeError):
        return replace(result, reason="The destination's percent encoding is malformed.")
    if "\\" in target_path or any(
        ord(character) < 32 or ord(character) == 127 for character in target_path
    ):
        return replace(result, reason="Use a local POSIX path without control characters.")
    raw_path = Path(target_path) if target_path else current.local_path
    if not raw_path.is_absolute():
        raw_path = current.local_path.parent / raw_path
    normalized = Path(os.path.normpath(raw_path))
    if normalized.suffix != ".md":
        return replace(
            result,
            status="external",
            reason="Canonical knowledge uses lowercase .md paths; this is external evidence.",
        )
    source = _owning_source(workspace, normalized)
    if source is None:
        return replace(
            result, reason="The Markdown target is outside all configured knowledge roots."
        )
    relative = normalized.relative_to(source.root).as_posix()
    if ".git" in relative.split("/")[:-1]:
        return replace(
            result,
            status="external",
            reason="Git metadata is outside the canonical knowledge corpus.",
        )
    try:
        if _traverses_symlink(workspace, raw_path):
            return replace(
                result,
                status="unsafe",
                reason="Knowledge links cannot traverse symlinks or unsafe path components.",
            )
        target = resolve_document_path(source.root, relative)
    except ValidationError as error:
        status: LinkStatus = "unsafe" if error.code == "unsafe-document-path" else "unresolved"
        return replace(result, status=status, reason=error.message)
    except (AdapterError, OSError):
        return replace(result, reason="The configured target path could not be checked safely.")
    result = replace(
        result, document=DocumentReference(source.id, relative), local_path=str(target)
    )
    status, reason = _target_status(target)
    result = replace(result, status=status, reason=reason)
    if status == "resolved" and target == current.local_path and anchor:
        present = any(heading.anchor == anchor for heading in navigation.headings)
        result = replace(
            result,
            anchor_status="resolved" if present else "missing",
            reason=None
            if present
            else "The anchor is absent from the current document's supported heading outline.",
        )
    return result


def _decode(value: str) -> str:
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise ValueError("Malformed percent escape")
    decoded = unquote(value, encoding="utf-8", errors="strict")
    if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
        raise ValueError("Encoded control character")
    return decoded


def _owning_source(workspace: Workspace, path: Path) -> Source | None:
    return next((source for source in workspace.sources if path.is_relative_to(source.root)), None)


def _traverses_symlink(workspace: Workspace, raw_path: Path) -> bool:
    """Check configured prefixes before collapsing parent traversals.

    Prefixes outside configured roots are not inspected. Missing intermediate
    paths may still be normalized lexically; only the final target establishes
    presence. Configured root ancestors retain the filesystem adapter's documented
    trusted-ancestor rename limitation.
    """
    prefix = Path(raw_path.anchor)
    for component in raw_path.parts[1:]:
        if component == "..":
            prefix = prefix.parent
            continue
        prefix /= component
        if _owning_source(workspace, prefix) is None:
            continue
        try:
            with open_directory(prefix.parent) as directory:
                value = os.stat(prefix.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except AdapterError as error:
            if error.code == "directory-missing":
                continue
            if error.code in {"unsafe-path", "path-changed"}:
                return True
            raise
        if stat.S_ISLNK(value.st_mode):
            return True
    return False


def _target_status(path: Path) -> tuple[LinkStatus, str | None]:
    try:
        with open_directory(path.parent) as directory:
            value = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return "missing", "The configured target file is missing."
    except AdapterError as error:
        if error.code in {"file-missing", "directory-missing"}:
            return "missing", "The configured target file or its parent directory is missing."
        if error.code in {"unsafe-path", "path-changed"}:
            return (
                "unsafe",
                "The target path contains a symlink, changed directory or invalid component.",
            )
        return "unresolved", "The configured target could not be accessed."
    except OSError:
        return "unresolved", "The configured target could not be accessed."
    if stat.S_ISLNK(value.st_mode):
        return "unsafe", "Knowledge links cannot target symlinks."
    if not stat.S_ISREG(value.st_mode):
        return "unresolved", "The configured target is not a regular file."
    return "resolved", None
