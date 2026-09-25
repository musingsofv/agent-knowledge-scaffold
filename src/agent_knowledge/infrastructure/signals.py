"""Capture complete immutable signal files and inventory explicitly selected buckets.

The caller validates authored bytes and durable origin before capture. This adapter
does not parse claims, infer origins, manage Git, or drain signals. Files become
visible as ``.md`` only after their complete bytes have been written and synced.
Directory descriptors reject internal symlink traversal. Rechecks detect concurrent
replacement but do not lock other filesystem writers; uncertain published files
are always retained for inspection.
"""

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agent_knowledge.domain.validation import ValidationError, read_relative_path

from .configuration import SignalStorage, Workspace, validate_signal_storage
from .errors import AdapterError
from .filesystem import _identity, _io_error, open_directory


@dataclass(frozen=True, slots=True)
class SignalInventory:
    """Bind a sorted direct-file listing to directory presence and file identities."""

    files: tuple[Path, ...]
    fingerprint: str


def capture_signal(workspace: Workspace, project_path: str | None, data: bytes) -> Path:
    """Publish exact prevalidated bytes under a unique name, never overwriting files."""
    storage = _storage(workspace)
    bucket = signal_bucket(storage, project_path)
    completed: Path | None = None
    try:
        with _open_bucket(storage, bucket, create=True) as (directory, _):
            assert directory is not None
            completed = _publish(workspace, bucket, directory, data)
        return completed
    except (OSError, AdapterError, ValidationError) as error:
        if completed is not None:
            raise _uncertain(completed) from error
        if isinstance(error, OSError):
            raise _io_error(error, bucket, directory=True) from error
        raise


def inventory_signals(
    workspace: Workspace, project_path: str | None, *, include_shared: bool = False
) -> SignalInventory:
    """List exact project/shared buckets read-only, rejecting incomplete discovery.

    Nested project directories are never traversed. Markdown bodies are left for
    the caller's shared codec/schema validation; standalone YAML is a visible
    unsupported-format error. Two stat passes detect changes during enumeration;
    callers also compare fresh inventories after loading the selected files.
    """
    storage = _storage(workspace)
    buckets = [signal_bucket(storage, project_path)]
    if include_shared and project_path is not None:
        buckets.append(signal_bucket(storage, None))
    first = _inventory(storage, tuple(sorted(buckets)))
    if first != _inventory(storage, tuple(sorted(buckets))):
        raise _changed(storage.signal_root)
    validate_signal_storage(workspace)
    return first


def _storage(workspace: Workspace) -> SignalStorage:
    storage = validate_signal_storage(workspace)
    if storage is None:
        raise ValidationError(
            "signal-storage-required",
            "workspace.signal_storage",
            "Configure durable signal storage.",
        )
    return storage


def signal_bucket(storage: SignalStorage, project_path: str | None) -> Path:
    """Return the exact direct signal bucket for one durable project origin."""
    if project_path is None:
        return storage.signal_root / "shared"
    return storage.signal_root / "projects" / read_relative_path(project_path, "project_path")


@contextmanager
def _open_bucket(
    storage: SignalStorage, bucket: Path, *, create: bool
) -> Iterator[tuple[int | None, tuple[str, ...]]]:
    """Walk one bucket from its existing scaffold, optionally creating inbox parents."""
    with open_directory(storage.scaffold_root) as root:
        root_identity = _identity(os.fstat(root))[:2]
        descriptor = os.dup(root)
        parts = [str(storage.scaffold_root), repr(_identity(os.fstat(root)))]
        current = storage.scaffold_root
        try:
            for part in bucket.relative_to(storage.scaffold_root).parts:
                current /= part
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=descriptor)
                        os.fsync(descriptor)
                    except FileExistsError:
                        pass
                try:
                    child = os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    if create:
                        raise
                    parts.extend((str(current), "missing"))
                    _check_root(storage, root_identity)
                    yield None, tuple(parts)
                    return
                try:
                    opened = os.fstat(child)
                    named = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                    if _identity(opened)[:2] != _identity(named)[:2]:
                        raise _changed(current)
                except BaseException:
                    os.close(child)
                    raise
                os.close(descriptor)
                descriptor = child
                parts.extend((str(current), repr(_identity(opened))))
            _check_root(storage, root_identity)
            yield descriptor, tuple(parts)
            _check_root(storage, root_identity)
        except OSError as error:
            raise _io_error(error, current, directory=True) from error
        finally:
            os.close(descriptor)


def _check_root(storage: SignalStorage, expected: tuple[int, int]) -> None:
    with open_directory(storage.scaffold_root) as current:
        if _identity(os.fstat(current))[:2] != expected:
            raise _changed(storage.scaffold_root)


def _check_destination(workspace: Workspace, bucket: Path, directory: int) -> None:
    validate_signal_storage(workspace)
    with open_directory(bucket) as current:
        if _identity(os.fstat(current))[:2] != _identity(os.fstat(directory))[:2]:
            raise _changed(bucket)


def _new_name() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex + ".md"


