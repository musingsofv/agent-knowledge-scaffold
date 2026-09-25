"""Exercise the provider-neutral discovery hook decision contract."""

import pytest

from agent_knowledge.domain.hooks import (
    HookAction,
    HookDecision,
    HookEvent,
    HookEventType,
    HookMessage,
    HookProvider,
    decide_hook,
)
from agent_knowledge.resources.hook_messages import (
    REFLECTION_REMINDER_MESSAGE,
    RESUME_DISCOVERY_MESSAGE,
    START_DISCOVERY_MESSAGE,
    discovery_message,
    render_message,
)


def _event(
    event: HookEventType,
    *,
    source: str | None = None,
    reason: str | None = None,
    session_id: str | None = None,
    event_id: str | None = None,
) -> HookEvent:
    return HookEvent(
        provider=HookProvider.CLAUDE,
        event=event,
        source=source,
        reason=reason,
        session_id=session_id,
        event_id=event_id,
    )


@pytest.mark.parametrize("source", [None, "startup", "new", " STARTUP "])
def test_new_session_selects_start_discovery(source: str | None) -> None:
    decision = decide_hook(_event(HookEventType.SESSION_START, source=source))

    assert decision == HookDecision(HookAction.START, HookMessage.START_DISCOVERY)
    assert decision.message is HookMessage.START_DISCOVERY


@pytest.mark.parametrize("source", ["resume", "clear", "compact", "fork", " RESUME "])
def test_session_context_transitions_select_resume_discovery(source: str) -> None:
    decision = decide_hook(_event(HookEventType.SESSION_START, source=source))

    assert decision == HookDecision(HookAction.RESUME, HookMessage.RESUME_DISCOVERY)


@pytest.mark.parametrize("event", [HookEventType.RESUME, HookEventType.COMPACTION])
def test_normalized_resume_and_compaction_select_resume_discovery(event: HookEventType) -> None:
    assert decide_hook(_event(event)) == HookDecision(
        HookAction.RESUME, HookMessage.RESUME_DISCOVERY
    )


@pytest.mark.parametrize("event", [HookEventType.FIRST_TASK, HookEventType.OTHER])
def test_reserved_and_ordinary_events_are_noop(event: HookEventType) -> None:
    assert decide_hook(_event(event)) == HookDecision(HookAction.NONE)


def test_user_prompt_selects_reflection_reminder() -> None:
    assert decide_hook(_event(HookEventType.USER_PROMPT)) == HookDecision(
        HookAction.REFLECT, HookMessage.REFLECTION
    )


def test_unknown_or_conflicting_session_source_fails_open_to_noop() -> None:
    assert decide_hook(_event(HookEventType.SESSION_START, source="future")) == HookDecision(
        HookAction.NONE
    )
    assert decide_hook(_event(HookEventType.SESSION_START, source=" ")) == HookDecision(
        HookAction.NONE
    )
    assert decide_hook(
        _event(HookEventType.SESSION_START, source="startup", reason="compact")
    ) == HookDecision(HookAction.NONE)


def test_identifiers_and_provider_do_not_change_the_pure_decision() -> None:
    baseline = decide_hook(_event(HookEventType.SESSION_START, source="startup"))
    variant = HookEvent(
        provider=HookProvider.CODEX,
        event=HookEventType.SESSION_START,
        source="startup",
        session_id="session-1",
        event_id="event-1",
    )

    assert decide_hook(variant) == baseline


def test_reminder_resources_are_static_and_distinct() -> None:
    assert discovery_message(HookMessage.START_DISCOVERY) == START_DISCOVERY_MESSAGE
    assert discovery_message(HookMessage.RESUME_DISCOVERY) == RESUME_DISCOVERY_MESSAGE
    assert START_DISCOVERY_MESSAGE != RESUME_DISCOVERY_MESSAGE
    assert len(START_DISCOVERY_MESSAGE) < 240
    assert len(RESUME_DISCOVERY_MESSAGE) < 240
    assert "search" in START_DISCOVERY_MESSAGE
    assert "inspect" in RESUME_DISCOVERY_MESSAGE


def test_rendered_messages_share_the_canonical_reflection_block_and_session_id() -> None:
    start = render_message(HookMessage.START_DISCOVERY, HookProvider.CLAUDE, "session-123")
    prompt = render_message(HookMessage.REFLECTION, HookProvider.CLAUDE, "session-123")

    assert REFLECTION_REMINDER_MESSAGE in start
    assert REFLECTION_REMINDER_MESSAGE in prompt
    assert start.count("session-123") == 1
    assert prompt.count("session-123") == 1
    assert start.count("origin.harness for a harness-origin signal): claude") == 1
    assert prompt.count("origin.harness for a harness-origin signal): claude") == 1
