"""Observe only bounded, non-secret local facts; never infer the outer harness."""

import os
import platform
import re
import selectors
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agent_knowledge.domain.preflight import ExecutionKind

_CGROUP_BYTES = 16_384
_RUNTIMES = frozenset(
    {"docker", "podman", "lxc", "lxc-libvirt", "systemd-nspawn", "openvz", "wsl", "proot", "pouch"}
)


@dataclass(frozen=True, slots=True)
class Observation:
    """Summarize a probe without retaining arbitrary kernel/file output."""

    probe: str
    outcome: str
    detail: str


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    """These facts describe this tool process, not its remote or outer harness."""

    observed: ExecutionKind
    system: str
    uid: int | None
    home: str | None
    cwd: str | None
    pid: int
    parent_pid: int
    evidence: tuple[Observation, ...]
    harness_location: str = "unverified"
    scope: str = "current-tool-process"
    limitation: str = "Container detection is supporting evidence, not a security boundary."


def _bounded_text(path: Path, size: int) -> str | None:
    try:
        with path.open("rb") as stream:
            return stream.read(size).decode("utf-8", errors="replace")
    except OSError:
        return None


def _detect_virt() -> Observation:
    executable = shutil.which("systemd-detect-virt")
    if executable is None:
        return Observation("systemd-detect-virt", "unavailable", "Executable is not on PATH.")
    try:
        with subprocess.Popen(
            [executable, "--container"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        ) as process:
            try:
                assert process.stdout is not None
                with selectors.DefaultSelector() as poll:
                    poll.register(process.stdout, selectors.EVENT_READ)
                    if not poll.select(timeout=0.5):
                        raise subprocess.TimeoutExpired(executable, 0.5)
                    output = os.read(process.stdout.fileno(), 128)
                process.wait(timeout=0.5)
                returncode = process.returncode
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    except (OSError, subprocess.TimeoutExpired):
        return Observation(
            "systemd-detect-virt", "unavailable", "Probe failed or exceeded its bounded wait."
        )
    runtime = output.decode("ascii", errors="replace").strip()
    # WSL/PRoot establish isolation, but neither proves a Docker/container target.
    if returncode == 0 and runtime in _RUNTIMES - {"wsl", "proot"}:
        return Observation("systemd-detect-virt", "container", "Reported runtime: " + runtime)
    return Observation(
        "systemd-detect-virt", "inconclusive", "No recognized container result; not host proof."
    )


def observe_execution() -> ExecutionObservation:
    """No argument/environment dump, Docker calls, installation or filesystem scan."""
    system = platform.system()
    evidence: list[Observation] = []
    observed: ExecutionKind = "unknown"
    if system == "Linux":
        for location in ("/.dockerenv", "/run/.containerenv"):
            try:
                present = Path(location).is_file()
            except OSError:
                evidence.append(
                    Observation(location, "unavailable", "Marker could not be inspected.")
                )
            else:
                evidence.append(
                    Observation(
                        location,
                        "container" if present else "inconclusive",
                        "Marker present." if present else "Marker absent; not host proof.",
                    )
                )
        for location in ("/proc/self/cgroup", "/proc/1/cgroup"):
            text = _bounded_text(Path(location), _CGROUP_BYTES)
            if text is None:
                evidence.append(Observation(location, "unavailable", "Cgroup probe is unreadable."))
                continue
            lines = "\n".join(text.splitlines()[:80])
            found = re.search(
                r"(?:^|[/:-])(?:docker|kubepods|libpod|lxc)(?:[/.:_-]|$)", lines, re.MULTILINE
            )
            evidence.append(
                Observation(
                    location,
                    "container" if found else "inconclusive",
                    "Container runtime entry found."
                    if found
                    else "No bounded runtime evidence; cgroup v2 root is inconclusive.",
                )
            )
        evidence.append(_detect_virt())
        for location in ("/proc/self/ns/mnt", "/proc/1/ns/mnt"):
            try:
                target = os.readlink(location)
            except OSError:
                target = None
            evidence.append(
                Observation(
                    location,
                    "observed" if target else "unavailable",
                    target
                    if target and re.fullmatch(r"mnt:\[\d+\]", target)
                    else "Namespace identity unavailable; not host proof.",
                )
            )
        for pid in (os.getpid(), os.getppid()):
            name = _bounded_text(Path(f"/proc/{pid}/comm"), 128)
            evidence.append(
                Observation(
                    f"process:{pid}",
                    "observed" if name else "unavailable",
                    "Executable name: " + name.strip()
                    if name and re.fullmatch(r"[\w. /()+-]+\n?", name)
                    else "Process name unavailable; no argv read.",
                )
            )
        if any(item.outcome == "container" for item in evidence):
            observed = "container"
    elif system == "Darwin":
        observed = "host"
        evidence.append(
            Observation(
                "kernel",
                "host",
                "Darwin kernel is outside a Linux container; VM and outer "
                "harness location remain unverified.",
            )
        )
    else:
        evidence.append(
            Observation(
                "kernel",
                "inconclusive",
                "No supported container evidence probe for this kernel; no Linux probes attempted.",
            )
        )
    try:
        cwd = str(Path.cwd())
    except OSError:
        cwd = None
    try:
        home = str(Path.home())
    except (OSError, RuntimeError):
        home = None
    return ExecutionObservation(
        observed,
        system,
        os.geteuid() if hasattr(os, "geteuid") else None,
        home,
        cwd,
        os.getpid(),
        os.getppid(),
        tuple(evidence),
    )


def executable_path(name: str) -> str | None:
    """Locate without running a provider or importing another runtime."""
    found = shutil.which(name)
    return str(Path(found).absolute()) if found else None


def available_executable(path: Path) -> bool:
    try:
        return path.is_file() and os.access(path, os.X_OK)
    except OSError:
        return False


def registration_availability(consumer: Path | None, provider: str | None) -> dict[str, object]:
    """Existence is not valid registration, provider trust, or live hook delivery."""
    relative = {
        "codex": ".codex/hooks.json",
        "claude": ".claude/settings.json",
        "copilot": ".github/hooks/knowledge-agent-pack-knowledge-discovery.json",
    }
    path = consumer / relative[provider] if consumer is not None and provider is not None else None
    try:
        available = path.is_file() if path else None
    except OSError:
        available = False
    return {
        "path": str(path) if path else None,
        "file_available": available,
        "registration": "unverified",
        "native_trust": "unverified",
        "firing": "unverified",
    }
