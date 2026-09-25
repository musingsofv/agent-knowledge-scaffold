"""Store mandatory compound evidence independently of optional diagnostic collection."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from time import monotonic

from agent_knowledge.domain.compounding import (
    PublicationEvidence,
    SignalDisposition,
    SignalSnapshot,
)
from agent_knowledge.domain.validation import ValidationError

from .configuration import Workspace
from .errors import AdapterError
from .filesystem import open_directory, read_bytes, resolve_document_path
from .receipts import common_event, persist_descriptor
from .usage import append_event, read_events, usage_lock, write_artifact

MAX_ARTIFACT_BYTES = 8_388_608
_RUN = re.compile(r"compound-[0-9a-f]{32}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


def run_root(workspace: Workspace, run_id: str) -> Path:
    """Resolve a tool-issued run ID without allowing caller-selected paths."""
    if not _RUN.fullmatch(run_id):
        raise ValidationError("invalid-run-id", "run_id", "Expected a tool-issued compound run ID.")
    return workspace.receipts.directory / "compound" / run_id


def archive_path(workspace: Workspace, run_id: str, snapshot: SignalSnapshot) -> Path:
    """Use the original identity's hash, never an untrusted signal ID as a filename."""
    identity = json.dumps([snapshot.id, snapshot.path], separators=(",", ":")).encode()
    return run_root(workspace, run_id) / "inputs" / (hashlib.sha256(identity).hexdigest() + ".md")


@contextmanager
def lifecycle_lock(path: Path) -> Iterator[None]:
    """Serialize the entire read/validate/archive/remove lifecycle across CLI processes."""
    with usage_lock(Path(str(path) + ".lock")):
        yield


def evidence_records(workspace: Workspace, run_id: str) -> tuple[dict[str, object], ...]:
    """Reject partial/torn history rather than using it as successful prior evidence."""
    path = run_root(workspace, run_id) / "events.jsonl"
    result = read_events(path)
    if result.diagnostics:
        raise AdapterError(
            "compound-evidence-incomplete",
            str(path),
            "Compound evidence is missing, torn or unreadable; retain inputs and inspect it.",
        )
    if not result.records:
        raise AdapterError(
            "compound-evidence-missing", str(path), "Compound evidence is unavailable."
        )
    for record in result.records:
        context = record.get("context")
        if (
            not isinstance(context, dict)
            or context.get("workspace_id") != workspace.definition.workspace_id
            or context.get("compound_run_id") != run_id
        ):
            raise ValidationError(
                "workspace-mismatch", str(path), "Run evidence has foreign context."
            )
    return result.records


def append_compound_event(
    workspace: Workspace,
    run_id: str,
    operation: str,
    *,
    context: Mapping[str, object],
    payload: Mapping[str, object],
    began: float | None = None,
) -> None:
    """Append durable lifecycle observations even when diagnostic receipts are disabled."""
    descriptor = persist_descriptor(workspace)
    record = common_event(
        workspace, dict(context), operation, 0 if began is None else (monotonic() - began) * 1000
    )
    record.update(payload)
    record["descriptor"] = str(descriptor.relative_to(workspace.receipts.directory))
    append_event(run_root(workspace, run_id) / "events.jsonl", record)


def disposition_view(disposition: SignalDisposition) -> dict[str, object]:
    """Keep owner candidates and unresolved reasons in the agent's durable report."""
    return {
        "signal_id": disposition.signal_id,
        "decision": disposition.decision.value,
        "rationale": disposition.rationale,
        "owners": [
            {key: value for key, value in asdict(owner).items() if value is not None}
            for owner in disposition.owners
        ],
        "owner_unavailable_reason": disposition.owner_unavailable_reason,
    }


