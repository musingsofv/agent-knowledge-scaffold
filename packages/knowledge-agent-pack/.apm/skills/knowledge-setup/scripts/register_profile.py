#!/usr/bin/env python3
"""Install reviewed registry bytes through the installed core's checked writer."""

import argparse
import json
from pathlib import Path

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import read_bytes
from agent_knowledge.infrastructure.profiles import replace_registry, settings_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--expected-sha256", required=True, help="Inspected SHA256, or missing.")
    args = parser.parse_args()
    try:
        path = settings_path(args.settings)
        candidate = read_bytes(args.candidate.absolute(), max_bytes=1_048_576)
        replace_registry(
            path, candidate,
            expected_sha256=None if args.expected_sha256 == "missing" else args.expected_sha256,
        )
    except (AdapterError, ValidationError) as error:
        print(json.dumps({"status": "error", "code": error.code, "message": error.message}))
        return 2
    print(json.dumps({"status": "ok", "settings_path": str(path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
