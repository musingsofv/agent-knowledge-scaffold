"""Normalize native lifecycle payloads and render one provider context field.

The installed ``agent-knowledge-hook`` entry point is the only runtime for
provider hooks. It uses this typed boundary from the verified scaffold virtual
environment and never reads transcripts, paths or configuration.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from agent_knowledge.domain.hooks import (
    HookDecision,
    HookEvent,
    HookEventType,
    HookProvider,
    decide_hook,
)
from agent_knowledge.resources.hook_messages import render_message


class HookAdapterError(ValueError):
    """Raised for a payload that cannot be normalized by a selected adapter."""


@dataclass(frozen=True, slots=True)
class AdaptedHook:
    """Hold the normalized event and its provider delivery mode."""

    provider: HookProvider
    event: HookEvent
    delivery: str
    transformed_prompt: str | None = None


class HookAdapter(Protocol):
    """Describe the tiny normalize/render surface shared by providers."""

    provider: HookProvider

    def normalize(self, payload: Mapping[str, object]) -> AdaptedHook:
        """Normalize one provider-native payload."""

    def render(self, decision: HookDecision, event: HookEvent) -> dict[str, object]:
        """Render one provider-native response."""


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    if not all(isinstance(key, str) for key in value):
        return None
    return value


def _optional_string(payload: Mapping[str, object], *keys: str) -> str | None:
    values = [payload[key] for key in keys if key in payload]
    if not values:
        return None
    if not all(isinstance(value, str) for value in values):
        raise HookAdapterError(f"Expected a string for {keys[0]}.")
    strings = tuple(value for value in values if isinstance(value, str))
    if len(set(strings)) != 1:
        raise HookAdapterError(f"Conflicting values for {keys[0]}.")
    return strings[0]


def _session_id(payload: Mapping[str, object]) -> str | None:
    return _optional_string(payload, "session_id", "sessionId")


def _required_session_id(payload: Mapping[str, object]) -> str:
    value = _session_id(payload)
    if value is None or not value.strip() or len(value) > 256 or value != value.strip():
        raise HookAdapterError("Payload omitted a usable session ID.")
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise HookAdapterError("Payload omitted a usable session ID.")
    if any(character in ("/", "\\", "$", "`") for character in value):
        raise HookAdapterError("Payload omitted a usable session ID.")
    return value


def _event_id(payload: Mapping[str, object]) -> str | None:
    return _optional_string(payload, "event_id", "eventId")


def _normalize_event(
    payload: Mapping[str, object],
    *,
    provider: HookProvider,
    require_event_name: bool,
    delivery: str,
) -> AdaptedHook:
    event_name = _optional_string(payload, "hook_event_name", "hookEventName")
    if require_event_name and event_name is None:
        raise HookAdapterError("Payload omitted hook_event_name.")
    if event_name is None:
        event_type = HookEventType.SESSION_START
    else:
        match event_name.casefold():
            case "sessionstart":
                event_type = HookEventType.SESSION_START
            case "userpromptsubmit" if provider in {
                HookProvider.CODEX,
                HookProvider.CLAUDE,
            }:
                event_type = HookEventType.USER_PROMPT
            case _:
                raise HookAdapterError("Payload is for a different hook event.")
    if (
        provider is HookProvider.COPILOT
        and event_name is None
        and not any(key in payload for key in ("sessionId", "session_id"))
    ):
        raise HookAdapterError("Copilot payload omitted sessionId.")
    event = HookEvent(
        provider=provider,
        event=event_type,
        source=_optional_string(payload, "source"),
        reason=_optional_string(payload, "reason"),
        session_id=_required_session_id(payload),
        event_id=_event_id(payload),
    )
    return AdaptedHook(provider=provider, event=event, delivery=delivery)


class CodexHookAdapter:
    """Adapt Codex command-hook lifecycle and prompt payloads."""

    provider = HookProvider.CODEX

    def normalize(self, payload: Mapping[str, object]) -> AdaptedHook:
        return _normalize_event(
            payload,
            provider=self.provider,
            require_event_name=True,
            delivery="hook_specific_output",
        )

    def render(self, decision: HookDecision, event: HookEvent) -> dict[str, object]:
        return _render_hook_specific_output(decision, event)


class ClaudeHookAdapter:
    """Adapt Claude Code lifecycle and prompt payloads."""

    provider = HookProvider.CLAUDE

    def normalize(self, payload: Mapping[str, object]) -> AdaptedHook:
        return _normalize_event(
            payload,
            provider=self.provider,
            require_event_name=True,
            delivery="hook_specific_output",
        )

    def render(self, decision: HookDecision, event: HookEvent) -> dict[str, object]:
        return _render_hook_specific_output(decision, event)


class CopilotHookAdapter:
    """Adapt Copilot CLI camelCase or VS Code-compatible session payloads."""

    provider = HookProvider.COPILOT

    def normalize(self, payload: Mapping[str, object]) -> AdaptedHook:
        if "transformedPrompt" in payload:
            transformed_prompt = _optional_string(payload, "transformedPrompt")
            if transformed_prompt is None or not transformed_prompt:
                raise HookAdapterError("Payload omitted transformedPrompt.")
            event = HookEvent(
                provider=self.provider,
                event=HookEventType.USER_PROMPT,
                session_id=_required_session_id(payload),
                event_id=_event_id(payload),
            )
            return AdaptedHook(
                provider=self.provider,
                event=event,
                delivery="transformed_prompt",
                transformed_prompt=transformed_prompt,
            )
        return _normalize_event(
            payload,
            provider=self.provider,
            require_event_name=False,
            delivery="additional_context",
        )

    def render(
        self, decision: HookDecision, event: HookEvent, *, transformed_prompt: str | None = None
    ) -> dict[str, object]:
        message = _decision_message(decision, event)
        if transformed_prompt is not None:
            if message is None:
                return {}
            trailer = "\n\n" + message
            if transformed_prompt.endswith(trailer):
                return {}
            return {"modifiedTransformedPrompt": transformed_prompt + trailer}
        return {"additionalContext": message} if message is not None else {}


_ADAPTERS: dict[HookProvider, HookAdapter] = {
    HookProvider.CODEX: CodexHookAdapter(),
    HookProvider.CLAUDE: ClaudeHookAdapter(),
    HookProvider.COPILOT: CopilotHookAdapter(),
}


def _provider(value: HookProvider | str | None) -> HookProvider | None:
    if value is None:
        return None
    if isinstance(value, HookProvider):
        return value
    try:
        return HookProvider(value.casefold())
    except (AttributeError, ValueError) as error:
        raise HookAdapterError("Unknown hook provider.") from error


def _infer_provider(payload: Mapping[str, object]) -> HookProvider | None:
    if "sessionId" in payload and "hook_event_name" not in payload:
        return HookProvider.COPILOT
    if "hook_event_name" in payload or "hookEventName" in payload:
        # Codex and Claude deliberately share the same native envelope and
        # delivery field. The explicit provider argument distinguishes them
        # when a caller needs provenance; rendering is identical.
        return HookProvider.CODEX
    return None


def adapt_payload(
    payload: object, *, provider: HookProvider | str | None = None
) -> AdaptedHook | None:
    """Return a normalized event, or ``None`` for an unsupported payload."""
    mapping = _mapping(payload)
    if mapping is None:
        return None
    selected = _provider(provider) or _infer_provider(mapping)
    if selected is None:
        return None
    try:
        return _ADAPTERS[selected].normalize(mapping)
    except HookAdapterError:
        return None


def _decision_message(decision: HookDecision, event: HookEvent) -> str | None:
    if decision.message_id is None:
        return None
    if event.session_id is None:
        return None
    return render_message(decision.message_id, event.provider, event.session_id)


def _render_hook_specific_output(decision: HookDecision, event: HookEvent) -> dict[str, object]:
    message = _decision_message(decision, event)
    if message is None:
        return {}
    event_name = "UserPromptSubmit" if event.event is HookEventType.USER_PROMPT else "SessionStart"
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": message,
        }
    }


def render_decision(adapted: AdaptedHook) -> dict[str, object]:
    """Render an adapted event through exactly one provider context channel."""
    decision = decide_hook(adapted.event)
    match adapted.provider:
        case HookProvider.COPILOT:
            return CopilotHookAdapter().render(
                decision,
                adapted.event,
                transformed_prompt=adapted.transformed_prompt,
            )
        case HookProvider.CODEX | HookProvider.CLAUDE:
            return _render_hook_specific_output(decision, adapted.event)


def handle_payload(
    payload: object, *, provider: HookProvider | str | None = None
) -> dict[str, object]:
    """Normalize, decide and render a payload with advisory fail-open behavior."""
    adapted = adapt_payload(payload, provider=provider)
    return render_decision(adapted) if adapted is not None else {}


__all__ = [
    "AdaptedHook",
    "ClaudeHookAdapter",
    "CopilotHookAdapter",
    "CodexHookAdapter",
    "HookAdapterError",
    "adapt_payload",
    "handle_payload",
    "render_decision",
]
