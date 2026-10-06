"""Prepare reviewed container-local profiles and explicitly owned private copies.

Projection provenance contains paths and file identities, never credential values
or digests. It is unrelated to knowledge/compounding coordination. A failed refresh
removes the owned launch target; callers must also stop on the non-success result.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import yaml
from yaml.tokens import ScalarToken

from agent_knowledge.domain.profiles import Profile, parse_profiles, profile_name, select_profile
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import resolve_workspace
from agent_knowledge.infrastructure.documents import load_mapping
from agent_knowledge.infrastructure.environment import (
    ENVIRONMENT_MAX_BYTES,
    inspect_pending_environment,
    parse_pending_dotenv_names,
)
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import open_directory, read_bytes
from agent_knowledge.infrastructure.profiles import ResolvedProfileEnvironment, replace_registry
from agent_knowledge.infrastructure.usage import usage_lock

_MAX_REGISTRY = 1_048_576
_SCHEMA = "container-profile-projection.v1"


@dataclass(frozen=True)
class _Projection:
    schema: str
    settings: str
    profile: str
    source: str
    target_identity: tuple[int, ...] | None = None
    temporary: str | None = None
    temporary_identity: tuple[int, ...] | None = None


def _error(code: str, path: Path, message: str) -> AdapterError:
    return AdapterError(code, str(path), message, exit_code=2)


def _absolute(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise _error(
            "container-profile-path", path, "Use an absolute path without parent traversal."
        )
    return path


def _current(path: Path, expected: str | None) -> bytes | None:
    try:
        data = read_bytes(path, max_bytes=_MAX_REGISTRY)
    except AdapterError as error:
        if error.code != "file-missing":
            raise
        data = None
    actual = hashlib.sha256(data).hexdigest() if data is not None else None
    if actual != expected:
        raise _error(
            "registry-changed", path, "Reinspect the registry before preparing this profile."
        )
    return data


def _comments(data: bytes) -> Counter[str]:
    text = data.decode("utf-8")
    scalars = bytearray(len(text))
    for token in yaml.scan(text):
        if isinstance(token, ScalarToken):
            begin, end = token.start_mark.index, token.end_mark.index
            scalars[begin:end] = b"\1" * (end - begin)
    result: Counter[str] = Counter()
    offset = 0
    for line in text.splitlines(keepends=True):
        for index, character in enumerate(line):
            if character == "#" and not scalars[offset + index]:
                result[line[index:].rstrip("\r\n")] += 1
                break
        offset += len(line)
    return result


def _checked_candidate(
    settings: Path, candidate: bytes, current: bytes | None, profile: str, operation: str
) -> Profile | None:
    proposed = parse_profiles(load_mapping(candidate, path=str(settings), max_bytes=_MAX_REGISTRY))
    if current is not None:
        existing = parse_profiles(load_mapping(current, path=str(settings)))
        others = {item.name: item for item in proposed.profiles}
        if proposed.default_profile != existing.default_profile or any(
            others.get(item.name) != item for item in existing.profiles if item.name != profile
        ):
            raise _error(
                "unrelated-profile-change",
                settings,
                "Preserve existing defaults and unrelated profiles in the reviewed candidate.",
            )
        if _comments(current) - _comments(candidate):
            raise _error(
                "registry-comments-changed", settings, "Preserve existing registry comments."
            )
        if operation == "refresh" and select_profile(existing, profile) != select_profile(
            proposed, profile
        ):
            raise _error(
                "projection-prepare-required",
                settings,
                "Changed profile declarations require prepare and a new harness session.",
            )
    selected = next((item for item in proposed.profiles if item.name == profile), None)
    if selected is None and operation != "remove":
        select_profile(proposed, profile)
    return selected


def _new_file(directory: int, name: str, data: bytes) -> os.stat_result:
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory,
    )
    try:
        os.fchmod(descriptor, 0o600)
        value = os.fstat(descriptor)
        if value.st_uid != os.getuid() or stat.S_IMODE(value.st_mode) != 0o600:
            raise _error(
                "projection-file-unsafe",
                Path(name),
                "Private-file permissions were not established.",
            )
        _write_all(descriptor, data)
        os.fsync(descriptor)
        return os.fstat(descriptor)
    finally:
        os.close(descriptor)


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        count = os.write(descriptor, view)
        if count <= 0:
            raise OSError("Incomplete private-file write")
        view = view[count:]


def _candidate_environment(
    settings: Path, candidate: bytes, profile: str, private: Path | None
) -> ResolvedProfileEnvironment | None:
    """Validate all selected effective paths using the registry's final relative base."""
    name = f".container-profile-candidate-{uuid.uuid4().hex}.yaml"
    with open_directory(settings.parent) as directory:
        created = _new_file(directory, name, candidate)
        try:
            workspace = resolve_workspace(settings=settings.parent / name, profile=profile)
            # Catalog/config validation above and source access here never scan bodies.
            for source in workspace.sources:
                if private is not None and private.is_relative_to(source.root):
                    raise _error(
                        "projection-in-knowledge",
                        private,
                        "Private projections must be outside canonical knowledge sources.",
                    )
                with open_directory(source.root):
                    pass
            return workspace.environment
        finally:
            _unlink_identity(directory, name, _identity(created)[:2])


