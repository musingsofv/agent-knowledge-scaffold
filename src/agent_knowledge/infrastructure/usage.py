"""Persist local usage evidence with serialized, guarded and durable file access."""

import fcntl
import hashlib
import json
import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent_knowledge.domain.usage import read_utc_timestamp
from agent_knowledge.domain.validation import ValidationError

from .errors import AdapterError
from .filesystem import open_directory, read_bytes

MAX_EVENT_BYTES = 16 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UsageDiagnostic:
    """Identify incomplete evidence without echoing malformed source contents."""

    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class EventRead:
    """Preserve valid complete records while reporting unavailable or partial evidence."""

    records: tuple[dict[str, object], ...]
    diagnostics: tuple[UsageDiagnostic, ...]


def canonical_json(value: object) -> bytes:
    """Define stable UTF-8 bytes for payload measurements, artifacts and checksums."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def ensure_directory(path: Path, *, exclusive: bool = False) -> None:
    """Create only real directories, rejecting symlinks and existing export targets."""
    absolute = path.absolute()
    if ".." in absolute.parts:
        raise AdapterError("unsafe-usage-path", str(path), "Usage paths cannot traverse parents.")
    if exclusive and len(absolute.parts) == 1:
        raise AdapterError(
            "usage-destination-exists", str(path), "Export requires a new directory."
        )
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for index, part in enumerate(absolute.parts[1:], start=1):
            try:
                os.mkdir(part, 0o700, dir_fd=descriptor)
                os.fsync(descriptor)
            except FileExistsError:
                if exclusive and index == len(absolute.parts) - 1:
                    raise AdapterError(
                        "usage-destination-exists", str(path), "Export requires a new directory."
                    ) from None
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        raise AdapterError(
            "usage-directory-unavailable", str(path), "Cannot safely create the usage directory."
        ) from error
    finally:
        os.close(descriptor)


@contextmanager
def usage_lock(path: Path) -> Iterator[None]:
    """Serialize a lifecycle through a persistent no-follow lock file."""
    ensure_directory(path.parent)
    try:
        with open_directory(path.parent) as directory:
            descriptor = os.open(
                path.name,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                0o600,
                dir_fd=directory,
            )
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                opened = os.fstat(descriptor)
                current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
                ):
                    raise AdapterError(
                        "unsafe-usage-lock", str(path), "Cannot trust the usage lock."
                    )
                yield
            finally:
                os.close(descriptor)
    except OSError as error:
        raise AdapterError(
            "usage-lock-failed", str(path), "Cannot acquire the usage lock."
        ) from error


@contextmanager
def _locked_file(path: Path, *, writing: bool) -> Iterator[int]:
    if writing:
        ensure_directory(path.parent)
    else:
        with open_directory(path.parent):
            pass
    try:
        with (
            usage_lock(path.with_name(f".{path.name}.lock")),
            open_directory(path.parent) as directory,
        ):
            flags = os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            flags |= os.O_RDWR | os.O_CREAT | os.O_APPEND if writing else os.O_RDONLY
            descriptor = os.open(path.name, flags, 0o600, dir_fd=directory)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX if writing else fcntl.LOCK_SH)
                opened = os.fstat(descriptor)
                current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
                ):
                    raise AdapterError(
                        "unsafe-usage-file",
                        str(path),
                        "Usage files must be unaliased regular files.",
                    )
                yield descriptor
                if writing:
                    os.fsync(directory)
            finally:
                os.close(descriptor)
    except OSError as error:
        raise AdapterError(
            "usage-file-unavailable", str(path), "Cannot safely access the usage evidence file."
        ) from error


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError("non-finite JSON number")


def _decode(data: bytes) -> dict[str, object]:
    value: object = json.loads(data, object_pairs_hook=_object, parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("event must be an object")
    return value


def append_event(path: Path, event: dict[str, object]) -> None:
    """Append one complete JSONL event under a lock; never extend a torn final record."""
    data = canonical_json(event) + b"\n"
    if len(data) > MAX_EVENT_BYTES:
        raise AdapterError(
            "usage-event-too-large", str(path), "Usage event exceeds the size limit."
        )
    with _locked_file(path, writing=True) as descriptor:
        size = os.fstat(descriptor).st_size
        if size:
            tail = os.pread(
                descriptor, min(size, MAX_EVENT_BYTES + 1), max(0, size - MAX_EVENT_BYTES - 1)
            )
            final = tail[:-1].rsplit(b"\n", 1)[-1] if tail.endswith(b"\n") else b""
            try:
                if not final or len(final) >= MAX_EVENT_BYTES:
                    raise ValueError("incomplete final record")
                _decode(final)
            except (ValueError, UnicodeError) as error:
                raise AdapterError(
                    "usage-torn-record",
                    str(path),
                    "The final usage record is incomplete or malformed; preserve it for review.",
                ) from error
        _write_all(descriptor, data)
        os.fsync(descriptor)


def read_events(path: Path) -> EventRead:
    """Read locked JSONL records, excluding malformed/torn entries with explicit diagnostics."""
    records: list[dict[str, object]] = []
    diagnostics: list[UsageDiagnostic] = []
    try:
        with _locked_file(path, writing=False) as descriptor:
            loaded = _read_descriptor(descriptor, path)
            records.extend(loaded.records)
            diagnostics.extend(loaded.diagnostics)
    except AdapterError as error:
        diagnostics.append(UsageDiagnostic(error.code, error.path, error.message))
    return EventRead(tuple(records), tuple(diagnostics))


def _read_descriptor(descriptor: int, path: Path) -> EventRead:
    records: list[dict[str, object]] = []
    diagnostics: list[UsageDiagnostic] = []
    os.lseek(descriptor, 0, os.SEEK_SET)
    with os.fdopen(os.dup(descriptor), "rb") as stream:
        line = 0
        while data := stream.readline(MAX_EVENT_BYTES + 1):
            line += 1
            location = f"{path}:{line}"
            if len(data) > MAX_EVENT_BYTES:
                while data and not data.endswith(b"\n"):
                    data = stream.readline(MAX_EVENT_BYTES + 1)
                diagnostics.append(
                    UsageDiagnostic(
                        "usage-event-too-large", location, "Oversized event was not interpreted."
                    )
                )
                continue
            if not data.endswith(b"\n"):
                diagnostics.append(
                    UsageDiagnostic(
                        "usage-torn-record", location, "Incomplete final event was not interpreted."
                    )
                )
                continue
            try:
                records.append(_decode(data))
            except (ValueError, UnicodeError):
                diagnostics.append(
                    UsageDiagnostic(
                        "usage-invalid-record", location, "Malformed event was not interpreted."
                    )
                )
    return EventRead(tuple(records), tuple(diagnostics))


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        count = os.write(descriptor, remaining)
        if count <= 0:
            raise OSError("write made no progress")
        remaining = remaining[count:]


def write_artifact(path: Path, data: bytes) -> None:
    """Publish immutable bytes atomically and exclusively; identical retries are harmless."""
    ensure_directory(path.parent)
    temporary = f".usage-{uuid.uuid4().hex}.tmp"
    try:
        with open_directory(path.parent) as directory:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=directory,
            )
            try:
                _write_all(descriptor, data)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            try:
                try:
                    os.link(
                        temporary,
                        path.name,
                        src_dir_fd=directory,
                        dst_dir_fd=directory,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    existing = read_bytes(path, max_bytes=max(len(data), 1))
                    if existing != data:
                        raise AdapterError(
                            "usage-artifact-collision",
                            str(path),
                            "Immutable evidence already exists with different bytes.",
                        ) from None
                os.fsync(directory)
            finally:
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
    except OSError as error:
        raise AdapterError(
            "usage-artifact-write-failed", str(path), "Cannot durably publish usage evidence."
        ) from error


def checksum(data: bytes) -> str:
    """Identify exact artifact bytes without claiming historical body reconstruction."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _event_workspace(event: dict[str, object]) -> object:
    context = event.get("context")
    return context.get("workspace_id") if isinstance(context, dict) else None


