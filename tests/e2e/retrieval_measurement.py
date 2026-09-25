#!/usr/bin/env python3
"""Measure selective retrieval in bytes, lines and elapsed time.

The report deliberately avoids token claims.  It records the metadata returned
by the tool, the body range an agent chose to read, and the complete corpus
size so a later corpus run can be compared using the same units.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from agent_knowledge.infrastructure.configuration import load_workspace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from agent_knowledge.application.retrieval import inspect_result, search_result  # noqa: E402
from tests.acceptance.test_retrieval_walkthrough import _workspace  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure preview/body consumption for the neutral retrieval contract."
    )
    parser.add_argument("--output", type=Path, help="Write the JSON report to this path.")
    parser.add_argument("--repeat", type=int, default=3, help="Warm runs per case (default: 3).")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary corpus.")
    return parser


def _line_bytes(path: Path, start: int, end: int) -> tuple[int, int]:
    lines = path.read_bytes().splitlines(keepends=True)
    selected = lines[max(0, start - 1) : end]
    return sum(len(line) for line in selected), len(selected)


def _skill_description_bytes() -> int:
    total = 0
    for path in (
        ROOT / "packages/knowledge-agent-pack/.apm/skills/knowledge-setup/SKILL.md",
        ROOT / "packages/knowledge-agent-pack/.apm/skills/knowledge-compound/SKILL.md",
    ):
        frontmatter = path.read_text(encoding="utf-8").split("\n---", 1)[0]
        total += len(frontmatter.encode("utf-8"))
    return total


def _case(
    name: str,
    config: Path,
    query: dict[str, object],
    *,
    selected_path: str | None = None,
    section_title: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    search = search_result(load_workspace(config), query)
    search_elapsed = (time.perf_counter() - started) * 1000
    preview_payload = json.dumps(search, ensure_ascii=False, separators=(",", ":")).encode()
    body_bytes = 0
    body_lines = 0
    selected_file_bytes = 0
    selected: dict[str, object] | None = None
    if selected_path is not None:
        selected = inspect_result(
            load_workspace(config),
            {"document": {"source": "example", "path": selected_path}, "limit": 100},
        )
        if section_title is not None:
            heading = next(
                item for item in selected["navigation"] if item.get("title") == section_title
            )
            source_file = config.parent / "knowledge" / selected_path
            selected_file_bytes = source_file.stat().st_size
            body_bytes, body_lines = _line_bytes(
                source_file,
                int(heading["start_line"]),
                int(heading["end_line"]),
            )
    matched_paths = {row["path"] for row in search["results"]}
    return {
        "name": name,
        "elapsed_ms": round(search_elapsed, 3),
        "query": query,
        "documents_returned": search["returned"],
        "matched_paths": sorted(matched_paths),
        "preview_bytes": len(preview_payload),
        "selected_body_bytes": body_bytes,
        "selected_body_lines": body_lines,
        "selected_file_bytes": selected_file_bytes,
        "selected_body_fraction": round(body_bytes / selected_file_bytes, 4)
        if selected_file_bytes
        else 0,
        "irrelevant_body_reads": 0,
        "misses": 0 if search["returned"] else 1,
        "section": section_title,
    }


def run_measurement(*, repeat: int, keep: bool) -> dict[str, Any]:
    if repeat < 1 or repeat > 20:
        raise ValueError("--repeat must be between 1 and 20")
    temp_root = Path(tempfile.mkdtemp(prefix="agent-knowledge-measurement."))
    try:
        config = _workspace(temp_root)
        corpus_files = sorted((temp_root / "knowledge").rglob("*.md"))
        corpus_bytes = sum(path.stat().st_size for path in corpus_files)
        queries: tuple[tuple[str, dict[str, object], str | None, str | None], ...] = (
            (
                "feature-context",
                {
                    "kind": ["feature", "workflow"],
                    "text": {"any": ["order history", "past orders"]},
                },
                None,
                None,
            ),
            (
                "engineering-guidance",
                {
                    "kind": ["guidance"],
                    "topics": [
                        "testing",
                        "data-design",
                        "performance",
                        "reliability",
                    ],
                    "languages": ["any", "typescript"],
                    "technologies": ["any", "postgresql", "family:relational-database"],
                    "environments": ["any", "prod"],
                },
                None,
                None,
            ),
            (
                "runbook-section",
                {"kind": ["runbook"], "text": {"any": ["production warning"]}},
                "runbooks/orders.md",
                "Production warning",
            ),
            (
                "empty-search",
                {"kind": ["runbook"], "text": {"any": ["phrase not present"]}},
                None,
                None,
            ),
        )
        cases: list[dict[str, Any]] = []
        for name, query, selected_path, section_title in queries:
            runs = [
                _case(
                    name,
                    config,
                    query,
                    selected_path=selected_path,
                    section_title=section_title,
                )
                for _ in range(repeat)
            ]
            first = runs[0]
            cases.append(
                {
                    **first,
                    "runs": runs,
                    "elapsed_ms_mean": round(
                        sum(float(run["elapsed_ms"]) for run in runs) / len(runs), 3
                    ),
                }
            )
        return {
            "schema": "retrieval-measurement.v1",
            "status": "ok",
            "revision": _revision(),
            "units": {
                "bytes": "UTF-8 response/file bytes",
                "lines": "physical inclusive line ranges",
                "elapsed_ms": "wall-clock milliseconds for the application call",
                "tokens": "not measured",
            },
            "always_loaded": {
                "agent_contract_bytes": (ROOT / "docs/agent-contract.md").stat().st_size,
                "skill_frontmatter_bytes": _skill_description_bytes(),
            },
            "corpus": {"files": len(corpus_files), "bytes": corpus_bytes},
            "cases": cases,
            "interpretation": {
                "preview_is_metadata_only": True,
                "body_reads_are_explicit": True,
                "irrelevant_body_reads_are_measured_as": "zero in this walkthrough",
                "misses_are": "a case with no returned document, not a claim of global absence",
            },
        }
    finally:
        if not keep:
            shutil.rmtree(temp_root, ignore_errors=True)


def _revision() -> str:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = run_measurement(repeat=args.repeat, keep=args.keep)
    except (OSError, ValueError, StopIteration) as error:
        payload = {
            "schema": "retrieval-measurement.v1",
            "status": "error",
            "diagnostic": str(error),
        }
        print(json.dumps(payload, indent=2))
        return 1
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
