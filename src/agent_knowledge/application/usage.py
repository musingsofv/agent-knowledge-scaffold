"""Export workspace-isolated usage evidence and conservative local summaries."""

import hashlib
import json
import os
import stat
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_knowledge.domain.usage import (
    UsageExportQuery,
    parse_usage_export_query,
    read_utc_timestamp,
)
from agent_knowledge.domain.validation import ValidationError, read_relative_path
from agent_knowledge.infrastructure.configuration import Workspace
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import open_directory, read_bytes
from agent_knowledge.infrastructure.usage import (
    MAX_ARTIFACT_BYTES,
    UsageDiagnostic,
    canonical_json,
    checksum,
    ensure_directory,
    prune_compound,
    prune_retrieval,
    read_events,
    usage_lock,
    write_artifact,
)

KNOWN_SCHEMAS = {"knowledge-retrieval-receipt.v1", "knowledge-compound-receipt.v1"}


def _context(event: dict[str, object]) -> dict[str, object]:
    context = event.get("context")
    return context if isinstance(context, dict) else {}


def _timestamp(event: dict[str, object]) -> datetime | None:
    try:
        return read_utc_timestamp(event.get("recorded_at"), "recorded_at")
    except ValidationError:
        return None


def _children(path: Path, diagnostics: list[UsageDiagnostic]) -> tuple[Path, ...]:
    try:
        with open_directory(path) as directory:
            return tuple(
                path / name for name in sorted(os.listdir(directory)) if not name.startswith(".")
            )
    except AdapterError as error:
        diagnostics.append(UsageDiagnostic(error.code, error.path, error.message))
        return ()


def _kind(path: Path, *, directory: bool = False) -> bool:
    try:
        with open_directory(path.parent) as parent:
            metadata = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            return stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    except (AdapterError, OSError):
        return False


def _logs(root: Path, diagnostics: list[UsageDiagnostic]) -> tuple[Path, ...]:
    logs: list[Path] = []
    for directory in (root / "retrieval", root / "compound"):
        if not directory.exists():
            if directory.is_symlink():
                diagnostics.append(
                    UsageDiagnostic(
                        "unsafe-usage-path", str(directory), "Usage directory is a symlink."
                    )
                )
            continue
        for child in _children(directory, diagnostics):
            if directory.name == "retrieval":
                if child.suffix == ".jsonl":
                    logs.append(child)
            elif _kind(child, directory=True):
                if (child / "expired.json").exists():
                    diagnostics.append(
                        UsageDiagnostic(
                            "usage-evidence-expired",
                            str(child),
                            "Retention expired this run; interrupted cleanup may leave some files.",
                        )
                    )
                if (child / "events.jsonl").exists():
                    logs.append(child / "events.jsonl")
                elif not (child / "expired.json").exists():
                    diagnostics.append(
                        UsageDiagnostic(
                            "usage-run-context-unavailable",
                            str(child),
                            "Run event evidence is missing.",
                        )
                    )
            else:
                diagnostics.append(
                    UsageDiagnostic(
                        "unsafe-usage-path", str(child), "Run storage is not a real directory."
                    )
                )
    return tuple(logs)


def _diagnostic(code: str, path: str, message: str, items: list[UsageDiagnostic]) -> None:
    value = UsageDiagnostic(code, path, message)
    if value not in items:
        items.append(value)


def _artifact_paths(value: object) -> set[str]:
    paths: set[str] = set()
    match value:
        case dict():
            for key, item in value.items():
                if key in {"path", "changes", "patch", "archive", "snapshot_path"} and isinstance(
                    item, str
                ):
                    paths.add(item)
                elif isinstance(item, dict | list):
                    paths.update(_artifact_paths(item))
        case list():
            for item in value:
                paths.update(_artifact_paths(item))
    return paths


def _run_artifacts(
    run: Path, events: list[dict[str, object]], diagnostics: list[UsageDiagnostic]
) -> set[str]:
    paths = {"start.json"}
    for event in events:
        paths.update(_artifact_paths(event.get("artifacts")))
    for candidate in _children(run, diagnostics):
        if candidate.name in {"events.jsonl", "start.json"}:
            continue
        if candidate.name == "inputs" and _kind(candidate, directory=True):
            paths.update(str(item.relative_to(run)) for item in _children(candidate, diagnostics))
    return paths


