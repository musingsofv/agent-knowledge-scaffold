"""Validate a bounded launch-readiness request without observing the machine."""

from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

from .validation import ValidationError, read_identifier, read_mapping, read_string

ExecutionKind: TypeAlias = Literal["container", "host", "unknown"]
Provider: TypeAlias = Literal["codex", "claude", "copilot"]


@dataclass(frozen=True, slots=True)
class PreflightRequest:
    """Keep expectations explicit; omission does not select a deployment target."""

    mode: Literal["read", "write"] = "read"
    provider: Provider | None = None
    expected_execution: Literal["container", "host"] | None = None
    expected_venv: str | None = None
    expected_workspace_id: str | None = None
    consumer: str | None = None


def parse_preflight_request(value: object) -> PreflightRequest:
    """Reject unsupported fields, types and modes before any write probe."""
    fields = read_mapping(
        value,
        "",
        set(),
        {
            "mode",
            "provider",
            "expected_execution",
            "expected_venv",
            "expected_workspace_id",
            "consumer",
        },
    )
    for name, allowed in (
        ("mode", {"read", "write"}),
        ("provider", {"codex", "claude", "copilot"}),
        ("expected_execution", {"container", "host"}),
    ):
        if name in fields and read_string(fields[name], name) not in allowed:
            raise ValidationError(
                "invalid-value", name, "Choose one of: " + ", ".join(sorted(allowed))
            )
    paths = {}
    for name in ("expected_venv", "consumer"):
        if name in fields:
            path = read_string(fields[name], name)
            if path != path.strip() or any(character in path for character in ("\r", "\n")):
                raise ValidationError("invalid-value", name, "Use a literal single-line path.")
            paths[name] = path
    return PreflightRequest(
        mode=cast(Literal["read", "write"], fields.get("mode", "read")),
        provider=cast(Provider | None, fields.get("provider")),
        expected_execution=cast(
            Literal["container", "host"] | None, fields.get("expected_execution")
        ),
        expected_venv=paths.get("expected_venv"),
        expected_workspace_id=read_identifier(
            fields["expected_workspace_id"], "expected_workspace_id"
        )
        if "expected_workspace_id" in fields
        else None,
        consumer=paths.get("consumer"),
    )
