#!/usr/bin/env python3
"""Exercise an installed compounding skill through real harness CLIs.

The driver creates one disposable consumer per provider, records one pending
signal, and asks the provider's non-interactive interface to run the installed
``knowledge-compound`` skill.  It never touches a user's harness state or a
real knowledge repository.  Without ``--live-agent`` it performs setup and
reports the exact one-shot commands that would be used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


class HarnessSmokeFailure(RuntimeError):
    """A disposable consumer or provider invocation could not be prepared."""

    def __init__(self, message: str, *, log: Path | None = None) -> None:
        super().__init__(message)
        self.log = log


_PROVIDERS = ("codex", "claude", "copilot")
_SECRET_PATTERNS = (
    re.compile(r"(?:ghp|github_pat|sk-ant|sk-proj|sk)-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(?:token|authorization|api[_ -]?key)\s*[:=]\s*\S+"),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a disposable agent-knowledge compounding harness proof."
    )
    parser.add_argument(
        "--providers",
        default=",".join(_PROVIDERS),
        help="Comma-separated providers (codex,claude,copilot; default: all).",
    )
    parser.add_argument(
        "--live-agent",
        action="store_true",
        help="Invoke authenticated provider model requests; otherwise report one-shot commands.",
    )
    parser.add_argument("--output", type=Path, help="Write the JSON evidence report to this path.")
    parser.add_argument("--keep", action="store_true", help="Keep disposable consumers and logs.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Provider command timeout in seconds (default: 180).",
    )
    parser.add_argument(
        "--require-passed",
        action="store_true",
        help="Exit non-zero unless every requested live provider passes.",
    )
    return parser


def _root() -> Path:
    root = Path(__file__).resolve().parents[2]
    if not (root / "pyproject.toml").is_file():
        raise HarnessSmokeFailure(f"Could not locate repository root from {__file__}.")
    return root


def _provider_list(raw: str) -> tuple[str, ...]:
    values = tuple(item.strip().lower() for item in raw.split(",") if item.strip())
    if not values or len(values) != len(set(values)):
        raise ValueError("--providers must contain one or more unique provider names")
    unknown = sorted(set(values) - set(_PROVIDERS))
    if unknown:
        raise ValueError("Unsupported provider(s): " + ", ".join(unknown))
    return tuple(provider for provider in _PROVIDERS if provider in values)


def _redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[redacted]", result)
    return result


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    timeout: int,
    input_text: str | None = None,
    expected_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        log.write_text("COMMAND: " + " ".join(command) + "\nTIMEOUT\n", encoding="utf-8")
        raise HarnessSmokeFailure(
            f"Command timed out after {timeout}s: {' '.join(command)}", log=log
        ) from error
    log.write_text(
        "COMMAND: "
        + " ".join(command)
        + "\nEXIT: "
        + str(result.returncode)
        + "\n\nSTDOUT:\n"
        + _redact(result.stdout)
        + "\nSTDERR:\n"
        + _redact(result.stderr),
        encoding="utf-8",
    )
    if result.returncode != expected_exit:
        raise HarnessSmokeFailure(
            f"Command failed ({result.returncode}, expected {expected_exit}): {' '.join(command)}",
            log=log,
        )
    return result


def _run_json(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    timeout: int,
    input_text: str | None = None,
    expected_exit: int = 0,
) -> dict[str, Any]:
    result = _run(
        command,
        cwd=cwd,
        env=env,
        log=log,
        timeout=timeout,
        input_text=input_text,
        expected_exit=expected_exit,
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HarnessSmokeFailure(
            f"Command did not return JSON: {' '.join(command)}", log=log
        ) from error
    if not isinstance(value, dict):
        raise HarnessSmokeFailure(f"Command returned non-object JSON: {' '.join(command)}", log=log)
    return value


def _clean_runtime_env() -> dict[str, str]:
    """Remove organization-specific ambient settings while retaining provider auth."""
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith(("KNOWLEDGE_", "AGENT_KNOWLEDGE_")):
            env.pop(key, None)
    return env


def _copilot_identity(config: Path) -> dict[str, object]:
    """Read only non-secret account selectors from Copilot's managed config."""
    if not config.is_file():
        return {}
    try:
        text = "\n".join(
            line
            for line in config.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("//")
        )
        value = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ("lastLoggedInUser", "loggedInUsers") if key in value}