def _event_time(event: dict[str, object]) -> datetime | None:
    try:
        return read_utc_timestamp(event.get("recorded_at"), "recorded_at")
    except ValidationError:
        return None


def prune_retrieval(
    path: Path,
    *,
    workspace_id: str,
    cutoff: datetime,
    expired_run_ids: frozenset[str] = frozenset(),
) -> int:
    """Atomically retire only known, old, uncorrelated records for the selected workspace."""
    with _locked_file(path, writing=True) as descriptor:
        loaded = _read_descriptor(descriptor, path)
        if loaded.diagnostics:
            return 0
        retained: list[dict[str, object]] = []
        for event in loaded.records:
            context = event.get("context")
            timestamp = _event_time(event)
            if not (
                event.get("schema_version") == "knowledge-retrieval-receipt.v1"
                and _event_workspace(event) == workspace_id
                and timestamp is not None
                and timestamp < cutoff
                and isinstance(context, dict)
                and (
                    context.get("compound_run_id") is None
                    or context.get("compound_run_id") in expired_run_ids
                )
            ):
                retained.append(event)
        removed = len(loaded.records) - len(retained)
        if removed:
            data = b"".join(canonical_json(event) + b"\n" for event in retained)
            # A persistent sidecar lock keeps appenders off the old inode during replacement.
            with open_directory(path.parent) as directory:
                temporary = f".usage-{uuid.uuid4().hex}.tmp"
                new_descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=directory,
                )
                try:
                    _write_all(new_descriptor, data)
                    os.fsync(new_descriptor)
                finally:
                    os.close(new_descriptor)
                os.rename(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
                os.fsync(directory)
        return removed


def prune_compound(run: Path, *, workspace_id: str, cutoff: datetime, activity_lock: Path) -> bool:
    """Expire a fully resolved completed run under its lifecycle lock; keep unknown evidence."""
    with usage_lock(activity_lock), _locked_file(run / "events.jsonl", writing=True) as descriptor:
        loaded = _read_descriptor(descriptor, run / "events.jsonl")
        if loaded.diagnostics or not loaded.records:
            return False
        if any(
            _event_workspace(event) != workspace_id
            or event.get("schema_version") != "knowledge-compound-receipt.v1"
            or _event_time(event) is None
            for event in loaded.records
        ):
            return False
        finish = loaded.records[-1]
        result = finish.get("tool_result")
        completed = _event_time(finish)
        if not (
            finish.get("operation") == "compound.finish"
            and isinstance(result, dict)
            and result.get("unresolved") is False
            and completed is not None
            and completed < cutoff
        ):
            return False
        candidates: list[tuple[Path, tuple[int, int, int, int]]] = []
        try:
            with open_directory(run) as directory:
                for name in os.listdir(directory):
                    if name.startswith(".") and name.endswith(".lock"):
                        continue
                    if name in {"inputs", "changes"}:
                        with open_directory(run / name) as inputs:
                            for item in os.listdir(inputs):
                                extension = ".md" if name == "inputs" else ".patch"
                                if not item.endswith(extension):
                                    return False
                                metadata = os.stat(item, dir_fd=inputs, follow_symlinks=False)
                                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                                    return False
                                candidates.append(
                                    (run / name / item, _retention_identity(metadata))
                                )
                    elif name in {
                        "start.json",
                        "events.jsonl",
                        "changes.patch",
                    } or name.endswith(".patch"):
                        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
                        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                            return False
                        candidates.append((run / name, _retention_identity(metadata)))
                    else:
                        return False
            marker = {
                "schema_version": "knowledge-usage-expiry.v1",
                "workspace_id": workspace_id,
                "compound_run_id": run.name,
                "completed_at": finish["recorded_at"],
                "expired_before": cutoff.isoformat().replace("+00:00", "Z"),
            }
            # Durable tombstone makes deliberately expired artifacts distinguishable.
            write_artifact(run / "expired.json", canonical_json(marker) + b"\n")
            for path, identity in candidates:
                with open_directory(path.parent) as directory:
                    current = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
                    if _retention_identity(current) != identity:
                        raise AdapterError(
                            "usage-retention-changed",
                            str(path),
                            "Evidence changed; remaining files were preserved.",
                        )
                    os.unlink(path.name, dir_fd=directory)
                    os.fsync(directory)
            return True
        except OSError as error:
            raise AdapterError(
                "usage-retention-failed",
                str(run),
                "Retention stopped; remaining evidence was preserved.",
            ) from error


def _retention_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns
