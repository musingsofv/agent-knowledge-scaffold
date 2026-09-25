"""Expose explicit structured requests through the installed local launcher."""

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from time import monotonic
from typing import Never

import yaml

from agent_knowledge.application.compounding import compound_result
from agent_knowledge.application.diagnostics import Diagnostic, from_error
from agent_knowledge.application.discovery import catalog_result, context_result
from agent_knowledge.application.doctor import run_doctor
from agent_knowledge.application.invocation import invocation_context, resolve_compound_invocation
from agent_knowledge.application.retrieval import inspect_result, search_result
from agent_knowledge.application.signals import list_signal_result, record_signal_result
from agent_knowledge.application.usage import export_usage, maintain_usage
from agent_knowledge.application.validation import validate_result
from agent_knowledge.domain.invocation import InvocationContext, validate_invocation
from agent_knowledge.domain.validation import ValidationError, read_mapping
from agent_knowledge.entrypoints.cli.contracts import describe
from agent_knowledge.infrastructure.configuration import Workspace, resolve_workspace
from agent_knowledge.infrastructure.documents import load_mapping
from agent_knowledge.infrastructure.errors import AdapterError
from agent_knowledge.infrastructure.filesystem import read_bytes, resolve_path
from agent_knowledge.infrastructure.profiles import list_profiles, settings_path
from agent_knowledge.infrastructure.receipts import record_terminal

_REQUEST_BYTES = 1048576


class Parser(argparse.ArgumentParser):
    """Keep argument failures in the same structured diagnostic channel."""

    def error(self, message: str) -> Never:
        """Convert invalid command syntax into a machine-readable input error."""
        raise ValidationError("invalid-arguments", "arguments", message)


def _parser() -> Parser:
    """Define only implemented commands, with global options before the command."""
    parser = Parser(prog="agent-knowledge", description="Explicit local knowledge discovery.")
    parser.add_argument("--config", help="Explicit workspace YAML; bypass profile settings.")
    parser.add_argument("--profile", help="Exact named knowledge profile.")
    parser.add_argument(
        "--settings",
        help=(
            "Profile registry; overrides AGENT_KNOWLEDGE_SETTINGS or "
            "~/.config/agent-knowledge/config.yaml."
        ),
    )
    parser.add_argument("--output", choices=("json", "text"), default="json")
    parser.add_argument("--harness", help="Caller-supplied claude, codex or copilot provenance.")
    parser.add_argument("--session-id", help="Exact opaque hook session handle; omit if unknown.")
    parser.add_argument("--compound-run-id", help="Recorded run belonging to this workspace.")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "describe",
        "context",
        "catalog",
        "doctor",
        "search",
        "inspect",
        "validate",
        "compound",
    ):
        child = commands.add_parser(command)
        child.add_argument("--request-file", help="JSON/YAML request path or - for explicit stdin.")
    signal = commands.add_parser("signal")
    signal_commands = signal.add_subparsers(required=True)
    for command in ("record", "list"):
        child = signal_commands.add_parser(command)
        child.set_defaults(command=f"signal {command}")
        child.add_argument("--request-file", help="JSON/YAML request path or - for explicit stdin.")
    profiles = commands.add_parser("profiles")
    profile_commands = profiles.add_subparsers(required=True)
    listing = profile_commands.add_parser("list")
    listing.set_defaults(command="profiles list", request_file=None)
    usage = commands.add_parser("usage")
    usage_commands = usage.add_subparsers(required=True)
    export = usage_commands.add_parser("export")
    export.set_defaults(command="usage export")
    export.add_argument("--request-file", help="JSON/YAML request path or - for explicit stdin.")
    return parser


def _request(path: str | None) -> dict[str, object]:
    """Read bounded request bytes only when an explicit input is supplied."""
    if path is None:
        return {}
    if path == "-":
        try:
            data = sys.stdin.buffer.read(_REQUEST_BYTES + 1)
        except OSError as error:
            raise AdapterError(
                "request-read-failed", "stdin", "Unable to read request input."
            ) from error
    else:
        data = read_bytes(resolve_path(path, base=Path.cwd()), max_bytes=_REQUEST_BYTES)
    return load_mapping(data, path=path, max_bytes=_REQUEST_BYTES)


def _validate_selectors(args: argparse.Namespace) -> None:
    if args.config is not None and (args.profile is not None or args.settings is not None):
        raise ValidationError(
            "invalid-arguments", "config", "Use --config or --profile/--settings, not both."
        )
    if args.command == "describe" and any(
        value is not None for value in (args.config, args.profile, args.settings)
    ):
        raise ValidationError(
            "invalid-arguments", "describe", "Use context or doctor to check a selection."
        )
    if args.command == "profiles list" and (args.config is not None or args.profile is not None):
        raise ValidationError(
            "invalid-arguments",
            "profiles",
            "Profile listing accepts --settings, not a workspace selector.",
        )


def _resolve(args: argparse.Namespace) -> Workspace:
    return resolve_workspace(
        config=Path(args.config) if args.config is not None else None,
        settings=Path(args.settings) if args.settings is not None else None,
        profile=args.profile,
    )


