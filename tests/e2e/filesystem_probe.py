#!/usr/bin/env python3
"""Probe an existing mount with installed runtime Python; use only a temporary child."""

from __future__ import annotations

import argparse
import fcntl
import json
import multiprocessing
import os
import stat
from multiprocessing.connection import Connection
from pathlib import Path
from tempfile import TemporaryDirectory

from agent_knowledge.infrastructure.environment import inspect_environment
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import read_bytes
from agent_knowledge.infrastructure.profiles import ResolvedProfileEnvironment
from agent_knowledge.infrastructure.usage import append_event, read_events, usage_lock

TIMEOUT = 10


class ProbeFailure(Exception):
    """Carry only an authored diagnostic, never file contents or exception messages."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ProbeFailure(code)


def _failure_code(error: Exception) -> str:
    if isinstance(error, ProbeFailure):
        return str(error)
    if isinstance(error, AdapterError):
        return error.code
    if isinstance(error, OSError):
        return f"{type(error).__name__}-errno-{error.errno}"
    return type(error).__name__


def _expect(connection: Connection, expected: str, timeout: float = TIMEOUT) -> None:
    if not connection.poll(timeout):
        raise ProbeFailure("worker-timeout")
    received = connection.recv()
    if isinstance(received, dict) and isinstance(received.get("failure"), str):
        raise ProbeFailure(received["failure"])
    _require(received == expected, "worker-protocol-failed")


def _worker(mode: str, role: int, path: Path, connection: Connection) -> None:
    try:
        if mode == "lock":
            if role == 0:
                with usage_lock(path):
                    connection.send("held")
                    _expect(connection, "release")
                connection.send("released")
            else:
                _expect(connection, "contest")
                # A nonblocking kernel attempt gives definite evidence of exclusion;
                # scheduling delays cannot masquerade as a blocked lock acquisition.
                descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
                try:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        connection.send("excluded")
                    else:
                        raise ProbeFailure("lock-did-not-exclude")
                finally:
                    os.close(descriptor)
                _expect(connection, "acquire")
                with usage_lock(path):
                    connection.send("acquired")
        else:
            connection.send("ready")
            _expect(connection, "append")
            for index in range(12):
                append_event(path, {"id": role * 12 + index, "payload": "x" * 5000})
            connection.send("written")
    except Exception as error:
        connection.send({"failure": _failure_code(error)})
    finally:
        connection.close()


def _concurrency(root: Path, mode: str) -> None:
    context = multiprocessing.get_context("spawn")
    path = root / ("usage.lock" if mode == "lock" else "receipts.jsonl")
    workers = []
    connections = []
    try:
        for role in range(2):
            parent, child = context.Pipe()
            process = context.Process(target=_worker, args=(mode, role, path, child))
            process.start()
            child.close()
            workers.append(process)
            connections.append(parent)
        holder, contender = connections
        if mode == "lock":
            _expect(holder, "held")
            contender.send("contest")
            _expect(contender, "excluded")
            holder.send("release")
            _expect(holder, "released")
            contender.send("acquire")
            _expect(contender, "acquired")
        else:
            for connection in connections:
                _expect(connection, "ready")
            for connection in connections:
                connection.send("append")
            for connection in connections:
                _expect(connection, "written")
        for process in workers:
            process.join(TIMEOUT)
            _require(process.exitcode == 0, "worker-exit-failed")
        if mode == "append":
            events = read_events(path)
            _require(not events.diagnostics, "receipt-read-failed")
            _require(
                len(events.records) == 24
                and {event["id"] for event in events.records} == set(range(24))
                and all(event["payload"] == "x" * 5000 for event in events.records),
                "receipt-records-mismatch",
            )
    finally:
        for process in workers:
            if process.is_alive():
                process.kill()
            process.join(TIMEOUT)
            process.close()
        for connection in connections:
            connection.close()


def _guarded_read(root: Path) -> None:
    path = root / "document.txt"
    path.write_bytes(b"filesystem-probe")
    _require(read_bytes(path, max_bytes=32) == b"filesystem-probe", "guarded-read-mismatch")
    alias = root / "document-link.txt"
    alias.symlink_to(path)
    try:
        read_bytes(alias, max_bytes=32)
    except AdapterError as error:
        _require(error.code == "unsafe-path", "unexpected-symlink-diagnostic")
    else:
        raise ProbeFailure("guarded-read-followed-symlink")


def _environment(root: Path, *, unsafe: bool) -> None:
    path = root / ("unsafe.env" if unsafe else "private.env")
    path.write_text("PROBE_TOKEN=filesystem-probe-placeholder\n", encoding="utf-8")
    mode = 0o640 if unsafe else 0o600
    path.chmod(mode)
    _require(stat.S_IMODE(path.stat().st_mode) == mode, "permission-mode-not-preserved")
    environment = ResolvedProfileEnvironment(path, ())
    try:
        result = inspect_environment(environment)
    except AdapterError as error:
        if unsafe and error.code == "environment-file-permissions":
            return
        raise
    _require(not unsafe, "unsafe-environment-accepted")
    _require(result.names == frozenset({"PROBE_TOKEN"}), "environment-read-mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path, help="Existing mount to probe")
    arguments = parser.parse_args()
    checks = {}
    try:
        directory = arguments.directory.resolve(strict=True)
        with TemporaryDirectory(prefix="agent-knowledge-probe-", dir=directory) as temporary:
            root = Path(temporary)
            for name, operation in (
                ("guarded_reads", _guarded_read),
                ("private_environment_0600", lambda path: _environment(path, unsafe=False)),
                ("unsafe_environment_rejected", lambda path: _environment(path, unsafe=True)),
                ("process_lock_exclusion", lambda path: _concurrency(path, "lock")),
                ("concurrent_receipts", lambda path: _concurrency(path, "append")),
            ):
                try:
                    operation(root)
                    checks[name] = {"status": "passed"}
                except Exception as error:
                    checks[name] = {"status": "failed", "code": _failure_code(error)}
    except OSError:
        checks["temporary_directory"] = {"status": "failed", "code": "directory-unavailable"}
    passed = all(check["status"] == "passed" for check in checks.values())
    print(
        json.dumps({"status": "passed" if passed else "failed", "checks": checks}, sort_keys=True)
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
