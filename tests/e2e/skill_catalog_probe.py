#!/usr/bin/env python3
"""Check installed skill navigation using the runtime's Markdown scanner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from agent_knowledge.domain.navigation import MarkdownLink, scan_markdown

SKILLS = ("knowledge-setup", "knowledge-compound", "knowledge-upgrade")


def _local_links(
    document: Path, catalog: Path, installed_catalog: Path | None
) -> list[tuple[MarkdownLink, Path, str, str]]:
    allowed = (catalog,) if installed_catalog is None else (catalog, installed_catalog.resolve())
    result = []
    navigation = scan_markdown(document.read_bytes().decode("utf-8"))
    for link in navigation.links:
        if link.target is None:
            raise ValueError(f"Unresolved reference in {document}: {link.label}")
        destination = urlsplit(link.target)
        if destination.scheme or destination.netloc:
            continue
        target = (
            (document.parent / unquote(destination.path)).resolve()
            if destination.path
            else document
        )
        owner = next((root for root in allowed if target.is_relative_to(root)), None)
        if owner is None:
            raise ValueError(f"Skill link escapes deployed catalog: {document}: {link.target}")
        relative = target.relative_to(owner)
        if not target.is_file() or relative.parts[0] not in SKILLS:
            raise ValueError(f"Skill link target is missing: {document}: {link.target}")
        fragment = unquote(destination.fragment)
        if fragment and target.suffix == ".md":
            headings = scan_markdown(target.read_bytes().decode("utf-8")).headings
            if fragment not in {heading.anchor for heading in headings}:
                raise ValueError(f"Skill link anchor is missing: {document}: {link.target}")
        result.append((link, relative, destination.query, fragment))
    return result


def verify_catalog_links(catalog: Path, *, installed_catalog: Path | None = None) -> dict[str, Any]:
    """Allow only this catalog or APM's exact installed owning-package catalog."""
    catalog = catalog.resolve()
    links = []
    documents = [path for skill in SKILLS for path in (catalog / skill).rglob("*.md")]
    for document in documents:
        for _, relative, _, fragment in _local_links(document, catalog, installed_catalog):
            links.append(
                {
                    "source": document.relative_to(catalog).as_posix(),
                    "target": relative.as_posix(),
                    "fragment": fragment,
                }
            )
    return {"catalog": str(catalog), "documents": len(documents), "local_links": links}


def _normalized_markdown(document: Path, catalog: Path, installed_catalog: Path | None) -> bytes:
    """Normalize verified inline destinations only, preserving every other byte."""
    body = document.read_bytes().decode("utf-8")
    lines = body.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    replacements = []
    for link, relative, query, fragment in _local_links(document, catalog, installed_catalog):
        # Distributed skills use ordinary inline links. Reject ambiguity or a
        # new syntax instead of silently normalizing prose or fenced examples.
        assert link.target is not None
        marker = "](" + link.target + ")"
        start, end = offsets[link.start_line - 1], offsets[link.end_line]
        region = body[start:end]
        if region.count(marker) != 1:
            raise ValueError(
                f"Unsupported or ambiguous skill link syntax: {document}: {link.target}"
            )
        begin = start + region.index(marker) + 2
        identity = relative.as_posix()
        if query:
            identity += "?" + query
        if fragment:
            identity += "#" + fragment
        replacements.append((begin, begin + len(link.target), identity))
    for begin, end, identity in sorted(replacements, reverse=True):
        body = body[:begin] + identity + body[end:]
    return body.encode("utf-8")


def verify_markdown_parity(source: Path, catalog: Path, installed_catalog: Path) -> None:
    """Permit APM link relocation, but not a changed owner, anchor or other text."""
    source, catalog = source.resolve(), catalog.resolve()
    for skill in SKILLS:
        for authored in (source / skill).rglob("*.md"):
            deployed = catalog / authored.relative_to(source)
            if _normalized_markdown(authored, source, None) != _normalized_markdown(
                deployed, catalog, installed_catalog
            ):
                raise ValueError(f"Installed Markdown differs from its source: {deployed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--installed-catalog", type=Path, required=True)
    parser.add_argument("catalogs", type=Path, nargs="+")
    arguments = parser.parse_args()
    reports = []
    for catalog in arguments.catalogs:
        verify_markdown_parity(arguments.source, catalog, arguments.installed_catalog)
        reports.append(verify_catalog_links(catalog, installed_catalog=arguments.installed_catalog))
    print(
        json.dumps(
            {
                "status": "ok",
                "catalogs": reports,
            }
        )
    )