def _isolated_copilot_environment(
    consumer: Path,
    *,
    base_env: dict[str, str],
    state_directory: Path,
) -> dict[str, str]:
    """Trust one disposable consumer without mutating the user's Copilot settings.

    Copilot prompt mode loads repository hooks only for an already-trusted folder.
    ``--add-dir`` trusts skills and agents but does not establish repository-hook
    trust.  The live tests therefore use a private ``COPILOT_HOME`` containing
    only the disposable folder trust and the non-secret selector for the user's
    existing provider-owned login.
    """
    consumer = consumer.resolve()
    state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_directory.chmod(0o700)
    settings = {
        "autoUpdate": False,
        "disableAllHooks": False,
        "memory": False,
        "trustedFolders": [str(consumer)],
    }
    (state_directory / "settings.json").write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )

    source_home = Path(
        base_env.get("COPILOT_HOME")
        or str(Path(base_env.get("HOME", str(Path.home()))) / ".copilot")
    ).expanduser()
    identity = _copilot_identity(source_home / "config.json")
    if identity:
        (state_directory / "config.json").write_text(
            "// Isolated acceptance state; contains account labels, never credentials.\n"
            + json.dumps(identity, indent=2)
            + "\n",
            encoding="utf-8",
        )

    env = dict(base_env)
    env["COPILOT_HOME"] = str(state_directory.resolve())
    if identity and not env.get("COPILOT_GITHUB_TOKEN"):
        # Classic GH_TOKEN/GITHUB_TOKEN values can override a valid provider-owned
        # Copilot login. The disposable proof never needs GitHub API access.
        env.pop("GH_TOKEN", None)
        env.pop("GITHUB_TOKEN", None)
    return env