def _identity(value: os.stat_result) -> tuple[int, ...]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _private_stat(directory: int, name: str) -> os.stat_result | None:
    try:
        value = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.getuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or value.st_nlink != 1
    ):
        raise _error(
            "projection-file-unsafe", Path(name), "Owned files must be private regular files."
        )
    return value


def _unlink_identity(directory: int, name: str, identity: tuple[int, ...]) -> None:
    try:
        value = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(value.st_mode) or _identity(value)[: len(identity)] != identity:
        raise _error(
            "projection-file-changed", Path(name), "Preserve the replaced or changed file."
        )
    os.unlink(name, dir_fd=directory)
    os.fsync(directory)


def _private_directory(path: Path, *, create: bool) -> None:
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            raise _error(
                "projection-in-repository", path, "Private projections must be outside Git."
            )
    with open_directory(path.parent) as parent:
        if create:
            try:
                os.mkdir(path.name, 0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
    with open_directory(path) as directory:
        value = os.fstat(directory)
        if value.st_uid != os.getuid() or stat.S_IMODE(value.st_mode) != 0o700:
            raise _error(
                "projection-directory-unsafe", path, "Use a current-user-owned 0700 directory."
            )


def _read_projection(path: Path, directory: int) -> _Projection | None:
    if _private_stat(directory, path.name) is None:
        return None
    value = load_mapping(read_bytes(path, max_bytes=16_384), path=str(path), max_bytes=16_384)
    fields = {
        "schema",
        "settings",
        "profile",
        "source",
        "target_identity",
        "temporary",
        "temporary_identity",
    }
    if (
        set(value) != fields
        or value["schema"] != _SCHEMA
        or any(not isinstance(value[key], str) for key in ("settings", "profile", "source"))
    ):
        raise _error("projection-provenance-invalid", path, "Cannot trust projection provenance.")
    identities: list[tuple[int, ...] | None] = []
    for key, length in (("target_identity", 5), ("temporary_identity", 2)):
        raw = value[key]
        if raw is not None and (
            not isinstance(raw, list)
            or len(raw) != length
            or any(type(item) is not int for item in raw)
        ):
            raise _error("projection-provenance-invalid", path, "Invalid owned file identity.")
        identities.append(tuple(raw) if isinstance(raw, list) else None)
    temporary = value["temporary"]
    prefix = f".{value['profile']}.projection-"
    if temporary is not None and (
        not isinstance(temporary, str)
        or not temporary.startswith(prefix)
        or not temporary.endswith(".tmp")
        or Path(temporary).name != temporary
    ):
        raise _error("projection-provenance-invalid", path, "Invalid owned temporary path.")
    if (temporary is None) != (identities[1] is None):
        raise _error("projection-provenance-invalid", path, "Incomplete temporary ownership.")
    return _Projection(
        _SCHEMA,
        str(value["settings"]),
        str(value["profile"]),
        str(value["source"]),
        identities[0],
        temporary,
        identities[1],
    )


def _save_projection(path: Path, directory: int, state: _Projection) -> None:
    _private_stat(directory, path.name)
    name = f".{state.profile}.provenance-{uuid.uuid4().hex}.tmp"
    created = _new_file(directory, name, json.dumps(asdict(state), sort_keys=True).encode() + b"\n")
    try:
        os.replace(name, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        _unlink_identity(directory, name, _identity(created)[:2])


def _invalidate(directory: int, target: str, state: _Projection) -> None:
    """Recover our interrupted files, never unlink a replacement owned by another writer."""
    if state.target_identity is not None:
        _unlink_identity(directory, target, state.target_identity)
    elif state.temporary_identity is not None:
        # A crash after publication but before final provenance can leave both links.
        _unlink_identity(directory, target, state.temporary_identity)
    elif _private_stat(directory, target) is not None:
        raise _error("projection-unowned-target", Path(target), "The target is not setup-owned.")
    if state.temporary is not None and state.temporary_identity is not None:
        _unlink_identity(directory, state.temporary, state.temporary_identity)


def _check_owned(directory: int, target: str, state: _Projection) -> None:
    """Refuse replaced ownership before a removal edits the registry."""
    for name, identity in (
        (target, state.target_identity or state.temporary_identity),
        (state.temporary, state.temporary_identity),
    ):
        if name is None:
            continue
        value = _private_stat(directory, name)
        if value is not None and (
            identity is None or _identity(value)[: len(identity)] != identity
        ):
            raise _error("projection-file-changed", Path(name), "Preserve the changed owned file.")


def _source_identity(source: Path) -> tuple[int, ...]:
    with open_directory(source.parent) as directory:
        value = os.stat(source.name, dir_fd=directory, follow_symlinks=False)
        if not stat.S_ISREG(value.st_mode):
            raise _error("projection-source-unsafe", source, "Source must be a regular file.")
        return _identity(value)


def _publish_projection(
    directory: int, private: Path, metadata: Path, state: _Projection, source: Path
) -> _Projection:
    target = f"{state.profile}.env"
    name = f".{state.profile}.projection-{uuid.uuid4().hex}.tmp"
    created = _new_file(directory, name, b"")
    state = replace(state, temporary=name, temporary_identity=_identity(created)[:2])
    # Record inode ownership before any secret bytes are written, so restart can clean up.
    _save_projection(metadata, directory, state)
    source_identity = _source_identity(source)
    data = read_bytes(source, max_bytes=ENVIRONMENT_MAX_BYTES)
    parse_pending_dotenv_names(data)
    with open_directory(private) as pinned:
        descriptor = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=pinned)
        try:
            if _identity(os.fstat(descriptor))[:2] != state.temporary_identity:
                raise _error(
                    "projection-file-changed", private / name, "Private staging file changed."
                )
            _write_all(descriptor, data)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    # A new destination must not overwrite a file created by an unrelated writer.
    if _source_identity(source) != source_identity:
        raise _error(
            "projection-source-changed", source, "Source changed during projection; retry."
        )
    os.link(name, target, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
    os.fsync(directory)
    _unlink_identity(directory, name, state.temporary_identity)
    final = _private_stat(directory, target)
    assert final is not None
    state = replace(
        state, temporary=None, temporary_identity=None, target_identity=_identity(final)
    )
    _save_projection(metadata, directory, state)
    return state


def _readiness(environment: ResolvedProfileEnvironment | None) -> dict[str, object]:
    if environment is None:
        return {"status": "not-configured", "missing": []}
    inspection = inspect_pending_environment(environment)
    missing = [
        item.from_env for item in environment.variables if item.from_env not in inspection.names
    ]
    return {
        "status": "pending" if missing or inspection.blank_names else "ready",
        "missing": missing,
        "blank": sorted(inspection.blank_names),
    }


def prepare_container_profile(
    *,
    operation: str,
    settings: Path,
    profile: str,
    candidate: bytes,
    expected_sha256: str | None,
    private_directory: Path | None = None,
    source_env_file: Path | None = None,
) -> dict[str, object]:
    """Prepare/refresh/remove one explicit private projection and checked registry route."""
    settings = _absolute(settings)
    profile = profile_name(profile, "profile")
    if operation not in {"prepare", "refresh", "remove"}:
        raise ValidationError("invalid-operation", "operation", "Use prepare, refresh or remove.")
    current = _current(settings, expected_sha256)
    selected = _checked_candidate(settings, candidate, current, profile, operation)
    private = _absolute(private_directory) if private_directory is not None else None
    environment = (
        _candidate_environment(settings, candidate, profile, private) if selected else None
    )
    report: dict[str, object] = {
        "schema": "container-profile-preparation.v1",
        "operation": operation,
        "settings_path": str(settings),
        "profile": profile,
        "registry": "unchanged" if candidate == current else "published",
    }
    if private_directory is None:
        if source_env_file is not None or operation != "prepare":
            raise ValidationError(
                "projection-arguments",
                "private_directory",
                "An owned private directory is required.",
            )
        readiness = _readiness(environment)
        if candidate != current:
            replace_registry(settings, candidate, expected_sha256=expected_sha256)
        else:
            _current(settings, expected_sha256)
        return {
            **report,
            "status": "pending" if readiness["status"] == "pending" else "ok",
            "projection": "reused-local",
            "environment": readiness,
        }
    assert private is not None
    target = private / f"{profile}.env"
    metadata = private / f".{profile}.projection.json"
    source = _absolute(source_env_file) if source_env_file is not None else None
    if source is not None and source.is_relative_to(private):
        raise _error(
            "projection-source-conflict",
            source,
            "Source must be outside the private projection directory.",
        )
    if operation != "remove" and (
        source is None or environment is None or environment.file != target
    ):
        raise _error(
            "projection-route-mismatch",
            settings,
            "Candidate must route the selected environment to private-directory/profile.env "
            "and name its source explicitly.",
        )
    if operation == "remove":
        profiles = parse_profiles(load_mapping(candidate, path=str(settings)))
        for item in profiles.profiles:
            if (
                item.environment is not None
                and Path(os.path.abspath(settings.parent / item.environment.file)) == target
            ):
                raise _error(
                    "projection-still-referenced",
                    settings,
                    "Detach every registry reference before removing the private file.",
                )
    _private_directory(private, create=operation == "prepare")
    try:
        with (
            usage_lock(private / f".{profile}.projection.lock", blocking=False),
            open_directory(private) as directory,
        ):
            _current(settings, expected_sha256)
            state = _read_projection(metadata, directory)
            if state is not None and (
                state.settings != str(settings)
                or state.profile != profile
                or (operation == "refresh" and source is not None and state.source != str(source))
            ):
                raise _error(
                    "projection-owner-conflict",
                    metadata,
                    "Existing provenance belongs to another route or source.",
                )
            if state is None:
                if operation == "refresh":
                    raise _error(
                        "projection-not-prepared",
                        metadata,
                        "Prepare an owned projection before refreshing it.",
                    )
                if _private_stat(directory, target.name) is not None:
                    raise _error(
                        "projection-unowned-target",
                        target,
                        "Existing target has no setup-owned provenance.",
                    )
                state = _Projection(_SCHEMA, str(settings), profile, str(source or ""))
            if operation == "remove":
                readiness = _readiness(environment)
                _check_owned(directory, target.name, state)
                # Detach the registry route before deleting its owned private file.
                if candidate != current:
                    replace_registry(settings, candidate, expected_sha256=expected_sha256)
                else:
                    _current(settings, expected_sha256)
                _invalidate(directory, target.name, state)
                owned_metadata = _private_stat(directory, metadata.name)
                if owned_metadata is not None:
                    _unlink_identity(directory, metadata.name, _identity(owned_metadata))
                return {
                    **report,
                    "status": "pending" if readiness["status"] == "pending" else "ok",
                    "projection": "removed",
                    "environment": readiness,
                }
            _invalidate(directory, target.name, state)
            state = replace(
                state,
                source=str(source),
                target_identity=None,
                temporary=None,
                temporary_identity=None,
            )
            _save_projection(metadata, directory, state)
            assert source is not None and environment is not None
            try:
                state = _publish_projection(directory, private, metadata, state, source)
                readiness = _readiness(environment)
                if candidate != current:
                    replace_registry(settings, candidate, expected_sha256=expected_sha256)
                else:
                    _current(settings, expected_sha256)
            except BaseException:
                # Read the last durable ownership journal, including interrupted publication.
                latest = _read_projection(metadata, directory)
                if latest is not None:
                    _invalidate(directory, target.name, latest)
                    _save_projection(
                        metadata,
                        directory,
                        replace(
                            latest, target_identity=None, temporary=None, temporary_identity=None
                        ),
                    )
                raise
            return {
                **report,
                "status": "pending" if readiness["status"] == "pending" else "ok",
                "projection": "refreshed" if operation == "refresh" else "prepared",
                "environment": readiness,
                "environment_file": str(target),
                "source_security": "unverified",
                "detail": "Private-copy permissions do not establish source-mount security. "
                "A new credentialed session is required.",
            }
    except OSError as error:
        raise _error(
            "projection-io-failed",
            private,
            "Could not safely prepare the private projection; do not launch.",
        ) from error
