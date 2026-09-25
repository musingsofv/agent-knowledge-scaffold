"""Resolve explicit operation provenance against recorded workspace runs."""

from agent_knowledge.domain.invocation import InvocationContext, validate_invocation
from agent_knowledge.domain.validation import ValidationError
from agent_knowledge.infrastructure.compounding import resolve_run
from agent_knowledge.infrastructure.configuration import Workspace


def invocation_context(
    workspace: Workspace,
    *,
    harness: str | None,
    session_id: str | None,
    compound_run_id: str | None,
) -> InvocationContext:
    """Apply run defaults and reject attribution to a different session/workspace."""
    validate_invocation(harness, session_id)
    if compound_run_id is not None:
        run = resolve_run(workspace, compound_run_id)
        for field, supplied, recorded in (
            ("harness", harness, run.harness),
            ("session_id", session_id, run.session_id),
        ):
            if supplied is not None and recorded is not None and supplied != recorded:
                raise ValidationError(
                    "context-mismatch", field, "Invocation disagrees with the recorded run."
                )
        harness = harness if harness is not None else run.harness
        session_id = session_id if session_id is not None else run.session_id
    return InvocationContext(
        workspace.definition.workspace_id, harness, session_id, compound_run_id
    )


def compound_invocation(
    request: dict[str, object], context: InvocationContext
) -> dict[str, object]:
    """Carry global provenance into lifecycle calls without mixing query filters."""
    result = dict(request)
    for field, value in (
        ("harness", context.harness),
        ("session_id", context.session_id),
        ("run_id", context.compound_run_id),
    ):
        if value is not None:
            if field in result and result[field] != value:
                raise ValidationError(
                    "context-mismatch", field, "Request disagrees with invocation context."
                )
            result[field] = value
    return result


def resolve_compound_invocation(
    workspace: Workspace, request: dict[str, object], context: InvocationContext
) -> dict[str, object]:
    """Resolve lifecycle body provenance against the same run as global options."""
    from agent_knowledge.domain.compounding import parse_compound_request

    combined = compound_invocation(request, context)
    parsed = parse_compound_request(combined)
    resolved = invocation_context(
        workspace,
        harness=parsed.harness,
        session_id=parsed.session_id,
        compound_run_id=parsed.run_id if parsed.action in {"drain", "finish"} else None,
    )
    return compound_invocation(combined, resolved)