def _fresh_consumer(
    root: Path, work: Path, timeout: int
) -> tuple[Path, Path, Path, dict[str, Any]]:
    report = work / "fresh-consumer.json"
    runner = root / "tests/e2e/fresh-consumer-smoke"
    result = _run(
        [str(runner), "--keep", "--output", str(report)],
        cwd=root,
        env=_clean_runtime_env(),
        log=work / "fresh-consumer.log",
        timeout=max(timeout, 300),
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HarnessSmokeFailure(
            "Fresh consumer smoke did not return JSON.", log=work / "fresh-consumer.log"
        ) from error
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise HarnessSmokeFailure(
            "Fresh consumer smoke did not report success.", log=work / "fresh-consumer.log"
        )
    consumer = Path(str(payload["consumer_root"])).resolve()
    setup = payload.get("setup")
    launcher_value = setup.get("launcher") if isinstance(setup, dict) else None
    launcher = Path(str(launcher_value)).resolve() if launcher_value else Path()
    config = consumer / "knowledge-workspace.yaml"
    if not (consumer.is_dir() and launcher.is_file() and config.is_file()):
        raise HarnessSmokeFailure("Fresh consumer omitted the launcher or explicit config.")
    return consumer, launcher, config, payload


def _skill_path(consumer: Path) -> Path:
    candidates = (
        consumer / ".agents/skills/knowledge-compound/SKILL.md",
        consumer / ".claude/skills/knowledge-compound/SKILL.md",
        consumer / ".github/skills/knowledge-compound/SKILL.md",
    )
    for path in candidates:
        if path.is_file():
            return path
    raise HarnessSmokeFailure("Installed knowledge-compound skill is missing from the consumer.")


def _signal_body(provider: str, session_id: str, automation_id: str) -> str:
    return "\n".join(
        [
            "---",
            "schema_version: knowledge-signal.v1",
            f"id: r8-{provider}-observation",
            "created_at: 2026-09-10T09:00:00Z",
            "kind_hint: limitation",
            "origin:",
            "  workspace_id: workspace:fresh-consumer",
            "  project_path: consumer",
            "  applicable_scopes: [org:example, group:commerce, repo:orders-api]",
            "  source_ids: [example-knowledge]",
            f"  harness: {provider}",
            f"  session_id: {session_id}",
            f"  automation_id: {automation_id}",
            "evidence:",
            "  - type: file",
            f"    reference: consumer/docs/r8-{provider}-observation.md",
            "---",
            "",
            "# R8 harness observation",
            "",
            "The one-shot provider run must follow knowledge-compound and retain provenance.",
            "",
        ]
    )


def _prepare_signal(
    consumer: Path,
    launcher: Path,
    config: Path,
    provider: str,
    env: dict[str, str],
    log_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    session_id = f"r8-{provider}-session"
    automation_id = f"agent-knowledge-compound:workspace:fresh-consumer:{provider}"
    authored = consumer / f"r8-{provider}-observation.md"
    authored.write_text(_signal_body(provider, session_id, automation_id), encoding="utf-8")
    recorded = _run_json(
        [
            str(launcher),
            "--config",
            str(config),
            "signal",
            "record",
            "--request-file",
            "-",
        ],
        cwd=consumer,
        env=env,
        input_text=f"file: {authored.name}\n",
        log=log_dir / "signal-record.log",
        timeout=timeout,
    )
    listed = _run_json(
        [
            str(launcher),
            "--config",
            str(config),
            "signal",
            "list",
            "--request-file",
            "-",
        ],
        cwd=consumer,
        env=env,
        input_text="include_shared: false\n",
        log=log_dir / "signal-list.log",
        timeout=timeout,
    )
    rows = listed.get("results")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise HarnessSmokeFailure(
            "Expected exactly one pending R8 signal.", log=log_dir / "signal-list.log"
        )
    selected = rows[0]
    return {
        "id": str(selected["id"]),
        "path": str(selected["local_path"]),
        "fingerprint": str(selected["fingerprint"]),
        "session_id": session_id,
        "automation_id": automation_id,
        "recorded_path": str(recorded.get("local_path", "")),
    }


def _prompt(
    *,
    provider: str,
    consumer: Path,
    launcher: Path,
    config: Path,
    skill: Path,
    signal: dict[str, Any],
) -> str:
    start_request = json.dumps(
        {
            "action": "start",
            "workspace_id": "workspace:fresh-consumer",
            "harness": provider,
            "session_id": signal["session_id"],
            "automation_id": signal["automation_id"],
            "selected": [
                {
                    "id": signal["id"],
                    "path": signal["path"],
                    "fingerprint": signal["fingerprint"],
                }
            ],
        },
        separators=(",", ":"),
    )
    disposition = json.dumps(
        {
            "signal_id": signal["id"],
            "decision": "keep",
            "rationale": (
                "R8 is a no-write harness proof; the observation is intentionally retained "
                "as handled."
            ),
        },
        separators=(",", ":"),
    )
    drain_request = json.dumps(
        {
            "action": "drain",
            "run_id": "COPY_RUN_ID_FROM_START",
            "selected": [
                {
                    "id": signal["id"],
                    "path": signal["path"],
                    "fingerprint": signal["fingerprint"],
                }
            ],
            "dispositions": [json.loads(disposition)],
            "publication_verified": False,
        },
        separators=(",", ":"),
    )
    return f"""You are running a disposable R8 one-shot automation proof for {provider}.

Before acting, read the installed skill at {skill} and follow it. Also read the
compiled discovery instruction in {consumer}/AGENTS.md or the provider's
compiled equivalent. Use only the installed launcher {launcher}; every command
must pass the explicit config {config}. Do not use repository source paths,
ambient organization variables, network services, GitHub, PRs or files outside
{consumer}. Do not ask a human a question.

Process the one pending signal in the configured workspace. Start one compound
run with this exact JSON request (you may use a temporary request file):
{start_request}
Inspect/list the signal and then handle it as a no-write proof. Use this exact
keep disposition and guarded drain request, replacing COPY_RUN_ID_FROM_START with
the exact run_id returned by start:
{drain_request}
Finish the run with outcome `no-update` and the same disposition. Do not submit
drained counts: the tool derives actual removals from its durable records.
Use ordinary shell/file tools only for request files and the
installed CLI. Confirm the final compound status is inactive, activity contains
the harness/session/automation provenance, and the selected signal is drained.
Report the commands and final status briefly. Do not edit canonical knowledge.
"""


def _provider_command(provider: str, prompt: str, consumer: Path) -> list[str]:
    if provider == "codex":
        return [
            "codex",
            "exec",
            "--json",
            "--ephemeral",
            "--dangerously-bypass-approvals-and-sandbox",
            "--cd",
            str(consumer),
            prompt,
        ]
    if provider == "claude":
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--no-session-persistence",
            "--dangerously-skip-permissions",
            "--add-dir",
            str(consumer),
        ]
    return [
        "copilot",
        "-p",
        prompt,
        "--model",
        "auto",
        "--auto-tier",
        "efficiency",
        "--allow-all",
        "--no-auto-update",
        "--silent",
        "-C",
        str(consumer),
    ]


def _display_command(command: list[str], prompt: str) -> list[str]:
    """Hide the long prompt while preserving its actual argument position."""
    return ["<prompt>" if item == prompt else item for item in command]


def _classify_failure(output: str, returncode: int | None = None) -> tuple[str, str]:
    lowered = output.casefold()
    if any(
        term in lowered
        for term in ("usage limit", "rate limit", "quota", "credits exhausted", "too many requests")
    ):
        return "usage-limited", "Provider account usage or rate limit prevented the model turn."
    if any(
        term in lowered
        for term in (
            "401",
            "unauthorized",
            "authentication",
            "authenticate",
            "login required",
            "not logged in",
            "access token has expired",
            "no authentication",
        )
    ):
        return "auth-required", "Provider authentication is missing or expired."
    if returncode is None:
        return "timeout", "Provider one-shot invocation timed out."
    return "failed", f"Provider one-shot invocation failed with exit {returncode}."


def _session_hint(output: str) -> str | None:
    patterns = (
        r'"(?:session_id|thread_id|conversation_id)"\s*:\s*"([^"]+)"',
        r"(?:session|thread|conversation)[ _-](?:id)?\s*[:=]\s*([A-Za-z0-9_-]+)",
    )
    for pattern in patterns:
        found = re.search(pattern, output, re.IGNORECASE)
        if found:
            return found.group(1)
    return None


def _verify_compound(
    launcher: Path,
    config: Path,
    provider: str,
    signal: dict[str, Any],
    env: dict[str, str],
    log_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    status = _run_json(
        [str(launcher), "--config", str(config), "compound", "--request-file", "-"],
        cwd=config.parent,
        env=env,
        input_text='{"action":"status"}\n',
        log=log_dir / "compound-status.log",
        timeout=timeout,
    )
    activity_path = Path(str(status.get("activity_path", "")))
    events = status.get("events", [])
    if not isinstance(events, list):
        events = []
    matching = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("harness") == provider
        and event.get("session_id") == signal["session_id"]
        and event.get("automation_id") == signal["automation_id"]
    ]
    signal_present = Path(signal["path"]).exists()
    return {
        "status": "passed"
        if not status.get("active") and matching and not signal_present
        else "failed",
        "active": bool(status.get("active")),
        "activity_path": str(activity_path),
        "provenance_events": len(matching),
        "signal_present": signal_present,
        "automation_id": signal["automation_id"],
        "session_id": signal["session_id"],
    }


def _run_provider(
    root: Path,
    provider: str,
    *,
    live: bool,
    keep: bool,
    timeout: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    work = Path(tempfile.mkdtemp(prefix=f"agent-knowledge-r8-{provider}."))
    logs = work / "logs"
    logs.mkdir()
    result: dict[str, Any] = {"provider": provider, "work_root": str(work), "status": "unknown"}
    consumer_path: Path | None = None
    try:
        provider_path = shutil.which(provider)
        if provider_path is None:
            result.update({"status": "unavailable", "reason": "CLI is not installed."})
            return result
        consumer, launcher, config, setup = _fresh_consumer(root, work, timeout)
        consumer_path = consumer
        skill = _skill_path(consumer)
        env = _clean_runtime_env()
        signal = _prepare_signal(consumer, launcher, config, provider, env, logs, timeout)
        prompt = _prompt(
            provider=provider,
            consumer=consumer,
            launcher=launcher,
            config=config,
            skill=skill,
            signal=signal,
        )
        command = _provider_command(provider, prompt, consumer)
        result.update(
            {
                "consumer": str(consumer),
                "launcher": str(launcher),
                "config": str(config),
                "skill": str(skill),
                "setup_revision": setup.get("revision"),
                "one_shot_command": _display_command(command, prompt),
                "live": live,
                "signal_id": signal["id"],
            }
        )
        if not live:
            result.update(
                {"status": "not-run", "reason": "Pass --live-agent to invoke the provider."}
            )
            return result
        provider_log = logs / "provider.log"
        try:
            provider_result = _run(
                command,
                cwd=consumer,
                env=env,
                log=provider_log,
                timeout=timeout,
            )
        except HarnessSmokeFailure as error:
            contents = (
                provider_log.read_text(encoding="utf-8") if provider_log.exists() else str(error)
            )
            status, reason = _classify_failure(contents, None if "timed out" in str(error) else 1)
            result.update(
                {"status": status, "reason": reason, "log": str(error.log or provider_log)}
            )
            return result
        output = provider_result.stdout + "\n" + provider_result.stderr
        verification = _verify_compound(
            launcher,
            config,
            provider,
            signal,
            env,
            logs,
            timeout,
        )
        skill_text = skill.read_text(encoding="utf-8")
        observed = str(skill) in output or "knowledge-compound" in output.casefold()
        result.update(
            {
                **verification,
                "provider_session_hint": _session_hint(output),
                "skill_contract_present": "knowledge-compound" in skill_text,
                "skill_read_observed": observed,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        )
        return result
    except HarnessSmokeFailure as error:
        result.update({"status": "setup-failed", "reason": str(error)})
        if error.log is not None:
            result["log"] = str(error.log)
        return result
    finally:
        result.setdefault("elapsed_ms", round((time.perf_counter() - started) * 1000, 3))
        if not keep:
            if consumer_path is not None and consumer_path.parent.name.startswith(
                "agent-knowledge-fresh-consumer."
            ):
                shutil.rmtree(consumer_path.parent, ignore_errors=True)
            shutil.rmtree(work, ignore_errors=True)


def run_smoke(
    *, providers: tuple[str, ...], live: bool, keep: bool, timeout: int
) -> dict[str, Any]:
    root = _root()
    results = [
        _run_provider(root, provider, live=live, keep=keep, timeout=timeout)
        for provider in providers
    ]
    statuses = {str(item.get("status")) for item in results}
    overall = "passed" if statuses and statuses == {"passed"} else "partial"
    if not live and statuses == {"not-run"}:
        overall = "ready"
    return {
        "schema": "harness-agent-smoke.v1",
        "status": overall,
        "revision": _revision(root),
        "live_agent": live,
        "providers": results,
        "semantics": {
            "one_consumer_per_provider": True,
            "explicit_config": True,
            "installed_skill_required": True,
            "no_publication": True,
            "no_real_scheduler_mutation": True,
            "provider_failures_are_classified": True,
        },
    }


def _revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        providers = _provider_list(args.providers)
        if args.timeout < 1 or args.timeout > 1800:
            raise ValueError("--timeout must be between 1 and 1800 seconds")
        report = run_smoke(
            providers=providers,
            live=args.live_agent,
            keep=args.keep,
            timeout=args.timeout,
        )
    except (HarnessSmokeFailure, OSError, ValueError) as error:
        report = {
            "schema": "harness-agent-smoke.v1",
            "status": "error",
            "diagnostic": str(error),
        }
        rendered = json.dumps(report, indent=2) + "\n"
        print(rendered, end="")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        return 1
    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.require_passed and report["status"] != "passed":
        return 1
    return 0 if report["status"] in {"passed", "ready", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
