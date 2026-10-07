#!/usr/bin/env python3
"""Prove BYO-container runtime binding on disposable Debian/Alpine images and volumes.

This acceptance driver builds temporary test images, not a distributed product
Dockerfile. It uses fictional configuration and provider fixtures, never real
credentials or live harnesses. Docker and uv are explicit host prerequisites.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

IMAGES = ("python:3.12-slim", "python:3.12-alpine")


def _run(arguments: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {arguments[0]}\n{result.stdout}{result.stderr}"
        )
    return result


def _json(arguments: list[str]) -> dict:
    return json.loads(_run(arguments).stdout)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def _snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def _fixtures() -> None:
    """Materialize only the APM projections needed by bind; no install claim."""
    state = Path("/state")
    knowledge = state / "knowledge"
    consumer = state / "consumer"
    (knowledge / "knowledge").mkdir(parents=True)
    (knowledge / "ai/signals").mkdir(parents=True)
    (knowledge / "ai/usage").mkdir(parents=True)
    _write(
        knowledge / "catalog.yaml",
        {
            "schema_version": "knowledge-catalog.v1",
            "scopes": {"org:example": {"label": "Example"}},
            "entities": {},
            "topics": {},
            "languages": {},
            "technologies": {},
            "technology_families": {},
            "environments": {},
        },
    )
    _write(
        knowledge / "knowledge-workspace.yaml",
        {
            "schema_version": "knowledge-workspace.v1",
            "workspace_id": "workspace:example",
            "applicable_scopes": ["org:example"],
            "sources": [{"id": "example", "root": "knowledge", "catalog": "catalog.yaml"}],
            "signal_storage": {"scaffold_root": str(knowledge), "code_root": str(state)},
            "receipts": {"enabled": True, "directory": "ai/usage", "retention_days": 30},
            "setup": {
                "venv": "/opt/runtime",
                "compounding": {"mode": "prompt", "owner": "example-store"},
            },
        },
    )
    _write(
        state / "profiles.yaml",
        {
            "schema_version": "knowledge-profiles.v1",
            "profiles": {"example": {"config": str(knowledge / "knowledge-workspace.yaml")}},
        },
    )
    source = "_local/knowledge-agent-pack"
    package = consumer / "apm_modules" / source
    shutil.copytree("/opt/knowledge-agent-pack", package)
    command = {"type": "command", "command": "agent-knowledge-hook"}
    for target in ("codex", "claude"):
        _write(
            consumer / f".{target}/apm-hooks.json",
            {
                event: [{"_apm_source": source, "hooks": [command]}]
                for event in ("SessionStart", "UserPromptSubmit")
            },
        )
    copilot_path = ".github/hooks/knowledge-agent-pack-knowledge-discovery.json"
    _write(
        consumer / copilot_path,
        {
            "version": 1,
            "hooks": {"sessionStart": [{"hooks": [command]}]},
        },
    )
    # The setup hash updater preserves APM's generated YAML block layout.
    (consumer / "apm.lock.yaml").write_text(
        "lockfile_version: '1'\ndependencies:\n"
        f"- repo_url: {source}\n  name: knowledge-agent-pack\n"
        "  source: local\n  local_path: ./packages/knowledge-agent-pack\n"
        f"  deployed_file_hashes:\n    {copilot_path}: sha256:fixture\n"
        "deployments:\n- kind: project-relative\n  target: copilot\n"
        f"  value: {copilot_path}\n  content_hash: sha256:fixture\n"
    )


def _inside(phase: str) -> dict:
    state = Path("/state")
    runtime = Path("/opt/runtime")
    assert os.getuid() == os.getgid() == 1000
    assert shutil.which("uv") is None
    assert runtime.stat().st_uid == 0 and not os.access(runtime, os.W_OK)
    assert all(not os.access(path, os.W_OK) for path in runtime.rglob("*") if path.is_file())
    (state / "home").mkdir(exist_ok=True)
    if phase == "first":
        _fixtures()
    earlier = json.loads((state / "first-report.json").read_text()) if phase == "second" else None
    before = _snapshot(runtime)
    arguments = [
        str(runtime / "bin/python"),
        "-B",
        "/opt/knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py",
        "--workspace",
        "/state/knowledge/knowledge-workspace.yaml",
        "--package",
        "/opt/reference.whl",
        "--venv",
        str(runtime),
        "--consumer",
        "/state/consumer",
        "--profile",
        "example",
        "--runtime-mode",
        "existing",
        "--apm-mode",
        "bind",
        "--portable-hooks",
    ]
    report = _json(arguments)
    assert report["runtime"]["status"] == "verified"
    assert report["automation_registration"] == "prompt-hook"
    assert report["hooks"]["status"] == "ready"
    activity = state / "knowledge/ai/signals/compound-activity.jsonl"
    if phase == "first":
        assert report["compounding"]["reason"] == "activation-required"
        assert not activity.exists()
        # These fixture binding checks are the consumer's verification boundary.
        # Real repository compilation and live-provider checks remain separate proof.
        assert set(report["hooks"]["registrations"]) == {"codex", "claude", "copilot"}
        for registration in report["hooks"]["registrations"].values():
            assert Path(registration["path"]).is_file()
            assert all(
                "--compound-skill" in command for command in registration["commands"].values()
            )
        activation = report["compounding"]["activation"]
        assert activation["after"] == "consumer-checks"
        activated = subprocess.run(
            shlex.split(activation["command"]),
            input=json.dumps(activation["request"]),
            capture_output=True,
            text=True,
            check=False,
        )
        assert activated.returncode == 0, activated.stdout + activated.stderr
        report = _json(arguments)
    assert report["compounding"]["status"] == "ready"
    activity_digest = hashlib.sha256(activity.read_bytes()).hexdigest()
    second_bind = _json(arguments)
    assert second_bind["apm_lock"]["status"] == "current"
    assert hashlib.sha256(activity.read_bytes()).hexdigest() == activity_digest
    probe = _json(
        [
            str(runtime / "bin/python"),
            "-B",
            "/opt/filesystem_probe.py",
            "--directory",
            "/state/knowledge/ai/usage",
        ]
    )
    assert probe["status"] == "passed"
    assert _snapshot(runtime) == before
    result = {
        "status": "passed",
        "phase": phase,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "python": sys.version.split()[0],
        "runtime": report["runtime"],
        "read_only_runtime_unchanged": True,
        "uv_absent": True,
        "activation": "explicit after consumer fixture checks",
        "hook_targets": report["hooks"]["targets"],
        "activity_sha256": activity_digest,
        "probe": probe,
        "container": os.environ.get("HOSTNAME"),
        "persistence_verified": earlier is not None,
        "provider_evidence": "installed projection fixtures; no live harness or APM install",
    }
    if earlier is not None:
        assert earlier["activity_sha256"] == activity_digest
        assert earlier["runtime"]["payload_sha256"] == report["runtime"]["payload_sha256"]
        assert earlier["container"] != result["container"]
    else:
        _write(state / "first-report.json", result)
    return result


def _host(output: Path, images: list[str]) -> dict:
    root = Path(__file__).resolve().parents[2]
    output.mkdir(parents=True, exist_ok=True)
    docker = shutil.which("docker")
    uv = shutil.which("uv")
    if docker is None or uv is None:
        raise RuntimeError("This explicit acceptance test requires Docker and uv")
    _run([docker, "info", "--format", "{{.OSType}}"])
    results = []
    with tempfile.TemporaryDirectory(prefix="knowledge-container-proof-") as temporary:
        context = Path(temporary)
        _run([uv, "build", "--wheel", "--out-dir", str(context / "dist"), str(root)])
        wheel = next((context / "dist").glob("*.whl"))
        shutil.copy2(wheel, context / "reference.whl")
        shutil.copy2(__file__, context / "container_runtime_smoke.py")
        shutil.copy2(root / "tests/e2e/filesystem_probe.py", context / "filesystem_probe.py")
        shutil.copytree(
            root / "packages/knowledge-agent-pack",
            context / "knowledge-agent-pack",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        for index, base in enumerate(images):
            suffix = uuid.uuid4().hex[:12]
            image = f"agent-knowledge-runtime-proof:{suffix}"
            volume = f"agent-knowledge-runtime-proof-{suffix}"
            packages = (
                "apk add --no-cache git bash"
                if "alpine" in base
                else "apt-get update && apt-get install -y --no-install-recommends git bash "
                "&& rm -rf /var/lib/apt/lists/*"
            )
            (context / "Dockerfile").write_text(
                f"FROM {base}\nRUN {packages}\n"
                "COPY dist/ /opt/wheels/\nCOPY reference.whl /opt/reference.whl\n"
                "RUN python -m venv /opt/runtime && /opt/runtime/bin/pip install /opt/wheels/*.whl "
                "&& chmod -R a-w /opt/runtime\n"
                "COPY knowledge-agent-pack/ /opt/knowledge-agent-pack/\n"
                "COPY container_runtime_smoke.py filesystem_probe.py /opt/\n"
                "ENV PATH=/opt/runtime/bin:/usr/local/bin:/usr/bin:/bin "
                "HOME=/state/home AGENT_KNOWLEDGE_SETTINGS=/state/profiles.yaml "
                "PYTHONDONTWRITEBYTECODE=1\n"
                "USER 1000:1000\nWORKDIR /state\n"
            )
            try:
                build = _run([docker, "build", "--tag", image, str(context)])
                (output / f"image-{index}-build.log").write_text(build.stdout + build.stderr)
                _run([docker, "volume", "create", volume])
                mount = ["--mount", f"type=volume,src={volume},dst=/state"]
                _run(
                    [
                        docker,
                        "run",
                        "--rm",
                        "--user",
                        "0:0",
                        *mount,
                        image,
                        "chown",
                        "1000:1000",
                        "/state",
                    ]
                )
                phases = []
                for phase in ("first", "second"):
                    phases.append(
                        _json(
                            [
                                docker,
                                "run",
                                "--rm",
                                "--network",
                                "none",
                                *mount,
                                image,
                                "/opt/runtime/bin/python",
                                "-B",
                                "/opt/container_runtime_smoke.py",
                                "--inside",
                                phase,
                            ]
                        )
                    )
                image_id = _run(
                    [docker, "image", "inspect", "--format", "{{.Id}}", image]
                ).stdout.strip()
                result = {"base": base, "image_id": image_id, "phases": phases}
                results.append(result)
                _write(output / f"image-{index}.json", result)
            finally:
                subprocess.run([docker, "volume", "rm", volume], capture_output=True, check=False)
                subprocess.run([docker, "image", "rm", image], capture_output=True, check=False)
        result = {
            "status": "passed",
            "images": results,
            "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "setup_sha256": hashlib.sha256(
                (
                    context
                    / "knowledge-agent-pack/.apm/skills/knowledge-setup/scripts/setup_runtime.py"
                ).read_bytes()
            ).hexdigest(),
            "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "nonroot immutable runtime, trigger binding, persisted state and filesystem "
            "guards; no live harnesses",
        }
        _write(output / "report.json", result)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--image", action="append", choices=IMAGES)
    parser.add_argument("--inside", choices=("first", "second"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        result = _inside(args.inside)
    else:
        if args.output is None:
            parser.error("--output is required")
        result = _host(args.output.resolve(), args.image or list(IMAGES))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
