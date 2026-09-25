"""Diagnose this invocation without repairing configuration or scanning knowledge."""

import os
import secrets
import stat
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Literal

from agent_knowledge.application.diagnostics import Diagnostic, from_error
from agent_knowledge.domain.validation import ValidationError, read_identifier, read_mapping
from agent_knowledge.infrastructure.configuration import (
    ReceiptStorage,
    effective_configuration,
    resolve_workspace,
    validate_signal_storage,
)
from agent_knowledge.infrastructure.environment import inspect_environment
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import check_directory, open_directory

ReadinessState = Literal["ready", "not-ready", "unverified", "not-configured"]
CheckStatus = Literal["passed", "failed", "unverified", "skipped"]


@dataclass(frozen=True)
class RuntimeInfo:
    """Report the package and paths used by this process, never shell guesses."""

    package_version: str | None
    interpreter: str
    launcher: str | None
    module_path: str


@dataclass(frozen=True)
class DoctorCheck:
    """Describe one bounded readiness check and what it actually established."""

    name: str
    status: CheckStatus
    message: str
    path: str | None = None


@dataclass(frozen=True)
class Readiness:
    """Keep read access distinct from the optional signal-write capability."""

    read: ReadinessState
    write: ReadinessState
    receipts: ReadinessState = "unverified"
    environment: ReadinessState = "not-configured"


@dataclass(frozen=True)
class DoctorResult:
    """Return useful diagnostics even when configuration cannot be loaded."""

    runtime: RuntimeInfo
    workspace_id: str | None
    config_path: str | None
    checks: tuple[DoctorCheck, ...]
    readiness: Readiness
    diagnostics: tuple[Diagnostic, ...]
    exit_code: int
    selection: dict[str, object] | None = None
    configuration: dict[str, object] | None = None


@dataclass(frozen=True)
class _Request:
    mode: Literal["read", "write"]
    expected_workspace_id: str | None


def _parse_request(value: object) -> _Request:
    fields = read_mapping(value, "", set(), {"mode", "expected_workspace_id"})
    mode = fields.get("mode", "read")
    if mode not in ("read", "write"):
        raise ValidationError("invalid-value", "mode", "Expected read or write.")
    expected = (
        read_identifier(fields["expected_workspace_id"], "expected_workspace_id")
        if "expected_workspace_id" in fields
        else None
    )
    return _Request("write" if mode == "write" else "read", expected)


def _runtime() -> RuntimeInfo:
    try:
        version = metadata.version("agent-knowledge-scaffold")
    except metadata.PackageNotFoundError:
        version = None
    invocation = sys.argv[0] if sys.argv else ""
    launcher = str(Path(invocation).absolute()) if invocation not in {"", "-", "-c"} else None
    return RuntimeInfo(version, sys.executable, launcher, str(Path(__file__).absolute()))


def _probe(directory: Path) -> tuple[tuple[DoctorCheck, ...], tuple[Diagnostic, ...]]:
    """Write only through a validated pinned directory and retain unsafe replacements."""
    name = f".agent-knowledge-doctor-{secrets.token_hex(16)}"
    probe_path = str(directory / name)
    checks: list[DoctorCheck] = []
    diagnostics: list[Diagnostic] = []
    with open_directory(directory) as directory_fd:
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
        except OSError as error:
            raise AdapterError(
                "write-probe-failed", probe_path, "Could not create the storage probe."
            ) from error
        identity: os.stat_result | None = None
        try:
            identity = os.fstat(descriptor)
            if os.write(descriptor, b"1") != 1:
                raise OSError("Incomplete probe write.")
            os.fsync(descriptor)
        except OSError:
            checks.append(DoctorCheck("write-probe", "failed", "Probe writing failed.", probe_path))
            diagnostics.append(
                Diagnostic(
                    "write-probe-failed",
                    probe_path,
                    "Could not write the storage probe.",
                    "Check the selected directory's permissions and available storage.",
                )
            )
        else:
            checks.append(
                DoctorCheck("write-probe", "passed", "Probe writing succeeded.", probe_path)
            )
        finally:
            try:
                os.close(descriptor)
            except OSError:
                checks.append(
                    DoctorCheck("probe-close", "failed", "Probe handle close failed.", probe_path)
                )
                diagnostics.append(
                    Diagnostic(
                        "probe-close-failed",
                        probe_path,
                        "The probe handle could not be closed; write readiness is not confirmed.",
                        "Inspect the selected storage's availability before retrying.",
                    )
                )
        try:
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                identity is None
                or not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)
            ):
                raise OSError("Probe identity changed.")
            os.unlink(name, dir_fd=directory_fd)
        except OSError:
            checks.append(
                DoctorCheck("probe-cleanup", "failed", "Probe cleanup failed.", probe_path)
            )
            diagnostics.append(
                Diagnostic(
                    "probe-cleanup-failed",
                    probe_path,
                    "The probe could not be safely removed; write readiness is not confirmed.",
                    "Inspect the reported probe path and remove it manually if it is the probe.",
                )
            )
        else:
            checks.append(DoctorCheck("probe-cleanup", "passed", "Probe removed.", probe_path))
    return tuple(checks), tuple(diagnostics)