def _artifact_fingerprints(value: object) -> dict[str, str]:
    result: dict[str, str] = {}
    match value:
        case dict():
            path, fingerprint = value.get("path"), value.get("fingerprint")
            if isinstance(path, str) and isinstance(fingerprint, str):
                result[path] = fingerprint
            for item in value.values():
                result.update(_artifact_fingerprints(item))
        case list():
            for item in value:
                result.update(_artifact_fingerprints(item))
    return result


def _copy_artifact(
    source: Path,
    destination: Path,
    manifest: list[dict[str, object]],
    diagnostics: list[UsageDiagnostic],
    *,
    relative: str,
    expected_checksum: str | None = None,
) -> None:
    try:
        data = read_bytes(source, max_bytes=MAX_ARTIFACT_BYTES)
        write_artifact(destination / relative, data)
        actual_checksum = checksum(data)
        entry: dict[str, object] = {
            "path": relative,
            "bytes": len(data),
            "checksum": actual_checksum,
        }
        if expected_checksum is not None:
            entry["expected_checksum"] = expected_checksum
            if actual_checksum != expected_checksum:
                diagnostics.append(
                    UsageDiagnostic(
                        "usage-artifact-fingerprint-mismatch",
                        str(source),
                        "Artifact fingerprint differs; changed bytes were exported for review.",
                    )
                )
        manifest.append(entry)
    except AdapterError as error:
        diagnostics.append(
            UsageDiagnostic(
                "usage-artifact-unavailable", str(source), f"Artifact not exported: {error.message}"
            )
        )


def _write_export(
    destination: Path, relative: str, data: bytes, manifest: list[dict[str, object]]
) -> None:
    write_artifact(destination / relative, data)
    manifest.append({"path": relative, "bytes": len(data), "checksum": checksum(data)})


def _summary(events: list[dict[str, object]], supporting: int) -> dict[str, object]:
    operations: Counter[str] = Counter()
    dispositions: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    elapsed: list[float] = []
    response_bytes = 0
    pages = 0
    missing_sessions = 0
    for event in events:
        operations[str(event.get("operation", "unknown"))] += 1
        if not _context(event).get("session_id"):
            missing_sessions += 1
        measurements = event.get("measurements")
        if isinstance(measurements, dict):
            duration = measurements.get("elapsed_ms")
            if (
                isinstance(duration, int | float)
                and not isinstance(duration, bool)
                and duration >= 0
            ):
                elapsed.append(float(duration))
            size = measurements.get("response_bytes")
            if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
                response_bytes += size
        response = event.get("response")
        if isinstance(response, dict):
            statuses[str(response.get("status", "unknown"))] += 1
            pages += response.get("truncated") is True
        # Count submitted dispositions once at the terminal drain, not its intent.
        report = event.get("agent_report")
        if event.get("operation") == "compound.drain" and isinstance(report, dict):
            decisions = report.get("dispositions")
            if isinstance(decisions, list):
                for decision in decisions:
                    if isinstance(decision, dict):
                        dispositions[str(decision.get("decision", "unknown"))] += 1
    return {
        "selected_events": len(events),
        "supporting_events": supporting,
        "operations": dict(sorted(operations.items())),
        "response_statuses": dict(sorted(statuses.items())),
        "dispositions": dict(sorted(dispositions.items())),
        "missing_session_ids": missing_sessions,
        "truncated_pages": pages,
        "elapsed_ms": {
            "count": len(elapsed),
            "total": sum(elapsed),
            "maximum": max(elapsed, default=None),
        },
        "response_bytes": response_bytes,
        "body_reads": "unknown",
        "semantic_relevance": "not-evaluated",
    }


def export_usage(workspace: Workspace, raw_request: object) -> dict[str, object]:
    """Write a portable evidence bundle for one explicit workspace and UTC interval."""
    query = parse_usage_export_query(raw_request)
    return export_workspace_usage(workspace, query)


