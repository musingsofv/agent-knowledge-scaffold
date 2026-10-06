#!/usr/bin/env python3
"""Check a setup-generated recipe and launch the selected CLI in this container.

No installation, profile refresh, hook mutation or shell evaluation happens here.
Keep the value-free setup report outside shared source; regenerate it after setup
changes. Provider arguments following -- retain their original argument boundaries.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


class LaunchFailure(Exception):
    """A value-free diagnostic safe to show before a provider starts."""


def _argv(value: object) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item and "\0" not in item for item in value
    ):
        raise LaunchFailure("Invalid launch recipe; rerun setup.")
    return value


def prepare_launch(report: dict, provider: str, arguments: list[str]) -> tuple[list[str], dict, str]:
    """Verify the route using the environment the real provider will inherit."""
    if report.get("schema") != "knowledge-setup-runtime.v1" or report.get("status") != "ok":
        raise LaunchFailure("Use a successful setup-runtime report.")
    recipe = report.get("launch", {})
    if recipe.get("schema") != "knowledge-launch-recipe.v1":
        raise LaunchFailure("Missing launch recipe; rerun the installed setup helper.")
    selected = recipe.get("providers", {}).get(provider, {})
    if selected.get("status") != "ready":
        raise LaunchFailure("This provider's setup or credentials are pending; rerun setup/doctor.")
    command = _argv(selected.get("argv"))
    cwd = recipe.get("cwd")
    runtime_bin = recipe.get("path_prepend")
    if not all(isinstance(p, str) and Path(p).is_absolute() for p in (cwd, runtime_bin)):
        raise LaunchFailure("Launch recipe requires absolute consumer/runtime paths.")
    environment = os.environ.copy()
    inherited_path = environment.get("PATH")
    environment["PATH"] = runtime_bin + (os.pathsep + inherited_path if inherited_path else "")
    registry = recipe.get("settings")
    if registry is not None:
        if not isinstance(registry, str) or not Path(registry).is_absolute():
            raise LaunchFailure("Launch recipe requires an absolute registry path.")
        environment["AGENT_KNOWLEDGE_SETTINGS"] = registry
    preflight = recipe["preflight"]
    request = dict(preflight["request"], provider=provider, expected_execution="container")
    result = subprocess.run(
        _argv(preflight["argv"]), input=json.dumps(request),
        cwd=cwd, env=environment, capture_output=True, text=True, timeout=30,
    )
    # Do not echo uncontrolled child output on parse/exec failures.
    try:
        status = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise LaunchFailure("Preflight returned no valid report; rerun the selected doctor.") from error
    if not isinstance(status, dict) or status.get("schema_version") != "knowledge-preflight.v1":
        raise LaunchFailure("Preflight contract mismatch; rerun setup with the matching package.")
    if result.returncode or status.get("status") != "ok":
        raise LaunchFailure("Container preflight failed; run the recipe's preflight command "
                            "with its request for value-free diagnostics. Provider was not started.")
    if status.get("selection") != recipe.get("selection"):
        raise LaunchFailure("The selected configuration changed; rerun the affected setup steps.")
    if status.get("environment_declaration") != recipe.get("environment_declaration"):
        raise LaunchFailure("The credential declaration changed; rerun setup before a new session.")
    print(json.dumps({"status": "ready", "phase": "container-launch",
                      "provider": provider, "native_session_acceptance": "unverified"}),
          file=sys.stderr)
    return [*command, *arguments], environment, cwd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-report", type=Path, required=True)
    parser.add_argument("--provider", choices=("codex", "claude", "copilot"), required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.setup_report.stat().st_size > 1_048_576:
            raise LaunchFailure("Setup report exceeds the size limit.")
        report = json.loads(args.setup_report.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise LaunchFailure("Setup report must be an object.")
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        command, environment, cwd = prepare_launch(report, args.provider, arguments)
        os.chdir(cwd)
        os.execvpe(command[0], command, environment)
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError, LaunchFailure) as error:
        message = str(error) if isinstance(error, LaunchFailure) else "Cannot use this launch recipe; rerun setup."
        print(json.dumps({"status": "error", "message": message}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
