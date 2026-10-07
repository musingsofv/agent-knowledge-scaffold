#!/usr/bin/env python3
"""Prepare one reviewed local profile using the installed runtime's guarded adapters."""

import argparse
import json
from pathlib import Path

from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.container_profiles import prepare_container_profile
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import read_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", required=True, choices=("prepare", "refresh", "remove"))
    parser.add_argument("--settings", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--expected-sha256", required=True, help="Inspected registry SHA256, or missing."
    )
    parser.add_argument("--private-directory", type=Path)
    parser.add_argument("--source-env-file", type=Path)
    args = parser.parse_args()
    try:
        if not args.candidate.is_absolute() or ".." in args.candidate.parts:
            raise ValidationError(
                "candidate-path-invalid",
                "candidate",
                "Use an absolute candidate path without parent traversal.",
            )
        result = prepare_container_profile(
            operation=args.operation,
            settings=args.settings,
            profile=args.profile,
            candidate=read_bytes(args.candidate, max_bytes=1_048_576),
            expected_sha256=None if args.expected_sha256 == "missing" else args.expected_sha256,
            private_directory=args.private_directory,
            source_env_file=args.source_env_file,
        )
    except (AdapterError, ValidationError) as error:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": error.code,
                    "message": error.message,
                    "launch_allowed": False,
                }
            )
        )
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "status": "error",
                    "code": "profile-preparation-io-failed",
                    "message": "Could not safely prepare this profile; do not launch.",
                    "launch_allowed": False,
                }
            )
        )
        return 2
    result["launch_allowed"] = result["status"] == "ok" and args.operation != "remove"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
