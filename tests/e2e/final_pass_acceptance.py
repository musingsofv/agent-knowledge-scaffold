#!/usr/bin/env python3
"""Stage or run final B3-B5 acceptance in four bounded disposable Claude turns.

Use --live-agent only after all slices and the wheel are complete. No native
scheduler, GitHub publication, global setup or production data is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from claude_hook_acceptance import _json_lines, _tool_commands, _tool_uses
from harness_agent_smoke import (
    HarnessSmokeFailure,
    _clean_runtime_env,
    _provider_command,
    _redact,
    _run,
    _run_json,
)

WORKSPACE = "workspace:studio"
SOURCE = "business-knowledge"
SCOPE = "org:studio"
PHASES = (
    "incoming-and-rename",
    "trial-and-owner-discovery",
    "confirmed-adoption",
    "current-versus-history",
)
PRESERVED = ("config", "untouched", "external", "external_instruction", "unrelated_skill")
UNRELATED_MARKER = "UNRELATED_INVOICE_BODY_61c2af_SHOULD_NOT_BE_LOADED"
OWNER_PATH = "packages/studio-agent-tools/.apm/skills/outreach-coach"


def _assert(value: object, message: str) -> None:
    if not value:
        raise HarnessSmokeFailure(message)


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _document(path: Path, kind: str, title: str, topic: str, body: str) -> None:
    metadata: dict[str, Any] = {
        "schema_version": "knowledge.v1",
        "kind": kind,
        "title": title,
        "description": title,
        "scope": [SCOPE],
        "topics": [topic],
    }
    if kind == "guidance":
        metadata.update(languages=["any"], technologies=["any"], environments=["any"])
    _write(path, "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n\n" + body)


def _prepare(consumer: Path, package: Path) -> dict[str, Path]:
    """Author synthetic context, preserving the same public contracts as a consumer."""
    knowledge = consumer / "knowledge"
    knowledge.mkdir()
    catalog = {
        "schema_version": "knowledge-catalog.v1",
        "scopes": {SCOPE: {"label": "Studio"}},
        "entities": {
            "feature:order-history": {
                "label": "Order history",
                "description": "Customer access to previous purchases and their availability.",
                "documents": [{"source": SOURCE, "path": "product/features/order-history.md"}],
            }
        },
        "topics": {
            "lead-generation": {"label": "Lead generation", "aliases": ["prospecting"]},
            "reliability": {"label": "Reliability"},
        },
        "languages": {},
        "technologies": {},
        "technology_families": {},
        "environments": {},
    }
    _write(consumer / "catalog.yaml", yaml.safe_dump(catalog, sort_keys=False))
    config = consumer / "knowledge-workspace.yaml"
    _write(
        config,
        yaml.safe_dump(
            {
                "schema_version": "knowledge-workspace.v1",
                "workspace_id": WORKSPACE,
                "applicable_scopes": [SCOPE],
                "sources": [{"id": SOURCE, "root": "knowledge", "catalog": "catalog.yaml"}],
                "signal_storage": {"scaffold_root": ".", "code_root": ".."},
                "receipts": {"enabled": True, "directory": "./ai/usage", "retention_days": 30},
            },
            sort_keys=False,
        ),
    )
    _write(consumer / ".gitignore", "ai/signals/\nai/usage/\n.agent-knowledge-venv/\n")
    _document(
        knowledge / "product/features/order-history.md",
        "feature",
        "Order history availability",
        "reliability",
        "# Order history\n\n## Availability\n\nCustomers can inspect previous purchases.\n",
    )
    _document(
        knowledge / "limitations/refresh-window.md",
        "limitation",
        "Allow a refresh interval after a purchase",
        "reliability",
        "# Refresh interval\n\nA completed purchase can take 30 seconds to appear. "
        "This constrains [order history availability]"
        "(../product/features/order-history.md#availability).\n",
    )
    _document(
        knowledge / "guidance/lead-generation.md",
        "guidance",
        "Current lead-generation approach and decision history",
        "lead-generation",
        "# Lead-generation approach\n\n## Current approach\n\nUse Pipedrive for the "
        "approved campaign. Qualify each prospect against the customer profile and retain "
        "the evidence. Follow the [campaign procedure](../runbooks/campaign.md).\n\n"
        "## Decision history\n\nPipedrive supported the initial manual follow-up process. "
        "The decision's effective date was not recorded.\n",
    )
    _document(
        knowledge / "runbooks/campaign.md",
        "runbook",
        "Run the approved outreach campaign",
        "lead-generation",
        "# Campaign procedure\n\nUse Pipedrive for approved prospects. Preserve qualification "
        "evidence and unresolved questions before sending outreach.\n",
    )
    _document(
        knowledge / "concepts/untouched.md",
        "concept",
        "Independent operating calendar",
        "reliability",
        "# Operating calendar\n\nAn unrelated document must remain unchanged.\n",
    )
    tools = consumer / "packages/studio-agent-tools"
    _write(tools / "apm.yml", "name: studio-agent-tools\nversion: 0.0.1\n")
    skill = consumer / OWNER_PATH
    _write(
        skill / "SKILL.md",
        "---\nname: outreach-coach\ndescription: Prepare qualified prospect exports and "
        "preserve traceable evidence during outreach handoffs.\n---\n\n"
        "# Prepare a prospect handoff\n\nUse references/export-checklist.md to prepare "
        "the export. Use the campaign's current tool and keep business claims evidenced.\n",
    )
    _write(
        skill / "references/export-checklist.md",
        "# Export checklist\n\nInclude company name, contact email and qualification result.\n",
    )
    unrelated = tools / ".apm/skills/invoice-reconciler/SKILL.md"
    _write(
        unrelated,
        "---\nname: invoice-reconciler\ndescription: Reconcile supplier invoice totals "
        "against the monthly payable ledger.\n---\n\n# Invoice procedure\n\n"
        + UNRELATED_MARKER
        + "\n",
    )
    external = consumer / "origin-context/installed-external/SKILL.md"
    _write(
        external,
        "---\nname: external-export-policy\ndescription: Apply the provider-managed "
        "export-retention policy.\n---\n\n# External export policy\n\n"
        "Installed projection from external-policy-kit; authoritative checkout unavailable. "
        "The recorded policy says every qualification source URL should be discarded.\n",
    )
    projection = consumer / "origin-context/external-policy.instructions.md"
    _write(
        projection,
        "# Originating workspace instruction projection\n\nOwner: external-policy-kit. "
        "Authored source: .apm/instructions/export-policy.instructions.md.\n"
        "Authoritative repository/checkout and publication authorization are unavailable.\n"
        "The active export instruction says to discard qualification source URLs.\n",
    )
    _write(
        consumer / "origin-context/skill-inventory.md",
        "# Originating workspace advertised skills\n\n"
        f"- outreach-coach: Prepare qualified prospect exports and preserve traceable "
        f"evidence during outreach handoffs. Authoritative local source: {skill}.\n"
        f"- invoice-reconciler: Reconcile supplier invoice totals against the monthly payable "
        f"ledger. Authoritative local source: {unrelated.parent}.\n"
        f"- external-export-policy: Apply provider-managed export-retention policy. Installed "
        f"projection: {external}; owner external-policy-kit is unavailable.\n\n"
        "Active external instruction projection: external-policy.instructions.md. "
        "Only the local studio-agent-tools source is authorized for prepared edits.\n",
    )
    _write(
        consumer / "apm.yml",
        "name: final-pass-consumer\nversion: 0.0.1\ndependencies:\n  apm:\n"
        f"    - {json.dumps(str(package))}\n    - {json.dumps(str(tools))}\n",
    )
    return _fixture_paths(consumer)


def _fixture_paths(consumer: Path) -> dict[str, Path]:
    knowledge = consumer / "knowledge"
    return {
        "config": consumer / "knowledge-workspace.yaml",
        "guidance": knowledge / "guidance/lead-generation.md",
        "procedure": knowledge / "runbooks/campaign.md",
        "owner_reference": consumer / OWNER_PATH / "references/export-checklist.md",
        "unrelated_skill": consumer
        / "packages/studio-agent-tools/.apm/skills/invoice-reconciler/SKILL.md",
        "external": consumer / "origin-context/installed-external/SKILL.md",
        "external_instruction": consumer / "origin-context/external-policy.instructions.md",
        "untouched": knowledge / "concepts/untouched.md",
    }


def _signal(consumer: Path, identifier: str, claim: str, evidence: str) -> Path:
    path = consumer / f"authored-signals/{identifier}.md"
    metadata = {
        "schema_version": "knowledge-signal.v1",
        "id": identifier,
        "kind_hint": "guidance",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "origin": {
            "workspace_id": WORKSPACE,
            "project_path": consumer.name,
            "applicable_scopes": [SCOPE],
            "source_ids": [SOURCE],
        },
        "evidence": [{"type": "file", "reference": evidence}],
    }
    _write(path, "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n\n" + claim + "\n")
    return path


def _current_section(path: Path) -> str:
    body = path.read_text()
    _assert("## Current approach" in body, "Current approach heading is missing.")
    _assert("## Decision history" in body, "Decision history heading is missing.")
    return body.split("## Current approach", 1)[-1].split("## Decision history", 1)[0]


def _usage_proof(destination: Path, originals: dict[str, bytes]) -> dict[str, Any]:
    manifest = json.loads((destination / "manifest.json").read_text())
    _assert(manifest["workspace_id"] == WORKSPACE, "Export has a foreign workspace.")
    for item in manifest["files"]:
        path = destination / item["path"]
        _assert(path.resolve().is_relative_to(destination), "Export manifest escaped destination.")
        data = path.read_bytes()
        _assert(
            len(data) == item["bytes"] and _hash(data) == item["checksum"], "Export hash mismatch."
        )
    events = _json_lines((destination / "events.jsonl").read_text())
    _assert(events, "Usage export is empty.")
    retrieval = [e for e in events if e.get("schema_version") == "knowledge-retrieval-receipt.v1"]
    compound = [e for e in events if e.get("schema_version") == "knowledge-compound-receipt.v1"]
    _assert(
        {e["operation"] for e in retrieval} >= {"catalog", "search", "inspect"},
        "Missing retrieval evidence.",
    )
    _assert(
        any(
            isinstance(e.get("request"), dict) and e["request"].get("view") == "incoming"
            for e in retrieval
        ),
        "No incoming lookup recorded.",
    )
    _assert(
        any(e["context"].get("compound_run_id") for e in retrieval),
        "Compound retrieval is uncorrelated.",
    )
    for event in retrieval:
        _assert(event["body_read"] == "unknown", "A receipt claims observed body coverage.")
        payload = json.dumps(
            event["response"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        _assert(
            event["measurements"]["response_bytes"] == len(payload),
            "Receipt bytes are not canonical JSON bytes.",
        )
    _assert(
        {e["operation"] for e in compound}
        >= {"compound.start", "compound.drain", "compound.finish"},
        "Missing lifecycle receipts.",
    )
    archived: set[str] = set()
    additional_archived: set[str] = set()
    for event in compound:
        if event["operation"] != "compound.start":
            continue
        run = event["context"]["compound_run_id"]
        for artifact in event["artifacts"]["signal_snapshots"]:
            data = (destination / "compound" / run / artifact["path"]).read_bytes()
            _assert(_hash(data) == artifact["fingerprint"], "Archived signal fingerprint differs.")
            identifier = artifact["signal_id"]
            if identifier in originals:
                _assert(
                    data == originals[identifier], "Archive did not preserve exact seeded bytes."
                )
            else:
                additional_archived.add(identifier)
            archived.add(identifier)
    _assert("covered-qualification" in archived, "Drained signal has no reviewable archive.")
    dispositions = [
        disposition
        for event in compound
        for disposition in event.get("agent_report", {}).get("dispositions", [])
    ]
    _assert(
        any(
            row["signal_id"] == "external-policy-source" and row["decision"] == "defer"
            for row in dispositions
        ),
        "Unavailable external owner was not explicitly deferred.",
    )
    _assert(
        any((destination / "descriptors").glob("*.json")),
        "Workspace/catalog descriptor was not exported.",
    )
    return {
        "retrieval_events": len(retrieval),
        "compound_events": len(compound),
        "archived_ids": sorted(archived),
        "additional_agent_signal_ids": sorted(additional_archived),
        "archive_proof": "Known seed bytes compared exactly; all snapshots fingerprint-checked.",
        "manifest": manifest,
    }


def _check_preserved(files: dict[str, Path], state: dict[str, Any]) -> None:
    for name, digest in state["baseline_hashes"].items():
        _assert(_hash(files[name].read_bytes()) == digest, f"Changed preserved fixture: {name}.")


def _resume_state(report: dict[str, Any], files: dict[str, Path], wheel: Path) -> dict[str, Any]:
    """Recover only evidenced state; never treat current mutable files as original baselines."""
    state = report.get("resume_state")
    if state is not None:
        _assert(state["wheel_fingerprint"] == _hash(wheel.read_bytes()), "Resume wheel changed.")
        _check_preserved(files, state)
        return state
    phases = [turn["phase"] for turn in report["turns"]]
    _assert(
        phases == list(PHASES[:2])
        and report.get("diagnostic") == "The relevant skill reference was not updated.",
        "No saved baseline: automatic recovery is restricted to the identified assertion bug.",
    )
    # The first run predated checkpoints. Reconstruct immutable seed expectations
    # in a separate disposable directory; never rewrite the existing consumer.
    with tempfile.TemporaryDirectory(prefix="knowledge-resume-baseline.") as temporary:
        pristine = Path(temporary) / "studio"
        pristine.mkdir()
        expected = _prepare(
            pristine, Path(__file__).resolve().parents[2] / "packages/knowledge-agent-pack"
        )
        baseline = {name: _hash(expected[name].read_bytes()) for name in PRESERVED}
    consumer = files["config"].parent
    recorded = [
        event
        for path in (consumer / "ai/usage").rglob("*.jsonl")
        for event in _json_lines(path.read_text())
        if isinstance(event.get("context"), dict)
        and event["context"].get("workspace_id") == WORKSPACE
        and isinstance(event.get("recorded_at"), str)
    ]
    _assert(recorded, "Cannot recover original run interval without tool-written receipts.")
    since = min(
        datetime.fromisoformat(event["recorded_at"].replace("Z", "+00:00")) for event in recorded
    )
    seed_hashes: dict[str, str] = {}
    for path in (consumer / "authored-signals").glob("*.md"):
        data = path.read_bytes()
        identifier = yaml.safe_load(data.decode().split("---", 2)[1])["id"]
        capture_records = [
            event
            for log in (consumer.parent / "logs").glob("cli-*-signal-record.log")
            for event in _json_lines(log.read_text())
            if event.get("id") == identifier and event.get("status") == "ok"
        ]
        _assert(capture_records, f"Missing original tool capture evidence for {identifier}.")
        _assert(
            all(event["fingerprint"] == _hash(data) for event in capture_records),
            f"Seed {identifier} changed since capture.",
        )
        seed_hashes[identifier] = _hash(data)
    _assert(
        set(seed_hashes)
        == {
            "trial-choice",
            "export-evidence-gap",
            "external-policy-source",
            "covered-qualification",
        },
        "Expected four originally captured seeds.",
    )
    state = {
        "baseline_hashes": baseline,
        "baseline_origin": (
            "Reconstructed immutable fixture expectations; matched against existing files. "
            "The original run passed byte-preservation assertions after both completed turns."
        ),
        "wheel_fingerprint": _hash(wheel.read_bytes()),
        "since": (since - timedelta(seconds=1)).isoformat(),
        "since_origin": "One second before earliest retained workspace tool receipt",
        "seed_fingerprints": seed_hashes,
        "verified_phases": [PHASES[0]],
        "session_id": report["turns"][0]["session_id"],
    }
    _check_preserved(files, state)
    return state


def _prior_events(report: dict[str, Any], consumer: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for turn in report["turns"]:
        path = Path(turn["log"]).resolve()
        _assert(
            path.is_relative_to(consumer.parent / "logs"), "Prior turn log is outside this run."
        )
        values = _json_lines(path.read_text())
        init = next((value for value in values if value.get("subtype") == "init"), {})
        final = next((value for value in reversed(values) if value.get("type") == "result"), {})
        _assert(
            init.get("session_id") == turn["session_id"], "Stored turn session differs from log."
        )
        _assert(
            final and not final.get("is_error"),
            "Stored completed turn lacks successful provider evidence.",
        )
        events.extend(values)
    return events


def _check_owner_reference(path: Path) -> None:
    reference = path.read_text().lower()
    _assert(
        "qualification" in reference
        and "source" in reference
        and ("url" in reference or "link" in reference),
        "The relevant skill reference does not require qualification source URLs/links.",
    )


def run(
    wheel: Path,
    *,
    live: bool,
    keep: bool,
    timeout: int,
    budget: float,
    resume_report: Path | None = None,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    if resume_report is None:
        work = Path(tempfile.mkdtemp(prefix="knowledge-final-pass.")).resolve()
        consumer = work / "studio"
        consumer.mkdir()
        logs = work / "logs"
        logs.mkdir()
        report: dict[str, Any] = {
            "schema": "final-pass-acceptance.v1",
            "status": "prepared",
            "consumer": str(consumer),
            "provider": "claude",
            "turns": [],
            "native_scheduling": "not tested; paused",
            "semantic_review": (
                "Review model choices and authored changes separately from structural checks."
            ),
        }
    else:
        report = json.loads(resume_report.read_text())
        _assert(report.get("schema") == "final-pass-acceptance.v1", "Unknown resume report.")
        phases = [turn["phase"] for turn in report["turns"]]
        _assert(
            phases == list(PHASES[: len(phases)]) and phases,
            "Completed turns are not a phase prefix.",
        )
        consumer = Path(report["consumer"]).resolve()
        work, logs = consumer.parent, consumer.parent / "logs"
        _assert(consumer.is_dir() and logs.is_dir(), "The recorded consumer/logs are unavailable.")
    env = _clean_runtime_env()
    for name in ("PYTHONPATH", "VIRTUAL_ENV", "CLAUDE_CONFIG_DIR"):
        env.pop(name, None)
    completed = False
    since = datetime.now(UTC) - timedelta(seconds=1)
    try:
        files = (
            _prepare(consumer, root / "packages/knowledge-agent-pack")
            if resume_report is None
            else _fixture_paths(consumer)
        )
        config = files["config"]
        if resume_report is not None:
            state = _resume_state(report, files, wheel)
            since = datetime.fromisoformat(state["since"])
            report["resume_state"] = state
            report.setdefault("resume_history", []).append(
                {
                    "report": str(resume_report),
                    "prior_status": report["status"],
                    "prior_diagnostic": report.pop("diagnostic", None),
                    "completed_turns_reused": [turn["phase"] for turn in report["turns"]],
                    "test_correction": (
                        "The original reference assertion required literal 'evidence'; "
                        "the authored qualification source URL requirement is correct. "
                        "Check qualification + source + URL/link instead."
                    ),
                }
            )

        def command(args: list[str], label: str) -> None:
            _run(args, cwd=consumer, env=env, log=logs / f"{label}.log", timeout=timeout)

        if resume_report is None:
            command(["git", "init", "-q", "--initial-branch=main"], "git-init")
            command(
                ["apm", "install", "--no-policy", "--target", "codex,claude,copilot"], "apm-install"
            )
            setup = consumer / ".claude/skills/knowledge-setup/scripts/setup_runtime.py"
            command(
                [
                    "uv",
                    "run",
                    "--python",
                    "3.11",
                    "--no-project",
                    "python",
                    str(setup),
                    "--workspace",
                    str(config),
                    "--consumer",
                    str(consumer),
                    "--package",
                    str(wheel),
                    "--targets",
                    "codex,claude,copilot",
                ],
                "runtime-setup",
            )
        launcher = consumer / ".agent-knowledge-venv/bin/agent-knowledge"
        env["PATH"] = str(launcher.parent) + os.pathsep + env.get("PATH", os.defpath)
        sequence = max((int(path.name.split("-")[1]) for path in logs.glob("cli-*.log")), default=0)

        def cli(operation: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
            nonlocal sequence
            sequence += 1
            return _run_json(
                [str(launcher), "--config", str(config), *operation.split(), "--request-file", "-"],
                cwd=consumer,
                env=env,
                input_text=json.dumps(request or {}),
                timeout=timeout,
                log=logs / f"cli-{sequence}-{operation.replace(' ', '-')}.log",
            )

        _assert(
            cli("validate", {"sources": [SOURCE]})["valid"], "Prepared corpus did not validate."
        )
        _assert(cli("doctor")["readiness"]["read"] == "ready", "Prepared runtime is not ready.")
        report["launcher"] = str(launcher)
        if not live and resume_report is None:
            # Exercise the same seed envelope and origin used by the later batches.
            probe = _signal(
                consumer,
                "prepared-signal-envelope",
                "The existing campaign guidance preserves qualification evidence before outreach.",
                "knowledge/guidance/lead-generation.md",
            )
            validated = cli("validate", {"signal_files": [str(probe)]})
            _assert(validated["valid"], "Prepared signal envelope did not validate.")
            captured = cli("signal record", {"file": str(probe)})
            pending = cli("signal list", {"include_shared": True, "limit": 100})
            _assert(pending["total_matches"] == 1, "Prepared signal was not captured exactly once.")
            origin = pending["results"][0]["origin"]
            _assert(origin["workspace_id"] == WORKSPACE, "Prepared signal has the wrong workspace.")
            _assert(
                origin["project_path"] == consumer.name, "Prepared signal has the wrong project."
            )
            _assert(origin["source_ids"] == [SOURCE], "Prepared signal has the wrong source.")
            report["seed_validation"] = validated
            report["seed_capture"] = captured
            report["seed_origin"] = origin
            report["next"] = "Rerun with --live-agent after final wheel/gates are complete."
            completed = True
            return report
        if resume_report is None:
            state = {
                "baseline_hashes": {name: _hash(files[name].read_bytes()) for name in PRESERVED},
                "baseline_origin": "Captured before the first model turn",
                "wheel_fingerprint": _hash(wheel.read_bytes()),
                "since": since.isoformat(),
                "since_origin": "Before setup",
                "seed_fingerprints": {},
                "verified_phases": [],
                "session_id": str(uuid4()),
            }
            report["resume_state"] = state
        session = state["session_id"]
        all_events = _prior_events(report, consumer) if resume_report else []
        originals: dict[str, bytes] = {}
        for identifier, fingerprint in state["seed_fingerprints"].items():
            data = (consumer / f"authored-signals/{identifier}.md").read_bytes()
            _assert(_hash(data) == fingerprint, f"Captured seed changed: {identifier}.")
            originals[identifier] = data

        def checkpoint() -> None:
            _check_preserved(files, state)
            report["checkpoint"] = str(work / "checkpoint.json")
            (work / "checkpoint.json").write_text(json.dumps(report, indent=2) + "\n")

        checkpoint()
        if resume_report is not None and not live:
            if [turn["phase"] for turn in report["turns"]] == list(PHASES[:2]):
                _assert(
                    "Pipedrive" in _current_section(files["guidance"]),
                    "Trial changed current adoption.",
                )
                _check_owner_reference(files["owner_reference"])
                pending = cli("signal list", {"include_shared": True, "limit": 100})
                ids = {row["id"] for row in pending["results"]}
                _assert(
                    "covered-qualification" not in ids, "Already-covered input was not drained."
                )
                _assert("external-policy-source" in ids, "External unresolved input was drained.")
                _assert(
                    not cli("compound", {"action": "status"})["active"],
                    "A compound run is still active.",
                )
                if PHASES[1] not in state["verified_phases"]:
                    state["verified_phases"].append(PHASES[1])
            report.update(
                status="prepared",
                next=(
                    "Resume remaining phases with --live-agent; "
                    "completed turns and fixtures are preserved."
                ),
            )
            checkpoint()
            completed = True
            return report
        boundary = (
            f"Work only within this disposable workspace: {consumer}. Configuration: {config}. "
            "Follow the installed guide and knowledge-compound skill. Carry --harness claude "
            "and the exact hook session ID on knowledge CLI calls, adding --compound-run-id "
            "during a run. Native scheduling is paused: do not create, trigger or alter jobs. "
            "No remote Git/GitHub, global settings or shell-profile changes. Publication is "
            "disabled. Authorized edits are local prepared knowledge, catalog and "
            "studio-agent-tools "
            "source updates; retain unpublished write decisions. Only confirmed no-write decisions "
            "can drain. Receipts and archives are tool-owned. Originating skill/instruction "
            "inventory is origin-context/skill-inventory.md. "
        )

        def turn(label: str, prompt: str, *, first: bool = False) -> str:
            previous = next((item for item in report["turns"] if item["phase"] == label), None)
            if previous is not None:
                return str(previous["response"])
            print(f"Claude final pass: {label}", file=sys.stderr, flush=True)
            args = _provider_command("claude", boundary + prompt, consumer)
            args.remove("--no-session-persistence")
            args[args.index("--output-format") + 1] = "stream-json"
            args.extend(
                [
                    "--model",
                    "opus",
                    "--verbose",
                    "--setting-sources",
                    "project,local",
                    "--strict-mcp-config",
                    "--mcp-config",
                    '{"mcpServers":{}}',
                    "--tools",
                    "Read,Write,Edit,Bash,Grep,Glob,Skill",
                    "--max-budget-usd",
                    str(budget),
                    "--session-id" if first else "--resume",
                    session,
                ]
            )
            result = _run(args, cwd=consumer, env=env, log=logs / f"{label}.log", timeout=timeout)
            events = _json_lines(result.stdout)
            all_events.extend(events)
            init = next((e for e in events if e.get("subtype") == "init"), {})
            final = next((e for e in reversed(events) if e.get("type") == "result"), {})
            _assert(init.get("session_id") == session, "Provider session changed.")
            _assert(init.get("model") == "claude-opus-5", "Expected Claude Opus 5.")
            _assert(final and not final.get("is_error"), f"Claude did not complete {label}.")
            response = _redact(str(final.get("result", "")))
            report["turns"].append(
                {
                    "phase": label,
                    "session_id": session,
                    "model": init["model"],
                    "response": response,
                    "commands": [_redact(c) for c in _tool_commands(events)],
                    "log": str(logs / f"{label}.log"),
                }
            )
            checkpoint()
            return response

        turn(
            "incoming-and-rename",
            "Starting with business-knowledge:product/features/order-history.md, discover its "
            "incoming knowledge references and explain any availability limitation. Then rename "
            "that feature document to product/features/purchase-history.md, repair "
            "affected authored "
            "and catalog references, and validate. Keep scope/topics and unrelated "
            "files unchanged. "
            "Do not use a whole-tree content search instead of incoming inspection.",
            first=True,
        )
        _assert(
            not (consumer / "knowledge/product/features/order-history.md").exists(),
            "Old feature path remains.",
        )
        _assert(
            (consumer / "knowledge/product/features/purchase-history.md").is_file(),
            "Feature was not renamed.",
        )
        _assert(
            "purchase-history.md#availability"
            in (consumer / "knowledge/limitations/refresh-window.md").read_text(),
            "Incoming reference was not repaired.",
        )
        catalog = yaml.safe_load((consumer / "catalog.yaml").read_text())
        _assert(
            catalog["entities"]["feature:order-history"]["documents"]
            == [{"source": SOURCE, "path": "product/features/purchase-history.md"}],
            "Catalog reference was not repaired.",
        )
        _assert(cli("validate", {"sources": [SOURCE]})["valid"], "Rename left invalid references.")

        def capture(identifier: str, claim: str, evidence_name: str, evidence: str) -> None:
            if identifier in originals:
                return
            _write(consumer / evidence_name, evidence)
            path = _signal(consumer, identifier, claim, evidence_name)
            _assert(
                cli("validate", {"signal_files": [str(path)]})["valid"],
                f"Seed signal {identifier} did not validate.",
            )
            cli("signal record", {"file": str(path)})
            originals[identifier] = path.read_bytes()
            state["seed_fingerprints"][identifier] = _hash(originals[identifier])
            checkpoint()

        capture(
            "trial-choice",
            "Solution X was tried for the qualification-to-outreach handoff; the "
            "trial did not resolve reconciliation. No replacement was adopted.",
            "evidence/trial.md",
            "Owner evaluation: Solution X remained a trial. Pipedrive is still the "
            "adopted choice; effective dates are unknown.\n",
        )
        capture(
            "export-evidence-gap",
            "The qualified-prospect CSV preserved decisions but lost the source URLs "
            "supporting them. Future handoffs need those URLs alongside the decisions.",
            "evidence/export-review.md",
            "The owner reviewed the export and confirmed missing qualification source "
            "URLs. The local export checklist enumerates fields but omits evidence "
            "links.\n",
        )
        capture(
            "external-policy-source",
            "An originating external policy instruction and its related skill say to "
            "discard qualification URLs, conflicting with the confirmed retention "
            "requirement. Their authoritative source is unavailable.",
            "evidence/policy-conflict.md",
            "See origin-context/external-policy.instructions.md and the originating "
            "skill inventory. Only installed projections are accessible; external "
            "source/publication authorization is unavailable.\n",
        )
        capture(
            "covered-qualification",
            "Prospects must match the stated customer profile, and qualification "
            "evidence must be retained before outreach.",
            "evidence/qualification.md",
            "This is the same qualification requirement already described by current "
            "lead-generation guidance. No new behavior was observed.\n",
        )
        turn(
            "trial-and-owner-discovery",
            "Process the four seeded pending signals as one manual compounding batch. "
            "Discover actual owners, prepare supported local updates, and report "
            "disposition/evidence. Distinguish the tool trial from adoption. The "
            "external policy owner cannot be published here. Finish the run; retain "
            "unpublished/unresolved inputs and safely drain only confirmed no-write "
            "outcomes.",
        )
        if PHASES[1] not in state["verified_phases"]:
            _assert(
                "Pipedrive" in _current_section(files["guidance"]),
                "A trial changed the adopted choice.",
            )
            _check_owner_reference(files["owner_reference"])
            pending = cli("signal list", {"include_shared": True, "limit": 100})
            ids = {row["id"] for row in pending["results"]}
            _assert(
                "covered-qualification" not in ids,
                "Confirmed already-covered signal was not safely drained.",
            )
            _assert("external-policy-source" in ids, "Unresolved external update was drained.")
            _assert(
                not cli("compound", {"action": "status"})["active"], "Trial batch remained active."
            )

            state["verified_phases"].append(PHASES[1])
            checkpoint()

        if "guidance_paths_before_adoption" not in state:
            state["guidance_paths_before_adoption"] = sorted(
                str(path) for path in (consumer / "knowledge/guidance").glob("*.md")
            )
            checkpoint()
        guidance_files = {Path(path) for path in state["guidance_paths_before_adoption"]}
        capture(
            "adopted-choice",
            "The owner has now confirmed Apollo adoption: its evaluated handoff "
            "preserves qualification evidence with less reconciliation. Reconsider if "
            "required export behavior changes. Effective adoption date was not "
            "recorded.",
            "evidence/adoption.md",
            "Owner-approved decision: adopt Apollo for the next campaign. Pipedrive "
            "was useful for early manual follow-up; Solution X stayed an unsuccessful "
            "trial. Apollo reduced manual reconciliation while preserving evidence. "
            "Update the current campaign procedure; no effective business date is "
            "known.\n",
        )
        turn(
            "confirmed-adoption",
            "Compound the new confirmed business-choice signal, taking prior retained "
            "signals into account. Update the existing guidance and linked current "
            "procedure with the evidenced decision and useful history. Finish the run "
            "with truthful local-preparation dispositions; remote publication is "
            "still unavailable.",
        )
        _assert(
            set((consumer / "knowledge/guidance").glob("*.md")) == guidance_files,
            "Successive decisions created parallel guidance owners.",
        )
        _assert(
            "Apollo" in _current_section(files["guidance"]),
            "Confirmed adoption is not the current approach.",
        )
        _assert(
            all(term in files["guidance"].read_text() for term in ("Pipedrive", "Solution X")),
            "Useful prior decision context was lost.",
        )
        _assert(
            "Apollo" in files["procedure"].read_text(),
            "Current campaign procedure was not updated.",
        )
        _assert(
            cli("validate", {"sources": [SOURCE]})["valid"], "Business updates did not validate."
        )
        _assert(
            not cli("compound", {"action": "status"})["active"], "Adoption batch remained active."
        )

        if "pending_before_read" not in state:
            state["pending_before_read"] = sorted(
                row["id"]
                for row in cli("signal list", {"include_shared": True, "limit": 100})["results"]
            )
            checkpoint()
        pending_before_read = set(state["pending_before_read"])
        final_response = turn(
            "current-versus-history",
            "Read-only: what should I use to run the next campaign, and why did we "
            "leave Pipedrive? Use focused CLI discovery and appropriate sections of "
            "the existing owners. Distinguish the current procedure from past "
            "rationale; do not invent missing dates. There is no new observation to "
            "record.",
        )
        _assert(
            "Apollo" in final_response and "Pipedrive" in final_response,
            "Retrieval answer omitted current/history distinction.",
        )
        pending_after_read = {
            row["id"]
            for row in cli("signal list", {"include_shared": True, "limit": 100})["results"]
        }
        _assert(
            pending_after_read == pending_before_read,
            "Read-only answer created a redundant signal.",
        )
        encoded = json.dumps(all_events)
        _assert(UNRELATED_MARKER not in encoded, "The unrelated invoice skill body was loaded.")
        reads = [
            str(inputs.get("file_path", ""))
            for name, inputs in _tool_uses(all_events)
            if name.lower() == "read"
        ]
        _assert(
            not any("invoice-reconciler/SKILL.md" in path for path in reads),
            "Unrelated skill body was explicitly read.",
        )
        _assert(
            any("outreach-coach" in path for path in reads)
            or any("outreach-coach" in command for command in _tool_commands(all_events)),
            "Relevant skill owner discovery was not observable.",
        )
        destination = consumer / "usage-review"
        if destination.exists():
            destination = consumer / f"usage-review-{uuid4().hex[:8]}"
        exported = cli(
            "usage export",
            {
                "since": since.isoformat().replace("+00:00", "Z"),
                "until": (datetime.now(UTC) + timedelta(seconds=1))
                .isoformat()
                .replace("+00:00", "Z"),
                "destination": str(destination),
            },
        )
        usage = _usage_proof(destination, originals)
        report.update(
            status="passed",
            usage=usage,
            export=exported,
            observed_skill_reads=reads,
            authored_content={
                name: files[name].read_text()
                for name in ("guidance", "procedure", "owner_reference")
            },
            checks=[
                "Incoming-only dependent discovery and rename/catalog repair",
                "Description-based skill owner/reference discovery",
                "Already-covered drainage with exact input archive",
                "External skill/instruction owner retained and deferred",
                "Trial versus adoption in one guidance owner",
                "Current versus historical retrieval",
                "Workspace and unrelated owners preserved",
                "Automatic receipts, correlated compound operations and checksummed export",
            ],
        )
        report.pop("diagnostic", None)
        checkpoint()
        completed = True
        return report
    except (HarnessSmokeFailure, OSError, KeyError, ValueError) as error:
        report.update(status="failed", diagnostic=_redact(str(error)))
        return report
    finally:
        if completed and not keep and resume_report is None:
            shutil.rmtree(work)
        elif not completed:
            print(f"Retained failed final-pass workspace: {work}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument(
        "--resume-report",
        type=Path,
        help=(
            "Continue a retained run without repeating completed model turns "
            "or recreating fixtures."
        ),
    )
    parser.add_argument(
        "--live-agent",
        action="store_true",
        help="Use authenticated Claude after all slices are built.",
    )
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--max-budget-usd", type=float, default=3.0, help="Per turn; four bounded turns."
    )
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error("--wheel must name a built wheel")
    report = run(
        wheel,
        live=args.live_agent,
        keep=args.keep,
        timeout=args.timeout,
        budget=args.max_budget_usd,
        resume_report=args.resume_report.resolve() if args.resume_report else None,
    )
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0 if report["status"] in {"prepared", "passed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