def _receipt_readiness(
    storage: ReceiptStorage, mode: Literal["read", "write"]
) -> tuple[ReadinessState, tuple[DoctorCheck, ...], tuple[Diagnostic, ...]]:
    """Check the selected usage root without creating it or changing collection policy."""
    directory = storage.directory
    collection = "enabled" if storage.enabled else "disabled"
    policy = DoctorCheck(
        "receipt-collection",
        "passed",
        f"Diagnostic collection is {collection}; retention is {storage.retention_days} days. "
        "Compounding archives and durable drain evidence remain required.",
        str(directory),
    )
    try:
        check_directory(directory)
    except AdapterError as error:
        if error.code == "directory-missing":
            return (
                "unverified",
                (
                    policy,
                    DoctorCheck(
                        "receipt-storage",
                        "unverified",
                        "Usage directory is not created yet; write readiness is unverified.",
                        str(directory),
                    ),
                ),
                (),
            )
        return (
            "not-ready",
            (policy, DoctorCheck("receipt-storage", "failed", error.message, str(directory))),
            (from_error(error),),
        )
    if mode == "read":
        return (
            "unverified",
            (
                policy,
                DoctorCheck(
                    "receipt-storage", "passed", "Usage directory is readable.", str(directory)
                ),
                DoctorCheck(
                    "receipt-write-probe", "unverified", "Read mode does not probe usage writes."
                ),
            ),
            (),
        )
    try:
        checks, diagnostics = _probe(directory)
    except AdapterError as error:
        return (
            "not-ready",
            (policy, DoctorCheck("receipt-write-probe", "failed", error.message, str(directory))),
            (from_error(error),),
        )
    return (
        "not-ready" if diagnostics else "ready",
        (
            policy,
            *(
                DoctorCheck(f"receipt-{check.name}", check.status, check.message, check.path)
                for check in checks
            ),
        ),
        diagnostics,
    )


