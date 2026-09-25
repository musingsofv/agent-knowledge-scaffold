"""Interleave real CLI processes with independent profile sources and inboxes."""

import json
import os
import subprocess
import sys
from pathlib import Path

from agent_knowledge.infrastructure.documents import dump_document, parse_document
from tests.factories import knowledge_data
from tests.integration.application.test_signals import signal_workspace


def test_two_processes_keep_sources_signals_and_receipts_separate(tmp_path: Path) -> None:
    configs = {}
    for name in ("personal", "work"):
        area = tmp_path / name
        area.mkdir()
        config, signal = signal_workspace(area)
        configs[name] = config
        document = area / "scaffold/knowledge/rule.md"
        document.write_bytes(dump_document(knowledge_data(title=f"{name} guidance"), f"# {name}\n"))
        parsed = parse_document(signal.read_bytes())
        parsed.metadata["origin"].update(harness="codex", session_id="same-opaque-session")
        signal.write_bytes(dump_document(parsed.metadata, f"# {name} observation\n"))
        (config.parent / "ai/usage").mkdir(parents=True)
    registry = {
        "schema_version": "knowledge-profiles.v1",
        "default_profile": "work",
        "profiles": {name: {"config": str(config)} for name, config in configs.items()},
    }
    settings = tmp_path / "profiles.yaml"
    settings.write_text(json.dumps(registry))
    env = {**os.environ, "HOME": str(tmp_path)}

    def together(command: list[str], request: object):
        processes = {}
        for name in configs:
            processes[name] = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "agent_knowledge.entrypoints.cli.main",
                    "--settings",
                    str(settings),
                    "--profile",
                    name,
                    *command,
                    "--request-file",
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=tmp_path,
            )
        results = {}
        for name, process in processes.items():
            stdout, stderr = process.communicate(json.dumps(request), timeout=30)
            assert process.returncode == 0, (stdout, stderr)
            assert not stderr
            results[name] = json.loads(stdout)
            assert results[name]["selection"]["profile"] == name
        return results

    found = together(["search"], {})
    for name, result in found.items():
        assert [item["title"] for item in result["results"]] == [f"{name} guidance"]
        assert str(tmp_path / name) in result["receipt"]["path"]
    recorded = together(["signal", "record"], {"file": "observation.md"})
    registry["default_profile"] = "personal"
    settings.write_text(json.dumps(registry))
    before = settings.read_bytes()
    listed = together(["signal", "list"], {"session_id": "same-opaque-session"})
    for name, result in listed.items():
        assert len(result["results"]) == 1
        assert result["results"][0]["local_path"] == recorded[name]["local_path"]
        assert Path(recorded[name]["local_path"]).read_text().endswith(f"# {name} observation\n")
    assert settings.read_bytes() == before
