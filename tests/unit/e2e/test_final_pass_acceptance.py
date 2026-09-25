"""Check that resuming acceptance preserves evidence instead of accepting mutable baselines."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tests/e2e/final_pass_acceptance.py"


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("final_pass_acceptance_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_reference_check_accepts_the_observed_requirement_without_literal_evidence(
    tmp_path: Path, driver
) -> None:
    reference = tmp_path / "export-checklist.md"
    reference.write_text(
        "Include the qualification source URL that supports each qualification result.\n"
        "The export is incomplete without it.\n"
    )
    driver._check_owner_reference(reference)
    reference.write_text("Include company name, contact email and qualification result.\n")
    with pytest.raises(driver.HarnessSmokeFailure, match="qualification source"):
        driver._check_owner_reference(reference)


def test_saved_resume_baseline_rejects_changed_config_and_changed_wheel(
    tmp_path: Path, driver
) -> None:
    config = tmp_path / "knowledge-workspace.yaml"
    wheel = tmp_path / "package.whl"
    config.write_bytes(b"original configuration")
    wheel.write_bytes(b"original wheel")
    state = {
        "baseline_hashes": {"config": driver._hash(config.read_bytes())},
        "wheel_fingerprint": driver._hash(wheel.read_bytes()),
    }
    report = {"resume_state": state}
    files = {"config": config}
    assert driver._resume_state(report, files, wheel) is state
    assert config.read_bytes() == b"original configuration"
    config.write_bytes(b"replacement configuration")
    with pytest.raises(driver.HarnessSmokeFailure, match="Changed preserved fixture"):
        driver._resume_state(report, files, wheel)
    config.write_bytes(b"original configuration")
    wheel.write_bytes(b"different wheel")
    with pytest.raises(driver.HarnessSmokeFailure, match="wheel changed"):
        driver._resume_state(report, files, wheel)


def test_missing_checkpoint_cannot_recover_an_unrelated_failure(tmp_path: Path, driver) -> None:
    with pytest.raises(driver.HarnessSmokeFailure, match="restricted"):
        driver._resume_state(
            {
                "turns": [{"phase": phase} for phase in driver.PHASES[:2]],
                "diagnostic": "Unrelated content validation failure",
            },
            {},
            tmp_path / "package.whl",
        )


def test_original_assertion_recovery_requires_matching_tool_capture_fingerprints(
    tmp_path: Path, driver
) -> None:
    consumer = tmp_path / "studio"
    consumer.mkdir()
    files = driver._prepare(consumer, tmp_path / "package-source")
    wheel = tmp_path / "package.whl"
    wheel.write_bytes(b"fixed runtime")
    receipt = consumer / "ai/usage/retrieval/day.jsonl"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "context": {"workspace_id": driver.WORKSPACE},
                "recorded_at": "2026-09-14T15:00:00Z",
            }
        )
        + "\n"
    )
    logs = tmp_path / "logs"
    logs.mkdir()
    for index, identifier in enumerate(
        ("trial-choice", "export-evidence-gap", "external-policy-source", "covered-qualification")
    ):
        authored = driver._signal(
            consumer, identifier, "A supported durable observation.", "ref.md"
        )
        (logs / f"cli-{index}-signal-record.log").write_text(
            "STDOUT:\n"
            + json.dumps(
                {
                    "id": identifier,
                    "status": "ok",
                    "fingerprint": driver._hash(authored.read_bytes()),
                }
            )
            + "\n"
        )
    report = {
        "turns": [
            {"phase": phase, "session_id": "original-session"} for phase in driver.PHASES[:2]
        ],
        "diagnostic": "The relevant skill reference was not updated.",
    }
    before = {name: files[name].read_bytes() for name in driver.PRESERVED}
    recovered = driver._resume_state(report, files, wheel)
    assert len(recovered["seed_fingerprints"]) == 4
    assert recovered["session_id"] == "original-session"
    assert recovered["since"] == "2026-09-14T14:59:59+00:00"
    assert before == {name: files[name].read_bytes() for name in driver.PRESERVED}
    authored.write_text(authored.read_text() + "\nChanged after capture.\n")
    with pytest.raises(driver.HarnessSmokeFailure, match="changed since capture"):
        driver._resume_state(report, files, wheel)


@pytest.mark.parametrize("session_id,is_error", [("foreign-session", False), ("original", True)])
def test_prior_turns_require_actual_success_in_the_recorded_session(
    tmp_path: Path, driver, session_id: str, is_error: bool
) -> None:
    consumer = tmp_path / "studio"
    consumer.mkdir()
    log = tmp_path / "logs/phase.log"
    log.parent.mkdir()
    events = [
        {"type": "system", "subtype": "init", "session_id": session_id},
        {"type": "result", "is_error": is_error},
    ]
    log.write_text("STDOUT:\n" + "\n".join(json.dumps(event) for event in events))
    report = {"turns": [{"log": str(log), "session_id": "original"}]}
    with pytest.raises(driver.HarnessSmokeFailure):
        driver._prior_events(report, consumer)
    events[0]["session_id"] = "original"
    events[1]["is_error"] = False
    log.write_text("\n".join(json.dumps(event) for event in events))
    assert driver._prior_events(report, consumer) == events


def _export(tmp_path: Path, driver) -> tuple[Path, bytes]:
    destination = tmp_path / "export"
    destination.mkdir()
    known = b"original seed bytes"
    generated = b"agent observed a separate durable conflict"
    events = []
    for operation in ("catalog", "search", "inspect"):
        events.append(
            {
                "schema_version": "knowledge-retrieval-receipt.v1",
                "operation": operation,
                "context": {"compound_run_id": "run-1"},
                "request": {"view": "incoming"} if operation == "inspect" else {},
                "response": {},
                "body_read": "unknown",
                "measurements": {"response_bytes": 2},
            }
        )
    inputs = destination / "compound/run-1/inputs"
    inputs.mkdir(parents=True)
    (inputs / "seed.md").write_bytes(known)
    (inputs / "agent.md").write_bytes(generated)
    events.append(
        {
            "schema_version": "knowledge-compound-receipt.v1",
            "operation": "compound.start",
            "context": {"compound_run_id": "run-1"},
            "artifacts": {
                "signal_snapshots": [
                    {
                        "signal_id": "covered-qualification",
                        "path": "inputs/seed.md",
                        "fingerprint": driver._hash(known),
                    },
                    {
                        "signal_id": "extra-agent-observation",
                        "path": "inputs/agent.md",
                        "fingerprint": driver._hash(generated),
                    },
                ]
            },
        }
    )
    for operation in ("compound.drain", "compound.finish"):
        events.append(
            {
                "schema_version": "knowledge-compound-receipt.v1",
                "operation": operation,
                "agent_report": {
                    "dispositions": [{"signal_id": "external-policy-source", "decision": "defer"}]
                },
            }
        )
    (destination / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events))
    (destination / "descriptors").mkdir()
    (destination / "descriptors/descriptor.json").write_text("{}")
    (destination / "manifest.json").write_text(
        json.dumps(
            {
                "workspace_id": driver.WORKSPACE,
                "files": [
                    {
                        "path": str(path.relative_to(destination)),
                        "bytes": len(path.read_bytes()),
                        "checksum": driver._hash(path.read_bytes()),
                    }
                    for path in destination.rglob("*")
                    if path.is_file()
                ],
            }
        )
    )
    return destination, known


def test_extra_agent_signal_archive_is_reported_while_seed_bytes_stay_strict(
    tmp_path: Path, driver
) -> None:
    destination, known = _export(tmp_path, driver)
    proof = driver._usage_proof(destination, {"covered-qualification": known})
    assert proof["additional_agent_signal_ids"] == ["extra-agent-observation"]
    with pytest.raises(driver.HarnessSmokeFailure, match="exact seeded bytes"):
        driver._usage_proof(destination, {"covered-qualification": b"wrong baseline"})
    (destination / "compound/run-1/inputs/agent.md").write_bytes(b"corrupt generated archive")
    with pytest.raises(driver.HarnessSmokeFailure, match="hash mismatch"):
        driver._usage_proof(destination, {"covered-qualification": known})
