"""Isolated fixture probes executed by real in-container harness tools.

This helper never reads a user's registry or credentials. Its fixed paths belong
only to the disposable container created by container_launch_acceptance.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml

STATE = Path("/state")
CONSUMER = STATE / "consumer"
REGISTRY = STATE / "profiles.yaml"
RUNTIME = Path("/opt/runtime")
PROFILE = "container-fixture"
SOURCE_VARIABLE = "CONTAINER_FIXTURE_SOURCE"
TARGET_VARIABLE = "CONTAINER_FIXTURE_TARGET"
REFLECTION = 'At a natural stopping point, follow "Reflect and record useful observations"'


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def cli(operation: list[str], request: dict | None, *, provider: str, session: str) -> dict:
    command = [
        str(RUNTIME / "bin/agent-knowledge"),
        "--settings",
        str(REGISTRY),
        "--profile",
        PROFILE,
        "--harness",
        provider,
        "--session-id",
        session,
        *operation,
    ]
    if request is not None:
        command += ["--request-file", "-"]
    result = subprocess.run(
        command,
        cwd=CONSUMER,
        text=True,
        capture_output=True,
        check=False,
        input=json.dumps(request) if request is not None else None,
    )
    if result.returncode:
        # Do not echo arbitrary runtime output into the model or a report.
        raise RuntimeError(
            f"Selected fixture CLI {' '.join(operation)} failed ({result.returncode})."
        )
    return json.loads(result.stdout)


def tool_probe(provider: str, session: str, phase: str) -> dict:
    """Run through a native harness shell tool, never call this as native proof from Docker exec."""
    if not session or any(char.isspace() for char in session):
        raise ValueError("The exact native session handle is required.")
    output = STATE / "evidence" / provider / f"{phase}-tool.json"
    if output.exists():
        raise ValueError("Refusing to overwrite prior native tool evidence.")
    context = cli(["context"], None, provider=provider, session=session)
    doctor = cli(["doctor"], {"mode": "write"}, provider=provider, session=session)
    catalog = cli(
        ["catalog"], {"dimension": "topics", "limit": 20}, provider=provider, session=session
    )
    search = cli(
        ["search"],
        {"kind": ["runbook"], "text": {"any": ["Orders service"]}},
        provider=provider,
        session=session,
    )
    inspected = cli(
        ["inspect"],
        {"document": {"source": "fixture", "path": "runbooks/orders.md"}},
        provider=provider,
        session=session,
    )
    if not search.get("results"):
        raise ValueError("The fictional source query returned no result.")
    body = Path("/opt/fixture/knowledge/runbooks/orders.md")
    if "Orders service runbook" not in body.read_text():
        raise ValueError("Selected source body did not match its fixture.")
    canonical_write_denied = False
    try:
        descriptor = os.open(body, os.O_WRONLY)  # No truncation or mutation, even on failure.
    except PermissionError:
        canonical_write_denied = True
    else:
        os.close(descriptor)
    # Compare only an isolated synthetic canary; never expose its bytes or a hash.
    expected = (STATE / "private/fixture.env").read_text().strip().partition("=")[2]
    credential = bool(expected) and os.environ.get(TARGET_VARIABLE) == expected
    source_hidden = SOURCE_VARIABLE not in os.environ
    identity = f"container-{provider}-{phase}"
    authored = CONSUMER / f"{identity}.md"
    metadata = {
        "schema_version": "knowledge-signal.v1",
        "id": identity,
        "created_at": datetime.now(UTC).isoformat(),
        "kind_hint": "runbook",
        "origin": {
            "workspace_id": "workspace:container-fixture",
            "project_path": None,
            "applicable_scopes": ["org:example", "group:commerce", "repo:orders-api"],
            "source_ids": ["fixture"],
            "harness": provider,
            "session_id": session,
        },
        "evidence": [{"type": "file", "reference": str(body)}],
    }
    authored.write_text(
        "---\n" + yaml.safe_dump(metadata) + "---\n\n"
        "Disposable acceptance observation; the existing runbook covers it.\n"
    )
    recorded = cli(
        ["signal", "record"], {"file": str(authored)}, provider=provider, session=session
    )
    listed = cli(
        ["signal", "list"],
        {"include_shared": True, "limit": 100},
        provider=provider,
        session=session,
    )
    matches = [row for row in listed["results"] if row["id"] == identity]
    if len(matches) != 1:
        raise ValueError("Fixture signal was not durably recorded and listed.")
    selected = [
        {"id": identity, "path": matches[0]["local_path"], "fingerprint": matches[0]["fingerprint"]}
    ]
    # Deterministic fixture cleanup through the sole supported archive/drain owner.
    # This does not invoke a model worker, real compounding, publication or a trigger.
    started = cli(
        ["compound"],
        {
            "action": "start",
            "workspace_id": "workspace:container-fixture",
            "selected": selected,
            "harness": provider,
            "session_id": session,
        },
        provider=provider,
        session=session,
    )
    disposition = {
        "signal_id": identity,
        "decision": "keep",
        "rationale": "The isolated observation is covered by the fixture runbook.",
        "owners": [{"source": "fixture", "path": "runbooks/orders.md"}],
    }
    drained = cli(
        ["compound"],
        {
            "action": "drain",
            "run_id": started["run_id"],
            "selected": selected,
            "dispositions": [disposition],
            "publication_verified": False,
        },
        provider=provider,
        session=session,
    )
    finished = cli(
        ["compound"],
        {
            "action": "finish",
            "run_id": started["run_id"],
            "completion": "completed",
            "outcome": "disposable-fixture-cleanup",
            "dispositions": [disposition],
        },
        provider=provider,
        session=session,
    )
    after = cli(
        ["signal", "list"],
        {"include_shared": True, "limit": 100},
        provider=provider,
        session=session,
    )
    absent_after = not after.get("truncated") and not any(
        row["id"] == identity for row in after["results"]
    )
    if drained.get("drained") != [identity] or drained.get("retained") or not absent_after:
        raise ValueError("Guarded cleanup did not drain the unchanged fixture signal.")
    receipts = [
        json.loads(line)
        for file in (STATE / "knowledge/ai/usage").rglob("*.jsonl")
        for line in file.read_text().splitlines()
        if line.strip()
    ]
    correlated = [
        r
        for r in receipts
        if r.get("context", {}).get("session_id") == session
        and r.get("context", {}).get("harness") == provider
        and r.get("selection", {}).get("profile") == PROFILE
    ]
    operations = sorted({r.get("operation") for r in correlated if r.get("operation")})
    activity = STATE / "knowledge/ai/signals/compound-activity.jsonl"
    result = {
        "schema_version": "container-launch-tool-proof.v1",
        "provider": provider,
        "session_id": session,
        "phase": phase,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "container_marker": Path("/.dockerenv").is_file(),
        "container_hostname": os.uname().nodename,
        "cwd": str(Path.cwd()),
        "runtime": str(RUNTIME),
        "registry": str(REGISTRY),
        "profile": PROFILE,
        "context": context,
        "doctor": doctor,
        "retrieval": {
            "catalog": catalog["status"],
            "search": search["status"],
            "inspect": inspected["status"],
            "body": str(body),
            "receipt_operations": operations,
            "receipt_count": len(correlated),
        },
        "credentials": {
            "target_matches_fixture": credential,
            "source_not_exposed": source_hidden,
            "evidence": "synthetic isolated canary; values never reported",
        },
        "scope": {"canonical_fixture_write_denied": canonical_write_denied},
        "signal": {
            "id": identity,
            "absent_after": absent_after,
            "recorded": recorded["status"],
            "listed": len(matches),
            "cleanup": drained,
            "finish": finished["status"],
        },
        "activity_bytes": activity.stat().st_size,
        "activity_sha256": hashlib.sha256(activity.read_bytes()).hexdigest(),
    }
    write_json(output, result)
    print(json.dumps({"status": "passed", "tool_proof": str(output), "session_id": session}))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("codex", "claude", "copilot"), required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--phase", choices=("fresh", "reused", "recreated"), required=True)
    args = parser.parse_args()
    tool_probe(args.provider, args.session_id, args.phase)


if __name__ == "__main__":
    main()
