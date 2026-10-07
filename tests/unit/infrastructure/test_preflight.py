"""Bounded execution evidence must not turn negative Linux probes into host proof."""

from pathlib import Path

import pytest

from agent_knowledge.infrastructure import preflight


def linux(monkeypatch, *, marker=False, cgroup="0::/\n", virt="inconclusive"):
    monkeypatch.setattr(preflight.platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "is_file", lambda self: marker and str(self) == "/.dockerenv")
    monkeypatch.setattr(
        preflight,
        "_bounded_text",
        lambda path, size: cgroup if "cgroup" in str(path) else "python\n",
    )
    monkeypatch.setattr(
        preflight,
        "_detect_virt",
        lambda: preflight.Observation("systemd-detect-virt", virt, "fixture"),
    )
    monkeypatch.setattr(preflight.os, "readlink", lambda path: "mnt:[101]")


def test_linux_and_plain_cgroup_v2_are_not_host_evidence(monkeypatch):
    linux(monkeypatch)
    observed = preflight.observe_execution()
    assert observed.observed == "unknown"
    assert observed.scope == "current-tool-process"
    assert observed.harness_location == "unverified"


@pytest.mark.parametrize("case", ["marker", "cgroup", "virt"])
def test_positive_container_observations_are_explicit_supporting_evidence(monkeypatch, case):
    linux(
        monkeypatch,
        marker=case == "marker",
        cgroup="0::/docker/abc\n" if case == "cgroup" else "0::/\n",
        virt="container" if case == "virt" else "inconclusive",
    )
    result = preflight.observe_execution()
    assert result.observed == "container"
    assert any(item.outcome == "container" for item in result.evidence)
    assert result.harness_location == "unverified"


def test_unreadable_linux_probes_remain_unknown(monkeypatch):
    linux(monkeypatch)
    monkeypatch.setattr(preflight, "_bounded_text", lambda path, size: None)
    result = preflight.observe_execution()
    assert result.observed == "unknown"
    assert any(item.outcome == "unavailable" for item in result.evidence)


@pytest.mark.parametrize(
    "kernel,expected", [("Darwin", "host"), ("Windows", "unknown"), ("Other", "unknown")]
)
def test_non_linux_does_not_run_linux_probes(monkeypatch, kernel, expected):
    monkeypatch.setattr(preflight.platform, "system", lambda: kernel)
    monkeypatch.setattr(preflight, "_detect_virt", lambda: pytest.fail("Linux probe"))
    monkeypatch.setattr(preflight, "_bounded_text", lambda *args: pytest.fail("Linux file"))
    result = preflight.observe_execution()
    assert result.observed == expected
    assert result.harness_location == "unverified"


def test_cgroup_probe_reads_only_requested_bytes(tmp_path):
    path = tmp_path / "cgroup"
    path.write_text("0::/\n" + "x" * 100_000)
    assert len(preflight._bounded_text(path, 32)) == 32


def test_registration_file_alone_cannot_prove_hook_delivery(tmp_path):
    path = tmp_path / ".claude/settings.json"
    path.parent.mkdir()
    path.write_text("{}")
    result = preflight.registration_availability(tmp_path, "claude")
    assert result["file_available"] is True
    assert result["registration"] == result["native_trust"] == result["firing"] == "unverified"


def test_missing_detector_is_unavailable_without_installation(monkeypatch):
    monkeypatch.setattr(preflight.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        preflight.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Executed")
    )
    assert preflight._detect_virt().outcome == "unavailable"


def test_inaccessible_registration_is_unavailable_without_unhandled_error(monkeypatch, tmp_path):
    def denied(path):
        raise PermissionError("fixture")

    monkeypatch.setattr(Path, "is_file", denied)
    result = preflight.registration_availability(tmp_path, "codex")
    assert result["file_available"] is False
    assert result["firing"] == "unverified"


@pytest.mark.parametrize(
    "output,returncode,outcome",
    [
        (b"docker", 0, "container"),
        (b"none", 1, "inconclusive"),
        (b"do-not-expose-fixture-value", 0, "inconclusive"),
    ],
)
def test_detector_classification_and_output_privacy(monkeypatch, output, returncode, outcome):
    from unittest.mock import MagicMock

    process = MagicMock()
    process.__enter__.return_value = process
    process.returncode = returncode
    process.poll.return_value = returncode
    selector = MagicMock()
    selector.__enter__.return_value = selector
    selector.select.return_value = [object()]
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/fixture/detector")
    monkeypatch.setattr(preflight.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(preflight.selectors, "DefaultSelector", lambda: selector)
    monkeypatch.setattr(preflight.os, "read", lambda fd, size: output)
    result = preflight._detect_virt()
    assert result.outcome == outcome
    assert "do-not-expose-fixture-value" not in result.detail
    selector.select.assert_called_once_with(timeout=0.5)
    process.wait.assert_called_once_with(timeout=0.5)


@pytest.mark.parametrize("stage", ["read", "wait"])
def test_detector_deadline_kills_child_without_output_leak(monkeypatch, stage):
    import subprocess
    from unittest.mock import MagicMock

    process = MagicMock()
    process.__enter__.return_value = process
    process.poll.return_value = None
    if stage == "wait":
        process.wait.side_effect = [subprocess.TimeoutExpired("fixture", 0.5), 0]
    selector = MagicMock()
    selector.__enter__.return_value = selector
    selector.select.return_value = [] if stage == "read" else [object()]
    monkeypatch.setattr(preflight.shutil, "which", lambda _: "/fixture/detector")
    monkeypatch.setattr(preflight.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(preflight.selectors, "DefaultSelector", lambda: selector)
    monkeypatch.setattr(preflight.os, "read", lambda fd, size: b"do-not-expose-fixture-value")
    result = preflight._detect_virt()
    assert result.outcome == "unavailable"
    assert "do-not-expose-fixture-value" not in result.detail
    process.kill.assert_called_once()


def test_noisy_real_detector_is_bounded_and_its_output_is_private(tmp_path, monkeypatch):
    import os

    if os.name == "nt":
        pytest.skip("POSIX detector fixture")
    program = tmp_path / "detect"
    program.write_text("#!/bin/sh\nwhile :; do printf excessive-output; done\n")
    program.chmod(0o700)
    monkeypatch.setattr(preflight.shutil, "which", lambda name: str(program))
    result = preflight._detect_virt()
    assert result.outcome == "unavailable"
    assert "excessive-output" not in result.detail
