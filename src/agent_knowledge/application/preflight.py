"""Coordinate lightweight local launch checks using existing doctor/profile APIs."""

import os
import sys
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from agent_knowledge.application.diagnostics import Diagnostic
from agent_knowledge.application.doctor import DoctorCheck, run_doctor
from agent_knowledge.domain.preflight import parse_preflight_request
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.configuration import Workspace, resolve_workspace
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.preflight import (
    ExecutionObservation,
    available_executable,
    executable_path,
    observe_execution,
    registration_availability,
)


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Report independent readiness without turning registration into native proof."""

    schema_version: str
    status: str
    mode: str
    execution: ExecutionObservation
    runtime: dict[str, object]
    routes: dict[str, object]
    hooks: dict[str, object]
    readiness: dict[str, str]
    checks: tuple[DoctorCheck, ...]
    diagnostics: tuple[Diagnostic, ...]
    selection: dict[str, object] | None
    environment_declaration: dict[str, object] | None
    exit_code: int
    write_scope: str = (
        "Only this preflight process and its inherited permissions; "
        "outer harness sandbox and another launch remain unverified."
    )


def _absolute(value: str | None, field: str) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        raise ValidationError(
            "invalid-path", field, "Use an absolute path in this execution environment."
        )
    return path


def _routes(workspace: Workspace | None) -> dict[str, object]:
    if workspace is None:
        return {}
    storage = workspace.signal_storage
    return {
        "workspace_id": workspace.definition.workspace_id,
        "config": str(workspace.path),
        "registry": str(workspace.selection.settings) if workspace.selection.settings else None,
        "sources": [
            {"id": source.id, "root": str(source.root), "catalog": str(source.catalog_path)}
            for source in workspace.sources
        ],
        "signal_root": str(storage.signal_root) if storage else None,
        "scaffold_root": str(storage.scaffold_root) if storage else None,
        "code_root": str(storage.code_root) if storage else None,
        "receipt_root": str(workspace.receipts.directory),
    }


def _environment_declaration(workspace: Workspace | None) -> dict[str, object] | None:
    environment = workspace.environment if workspace else None
    return (
        {
            "file": str(environment.file),
            "variables": [
                {"from_env": item.from_env, "expose_as": item.expose_as}
                for item in environment.variables
            ],
        }
        if environment
        else None
    )


def run_preflight(
    config_path: Path | None,
    request: object,
    *,
    settings: Path | None = None,
    profile: str | None = None,
) -> PreflightResult:
    """Observe only; explicit write mode reuses doctor's temporary-file probes."""
    parsed = parse_preflight_request(request)
    expected_venv = _absolute(parsed.expected_venv, "expected_venv")
    consumer = _absolute(parsed.consumer, "consumer")
    execution = observe_execution()
    diagnostics: list[Diagnostic] = []
    readiness: dict[str, str] = {
        "execution": "unverified",
        "runtime": "ready",
        "path_launchers": "ready",
        "provider_launcher": "not-requested",
        "hook_registration": "unverified",
        "native_trust": "unverified",
        "hook_firing": "unverified",
        "credential_activation": "unverified",
        "harness_sandbox": "unverified",
    }
    exit_code = 0

    def failed(
        code: str, field: str, message: str, remediation: str, *, exit_status: int = 2
    ) -> None:
        nonlocal exit_code
        exit_code = max(exit_code, exit_status)
        diagnostics.append(Diagnostic(code, field, message, remediation))

    def same_route(first: Path, second: Path) -> bool:
        try:
            return first.resolve() == second.resolve()
        except (OSError, RuntimeError):
            failed(
                "runtime-path-unavailable",
                "runtime",
                "A runtime path cannot be resolved safely.",
                "Inspect path permissions and symlink loops before relaunching.",
            )
            return False

    if parsed.expected_execution is not None:
        if execution.observed != parsed.expected_execution:
            readiness["execution"] = "not-ready"
            failed(
                "execution-unverified" if execution.observed == "unknown" else "execution-mismatch",
                "expected_execution",
                "Observed tool execution does not establish the requested target.",
                "Enter the established target route and rerun preflight there; "
                "do not infer the outer harness location.",
            )
        else:
            readiness["execution"] = "ready"
    workspace = None
    # Doctor supplies normal structured diagnostics if configuration is unavailable.
    with suppress(ValidationError, AdapterError):
        workspace = resolve_workspace(config=config_path, settings=settings, profile=profile)
    selected_venv = (
        Path(workspace.definition.setup.venv)
        if workspace and workspace.definition.setup and workspace.definition.setup.venv
        else None
    )
    current_venv = Path(sys.prefix)
    target_venv = expected_venv or selected_venv or current_venv
    if (
        expected_venv and selected_venv and not same_route(expected_venv, selected_venv)
    ) or not same_route(current_venv, target_venv):
        readiness["runtime"] = "not-ready"
        failed(
            "runtime-venv-mismatch",
            "expected_venv",
            "Running interpreter does not match the requested and configured runtime route.",
            "Use the selected runtime's installed launcher; prepare changed "
            "runtime/profile paths explicitly.",
        )
    bin_dir = target_venv / ("Scripts" if os.name == "nt" else "bin")
    launchers: dict[str, object] = {}
    for name in ("agent-knowledge", "agent-knowledge-hook"):
        expected = bin_dir / (name + ".exe" if os.name == "nt" else name)
        actual = executable_path(name)
        available = available_executable(expected)
        matches = actual is not None and same_route(Path(actual), expected)
        launchers[name] = {
            "expected": str(expected),
            "available": available,
            "path_launcher": actual,
            "path_matches": matches,
        }
        if not available or not matches:
            readiness["path_launchers"] = "not-ready"
            failed(
                "launcher-route-mismatch",
                name,
                "Selected executable is unavailable or PATH resolves another launcher.",
                "Preserve the selected runtime and prepend its executable "
                "directory in the actual harness launch environment.",
            )
    provider_path = executable_path(parsed.provider) if parsed.provider else None
    if parsed.provider:
        readiness["provider_launcher"] = "ready" if provider_path else "not-ready"
        if provider_path is None:
            failed(
                "provider-launcher-unavailable",
                "provider",
                "The requested harness executable is not on this process's PATH.",
                "Use the consumer's existing provider installation/launcher; "
                "preflight does not install it.",
            )
    hooks = registration_availability(consumer, parsed.provider)
    if hooks["file_available"] is False:
        failed(
            "hook-registration-unavailable",
            "consumer",
            "The provider registration file is absent at the selected consumer.",
            "Use the owning setup/APM bind workflow, then verify native "
            "registration, trust and delivery independently.",
        )
    probe_mode = "read" if parsed.mode == "write" and exit_code else parsed.mode
    doctor_request: dict[str, object] = {"mode": probe_mode}
    if parsed.expected_workspace_id is not None:
        doctor_request["expected_workspace_id"] = parsed.expected_workspace_id
    checked = run_doctor(config_path, doctor_request, settings=settings, profile=profile)
    exit_code = max(exit_code, checked.exit_code)
    diagnostics.extend(checked.diagnostics)
    readiness.update(
        read=checked.readiness.read,
        write=checked.readiness.write,
        receipts=checked.readiness.receipts,
        environment=checked.readiness.environment,
    )
    if checked.runtime.package_version is None:
        readiness["runtime"] = "not-ready"
    if (
        workspace is not None
        and checked.selection is not None
        and checked.selection.get("effective_fingerprint") != workspace.fingerprint
    ):
        failed(
            "context-changed",
            "selection",
            "Configuration changed between route and readiness checks.",
            "Repeat preflight with the same explicit selector before launching.",
        )
    if parsed.mode == "write" and any(readiness[name] != "ready" for name in ("write", "receipts")):
        failed(
            "write-readiness-unverified",
            "mode",
            "Requested signal and receipt writes were not both verified.",
            "Check existing storage and the current tool's permissions; rerun "
            "explicit write preflight in the intended harness sandbox.",
        )
    declaration = _environment_declaration(workspace)
    if workspace is not None:
        try:
            current = resolve_workspace(config=config_path, settings=settings, profile=profile)
        except (ValidationError, AdapterError):
            current = None
        if (
            current is None
            or current.fingerprint != workspace.fingerprint
            or _environment_declaration(current) != declaration
        ):
            failed(
                "context-changed",
                "selection",
                "Selected configuration or credential declaration changed during preflight.",
                "Repeat the same selected preflight; do not launch from this stale report.",
            )
    return PreflightResult(
        schema_version="knowledge-preflight.v1",
        status="ok" if exit_code == 0 else "error",
        mode=parsed.mode,
        execution=execution,
        runtime={
            "package_version": checked.runtime.package_version,
            "interpreter": checked.runtime.interpreter,
            "invoked_launcher": checked.runtime.launcher,
            "current_venv": str(current_venv),
            "selected_venv": str(selected_venv) if selected_venv else None,
            "expected_venv": str(expected_venv) if expected_venv else None,
            "launchers": launchers,
            "provider": parsed.provider,
            "provider_launcher": provider_path,
            "provider_executed": False,
        },
        routes=_routes(workspace),
        hooks=hooks,
        readiness=readiness,
        checks=checked.checks,
        diagnostics=tuple(diagnostics),
        selection=checked.selection,
        environment_declaration=declaration,
        exit_code=exit_code,
    )