def _run(command: str, workspace: Workspace, request: object) -> tuple[dict[str, object], int]:
    """Dispatch the same effective snapshot to every configured operation."""
    match command:
        case "context":
            return dict(context_result(workspace, request)), 0
        case "catalog":
            return dict(catalog_result(workspace, request)), 0
        case "search":
            return dict(search_result(workspace, request)), 0
        case "inspect":
            return dict(inspect_result(workspace, request)), 0
        case "validate":
            validation = validate_result(workspace, request)
            return dict(validation), 0 if validation["valid"] else 2
        case "usage export":
            return export_usage(workspace, request), 0
        case "compound":
            return dict(compound_result(workspace, request)), 0
        case "signal record":
            return dict(record_signal_result(workspace, request)), 0
        case "signal list":
            return dict(list_signal_result(workspace, request)), 0
        case _:
            raise ValidationError("invalid-arguments", "command", "Command is not available.")


def main(argv: Sequence[str] | None = None) -> int:
    """Return one JSON/text response and the documented exit category."""
    output = "json"
    started = monotonic()
    args = argparse.Namespace(
        command=None,
        config=None,
        profile=None,
        settings=None,
        harness=None,
        session_id=None,
        compound_run_id=None,
    )
    request: dict[str, object] | None = None
    workspace: Workspace | None = None
    context: InvocationContext | None = None
    collection_error: dict[str, object] | None = None
    try:
        _parser().parse_args(argv, namespace=args)
        output = args.output
        _validate_selectors(args)
        # Resolve before request decoding so malformed requests have the right receipt store.
        if args.command not in {"describe", "doctor", "profiles list"}:
            workspace = _resolve(args)
            context = InvocationContext(workspace.definition.workspace_id)
        validate_invocation(args.harness, args.session_id)
        if args.compound_run_id is not None and workspace is None:
            raise ValidationError(
                "configuration-required", "config", "Run context requires configuration."
            )
        if workspace is not None:
            context = invocation_context(
                workspace,
                harness=args.harness,
                session_id=args.session_id,
                compound_run_id=args.compound_run_id,
            )
        request = _request(args.request_file)
        effective_request = (
            resolve_compound_invocation(workspace, request, context)
            if args.command == "compound" and context is not None and workspace is not None
            else request
        )
        match args.command:
            case "describe":
                data, exit_code = dict(describe(request)), 0
            case "profiles list":
                read_mapping(request, "request", set())
                data, exit_code = (
                    list_profiles(Path(args.settings) if args.settings is not None else None),
                    0,
                )
            case "doctor":
                checked = run_doctor(
                    Path(args.config) if args.config is not None else None,
                    request,
                    settings=Path(args.settings) if args.settings is not None else None,
                    profile=args.profile,
                )
                data, exit_code = asdict(checked), checked.exit_code
                data.pop("exit_code")
            case _:
                assert workspace is not None
                data, exit_code = _run(args.command, workspace, effective_request)
        payload = {"status": "ok" if exit_code == 0 else "error", "diagnostics": [], **data}
    except (ValidationError, AdapterError) as error:
        exit_code = error.exit_code if isinstance(error, AdapterError) else 2
        payload = {"status": "error", "diagnostics": [asdict(from_error(error))]}
    except KeyboardInterrupt:
        exit_code = 3
        payload = {
            "status": "error",
            "diagnostics": [
                asdict(
                    Diagnostic("interrupted", "", "Operation interrupted; discovery is incomplete.")
                )
            ],
        }
    if workspace is not None:
        payload["selection"] = workspace.selection.summary(workspace.fingerprint)
    elif args.command not in {"describe", "profiles list", None} and not payload.get("selection"):
        selected_settings = None
        if args.config is None:
            with suppress(ValidationError, AdapterError):
                selected_settings = str(
                    settings_path(Path(args.settings) if args.settings is not None else None)
                )
        payload["selection"] = {
            "profile": args.profile,
            "settings_path": selected_settings,
            "config_path": str(Path(args.config).absolute()) if args.config is not None else None,
            "mode": "config" if args.config else "profile" if args.profile else "default",
            "effective_fingerprint": None,
        }
    if args.command in {"catalog", "search", "inspect"} or (
        args.command == "validate" and args.compound_run_id is not None
    ):
        if (
            workspace is None
            and args.config is not None
            and args.profile is None
            and args.settings is None
        ):
            # argparse can reject an extra argument after recognizing a valid
            # command/config. Recover only that explicit destination for diagnostics.
            try:
                _validate_selectors(args)
                workspace = _resolve(args)
                payload["selection"] = workspace.selection.summary(workspace.fingerprint)
                context = InvocationContext(workspace.definition.workspace_id)
                context = invocation_context(
                    workspace,
                    harness=args.harness,
                    session_id=args.session_id,
                    compound_run_id=args.compound_run_id,
                )
            except (ValidationError, AdapterError):
                pass
        if workspace is not None and context is not None:
            receipt = record_terminal(
                workspace,
                context,
                operation=args.command,
                request=request,
                response=dict(payload),
                elapsed_ms=(monotonic() - started) * 1000,
            )
            if receipt.get("status") == "written":
                receipt["maintenance"] = maintain_usage(workspace)
            payload["receipt"] = receipt
        else:
            collection_error = {
                "status": "unavailable",
                "diagnostic": {
                    "code": "receipt-context-unavailable",
                    "message": "No valid workspace destination or invocation context was resolved.",
                },
            }
            payload["receipt"] = collection_error
    if (
        args.command == "compound"
        and exit_code == 0
        and workspace is not None
        and request is not None
        and request.get("action") == "finish"
    ):
        payload["usage_maintenance"] = maintain_usage(workspace)
    rendered = (
        json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n"
        if output == "json"
        else yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    )
    try:
        sys.stdout.write(rendered)
    except BrokenPipeError:
        return 3
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
