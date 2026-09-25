"""Validate caller-supplied provenance independently of retrieval filters."""

from dataclasses import asdict, dataclass

from .validation import ValidationError


@dataclass(frozen=True, slots=True)
class InvocationContext:
    """Describe attribution without implying authenticated provider identity."""

    workspace_id: str
    harness: str | None = None
    session_id: str | None = None
    compound_run_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        """Return the shared event context."""
        return asdict(self)


def validate_invocation(harness: str | None, session_id: str | None) -> None:
    """Accept supported harness names and exact opaque handles, including unknowns."""
    if harness is not None and harness not in {"claude", "codex", "copilot"}:
        raise ValidationError("invalid-harness", "harness", "Expected claude, codex or copilot.")
    if session_id is not None and (
        not session_id
        or len(session_id) > 256
        or any(char.isspace() or ord(char) < 32 or char in "/\\$`" for char in session_id)
    ):
        raise ValidationError(
            "invalid-session-id", "session_id", "Expected an opaque session handle."
        )
