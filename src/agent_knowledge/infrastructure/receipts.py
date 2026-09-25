"""Collect terminal tool observations; ordinary file/body reads remain unknown."""

import hashlib
import secrets
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from agent_knowledge.domain.invocation import InvocationContext
from agent_knowledge.domain.validation import ValidationError

from .configuration import (
    CONFIG_MAX_BYTES,
    Workspace,
    effective_configuration,
    workspace_is_current,
)
from .documents import load_mapping
from .errors import AdapterError
from .filesystem import read_bytes
from .usage import append_event, canonical_json, write_artifact


def cli_version() -> str:
    """Expose package version without guessing source revision."""
    try:
        return version("agent-knowledge-scaffold")
    except PackageNotFoundError:
        return "unavailable"


def common_event(
    workspace: Workspace,
    context: dict[str, object],
    operation: str,
    elapsed_ms: float = 0,
) -> dict[str, object]:
    """Create shared event fields; callers add observations and measurements."""
    return {
        "schema_version": (
            "knowledge-compound-receipt.v1"
            if operation.startswith("compound.") or operation == "validate"
            else "knowledge-retrieval-receipt.v1"
        ),
        "event_id": "event-" + secrets.token_hex(16),
        "recorded_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "context": context,
        "selection": workspace.selection.summary(workspace.fingerprint),
        "cli_version": cli_version(),
        "workspace_fingerprint": "sha256:" + workspace.fingerprint,
        "operation": operation,
        "measurements": {"elapsed_ms": round(elapsed_ms, 3)},
    }


def persist_descriptor(workspace: Workspace) -> Path:
    """Retain the exact interpreted vocabulary, without runtime secrets or transcripts."""
    catalogs: list[dict[str, object]] = []
    for source in workspace.sources:
        raw = read_bytes(source.catalog_path, max_bytes=CONFIG_MAX_BYTES)
        catalogs.append(
            {
                "id": source.id,
                "root": str(source.root),
                "catalog_path": str(source.catalog_path),
                "catalog_fingerprint": "sha256:" + hashlib.sha256(raw).hexdigest(),
                "catalog": load_mapping(raw, path=str(source.catalog_path)),
                "source_version": "unavailable",
            }
        )
    descriptor = {
        "schema_version": "knowledge-usage-descriptor.v1",
        "workspace_id": workspace.definition.workspace_id,
        "configuration": effective_configuration(workspace),
        "workspace_fingerprint": "sha256:" + workspace.fingerprint,
        "applicable_scopes": list(workspace.definition.applicable_scopes),
        "sources": catalogs,
        "source_history": (
            "Catalog values and source paths only; document bodies are not replayable."
        ),
    }
    if not workspace_is_current(workspace):
        raise AdapterError(
            "workspace-changed", str(workspace.path), "Workspace changed during evidence capture."
        )
    descriptor["selection"] = workspace.selection.summary(workspace.fingerprint)
    encoded = canonical_json(descriptor)
    path = (
        workspace.receipts.directory / "descriptors" / f"{hashlib.sha256(encoded).hexdigest()}.json"
    )
    write_artifact(path, encoded)
    return path


def record_terminal(
    workspace: Workspace,
    context: InvocationContext,
    *,
    operation: str,
    request: object,
    response: dict[str, object],
    elapsed_ms: float,
) -> dict[str, object]:
    """Append one response; diagnostic collection never changes retrieval success."""
    if not workspace.receipts.enabled:
        return {"status": "disabled"}
    path: Path | None = None
    try:
        descriptor = persist_descriptor(workspace)
        event = common_event(workspace, context.as_dict(), operation, elapsed_ms)
        measured = canonical_json(response)
        event.update(
            request=request,
            response=response,
            measurements={"elapsed_ms": round(elapsed_ms, 3), "response_bytes": len(measured)},
            body_read="unknown",
            descriptor=str(descriptor.relative_to(workspace.receipts.directory)),
        )
        if operation == "validate" and context.compound_run_id is not None:
            path = (
                workspace.receipts.directory / "compound" / context.compound_run_id / "events.jsonl"
            )
        else:
            day = str(event["recorded_at"])[:10]
            path = workspace.receipts.directory / "retrieval" / f"{day}.jsonl"
        append_event(path, event)
        return {"status": "written", "path": str(path), "event_id": event["event_id"]}
    except (AdapterError, ValidationError, OSError, ValueError, TypeError):
        return {
            "status": "failed",
            "diagnostic": {
                "code": "receipt-write-failed",
                "path": str(path) if path else str(workspace.receipts.directory),
                "message": (
                    "Usage evidence could not be safely persisted; the operation "
                    "result is unchanged."
                ),
            },
        }
