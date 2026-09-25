"""Choose an advisory discovery or reflection reminder from a normalized event.

Provider adapters translate their native hook payloads into these values.  The
decision function deliberately receives no prompt body, transcript, path,
configuration or taxonomy state.  It only selects a message identifier;
delivery and provider serialization belong outside this module.
"""

from dataclasses import dataclass
from enum import StrEnum


class HookProvider(StrEnum):
    """Name the providers supported by the first hook contract."""

    CODEX = "codex"
    CLAUDE = "claude"
    COPILOT = "copilot"


class HookEventType(StrEnum):
    """Describe normalized lifecycle and prompt events."""

    SESSION_START = "session_start"
    FIRST_TASK = "first_task"
    RESUME = "resume"
    COMPACTION = "compaction"
    USER_PROMPT = "user_prompt"
    OTHER = "other"


class HookAction(StrEnum):
    """Name the pure decision made for one normalized event."""

    START = "start"
    RESUME = "resume"
    REFLECT = "reflect"
    NONE = "none"


class HookMessage(StrEnum):
    """Identify the source-owned reminder selected by the core."""

    START_DISCOVERY = "start_discovery"
    RESUME_DISCOVERY = "resume_discovery"
    REFLECTION = "reflection"


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Carry normalized lifecycle data without exposing provider payloads."""

    provider: HookProvider
    event: HookEventType
    source: str | None = None
    reason: str | None = None
    session_id: str | None = None
    event_id: str | None = None


@dataclass(frozen=True, slots=True)
class HookDecision:
    """Return an advisory action and, when applicable, its message identity."""

    action: HookAction
    message_id: HookMessage | None = None

    @property
    def message(self) -> HookMessage | None:
        """Expose a readable alias for callers that render the selected message."""
        return self.message_id


def decide_hook(event: HookEvent) -> HookDecision:
    """Select one discovery/reflection reminder or no-op for a normalized event.

    A native ``session_start`` without a source is treated as a new session;
    adapters that supply a source can map explicit resume-like values without
    relying on prompt or tool heuristics.  Unknown or conflicting source data
    fails closed to no-op.  ``first_task`` is reserved for a future provider
    and is intentionally not inferred by the current adapters.
    """
    match event.event:
        case HookEventType.SESSION_START:
            match _session_start_action(event.source, event.reason):
                case HookAction.START:
                    return HookDecision(HookAction.START, HookMessage.START_DISCOVERY)
                case HookAction.RESUME:
                    return HookDecision(HookAction.RESUME, HookMessage.RESUME_DISCOVERY)
                case HookAction.NONE:
                    return HookDecision(HookAction.NONE)
        case HookEventType.RESUME | HookEventType.COMPACTION:
            return HookDecision(HookAction.RESUME, HookMessage.RESUME_DISCOVERY)
        case HookEventType.USER_PROMPT:
            return HookDecision(HookAction.REFLECT, HookMessage.REFLECTION)
        case HookEventType.FIRST_TASK | HookEventType.OTHER:
            return HookDecision(HookAction.NONE)
    return HookDecision(HookAction.NONE)


def _session_start_action(source: str | None, reason: str | None) -> HookAction:
    """Interpret optional lifecycle source fields without guessing unknown values."""
    supplied = tuple(value for value in (source, reason) if value is not None)
    if any(not value.strip() for value in supplied):
        return HookAction.NONE
    values = tuple(value.strip().casefold() for value in supplied)
    if not values:
        return HookAction.START
    categories = {_source_action(value) for value in values}
    if len(categories) != 1:
        return HookAction.NONE
    return categories.pop()


def _source_action(value: str) -> HookAction:
    """Map a normalized provider source to the pure lifecycle action."""
    match value:
        case "new" | "startup":
            return HookAction.START
        case "clear" | "compact" | "fork" | "resume":
            return HookAction.RESUME
        case _:
            return HookAction.NONE


__all__ = [
    "HookAction",
    "HookDecision",
    "HookEvent",
    "HookEventType",
    "HookMessage",
    "HookProvider",
    "decide_hook",
]