def run_doctor(
    config_path: Path | None,
    request: object,
    *,
    settings: Path | None = None,
    profile: str | None = None,
) -> DoctorResult:
    """Check runtime, config and roots; only explicit write mode makes a temporary probe."""
    selection: dict[str, object] | None = None
    configuration: dict[str, object] | None = None
    runtime = _runtime()
    checks: list[DoctorCheck] = []
    diagnostics: list[Diagnostic] = []
    exit_code = 0
    workspace_id: str | None = None
    resolved_config = str(config_path.absolute()) if config_path is not None else None
    read: ReadinessState = "not-ready"
    write: ReadinessState = "not-configured"
    receipts: ReadinessState = "unverified"
    environment: ReadinessState = "not-configured"

    def finish() -> DoctorResult:
        return DoctorResult(
            runtime,
            workspace_id,
            resolved_config,
            tuple(checks),
            Readiness(read, write, receipts, environment),
            tuple(diagnostics),
            exit_code,
            selection,
            configuration,
        )

    def failed(error: ValidationError | AdapterError, name: str) -> None:
        nonlocal exit_code
        exit_code = max(exit_code, error.exit_code if isinstance(error, AdapterError) else 2)
        diagnostics.append(from_error(error))
        checks.append(DoctorCheck(name, "failed", error.message, error.path or None))

    if runtime.package_version is None:
        failed(
            AdapterError(
                "package-metadata-unavailable",
                "runtime",
                "Installed package metadata is unavailable.",
            ),
            "runtime",
        )
    else:
        checks.append(DoctorCheck("runtime", "passed", "Installed package metadata is available."))
    try:
        parsed = _parse_request(request)
    except ValidationError as error:
        failed(error, "request")
        return finish()
    try:
        workspace = resolve_workspace(config=config_path, settings=settings, profile=profile)
        selection = workspace.selection.summary(workspace.fingerprint)
        configuration = effective_configuration(workspace)
    except (ValidationError, AdapterError) as error:
        failed(error, "configuration")
        return finish()
    workspace_id = workspace.definition.workspace_id
    resolved_config = str(workspace.path)
    checks.append(
        DoctorCheck("configuration", "passed", "Workspace configuration is valid.", resolved_config)
    )
    checks.append(
        DoctorCheck("catalog", "passed", "Configured catalogs and identifiers are valid.")
    )
    if workspace.environment is None:
        checks.append(
            DoctorCheck("environment", "skipped", "Profile environment is not configured.")
        )
    else:
        try:
            inspection = inspect_environment(workspace.environment)
        except (ValidationError, AdapterError) as error:
            environment = "not-ready"
            failed(error, "environment-file")
        else:
            checks.append(
                DoctorCheck(
                    "environment-file",
                    "passed",
                    "Profile environment file is private and valid.",
                    str(workspace.environment.file),
                )
            )
            missing = False
            for variable in workspace.environment.variables:
                if variable.from_env in inspection.names:
                    checks.append(
                        DoctorCheck(
                            f"environment:{variable.label}",
                            "passed",
                            f"Source variable {variable.from_env} is available.",
                            str(workspace.environment.file),
                        )
                    )
                    continue
                missing = True
                failed(
                    ValidationError(
                        "environment-variable-missing",
                        f"environment.variables.{variable.label}.from_env",
                        f"Source variable {variable.from_env} is not assigned.",
                    ),
                    f"environment:{variable.label}",
                )
            environment = "not-ready" if missing else "ready"
    if parsed.expected_workspace_id is not None and parsed.expected_workspace_id != workspace_id:
        failed(
            ValidationError(
                "workspace-mismatch",
                "expected_workspace_id",
                f"Expected workspace {parsed.expected_workspace_id}; selected {workspace_id}.",
            ),
            "workspace-identity",
        )
        return finish()
    receipts, receipt_checks, receipt_diagnostics = _receipt_readiness(
        workspace.receipts, parsed.mode
    )
    checks.extend(receipt_checks)
    diagnostics.extend(receipt_diagnostics)
    if receipt_diagnostics:
        exit_code = max(exit_code, 3)
    sources_ready = True
    for source in workspace.sources:
        try:
            check_directory(source.root)
        except AdapterError as error:
            sources_ready = False
            failed(error, f"source:{source.id}")
        else:
            checks.append(
                DoctorCheck(
                    f"source:{source.id}", "passed", "Source root is readable.", str(source.root)
                )
            )
    read = "ready" if sources_ready and runtime.package_version is not None else "not-ready"
    try:
        storage = validate_signal_storage(workspace)
    except (ValidationError, AdapterError) as error:
        write = "not-ready"
        failed(error, "signal-storage")
        return finish()
    if storage is None:
        checks.append(DoctorCheck("signal-storage", "skipped", "Signal storage is not configured."))
        if parsed.mode == "write":
            failed(
                ValidationError(
                    "signal-storage-required",
                    "signal_storage",
                    "Write mode requires signal storage.",
                ),
                "write-probe",
            )
        return finish()
    write = "unverified"
    checks.append(
        DoctorCheck(
            "signal-storage",
            "passed",
            "Storage paths are separated from canonical roots.",
            str(storage.signal_root),
        )
    )
    if parsed.mode == "read":
        checks.append(
            DoctorCheck("write-probe", "unverified", "Read mode does not probe signal writes.")
        )
        return finish()
    try:
        probe_checks, probe_diagnostics = _probe(storage.signal_root)
    except AdapterError as error:
        write = "not-ready"
        failed(error, "write-probe")
        return finish()
    checks.extend(probe_checks)
    diagnostics.extend(probe_diagnostics)
    write = "not-ready" if probe_diagnostics else "ready"
    if probe_diagnostics:
        exit_code = max(exit_code, 3)
    return finish()
