#!/usr/bin/env python3
"""Verify source attribution and refresh through real isolated APM compilation."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from fresh_consumer_smoke import (
    SmokeFailure,
    _assert,
    _clean_environment,
    _command,
    _generated_projection_proof,
    _repo_root,
    _run,
    _yaml_string,
)

SOURCE_LABEL = ".apm/instructions/agent-knowledge-discovery.instructions.md"
OLD_RULE = "Discovery ownership fixture: original rule."
NEW_RULE = "Discovery ownership fixture: revised rule."
CONSUMER_RULE = "Consumer ownership fixture: preserve this independent rule."
SCOPED_RULE = "Scoped ownership fixture: applies only to Python source files."


def _check_surfaces(consumer: Path, source: Path, *, current: str, absent: str) -> list[str]:
    paths = _generated_projection_proof(_repo_root(), consumer, source)
    for location in paths:
        text = Path(location).read_text()
        _assert(text.count(SOURCE_LABEL) == 1, f"Missing/duplicate source attribution: {location}")
        _assert("Owner: `knowledge-agent-pack`" in text, f"Missing package owner: {location}")
        _assert(text.count(current) == 1, f"Missing/duplicate current rule: {location}")
        _assert(absent not in text, f"Stale instruction after compilation: {location}")
    return paths


def run_smoke(*, keep: bool) -> dict[str, object]:
    root = _repo_root()
    temporary = Path(tempfile.mkdtemp(prefix="agent-knowledge-instruction-ownership."))
    apm = _command("apm")
    consumer = temporary / "consumer"
    package = temporary / "knowledge-agent-pack"
    logs = temporary / "logs"
    home = temporary / "home"
    xdg = temporary / "xdg"
    for path in (consumer, logs, home, xdg):
        path.mkdir()
    shutil.copytree(root / "packages/knowledge-agent-pack", package)
    source = package / SOURCE_LABEL
    _assert(
        len(list((package / ".apm/instructions").glob("*.instructions.md"))) == 1,
        "Distributed package must have one authored always-on instruction owner.",
    )
    source.write_text(source.read_text() + "\n## Ownership test\n\n" + OLD_RULE + "\n")
    scoped = package / ".apm/instructions/python-only.instructions.md"
    scoped.write_text(
        '---\ndescription: Isolated file-scope preservation fixture.\napplyTo: "src/**/*.py"\n'
        "---\n\n# Python source fixture\n\n" + SCOPED_RULE + "\n"
    )
    owned = consumer / ".apm/instructions/consumer.instructions.md"
    owned.parent.mkdir(parents=True)
    owned.write_text(
        "---\ndescription: Independent consumer instruction.\n---\n\n" + CONSUMER_RULE + "\n"
    )
    original_owned = owned.read_bytes()
    original_scoped = scoped.read_bytes()
    (consumer / "src").mkdir()
    (consumer / "src/example.py").write_text("pass\n")
    (consumer / "apm.yml").write_text(
        "name: instruction-ownership-consumer\nversion: 0.0.1\n"
        "dependencies:\n  apm:\n    - " + _yaml_string(str(package)) + "\n"
    )
    env = _clean_environment(home=home, xdg_config=xdg, path_entries=[apm.parent])
    try:
        for phase, current, absent in (
            ("initial", OLD_RULE, NEW_RULE),
            ("revised", NEW_RULE, OLD_RULE),
        ):
            if phase == "revised":
                source.write_text(source.read_text().replace(OLD_RULE, NEW_RULE))
            for operation, arguments in (
                ("install", ["install", "--no-policy", "--target", "codex,claude,copilot"]),
                (
                    "compile",
                    ["compile", "--target", "codex,claude,copilot", "--force-instructions"],
                ),
            ):
                _run(
                    [str(apm), *arguments],
                    cwd=consumer,
                    env=env,
                    logs=logs,
                    label=f"{phase}-{operation}",
                )
            paths = _check_surfaces(consumer, source, current=current, absent=absent)
            _assert(
                owned.read_bytes() == original_owned, "Consumer instruction source was changed."
            )
            _assert(
                scoped.read_bytes() == original_scoped, "Scoped instruction source was changed."
            )
            for filename in ("AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"):
                text = (consumer / filename).read_text()
                _assert(CONSUMER_RULE in text, f"Consumer instruction lost from {filename}.")
            installed_scoped = consumer / ".github/instructions/python-only.instructions.md"
            _assert(
                installed_scoped.read_bytes() == original_scoped,
                "Scoped instruction lost its authored applicability.",
            )
            claude_scoped = consumer / ".claude/rules/python-only.md"
            _assert(
                "src/**/*.py" in claude_scoped.read_text(), "Claude rule lost scoped applicability."
            )
        result: dict[str, object] = {
            "schema": "instruction-ownership-smoke.v1",
            "status": "passed",
            "targets": ["codex", "claude", "copilot"],
            "consumer_root": str(consumer),
            "retained": keep,
            "projections": paths,
            "proof": [
                "One distributed always-on instruction source",
                "Portable package/source attribution in five generated surfaces",
                "Source amendment survives reinstall/compile with no stale or duplicate rule",
                "Independent consumer source and compiled content preserved",
                "File-scoped source and installed Python applicability preserved",
            ],
            "limits": ["No live model or native scheduler was invoked."],
        }
    except (OSError, SmokeFailure):
        # Keep failed evidence for diagnosis even when --keep was omitted.
        raise
    else:
        if not keep:
            shutil.rmtree(temporary)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = run_smoke(keep=args.keep)
    except (OSError, SmokeFailure) as error:
        result = {"status": "failed", "error": str(error)}
        if isinstance(error, SmokeFailure) and error.log:
            result["log"] = str(error.log)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