def resolved_owners(
    workspace: Workspace, dispositions: tuple[SignalDisposition, ...]
) -> list[dict[str, object]]:
    """Label candidates independently from agent-declared publication assertions."""
    result: list[dict[str, object]] = []
    for disposition in dispositions:
        for owner in disposition.owners:
            record: dict[str, object] = {
                "signal_id": disposition.signal_id,
                "owner": asdict(owner),
                "status": "declared",
                "reason": "External source identity and publication are agent-reported.",
            }
            if owner.source is not None:
                source = next((item for item in workspace.sources if item.id == owner.source), None)
                if source is None:
                    record["status"] = "unresolved"
                    record["reason"] = "The owner source is not configured in this workspace."
                else:
                    try:
                        path = resolve_document_path(source.root, owner.path)
                        read_bytes(path, max_bytes=MAX_ARTIFACT_BYTES)
                        record.update(status="resolved", local_path=str(path), reason=None)
                    except (AdapterError, ValidationError) as error:
                        record["status"] = "unresolved"
                        if (
                            error.code == "file-missing"
                            and disposition.decision.value == "delete-retire"
                        ):
                            record.update(status="resolved-missing", local_path=str(path))
                        record["reason"] = error.message
            result.append(record)
    return result


def publication_view(
    publication: PublicationEvidence | None, *, verified: bool
) -> dict[str, object]:
    """Never upgrade caller-reported verification into independent proof."""
    return {
        **({} if publication is None else asdict(publication)),
        "verification": "agent-reported",
        "publication_verified": verified,
        **(
            {
                "status": "unavailable",
                "unavailable_reason": "Publication evidence was not supplied.",
            }
            if publication is None
            else {}
        ),
    }


def capture_changes(
    workspace: Workspace, run_id: str, attempt_id: str, publication: PublicationEvidence | None
) -> dict[str, object]:
    """Capture only a bounded local diff between explicitly supplied immutable commits."""
    unavailable: dict[str, object] = {
        "status": "unavailable",
        "reason": "Exact checkout and before/after commit IDs were not supplied.",
    }
    if publication is None:
        return unavailable
    before, after, checkout = (
        publication.before_revision,
        publication.after_revision,
        publication.checkout,
    )
    if before is None or after is None or checkout is None:
        return unavailable
    boundaries: dict[str, object] = {
        "before_revision": before,
        "after_revision": after,
        "checkout": checkout,
    }
    if (
        not _COMMIT.fullmatch(before)
        or not _COMMIT.fullmatch(after)
        or not Path(checkout).is_absolute()
    ):
        return {
            **boundaries,
            "status": "unavailable",
            "reason": "Require absolute checkout and full commit hashes.",
        }
    try:
        with open_directory(Path(checkout)):
            pass
        environment = {
            "PATH": os.defpath,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
        command = ["git", "--no-pager", "-c", "core.hooksPath=" + os.devnull, "-C", checkout]
        for revision in (before, after):
            subprocess.run(
                [*command, "cat-file", "-e", revision + "^{commit}"],
                check=True,
                capture_output=True,
                timeout=10,
                env=environment,
            )
        with tempfile.TemporaryFile() as output:
            subprocess.run(
                [
                    *command,
                    "diff",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--no-renames",
                    before,
                    after,
                    "--",
                ],
                check=True,
                stdout=output,
                stderr=subprocess.PIPE,
                timeout=20,
                env=environment,
            )
            if output.tell() > MAX_ARTIFACT_BYTES:
                return {
                    **boundaries,
                    "status": "unavailable",
                    "reason": "Declared diff exceeds artifact size limit.",
                }
            output.seek(0)
            raw = output.read(MAX_ARTIFACT_BYTES + 1)
        relative = "changes/" + attempt_id + ".patch"
        write_artifact(run_root(workspace, run_id) / relative, raw)
        return {
            **boundaries,
            "status": "captured",
            "path": relative,
            "fingerprint": "sha256:" + hashlib.sha256(raw).hexdigest(),
        }
    except (OSError, subprocess.SubprocessError, AdapterError) as error:
        return {
            **boundaries,
            "status": "unavailable",
            "reason": "Declared Git evidence could not be read safely.",
            "error_type": type(error).__name__,
        }
