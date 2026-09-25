"""Provide bounded local reads and pinned, no-follow directory access."""

import errno
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from agent_knowledge.domain.validation import ValidationError, read_relative_path

from .errors import AdapterError


def resolve_path(value: str, *, base: Path) -> Path:
    """Resolve an explicitly named path, including symlink aliases, against its config.

    No shell-variable or home expansion is performed. Callers validate syntax before
    resolution. Nonexistent suffixes remain resolved paths so containment does not
    depend on availability. Subsequent guarded access rejects new symlink traversal.
    """
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        return candidate.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise AdapterError(
            "path-resolution-failed", str(candidate), "Cannot resolve the configured local path."
        ) from error


@contextmanager
def open_directory(path: Path) -> Iterator[int]:
    """Pin an absolute directory through no-follow component opens; never create it.

    Explicitly configured aliases must first pass through resolve_path. Traversal
    rejects symlinks introduced after resolution and checks each opened identity.
    The yielded descriptor stays bound to the opened directory until context exit.
    It does not prevent another process from renaming a trusted ancestor.
    """
    absolute = path.absolute()
    descriptor = -1
    try:
        descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for part in absolute.parts[1:]:
            next_descriptor = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor
            )
            try:
                opened = os.fstat(next_descriptor)
                current = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISDIR(current.st_mode) or (opened.st_dev, opened.st_ino) != (
                    current.st_dev,
                    current.st_ino,
                ):
                    raise AdapterError(
                        "path-changed", str(absolute), "Directory identity changed during access."
                    )
            except BaseException:
                os.close(next_descriptor)
                raise
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        raise _io_error(error, absolute, directory=True) from error
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def check_directory(path: Path) -> None:
    """Verify directory access without enumerating or opening knowledge documents."""
    with open_directory(path) as descriptor:
        if not os.access(".", os.R_OK | os.X_OK, dir_fd=descriptor):
            raise AdapterError(
                "directory-unreadable",
                str(path),
                "Directory is not readable and searchable by this process.",
            )


def read_bytes(path: Path, *, max_bytes: int) -> bytes:
    """Read exact bounded bytes from one regular file, rejecting links and replacement."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    absolute = path.absolute()
    try:
        with open_directory(absolute.parent) as directory:
            descriptor = os.open(
                absolute.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=directory,
            )
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode):
                    raise AdapterError(
                        "not-regular-file", str(absolute), "Expected a regular file.", exit_code=2
                    )
                if before.st_size > max_bytes:
                    raise AdapterError(
                        "file-too-large",
                        str(absolute),
                        f"File exceeds the {max_bytes}-byte limit.",
                        exit_code=2,
                    )
                chunks: list[bytes] = []
                remaining = max_bytes + 1
                while remaining:
                    chunk = os.read(descriptor, min(65536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                data = b"".join(chunks)
                if len(data) > max_bytes:
                    raise AdapterError(
                        "file-too-large",
                        str(absolute),
                        f"File exceeds the {max_bytes}-byte limit.",
                        exit_code=2,
                    )
                after = os.fstat(descriptor)
                current = os.stat(absolute.name, dir_fd=directory, follow_symlinks=False)
                if (
                    not stat.S_ISREG(current.st_mode)
                    or _identity(before) != _identity(after)
                    or _identity(after) != _identity(current)
                ):
                    raise AdapterError(
                        "file-changed",
                        str(absolute),
                        "File changed while being read; retry from a fresh snapshot.",
                    )
                return data
            finally:
                os.close(descriptor)
    except OSError as error:
        raise _io_error(error, absolute, directory=False) from error


def resolve_document_path(root: Path, relative: str) -> Path:
    """Resolve a source-relative document without accepting any internal symlink.

    This is a location check, not a read: missing files remain resolvable so callers
    can label missing references. Guarded reads must still recheck the opened file.
    """
    relative = read_relative_path(relative, "document.path")
    candidate = root / relative
    current = root
    try:
        for part in ("", *relative.split("/")):
            if part:
                current /= part
            if current.is_symlink():
                raise ValidationError(
                    "unsafe-document-path",
                    str(candidate),
                    "Knowledge document paths cannot traverse symlinks.",
                )
        if not candidate.resolve(strict=False).is_relative_to(root.resolve(strict=False)):
            raise ValidationError(
                "unsafe-document-path",
                str(candidate),
                "Document escapes its configured source root.",
            )
    except (OSError, RuntimeError) as error:
        raise AdapterError(
            "path-resolution-failed", str(candidate), "Cannot resolve the document path."
        ) from error
    return candidate


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _io_error(error: OSError, path: Path, *, directory: bool) -> AdapterError:
    noun = "directory" if directory else "file"
    if error.errno == errno.ENOENT:
        return AdapterError(
            f"{noun}-missing", str(path), f"Configured {noun} does not exist.", exit_code=2
        )
    if error.errno in {errno.ELOOP, errno.ENOTDIR}:
        return AdapterError(
            "unsafe-path",
            str(path),
            "Path contains a symlink or a non-directory component.",
            exit_code=2,
        )
    if error.errno in {errno.EACCES, errno.EPERM}:
        return AdapterError(
            f"{noun}-unreadable", str(path), f"This process cannot access the configured {noun}."
        )
    return AdapterError(f"{noun}-io-failed", str(path), f"Cannot access the configured {noun}.")
