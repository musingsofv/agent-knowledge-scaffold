"""Exercise the mount probe as an installed-runtime subprocess on a disposable directory."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "e2e" / "filesystem_probe.py"


def test_probe_checks_real_processes_and_preserves_existing_files(tmp_path: Path) -> None:
    existing = tmp_path / "existing.env"
    existing.write_text("PRIVATE=existing-file-canary\n")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--directory", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "passed"
    assert report["checks"] == {
        name: {"status": "passed"}
        for name in (
            "guarded_reads",
            "private_environment_0600",
            "unsafe_environment_rejected",
            "process_lock_exclusion",
            "concurrent_receipts",
        )
    }
    assert list(tmp_path.iterdir()) == [existing]
    assert existing.read_text() == "PRIVATE=existing-file-canary\n"
    assert "canary" not in result.stdout + result.stderr
    assert "filesystem-probe-placeholder" not in result.stdout + result.stderr


def test_missing_directory_fails_without_creating_it(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--directory", str(missing)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "status": "failed",
        "checks": {"temporary_directory": {"status": "failed", "code": "directory-unavailable"}},
    }
    assert not missing.exists()


@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("filesystem_probe_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_protocol_timeout_is_bounded(probe) -> None:
    parent, child = probe.multiprocessing.Pipe()
    try:
        with pytest.raises(probe.ProbeFailure, match="worker-timeout"):
            probe._expect(parent, "held", timeout=0.01)
    finally:
        parent.close()
        child.close()


@pytest.mark.parametrize("existing", [True, False])
def test_worker_reports_specific_failure_without_exception_messages(
    tmp_path: Path, probe, existing: bool
) -> None:
    path = tmp_path / "sensitive-path-canary"
    if existing:
        path.touch()
    parent, child = probe.multiprocessing.Pipe()
    try:
        parent.send("contest")
        probe._worker("lock", 1, path, child)
        expected = "lock-did-not-exclude" if existing else "FileNotFoundError-errno-2"
        with pytest.raises(probe.ProbeFailure, match=f"^{expected}$"):
            probe._expect(parent, "excluded")
    finally:
        parent.close()
        child.close()
