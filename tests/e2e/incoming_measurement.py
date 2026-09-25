#!/usr/bin/env python3
"""Reproduce on-demand incoming scan measurements with neutral file-backed fixtures.

No model, persistent index, scheduler or provider credentials are involved. The
fixture has independent source roots and many procedure-sized files; only every
tenth file contains an authored link to the selected target. Byte counts measure
the selected source files internally scanned, not token consumption or body reads
by an agent. Timings include target reads and before/after safety checks.
"""

import argparse
import json
import shutil
import statistics
import sys
import tempfile
from pathlib import Path

import yaml

from agent_knowledge.infrastructure.configuration import load_workspace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from agent_knowledge.application.retrieval import inspect_result  # noqa: E402
from agent_knowledge.infrastructure.documents import dump_document  # noqa: E402
from tests.factories import catalog_data, knowledge_data  # noqa: E402


def measure(*, documents: int, repeat: int) -> dict[str, object]:
    if not 20 <= documents <= 10_000 or not 1 <= repeat <= 20:
        raise ValueError("Use 20-10000 documents and 1-20 repeats.")
    temporary = Path(tempfile.mkdtemp(prefix="incoming-measurement."))
    try:
        roots = [temporary / "shared", temporary / "project"]
        for root in roots:
            root.mkdir()
        (temporary / "catalog.yaml").write_text(yaml.safe_dump(catalog_data()))
        config = temporary / "workspace.yaml"
        config.write_text(
            yaml.safe_dump(
                {
                    "schema_version": "knowledge-workspace.v1",
                    "workspace_id": "repo:orders",
                    "applicable_scopes": ["org:example"],
                    "sources": [
                        {"id": root.name, "root": root.name, "catalog": "catalog.yaml"}
                        for root in roots
                    ],
                }
            )
        )
        (roots[0] / "target.md").write_bytes(
            dump_document(knowledge_data(title="Query planning"), "# Query planning\n## Safety\n")
        )
        for index in range(documents - 1):
            body = (
                "# Procedure\n\n"
                + "Evaluate the documented prerequisites before proceeding.\n" * 140
            )
            if index % 10 == 0:
                body += "\n[Query prerequisites](../shared/target.md#safety)\n"
            (roots[index % 2] / f"procedure-{index:05}.md").write_bytes(
                dump_document(knowledge_data(title=f"Procedure {index}"), body)
            )
        scanned_bytes = sum(path.stat().st_size for root in roots for path in root.glob("*.md"))
        runs: list[dict[str, object]] = []
        for _ in range(repeat):
            result = inspect_result(
                load_workspace(config),
                {
                    "document": {"source": "shared", "path": "target.md"},
                    "view": "incoming",
                    "limit": 10,
                },
            )
            assert result["view"] == "incoming"
            assert result["scan_status"] == "complete"
            assert result["scan"]["documents"] == documents
            assert result["scan"]["byte_count"] == scanned_bytes
            assert result["total_entries"] == (documents - 2) // 10 + 1
            runs.append(
                {
                    "elapsed_ms": result["scan"]["elapsed_ms"],
                    "response_bytes": len(json.dumps(result, ensure_ascii=False).encode("utf-8")),
                    "returned": result["returned"],
                    "total_references": result["total_entries"],
                    "scan_status": result["scan_status"],
                }
            )
        return {
            "schema": "incoming-measurement.v1",
            "status": "passed",
            "corpus": {"files": documents, "bytes": scanned_bytes, "sources": 2},
            "page_limit": 10,
            "runs": runs,
            "elapsed_ms_mean": statistics.mean(float(str(run["elapsed_ms"])) for run in runs),
            "coverage": (
                "Supported authored Markdown links; no catalog references or agent body reads."
            ),
        }
    finally:
        shutil.rmtree(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=400)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = measure(documents=args.documents, repeat=args.repeat)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