def _publish(workspace: Workspace, bucket: Path, directory: int, data: bytes) -> Path:
    name = _new_name()
    path = bucket / name
    temporary = ".capture-" + uuid4().hex + ".tmp"
    descriptor = -1
    owned: tuple[int, int] | None = None
    published = False
    try:
        _check_destination(workspace, bucket, directory)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=directory,
        )
        owned = _identity(os.fstat(descriptor))[:2]
        remaining = memoryview(data)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("Cannot complete signal write.")
            remaining = remaining[written:]
        os.fsync(descriptor)
        expected = _identity(os.fstat(descriptor))
        closing, descriptor = descriptor, -1
        os.close(closing)
        _check_destination(workspace, bucket, directory)
        if expected != _identity(os.stat(temporary, dir_fd=directory, follow_symlinks=False)):
            raise _changed(bucket / temporary)
        try:
            os.link(
                temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False
            )
        except FileExistsError as error:
            raise AdapterError(
                "signal-collision", str(path), "Signal name already exists; existing file retained."
            ) from error
        published = True
        # Linking changes ctime; identity, size and mtime must still match the
        # complete synced temporary file. A concurrent edit is an uncertain result.
        if expected[:4] != _identity(os.stat(name, dir_fd=directory, follow_symlinks=False))[:4]:
            raise _changed(path)
        _clean_temporary(directory, temporary, owned, bucket)
        owned = None
        os.fsync(directory)
        _check_destination(workspace, bucket, directory)
        return path
    except (OSError, AdapterError, ValidationError) as error:
        if published:
            raise _uncertain(path) from error
        if isinstance(error, OSError):
            raise AdapterError(
                "signal-write-failed", str(path), "Could not publish the signal."
            ) from error
        raise
    finally:
        try:
            if descriptor >= 0:
                os.close(descriptor)
        finally:
            if owned is not None:
                try:
                    _clean_temporary(directory, temporary, owned, bucket)
                except AdapterError as error:
                    if published:
                        raise _uncertain(path) from error
                    raise


def _clean_temporary(directory: int, name: str, owned: tuple[int, int], bucket: Path) -> None:
    """Remove only this invocation's temporary inode; preserve every replacement."""
    try:
        current = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if stat.S_ISREG(current.st_mode) and _identity(current)[:2] == owned:
            os.unlink(name, dir_fd=directory)
    except FileNotFoundError:
        pass
    except OSError as error:
        raise AdapterError(
            "signal-cleanup-failed", str(bucket / name), "Could not clean the owned temporary file."
        ) from error


def _inventory(storage: SignalStorage, buckets: tuple[Path, ...]) -> SignalInventory:
    files: list[Path] = []
    parts: list[str] = []
    for bucket in buckets:
        with _open_bucket(storage, bucket, create=False) as (directory, ancestors):
            parts.extend((str(bucket), *ancestors))
            if directory is None:
                continue
            try:
                before = _identity(os.fstat(directory))
                if not os.access(".", os.R_OK | os.X_OK, dir_fd=directory):
                    raise AdapterError("directory-unreadable", str(bucket), "Cannot list signals.")
                for name in sorted(os.listdir(directory)):
                    path = bucket / name
                    item = os.stat(name, dir_fd=directory, follow_symlinks=False)
                    if stat.S_ISLNK(item.st_mode):
                        raise AdapterError(
                            "unsafe-path", str(path), "Signal buckets cannot contain symlinks.", 2
                        )
                    if stat.S_ISDIR(item.st_mode):
                        continue
                    if name.endswith((".yaml", ".yml")):
                        raise ValidationError(
                            "unsupported-signal-format",
                            str(path),
                            "Signals must use Markdown with frontmatter.",
                        )
                    if not name.endswith(".md"):
                        continue
                    if not stat.S_ISREG(item.st_mode):
                        raise AdapterError(
                            "not-regular-file", str(path), "Expected a regular signal file.", 2
                        )
                    if not os.access(name, os.R_OK, dir_fd=directory, follow_symlinks=False):
                        raise AdapterError("file-unreadable", str(path), "Cannot read this signal.")
                    files.append(path)
                    parts.extend((str(path), repr(_identity(item))))
                if before != _identity(os.fstat(directory)):
                    raise _changed(bucket)
                with open_directory(bucket) as current:
                    if before != _identity(os.fstat(current)):
                        raise _changed(bucket)
            except OSError as error:
                raise _io_error(error, bucket, directory=True) from error
    digest = hashlib.sha256()
    for part in parts:
        value = part.encode()
        digest.update(len(value).to_bytes(8, "big") + value)
    return SignalInventory(tuple(sorted(files)), "sha256:" + digest.hexdigest())


def _changed(path: Path) -> AdapterError:
    return AdapterError(
        "signals-changed",
        str(path),
        "Signal storage changed during access; retry from a fresh listing.",
    )


def _uncertain(path: Path) -> AdapterError:
    return AdapterError(
        "signal-publication-uncertain",
        str(path),
        "Publication could not be confirmed durable and unchanged; retain and inspect the "
        "completed signal and any temporary file before retrying.",
    )