def export_workspace_usage(workspace: Workspace, query: UsageExportQuery) -> dict[str, object]:
    """Select records before creating an exclusive destination; never modify originals."""
    root = workspace.receipts.directory
    destination = Path(query.destination)
    if not destination.is_absolute():
        destination = workspace.path.parent / destination
    destination = Path(os.path.abspath(destination))
    # Do not resolve aliases: every component is checked again during creation.
    protected = [root, *(source.root for source in workspace.sources)]
    if workspace.signal_storage:
        protected.append(workspace.signal_storage.signal_root)
    for location in protected:
        if destination.is_relative_to(location) or location.is_relative_to(destination):
            raise ValidationError(
                "unsafe-usage-destination",
                "destination",
                "Export destination overlaps managed storage.",
            )
    diagnostics: list[UsageDiagnostic] = []
    logs: dict[Path, list[dict[str, object]]] = {}
    selected: list[dict[str, object]] = []
    supporting: list[dict[str, object]] = []
    selected_runs: set[str] = set()
    workspace_id = workspace.definition.workspace_id
    for path in _logs(root, diagnostics):
        loaded = read_events(path)
        diagnostics.extend(loaded.diagnostics)
        records = list(loaded.records)
        logs[path] = records
        for event in records:
            if _context(event).get("workspace_id") != workspace_id:
                continue
            timestamp = _timestamp(event)
            if timestamp is None:
                _diagnostic(
                    "usage-invalid-timestamp",
                    str(path),
                    "An event cannot be assigned to an interval.",
                    diagnostics,
                )
                continue
            if query.since <= timestamp < query.until:
                selected.append(event)
                run_id = _context(event).get("compound_run_id")
                if isinstance(run_id, str):
                    selected_runs.add(run_id)
    # Retrieval in the interval can reference a compound run whose start precedes it.
    for records in logs.values():
        related = [
            event
            for event in records
            if _context(event).get("workspace_id") == workspace_id
            and _context(event).get("compound_run_id") in selected_runs
        ]
        for event in related:
            timestamp = _timestamp(event)
            if timestamp is not None and timestamp < query.since:
                supporting.append(event)
    evidence = selected + supporting
    for event in evidence:
        if event.get("schema_version") not in KNOWN_SCHEMAS:
            _diagnostic(
                "usage-unknown-version",
                str(event.get("event_id", "unknown")),
                "Unknown event version is preserved without a completeness claim.",
                diagnostics,
            )
        if not _context(event).get("session_id"):
            _diagnostic(
                "usage-session-unavailable",
                "context.session_id",
                "Some events lack a supplied session handle.",
                diagnostics,
            )
        if event.get("cli_version") in (None, "unavailable"):
            _diagnostic(
                "usage-cli-version-unavailable",
                str(event.get("event_id", "unknown")),
                "Some events lack an available CLI package version.",
                diagnostics,
            )
    if not selected:
        diagnostics.append(
            UsageDiagnostic(
                "usage-no-records",
                str(root),
                "No retained events match; this does not prove no activity occurred.",
            )
        )
    ensure_directory(destination, exclusive=True)
    manifest: list[dict[str, object]] = []
    output_records = [dict(event, export_supporting_context=False) for event in selected]
    output_records.extend(dict(event, export_supporting_context=True) for event in supporting)
    output_records.sort(
        key=lambda event: (str(event.get("recorded_at", "")), str(event.get("event_id", "")))
    )
    _write_export(
        destination,
        "events.jsonl",
        b"".join(canonical_json(event) + b"\n" for event in output_records),
        manifest,
    )
    for run_id in sorted(selected_runs):
        try:
            safe_id = read_relative_path(run_id, "context.compound_run_id")
            if "/" in safe_id:
                raise ValidationError(
                    "unsafe-run-id", "context.compound_run_id", "Expected one run name."
                )
        except ValidationError:
            diagnostics.append(
                UsageDiagnostic(
                    "unsafe-run-id",
                    "context.compound_run_id",
                    "Run artifacts were not followed for an unsafe identifier.",
                )
            )
            continue
        run = root / "compound" / safe_id
        records = logs.get(run / "events.jsonl", [])
        # Artifacts cannot safely be attributed from mixed or unidentified run logs.
        if not records or any(
            _context(event).get("workspace_id") != workspace_id for event in records
        ):
            diagnostics.append(
                UsageDiagnostic(
                    "usage-run-context-unavailable",
                    str(run),
                    "Missing or mixed-workspace run context; artifacts were not exported.",
                )
            )
            continue
        relevant = [event for event in evidence if _context(event).get("compound_run_id") == run_id]
        expected_fingerprints: dict[str, str] = {}
        for event in relevant:
            expected_fingerprints.update(_artifact_fingerprints(event.get("artifacts")))
        if not any(event.get("operation") == "compound.start" for event in relevant):
            diagnostics.append(
                UsageDiagnostic(
                    "usage-run-start-unavailable",
                    str(run),
                    "Run-start context is missing from the retained evidence.",
                )
            )
        for relative in sorted(_run_artifacts(run, relevant, diagnostics)):
            try:
                read_relative_path(relative, "artifact.path")
            except ValidationError:
                diagnostics.append(
                    UsageDiagnostic(
                        "unsafe-artifact-reference",
                        str(run),
                        "Unsafe artifact reference was not followed.",
                    )
                )
                continue
            _copy_artifact(
                run / relative,
                destination,
                manifest,
                diagnostics,
                relative=f"compound/{safe_id}/{relative}",
                expected_checksum=expected_fingerprints.get(relative),
            )
    descriptors = {
        str(event["descriptor"]) for event in evidence if isinstance(event.get("descriptor"), str)
    }
    if any(not isinstance(event.get("descriptor"), str) for event in evidence):
        diagnostics.append(
            UsageDiagnostic(
                "usage-descriptor-unavailable",
                "descriptor",
                "Selected events do not identify a workspace descriptor.",
            )
        )
    for relative in sorted(descriptors):
        assert isinstance(relative, str)
        digest = Path(relative).stem
        if (
            relative != f"descriptors/{digest}.json"
            or len(digest) != 64
            or any(value not in "0123456789abcdef" for value in digest)
        ):
            diagnostics.append(
                UsageDiagnostic(
                    "usage-descriptor-unavailable",
                    "descriptor",
                    "Unsupported descriptor reference.",
                )
            )
            continue
        path = root / relative
        try:
            data = read_bytes(path, max_bytes=MAX_ARTIFACT_BYTES)
            if hashlib.sha256(data).hexdigest() != digest:
                raise AdapterError(
                    "usage-descriptor-invalid", str(path), "Descriptor bytes changed."
                )
            descriptor: object = json.loads(data)
            if not isinstance(descriptor, dict) or descriptor.get("workspace_id") != workspace_id:
                raise AdapterError(
                    "usage-descriptor-foreign",
                    str(path),
                    "Descriptor ownership is unavailable or foreign.",
                )
            sources = descriptor.get("sources")
            if not isinstance(sources, list) or any(
                not isinstance(source, dict)
                or source.get("source_version") in (None, "unavailable", "unknown")
                for source in sources
            ):
                diagnostics.append(
                    UsageDiagnostic(
                        "usage-source-version-unavailable",
                        str(path),
                        "Source revisions are unavailable; descriptors cannot replay old bodies.",
                    )
                )
            _write_export(destination, f"descriptors/{digest}.json", data, manifest)
        except (AdapterError, ValueError):
            diagnostics.append(
                UsageDiagnostic(
                    "usage-descriptor-unavailable",
                    str(path),
                    "Workspace/source/catalog version descriptor is missing, invalid or foreign.",
                )
            )
    summary = _summary(selected, len(supporting))
    summary["coverage"] = [asdict(item) for item in diagnostics]
    _write_export(destination, "summary.json", canonical_json(summary) + b"\n", manifest)
    export_manifest = {
        "schema_version": "knowledge-usage-export.v1",
        "workspace_id": workspace_id,
        "since": query.since.isoformat().replace("+00:00", "Z"),
        "until": query.until.isoformat().replace("+00:00", "Z"),
        "interval": "since-inclusive-until-exclusive",
        "files": manifest,
        "diagnostics": [asdict(item) for item in diagnostics],
        "limitations": [
            "ordinary body reads are unknown",
            "hashes do not reconstruct historical corpus bodies",
            "publication assertions remain agent-reported unless independently verified",
        ],
    }
    write_artifact(destination / "manifest.json", canonical_json(export_manifest) + b"\n")
    return {
        "status": "ok",
        "destination": str(destination),
        "manifest": str(destination / "manifest.json"),
        "summary": summary,
        "diagnostics": [asdict(item) for item in diagnostics],
    }


def retain_usage(workspace: Workspace, *, now: datetime | None = None) -> dict[str, object]:
    """Apply configured retention without deleting active, unresolved or unknown evidence."""
    instant = now if now is not None else datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise ValueError("retention requires a UTC time")
    oldest = datetime.min.replace(tzinfo=UTC)
    days = workspace.receipts.retention_days
    cutoff = oldest if days > (instant - oldest).days else instant - timedelta(days=days)
    root = workspace.receipts.directory
    diagnostics: list[UsageDiagnostic] = []
    logs = _logs(root, diagnostics)
    expired_runs: set[str] = set()
    if workspace.signal_storage is not None:
        activity_lock = workspace.signal_storage.signal_root / "compound-activity.jsonl.lock"
        for path in logs:
            if path.parent.parent != root / "compound":
                continue
            try:
                if prune_compound(
                    path.parent,
                    workspace_id=workspace.definition.workspace_id,
                    cutoff=cutoff,
                    activity_lock=activity_lock,
                ):
                    expired_runs.add(path.parent.name)
            except AdapterError as error:
                diagnostics.append(UsageDiagnostic(error.code, error.path, error.message))
    removed = 0
    for path in logs:
        if path.parent != root / "retrieval":
            continue
        try:
            removed += prune_retrieval(
                path,
                workspace_id=workspace.definition.workspace_id,
                cutoff=cutoff,
                expired_run_ids=frozenset(expired_runs),
            )
        except AdapterError as error:
            diagnostics.append(UsageDiagnostic(error.code, error.path, error.message))
    return {
        "retrieval_records_removed": removed,
        "completed_runs_expired": sorted(expired_runs),
        "diagnostics": [asdict(item) for item in diagnostics],
    }


def maintain_usage(workspace: Workspace) -> dict[str, object]:
    """Bound normal CLI retention to once per UTC day/workspace without failing its result."""
    instant = datetime.now(UTC)
    root = workspace.receipts.directory
    workspace_id = workspace.definition.workspace_id
    digest = hashlib.sha256(workspace_id.encode("utf-8")).hexdigest()
    marker = root / "maintenance" / f"{instant.date().isoformat()}-{digest}.json"
    try:
        with usage_lock(root / ".maintenance.lock"):
            if marker.exists() or marker.is_symlink():
                raw = read_bytes(marker, max_bytes=MAX_ARTIFACT_BYTES)
                document: object = json.loads(raw)
                if (
                    not isinstance(document, dict)
                    or document.get("workspace_id") != workspace_id
                    or document.get("schema_version") != "knowledge-usage-maintenance.v1"
                ):
                    raise AdapterError(
                        "usage-maintenance-invalid",
                        str(marker),
                        "Existing maintenance evidence is invalid; it was preserved.",
                    )
                return {"status": "already-applied", "diagnostics": []}
            result = retain_usage(workspace, now=instant)
            write_artifact(
                marker,
                canonical_json(
                    {
                        "schema_version": "knowledge-usage-maintenance.v1",
                        "workspace_id": workspace_id,
                        "recorded_at": instant.isoformat().replace("+00:00", "Z"),
                        "result": result,
                    }
                )
                + b"\n",
            )
            return {"status": "completed", **result}
    except (AdapterError, ValueError, OSError):
        return {
            "status": "failed",
            "diagnostics": [
                {
                    "code": "usage-maintenance-failed",
                    "path": str(root),
                    "message": "Usage retention could not complete; operation result is unchanged.",
                }
            ],
        }
